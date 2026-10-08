"""Root-anchored filesystem I/O for MCP skill state and artifacts.

Two backends implement one contract: every managed path is walked from an
unfollowed root, and a symlink/junction swapped into the tree can never redirect
a read or a write outside it.

* **POSIX** -- ``openat``-style ``dir_fd`` walking with ``O_NOFOLLOW`` /
  ``O_DIRECTORY``. Every component stays bound to a directory descriptor, so the
  check and the use are the same syscall: there is no race window at all.
* **Windows** -- the stdlib exposes no ``dir_fd`` equivalent (``os.supports_dir_fd``
  is empty and ``O_NOFOLLOW`` does not exist), so the walk validates every
  component with ``lstat`` and rejects *any* reparse point (symlink, junction,
  mount point), and the leaf is opened through ``CreateFileW`` with
  ``FILE_FLAG_OPEN_REPARSE_POINT`` so the handle always names the object itself
  rather than whatever it points at. Parent directories are therefore validated
  and then used instead of descriptor-bound: a component swapped between the
  validation and the use is a residual race that requires a local attacker able
  to write inside the managed tree, which Hermes owns below ``HERMES_HOME``.

``_descriptor_safety_available()`` still answers the question the callers ask --
"can managed paths stay anchored to unfollowed handles?" -- and is True on both
backends whenever the primitives they need are present.
"""
from __future__ import annotations

import contextlib
import errno
import json
import os
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_FILE_ATTRIBUTE_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

# ── Windows primitives (no-op on POSIX) ────────────────────────────────────────
_WIN_GENERIC_READ = 0x80000000
_WIN_GENERIC_WRITE = 0x40000000
_WIN_FILE_SHARE_ALL = 0x00000007
_WIN_OPEN_EXISTING = 3
_WIN_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_WIN_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_WIN_FILE_ATTRIBUTE_DIRECTORY = 0x00000010
_WIN_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_WIN_ERROR_FILE_NOT_FOUND = 2
_WIN_ERROR_PATH_NOT_FOUND = 3

_win32_runtime_cache: Any = "unset"


def _build_win32_runtime():
    """Load the kernel32 entry points the Windows backend needs, or None."""
    try:
        import ctypes
        from ctypes import wintypes

        class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("dwFileAttributes", wintypes.DWORD),
                ("ftCreationTime", wintypes.FILETIME),
                ("ftLastAccessTime", wintypes.FILETIME),
                ("ftLastWriteTime", wintypes.FILETIME),
                ("dwVolumeSerialNumber", wintypes.DWORD),
                ("nFileSizeHigh", wintypes.DWORD),
                ("nFileSizeLow", wintypes.DWORD),
                ("nNumberOfLinks", wintypes.DWORD),
                ("nFileIndexHigh", wintypes.DWORD),
                ("nFileIndexLow", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
        kernel32.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(BY_HANDLE_FILE_INFORMATION)]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    except Exception:  # pragma: no cover - platform/ctypes failure only
        return None

    class _Win32Runtime:
        @staticmethod
        def create_file(path: str, access: int):
            """Open *path itself*, never the object a reparse point names."""
            return kernel32.CreateFileW(
                path, access, _WIN_FILE_SHARE_ALL, None, _WIN_OPEN_EXISTING,
                _WIN_FILE_FLAG_OPEN_REPARSE_POINT | _WIN_FILE_FLAG_BACKUP_SEMANTICS, None)

        @staticmethod
        def attributes(handle) -> int:
            info = BY_HANDLE_FILE_INFORMATION()
            if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
                raise OSError(ctypes.get_last_error(), "GetFileInformationByHandle failed")
            return int(info.dwFileAttributes)

        @staticmethod
        def close(handle) -> None:
            kernel32.CloseHandle(handle)

        @staticmethod
        def last_error() -> int:
            return int(ctypes.get_last_error())

        @staticmethod
        def invalid_handle() -> int:
            """INVALID_HANDLE_VALUE as an int, without sign/width assumptions."""
            return int(ctypes.c_void_p(-1).value)

    return _Win32Runtime()


