# hermes-agent — dxianping fork

[简体中文](#简体中文) · [English](#english)

---

## 简体中文

本仓库是 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) 的 fork。
魔改集中在 **`feat/sep-2640`** 分支上：

- **SEP-2640 "Skills over MCP"** —— 原生远程技能（`skills/list`、`skills/get`、`resources/read`），含 Skills Guard 授权边界与会话级 pin
- **Windows 文件系统后端** —— 用 junction 而非符号链接、`portalocker` 替代 `fcntl.flock`、空 pin 自愈

`main` 是上游镜像，不承载魔改。`installer` 是**孤儿分支**，保存安装说明与可选补丁，与代码分支无共同历史。

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

### 可选补丁：无人值守默认授权所有远端 skills

`patches/auto-trust-all-remote-skills.patch` 面向无人值守环境（CI、后台任务等）。应用后，
凡是在本 profile `config.yaml` 的 `mcp_servers` 中配置的 skills 服务器，其**所有**远端
MCP skill 默认自动通过加载与执行同意门（等价 `trust: all`），无需逐条执行
`hermes skills trust-mcp`。

应用（基线 `feat/sep-2640` @ `038cd92a0f`；建议先 `hermes update` 再打补丁）：

**Windows（PowerShell）**

```powershell
$patch = Join-Path $env:TEMP 'auto-trust-all-remote-skills.patch'
Invoke-WebRequest 'https://raw.githubusercontent.com/dxianping/hermes-agent/installer/patches/auto-trust-all-remote-skills.patch' -OutFile $patch
git -C 'D:\Apps\hermes\hermes-agent' apply --check $patch
git -C 'D:\Apps\hermes\hermes-agent' apply $patch
```

**Linux / macOS**（将 `<安装目录>` 替换为实际路径）

```bash
curl -fsSL https://raw.githubusercontent.com/dxianping/hermes-agent/installer/patches/auto-trust-all-remote-skills.patch -o /tmp/auto-trust.patch
git -C <安装目录> apply --check /tmp/auto-trust.patch
git -C <安装目录> apply /tmp/auto-trust.patch
```

语义与逃生口：

- 未配置（不在 `mcp_servers` 里）的服务器一律 fail-closed，仍逐次人工应答。
- 单个服务器写 `trust: prompt` 可退回人工同意；`trust: auto` 保持按 `trust-mcp` 记录授权。
  **已有 `trust: auto` 不会被补丁覆盖**：需要全部授权时把该键改为 `trust: all`，或删除该键使用补丁默认值。
- 仍需 `skills.enabled: true`；本补丁不自动启用 skills 发现。
- `trusted-mcp` 仍只列逐条记录，不列 blanket trust；`all` 模式下 `untrust-mcp` 仅删除记录，不撤销服务器级授权。
- Skills Guard 扫描、跨源读逐次应答、普通工具审批不受影响。
- 所有自动放行写 warning 审计日志（`under configured mcp_servers.<server>.skills.trust policy`）。

维护：保存下载的补丁。`hermes update` 前用 `git -C <安装目录> apply --reverse --check <补丁路径>`
检查，再用 `git -C <安装目录> apply --reverse <补丁路径>` 撤销；更新后重新 `apply --check` 和 `apply`。
补丁以未提交改动保留，不改变 `feat/sep-2640` 的安全默认值。若基线前移导致冲突，
在开发分支解决并提交补丁改动后，用 `git format-patch -1 --stdout HEAD` 重新生成，
替换 `patches/auto-trust-all-remote-skills.patch` 并更新基线提交号。修改后需重启现有 ACP/网关进程；新 CLI 进程直接读取新代码。

验证：在 `038cd92a0f` 上通过 `git apply --check`，应用后的内容与补丁开发分支一致；
20 个相关测试文件 **402 项通过、4 项跳过**，改动文件 ruff 与提交钩子通过。

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
only install instructions and optional patches, and shares no history with the code branches.

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

### Optional patch: blanket-trust all remote skills (unattended installs)

`patches/auto-trust-all-remote-skills.patch` targets unattended environments (CI, scheduled
jobs). Once applied, every remote MCP skill served by a server listed in this profile's
`mcp_servers` auto-passes the activation and host-execution consent gates (equivalent to
`trust: all`) — no per-skill `hermes skills trust-mcp` needed.

Apply (baseline `feat/sep-2640` @ `038cd92a0f`; run `hermes update` first, then apply):

```bash
curl -fsSL https://raw.githubusercontent.com/dxianping/hermes-agent/installer/patches/auto-trust-all-remote-skills.patch -o /tmp/auto-trust.patch
git -C <install-dir> apply --check /tmp/auto-trust.patch
git -C <install-dir> apply /tmp/auto-trust.patch
```

Semantics and escape hatches:

- Servers not listed in `mcp_servers` fail closed (per-call human consent).
- `trust: prompt` on one server restores human consent; `trust: auto` keeps the
  `trust-mcp` record-gated behavior. Existing explicit `auto` settings are not overridden;
  set them to `all` (or remove the trust key) to blanket-authorize that server.
- `skills.enabled: true` is still required. `trusted-mcp` only lists individual records;
  deleting one with `untrust-mcp` does not revoke a server's `all` policy.
- Skills Guard scanning, cross-origin read consent, and ordinary tool approvals are unchanged.
- Every auto approval is logged as a warning (`under configured mcp_servers.<server>.skills.trust policy`).

Maintenance: keep the downloaded patch. Before `hermes update`, run
`git -C <install-dir> apply --reverse --check <patch-path>`, then
`git -C <install-dir> apply --reverse <patch-path>`. After updating, run `apply --check`
and `apply` again. Leave it as an uncommitted local change so the feature branch retains
its safe defaults. If a new baseline conflicts, resolve and commit on a development branch,
regenerate with `git format-patch -1 --stdout HEAD`, and replace the patch plus its documented
baseline. Restart existing ACP/gateway processes after applying; new CLI processes load it immediately.

Verified on `038cd92a0f`: clean patch application and byte-identical result against the
patch development branch; **402 tests passed, 4 skipped** across 20 related test files;
changed-file ruff and commit hooks passed.

### Back to upstream

Point the install back at the official repository, or uninstall and reinstall following the
official documentation:

```bash
git -C <install-dir> remote set-url origin https://github.com/NousResearch/hermes-agent.git
```
