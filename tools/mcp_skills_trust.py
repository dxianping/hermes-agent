"""Persistent, profile-scoped trust for remote MCP skill origins.

Local skills load under a standing trust decision (``skills.trusted_project_dirs``);
remote MCP skills needed a live human answer for every session. This module gives remote
origins the same shape: an explicit per-server config opt-in
(``mcp_servers.<server>.skills.trust: auto``) plus an exact ``server + URI`` record granted
through ``hermes skills trust-mcp``. A matching record pre-authorizes the activation and
host-execution consent gates for that one skill; it never covers cross-origin reads, and
neither Skills Guard scanning nor the ordinary tool approvals are skipped.

The recorded manifest fingerprint is informational (shown by ``hermes skills trusted-mcp``):
by design a content update does not revoke trust — the server is the trusted identity, and
every served manifest still goes through the scan chain. Removing the record or setting the
policy back to ``prompt`` re-blocks the next gate call; auto approvals are never cached.
"""
from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.mcp_skills_fs import secure_atomic_json, secure_file_lock, secure_read_json
from tools.mcp_skills_protocol import MCP_SKILLS_DEFAULTS
from tools.mcp_skills_registry import _home_key, _profile_key

logger = logging.getLogger("tools.mcp_skills")

_SCHEMA_VERSION = 1
_lock = threading.RLock()


def _trust_rel() -> Path:
    return Path("cache") / "mcp-skills" / "trusted-origins.json"


def _trust_lock_rel() -> Path:
    return Path("cache") / "mcp-skills" / "locks" / "trusted-origins.lock"


def _read_rows(home_key: str) -> dict[tuple[str, str], dict[str, Any]]:
    """Trusted ``(server, uri)`` rows; a missing, foreign-profile or malformed file means no trust."""
    try:
        raw = secure_read_json(home_key, _trust_rel())
        if raw.get("schema_version") != _SCHEMA_VERSION or raw.get("profile_key") != _profile_key(home_key):
            return {}
        rows: dict[tuple[str, str], dict[str, Any]] = {}
        for item in raw.get("trusted", []):
            if not isinstance(item, dict):
                continue
            server, uri = item.get("server"), item.get("uri")
            if isinstance(server, str) and server and isinstance(uri, str) and uri:
                rows[(server, uri)] = item
        return rows
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def _write_rows(home_key: str, rows: dict[tuple[str, str], dict[str, Any]]) -> None:
    secure_atomic_json(home_key, _trust_rel(), {
        "schema_version": _SCHEMA_VERSION, "profile_key": _profile_key(home_key),
        "trusted": list(rows.values())}, mode=0o600)


def trust_policy(server: str) -> str:
    """``mcp_servers.<server>.skills.trust`` from the USER's config: ``"auto"`` or ``"prompt"``.

    Read through the merged user config (never the plugin/portable-server merge in
    ``mcp_tool_config._load_mcp_config``) so a package can never widen trust; anything
    unreadable or unrecognized fails closed to ``"prompt"``.
    """
    from hermes_cli.config import load_config_readonly
    try:
        servers = load_config_readonly().get("mcp_servers")
        entry = servers.get(server) if isinstance(servers, dict) else None
        skills = entry.get("skills") if isinstance(entry, dict) else None
        value = skills.get("trust", MCP_SKILLS_DEFAULTS["trust"]) if isinstance(skills, dict) else None
        return "auto" if isinstance(value, str) and value.strip().lower() == "auto" else "prompt"
    except Exception:  # fail closed: any config-read failure means "prompt"
        logger.debug("Could not read MCP skills trust policy for %r", server, exc_info=True)
        return "prompt"


def is_origin_trusted(server: str, uri: str, home: Path | str | None = None) -> bool:
    """Whether an exact ``server + URI`` trust record exists for this profile."""
    if not server or not uri:
        return False
    return (server, uri) in _read_rows(_home_key(home))


def origin_auto_trusted(record: dict[str, Any], home: Path | str | None = None) -> bool:
    """``is_origin_trusted`` for a pinned record, gated by the per-server config opt-in."""
    server = record.get("server") or ""
    uri = record.get("uri") or ""
    return trust_policy(server) == "auto" and is_origin_trusted(server, uri, home)


def record_trust(server: str, uri: str, *, home: Path | str | None = None, name: str = "",
                 manifest_fingerprint: str = "", config_fingerprint: str = "") -> dict[str, Any]:
    """Upsert one trust record; the fingerprint fields are display-only."""
    home_key = _home_key(home)
    row = {
        "server": server, "uri": uri, "name": name,
        "manifest_fingerprint": manifest_fingerprint,
        "config_fingerprint": config_fingerprint,
        "trusted_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    with _lock, secure_file_lock(home_key, _trust_lock_rel()):
        rows = _read_rows(home_key)  # reload under the kernel lock; a sibling may have committed
        rows[(server, uri)] = row
        _write_rows(home_key, rows)
    return row


def remove_trust(server: str, uri: str, *, home: Path | str | None = None) -> bool:
    """Drop one record; True when it existed. Idempotent."""
    home_key = _home_key(home)
    with _lock, secure_file_lock(home_key, _trust_lock_rel()):
        rows = _read_rows(home_key)
        existed = rows.pop((server, uri), None) is not None
        if existed:
            _write_rows(home_key, rows)
    return existed


def list_trusted(home: Path | str | None = None) -> list[dict[str, Any]]:
    """Every trust record for this profile, sorted by (server, uri)."""
    rows = _read_rows(_home_key(home))
    return [rows[key] for key in sorted(rows)]