def _win32_runtime():
    global _win32_runtime_cache
    if os.name != "nt":
        return None
    if _win32_runtime_cache == "unset":
        _win32_runtime_cache = _build_win32_runtime()
    return _win32_runtime_cache


def _is_reparse(info: os.stat_result) -> bool:
    """True for a symlink on any platform, and for any NTFS reparse point on Windows.

    Junctions and mount points are reparse points but are *not* reported as
    symlinks by :func:`os.lstat`, so mode bits alone would let one through.
    """
    return bool(getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT) \
        or stat.S_ISLNK(info.st_mode)


def _descriptor_safety_available() -> bool:
    """Whether managed paths can stay anchored to unfollowed handles."""
    if os.name == "nt":
        return _win32_runtime() is not None
    return (
        os.name == "posix"
        and bool(_NOFOLLOW)
        and bool(_DIRECTORY)
        and all(fn in os.supports_dir_fd for fn in (os.open, os.mkdir, os.unlink))
    )


def _require_descriptor_safety() -> None:
    if not _descriptor_safety_available():
        raise RuntimeError(
            "managed MCP skill files require POSIX root-descriptor and no-follow filesystem semantics")


def _relative_parts(relative: str | Path) -> tuple[str, ...]:
    text = Path(relative).as_posix()
    pure = PurePosixPath(text)
    # ``PurePosixPath`` treats ``C:/x`` and ``C:x`` as relative, so a Windows
    # drive-qualified path would otherwise be walked as literal directory names.
    if os.name == "nt":
        windows = PureWindowsPath(text)
        if windows.drive or windows.root:
            raise ValueError("managed path must be normalized and relative")
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("managed path must be normalized and relative")
    return tuple(pure.parts)


def _root_path(root: str | Path) -> Path:
    path = Path(root).expanduser()
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError(f"managed root does not exist: {path}") from exc
    if _is_reparse(info) or not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"managed root is not a real directory: {path}")
    return path


def validate_managed_root(root: str | Path) -> Path:
    """Validate a configured managed root without resolving a symlink alias."""
    return _root_path(root)


# ── POSIX backend ──────────────────────────────────────────────────────────────
def _open_parent(root: str | Path, relative: str | Path, *, create: bool) -> tuple[int, str]:
    """Open a leaf parent by walking from an unfollowed root descriptor."""
    _require_descriptor_safety()
    root_path = _root_path(root)
    parts = _relative_parts(relative)
    flags = os.O_RDONLY | _DIRECTORY | _NOFOLLOW
    fd = os.open(root_path, flags)
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    # A sibling process may have created the same managed
                    # component after our failed open; the unfollowed reopen
                    # below validates what won the race.
                    pass
                child = os.open(part, flags, dir_fd=fd)
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise ValueError(f"managed path crosses a non-directory or symlink: {part}") from exc
                raise
            os.close(fd)
            fd = child
        return fd, parts[-1]
    except Exception:
        os.close(fd)
        raise


