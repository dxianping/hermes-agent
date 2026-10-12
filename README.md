# hermes-agent — dxianping fork

[简体中文](#简体中文) · [English](#english)

---

## 简体中文

本仓库是 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) 的 fork。
魔改集中在 **`feat/sep-2640`** 分支上：

- **SEP-2640 "Skills over MCP"** —— 原生远程技能（`skills/list`、`skills/get`、`resources/read`），含 Skills Guard 授权边界与会话级 pin
- **Windows 文件系统后端** —— 用 junction 而非符号链接、`portalocker` 替代 `fcntl.flock`、空 pin 自愈

`main` 是上游镜像，不承载魔改。`installer` 是**孤儿分支**，只放这份安装说明，与代码分支无共同历史。

### 安装

官方安装脚本原生支持指定仓库和分支（环境变量 `HERMES_REPO_URL` + 参数 `-Branch` / `--branch`），
**直接用官方脚本即可，不需要额外的安装器**：

**Windows（PowerShell）**

```powershell
$env:HERMES_REPO_URL = 'https://github.com/dxianping/hermes-agent.git'
& ([scriptblock]::Create((irm https://hermes-agent.nousresearch.com/install.ps1))) -Branch feat/sep-2640
```

**Linux / macOS**

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh \
  | HERMES_REPO_URL=https://github.com/dxianping/hermes-agent.git bash -s -- --branch feat/sep-2640
```

> Windows 上 `irm ... | iex` 无法传参，所以用上面的 `[scriptblock]::Create(...)` 形式；
> Linux 上的 `bash -s --` 用于把参数传给管道里的脚本。

### 更新

```bash
hermes update
```

`hermes update` 跟随当前 checkout 分支的远端。从本 fork 安装后，它拉取的就是本 fork 的
`feat/sep-2640` —— 在任一机器上 `git push` 之后，其他机器执行 `hermes update` 即可同步。

建议同时接上上游通道，便于跟进官方基线：

```bash
git remote add upstream https://github.com/NousResearch/hermes-agent.git
```

### 常用参数

官方安装脚本支持的其他参数：

| 参数 | 说明 |
|---|---|
| `-NonInteractive` / `--skip-setup` | 跳过交互式初始化 |
| `-SkipBrowser` / `--skip-browser` | 不安装浏览器工具 |
| `-SkipComputerUse` / `--skip-computer-use` | 不安装 computer-use |
| `-IncludeDesktop` / `--include-desktop` | 一并安装桌面端 |
| `-Commit <sha>` / `--commit <sha>` | 固定到某个提交 |
| `--dir <路径>` | 自定义安装目录 |

### 回到官方版本

在安装目录里把远端改回上游，或卸载后按官方文档重装：

```bash
git -C <安装目录> remote set-url origin https://github.com/NousResearch/hermes-agent.git
```

---

## English

This repository is a fork of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).
The modifications live on the **`feat/sep-2640`** branch:

- **SEP-2640 "Skills over MCP"** — native remote skills (`skills/list`, `skills/get`, `resources/read`) with the Skills Guard authorization boundary and per-session pinning
- **Windows filesystem backend** — junctions instead of symlinks, `portalocker` instead of `fcntl.flock`, self-healing of empty session pins

`main` mirrors upstream and carries no modifications. `installer` is an **orphan branch**: it holds
only these install instructions and shares no history with the code branches.

### Install

The official installer already accepts a custom repository and branch (the `HERMES_REPO_URL`
environment variable plus `-Branch` / `--branch`), so **use the official script directly — no extra
installer is needed**:

**Windows (PowerShell)**

```powershell
$env:HERMES_REPO_URL = 'https://github.com/dxianping/hermes-agent.git'
& ([scriptblock]::Create((irm https://hermes-agent.nousresearch.com/install.ps1))) -Branch feat/sep-2640
```

**Linux / macOS**

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh \
  | HERMES_REPO_URL=https://github.com/dxianping/hermes-agent.git bash -s -- --branch feat/sep-2640
```

> On Windows `irm ... | iex` cannot take parameters — hence the `[scriptblock]::Create(...)` form.
> On Linux, `bash -s --` passes the arguments through to the script on stdin.

### Updating

```bash
hermes update
```

`hermes update` follows the remote of the currently checked-out branch. After installing from this
fork it pulls this fork's `feat/sep-2640`, so a `git push` from any machine is picked up by
`hermes update` on every other machine.

Adding the upstream remote is recommended for tracking the official baseline:

```bash
git remote add upstream https://github.com/NousResearch/hermes-agent.git
```

### Options

Other arguments the official installer accepts:

| Option | Description |
|---|---|
| `-NonInteractive` / `--skip-setup` | Skip interactive setup |
| `-SkipBrowser` / `--skip-browser` | Do not install browser tooling |
| `-SkipComputerUse` / `--skip-computer-use` | Do not install computer-use |
| `-IncludeDesktop` / `--include-desktop` | Also install the desktop app |
| `-Commit <sha>` / `--commit <sha>` | Pin to a specific commit |
| `--dir <path>` | Custom install directory |

### Back to upstream

Point the install back at the official repository, or uninstall and reinstall following the
official documentation:

```bash
git -C <install-dir> remote set-url origin https://github.com/NousResearch/hermes-agent.git
```
