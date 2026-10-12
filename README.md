# hermes-agent — dxianping fork

[简体中文](#简体中文) · [English](#english)

---

## 简体中文

本仓库是 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) 的 fork。
魔改集中在 **`feat/sep-2640`** 分支上：

- **SEP-2640 "Skills over MCP"** —— 原生远程技能（`skills/list`、`skills/get`、`resources/read`），含 Skills Guard 授权边界与会话级 pin
- **Windows 文件系统后端** —— 用 junction 而非符号链接、`portalocker` 替代 `fcntl.flock`、空 pin 自愈

`main` 是上游镜像，不承载魔改。本 `installer` 是**孤儿分支**，只放安装说明和引导脚本，与代码分支无共同历史。

### 一键安装

**Windows（PowerShell）**

```powershell
irm https://raw.githubusercontent.com/dxianping/hermes-agent/installer/install.ps1 | iex
```

**Linux / macOS**

```bash
curl -fsSL https://raw.githubusercontent.com/dxianping/hermes-agent/installer/install.sh | bash
```

### 不用引导脚本（直接调官方安装器）

引导脚本做的事只有一件：把仓库指向本 fork、分支指向 `feat/sep-2640`。
官方安装脚本原生支持这两个参数，所以也可以直接调用：

**Windows**

```powershell
$env:HERMES_REPO_URL = 'https://github.com/dxianping/hermes-agent.git'
& ([scriptblock]::Create((irm https://hermes-agent.nousresearch.com/install.ps1))) -Branch feat/sep-2640
```

**Linux / macOS**

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh \
  | HERMES_REPO_URL=https://github.com/dxianping/hermes-agent.git bash -s -- --branch feat/sep-2640
```

> 官方 `install.ps1` / `install.sh` 已内建 `HERMES_REPO_URL` + `-Branch` / `--branch`，
> 因此不需要维护一份 fork 版的安装器。Windows 上 `irm ... | iex` 无法传参，
> 所以要用上面的 `[scriptblock]::Create(...)` 形式。

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

### 可选参数

引导脚本会把额外参数原样透传给官方安装器：

| 参数 | 说明 |
|---|---|
| `--skip-setup` / `-NonInteractive` | 跳过交互式初始化 |
| `--skip-browser` / `-SkipBrowser` | 不安装浏览器工具 |
| `--skip-computer-use` / `-SkipComputerUse` | 不安装 computer-use |
| `--include-desktop` / `-IncludeDesktop` | 一并安装桌面端 |
| `--dir <路径>` | 自定义安装目录 |

例：

```bash
curl -fsSL https://raw.githubusercontent.com/dxianping/hermes-agent/installer/install.sh | bash -s -- --skip-setup
```

### 回到官方版本

在安装目录里把远端改回上游，或直接卸载后按官方文档重装：

```bash
git -C <安装目录> remote set-url origin https://github.com/NousResearch/hermes-agent.git
```

---

## English

This repository is a fork of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).
The modifications live on the **`feat/sep-2640`** branch:

- **SEP-2640 "Skills over MCP"** — native remote skills (`skills/list`, `skills/get`, `resources/read`) with the Skills Guard authorization boundary and per-session pinning
- **Windows filesystem backend** — junctions instead of symlinks, `portalocker` instead of `fcntl.flock`, self-healing of empty session pins

`main` mirrors upstream and carries no modifications. This `installer` branch is an **orphan branch**:
it holds only the install instructions and bootstrap scripts, and shares no history with the code branches.

### One-command install

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/dxianping/hermes-agent/installer/install.ps1 | iex
```

**Linux / macOS**

```bash
curl -fsSL https://raw.githubusercontent.com/dxianping/hermes-agent/installer/install.sh | bash
```

### Without the bootstrap scripts

All the bootstrap scripts do is point the repo at this fork and the branch at `feat/sep-2640`.
The official installers accept both natively, so you can call them directly:

**Windows**

```powershell
$env:HERMES_REPO_URL = 'https://github.com/dxianping/hermes-agent.git'
& ([scriptblock]::Create((irm https://hermes-agent.nousresearch.com/install.ps1))) -Branch feat/sep-2640
```

**Linux / macOS**

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh \
  | HERMES_REPO_URL=https://github.com/dxianping/hermes-agent.git bash -s -- --branch feat/sep-2640
```

> The official `install.ps1` / `install.sh` already support `HERMES_REPO_URL` plus
> `-Branch` / `--branch`, so there is no need to maintain a forked installer.
> On Windows `irm ... | iex` cannot take parameters — hence the
> `[scriptblock]::Create(...)` form above.

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

The bootstrap scripts pass any extra arguments straight through to the official installer:

| Option | Description |
|---|---|
| `--skip-setup` / `-NonInteractive` | Skip interactive setup |
| `--skip-browser` / `-SkipBrowser` | Do not install browser tooling |
| `--skip-computer-use` / `-SkipComputerUse` | Do not install computer-use |
| `--include-desktop` / `-IncludeDesktop` | Also install the desktop app |
| `--dir <path>` | Custom install directory |

Example:

```bash
curl -fsSL https://raw.githubusercontent.com/dxianping/hermes-agent/installer/install.sh | bash -s -- --skip-setup
```

### Back to upstream

Point the install back at the official repository, or uninstall and reinstall following the
official documentation:

```bash
git -C <install-dir> remote set-url origin https://github.com/NousResearch/hermes-agent.git
```