def _posix_secure_read_bytes(root: str | Path, relative: str | Path) -> bytes:
    parent_fd, leaf = _open_parent(root, relative, create=False)
    try:
        fd = os.open(leaf, os.O_RDONLY | _NOFOLLOW, dir_fd=parent_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("managed file is not a regular file")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _posix_secure_atomic_bytes(root: str | Path, relative: str | Path, raw: bytes, *,
                               mode: int = 0o600) -> Path:
    """Atomically replace a regular leaf without following any parent or leaf symlink."""
    parent_fd, leaf = _open_parent(root, relative, create=True)
    temp_name = f".{leaf}.{os.getpid()}.{os.urandom(8).hex()}"
    try:
        try:
            existing = os.open(leaf, os.O_RDONLY | _NOFOLLOW, dir_fd=parent_fd)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            try:
                if not stat.S_ISREG(os.fstat(existing).st_mode):
                    raise ValueError("managed target is not a regular file")
            finally:
                os.close(existing)
        fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, mode, dir_fd=parent_fd)
        try:
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
            os.fchmod(fd, mode)
        finally:
            os.close(fd)
        os.replace(temp_name, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    finally:
        try:
            os.unlink(temp_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)
    return _root_path(root).joinpath(*_relative_parts(relative))


@contextlib.contextmanager
def _posix_secure_file_lock(root: str | Path, relative: str | Path):
    """Hold a blocking cross-process lock at an unfollowed managed path."""
    parent_fd, leaf = _open_parent(root, relative, create=True)
    try:
        target = Path(leaf) if parent_fd == -1 else leaf
        kwargs = {} if parent_fd == -1 else {"dir_fd": parent_fd}
        try:
            fd = os.open(target, os.O_RDWR | _NOFOLLOW, **kwargs)
        except FileNotFoundError:
            try:
                # O_EXCL makes creation symlink-safe without relying on the
                # macOS O_NOFOLLOW|O_CREAT behavior for an absent leaf.
                fd = os.open(target, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600, **kwargs)
            except FileExistsError:
                fd = os.open(target, os.O_RDWR | _NOFOLLOW, **kwargs)
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise ValueError("managed lock is a symlink or non-file") from exc
            raise
    except Exception:
        if parent_fd != -1:
            os.close(parent_fd)
        raise
    handle = os.fdopen(fd, "r+b", closefd=True)
    try:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("managed lock is not a singly-linked regular file")
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()
        if parent_fd != -1:
            os.close(parent_fd)


# ── Windows backend ────────────────────────────────────────────────────────────
def _win_reject_reparse(path: Path, *, allow_missing: bool = False) -> os.stat_result | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if allow_missing:
            return None
        raise
    if _is_reparse(info):
        raise ValueError(f"managed path crosses a non-directory or symlink: {path.name}")
    return info


def _win_beneath(root_path: Path, candidate: Path) -> bool:
    """Defense in depth: the walked path must still resolve inside the root."""
    try:
        root_real = os.path.normcase(os.path.realpath(root_path))
        candidate_real = os.path.normcase(os.path.realpath(candidate))
    except OSError:
        return False
    return candidate_real == root_real or candidate_real.startswith(root_real + os.sep)


def _win_open_parent(root: str | Path, relative: str | Path, *, create: bool) -> tuple[Path, str]:
    """Validate a leaf parent component by component, rejecting reparse points."""
    _require_descriptor_safety()
    root_path = _root_path(root)
    parts = _relative_parts(relative)
    current = root_path
    for part in parts[:-1]:
        current = current / part
        info = _win_reject_reparse(current, allow_missing=True)
        if info is None:
            if not create:
                raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(current))
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                # A sibling process may have created the same managed component
                # after our failed open; the re-check below validates the winner.
                pass
            info = _win_reject_reparse(current)
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"managed path crosses a non-directory or symlink: {part}")
    if not _win_beneath(root_path, current):
        raise ValueError("managed path escapes its configured root")
    return current, parts[-1]


def _win_open_leaf(parent: Path, leaf: str, *, access: int) -> int:
    """Open the leaf object itself and hand back a Python file descriptor.

    ``FILE_FLAG_OPEN_REPARSE_POINT`` makes the handle name the reparse point
    rather than its target, so a symlink or junction cannot be traversed even if
    one appears between the parent walk and this call; the attributes read back
    from the handle then fail the operation closed.
    """
    runtime = _win32_runtime()
    if runtime is None:  # pragma: no cover - only if kernel32 is unavailable
        raise RuntimeError("managed MCP skill files require reparse-point-safe Windows file handles")
    path = parent / leaf
    handle = runtime.create_file(str(path), access)
    value = 0 if handle is None else int(handle)
    if value == 0 or value == runtime.invalid_handle():
        error = runtime.last_error()
        if error in {_WIN_ERROR_FILE_NOT_FOUND, _WIN_ERROR_PATH_NOT_FOUND}:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(path))
        raise OSError(error, f"CreateFileW failed for managed path: {path}")
    handed_off = False
    try:
        attributes = runtime.attributes(handle)
        if attributes & _WIN_FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f"managed path crosses a non-directory or symlink: {leaf}")
        if attributes & _WIN_FILE_ATTRIBUTE_DIRECTORY:
            raise ValueError(f"managed path is a directory, not a regular file: {leaf}")
        import msvcrt
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY if not (access & _WIN_GENERIC_WRITE)
                                   else os.O_RDWR | os.O_BINARY)
        handed_off = True
        return fd
    finally:
        if not handed_off:
            runtime.close(handle)


def _win_secure_read_bytes(root: str | Path, relative: str | Path) -> bytes:
    parent, leaf = _win_open_parent(root, relative, create=False)
    fd = _win_open_leaf(parent, leaf, access=_WIN_GENERIC_READ)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("managed file is not a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(fd)


def _win_secure_atomic_bytes(root: str | Path, relative: str | Path, raw: bytes, *,
                             mode: int = 0o600) -> Path:
    """Atomically replace a regular leaf after rejecting any reparse-point target."""
    parent, leaf = _win_open_parent(root, relative, create=True)
    target = parent / leaf
    temp_name = f".{leaf}.{os.getpid()}.{os.urandom(8).hex()}"
    temp_path = parent / temp_name
    try:
        # The leaf is either absent or a real regular file; never redirect a
        # write through a symlink/junction planted at the managed leaf name.
        existing = _win_reject_reparse(target, allow_missing=True)
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise ValueError("managed target is not a regular file")
        fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_BINARY, mode)
        try:
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp_path, target)
    finally:
        with contextlib.suppress(FileNotFoundError, OSError):
            os.unlink(temp_path)
    return target


def _win_open_lock_file(parent: Path, leaf: str) -> int:
    try:
        return _win_open_leaf(parent, leaf, access=_WIN_GENERIC_READ | _WIN_GENERIC_WRITE)
    except FileNotFoundError:
        path = parent / leaf
        try:
            # CREATE_NEW fails if *any* object with the name exists, reparse
            # points included, so this can only ever create a fresh regular file.
            return os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_BINARY, 0o600)
        except FileExistsError:
            return _win_open_leaf(parent, leaf, access=_WIN_GENERIC_READ | _WIN_GENERIC_WRITE)


@contextlib.contextmanager
def _win_secure_file_lock(root: str | Path, relative: str | Path):
    """Hold a blocking cross-process lock at a reparse-point-free managed path."""
    parent, leaf = _win_open_parent(root, relative, create=True)
    handle = os.fdopen(_win_open_lock_file(parent, leaf), "r+b", closefd=True)
    try:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("managed lock is not a singly-linked regular file")
        import portalocker
        portalocker.lock(handle, portalocker.LOCK_EX)
        try:
            yield
        finally:
            portalocker.unlock(handle)
    finally:
        handle.close()


# ── Public API ─────────────────────────────────────────────────────────────────
def secure_read_bytes(root: str | Path, relative: str | Path) -> bytes:
    if os.name == "nt":
        return _win_secure_read_bytes(root, relative)
    return _posix_secure_read_bytes(root, relative)


def secure_read_json(root: str | Path, relative: str | Path) -> Any:
    return json.loads(secure_read_bytes(root, relative).decode("utf-8"))


def secure_atomic_bytes(root: str | Path, relative: str | Path, raw: bytes, *, mode: int = 0o600) -> Path:
    if os.name == "nt":
        return _win_secure_atomic_bytes(root, relative, raw, mode=mode)
    return _posix_secure_atomic_bytes(root, relative, raw, mode=mode)


def secure_atomic_json(root: str | Path, relative: str | Path, data: Any, *, mode: int = 0o600) -> Path:
    raw = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return secure_atomic_bytes(root, relative, raw, mode=mode)


@contextlib.contextmanager
def secure_file_lock(root: str | Path, relative: str | Path):
    """Hold a blocking cross-process lock at a validated managed path."""
    if os.name == "nt":
        with _win_secure_file_lock(root, relative):
            yield
        return
    with _posix_secure_file_lock(root, relative):
        yield
