# Changelog

## [Unreleased]

### ✨ 新特性 / New Features
- 新增按账户的 `tunnel.name`：按 cpolar 控制台上的隧道名称选择隧道，多台机器可以共用一个 cpolar 账号；存在其他 SSH 隧道、同名隧道或指定的名称不在线时给出提示和修复命令；新增 `config unset` / New per-account `tunnel.name` picks a tunnel by its dashboard name, so several machines can share one cpolar login; other SSH tunnels, same-named tunnels and a name that is not online are reported together with the command that fixes them; new `config unset`
- `ssh.key_path` 可指向已有的无口令 RSA/Ed25519/ECDSA 密钥（RSA、ECDSA 也可以是 PKCS#8 格式）；服务器已经接受该密钥时不再上传 / `ssh.key_path` may point at an existing passphrase-free RSA/Ed25519/ECDSA key (RSA and ECDSA also in PKCS#8 form); nothing is uploaded when the server already accepts it
- 支持在 Windows 服务器上自动安装公钥：默认 shell 是 cmd 或 PowerShell 均可，管理员账户写入 `administrators_authorized_keys`，其他账户写入用户目录下的 `.ssh\authorized_keys` / The public key is installed automatically on Windows servers too: with cmd or PowerShell as the default shell, into `administrators_authorized_keys` for administrator accounts and the profile's `.ssh\authorized_keys` for others
- 连不上服务器时（隧道域名无法解析、端口不通、握手失败）仍把隧道的当前地址写入 `~/.ssh/config`，并在报错后说明；同一账号下有多条候选隧道而未指定 `tunnel.name` 时除外（#3）/ When the server cannot be reached (the tunnel's host name does not resolve, nothing answers, the handshake fails), the tunnel's current address is still written to `~/.ssh/config` and the run says so; not when several tunnels qualify and no `tunnel.name` is set (#3)
- `doctor` 新增“隧道域名解析”检查：有些网络不解析隧道域名（#3）/ `doctor` gains a "Tunnel DNS" check: some networks do not resolve tunnel host names (#3)

### 🔒 安全 / Security
- 主机密钥：一旦有记录，只接受记录中的密钥。此前另一种类型的密钥会被当作首次连接而接受并记录，隧道路径上的任何人都可以借此冒充服务器 / Host keys: once a key is on record, only a key on record is accepted. A key of another type used to be accepted and recorded as on a first connection, which let anyone on the tunnel's path pose as the server
- 主机密钥文件中损坏的记录会报错，不再被跳过 / A damaged record in the host key file is an error instead of being skipped

### 🐛 修复 / Fixes
- 修复服务器不可达、握手失败等情况被当作“首次连接”而要求输入服务器密码的问题；这些情况现在各有明确的报错，服务器不提供密码登录时也会直接说明 / Fix an unreachable server or a failed handshake being taken for a first connection and answered with a prompt for the server password; each now ends in its own clear error, and a server that offers no password login says so
- 隧道域名无法解析时给出专门的提示（原因在本机网络的 DNS），不再建议检查服务器上的 sshd（#3）/ A tunnel host name that does not resolve gets a message of its own (the cause is the local network's DNS) instead of advice about sshd on the server (#3)
- 修复 `~/.ssh/config` 不是 UTF-8（例如含 GBK 注释）或无法读写时崩溃的问题 / Fix crashes when `~/.ssh/config` is not UTF-8 (GBK comments, say) or cannot be read or written
- 公钥上传：公钥始终独占一行（`authorized_keys` 末尾缺少换行时也是如此）；“已安装”按 sshd 的读法判断，不再做子串匹配；登录 shell 是 zsh、dash、csh、tcsh 时同样可用；服务器 60 秒没有回应就放弃 / Public key upload: the key always lands on a line of its own (also when `authorized_keys` lacks a final newline); "already installed" means an entry as sshd reads it, not a substring match; works with zsh, dash, csh and tcsh as the login shell; gives up after 60 seconds without a reply
- Windows 客户端：生成的私钥和新建的 `~/.ssh/config` 能通过 `ssh.exe` 的权限检查（Python ≥ 3.12.4 下，在没有 `~/.ssh` 的机器上首次运行曾以 Permission denied 告终）；旧版本留下的文件会在下次运行时修复 / Windows client: the generated key and a newly created `~/.ssh/config` pass `ssh.exe`'s access check (with Python ≥ 3.12.4, a first run on a machine without `~/.ssh` ended in "Permission denied"); files left by earlier versions are repaired on the next run
- 含空格、引号、`#`、`=`、`%` 的 ssh_config 值会被正确转义 / ssh_config values containing spaces, quotes, `#`, `=` or `%` are rendered so that OpenSSH reads them back unchanged
- `init` 保留它没有问到的设置；消息里出现的命令都带账户名（`-a <账户>`），错误后的提示在静默模式下同样显示 / `init` keeps the settings it does not ask about; every command printed in a message names the account (`-a <name>`), and hints after an error are shown in quiet mode too

### 🔧 改进 / Improvements
- ⚠️ 依赖变化：需要 `paramiko>=3.2`，并显式依赖 `cryptography` / Dependency change: `paramiko>=3.2` is required, and `cryptography` is a declared dependency
- ⚠️ 输出契约变化：`status -f json` 的 `tunnel` 新增 `name` 与 `other_candidates`；直连命令改用 `-o IdentityFile=` 传递密钥 / Contract change: `tunnel` in `status -f json` gains `name` and `other_candidates`; the direct ssh command passes the key as `-o IdentityFile=`
- 新增 GitHub Actions CI：在 Linux、macOS、Windows 上运行测试，并对真实的 sshd（Linux 与 Windows）运行端到端测试 / GitHub Actions CI: the tests run on Linux, macOS and Windows, and end-to-end tests run against real sshd on Linux and Windows

## [0.3.0] - 2026-07-10

### ✨ 新特性 / New Features
- 多账户支持：`cpc use <name>` 粘性切换、`-a` 临时指定（所有命令、前后位置均可）、`cpc list`（顶层别名）与 `cpc account list/remove` 管理 / Multi-account support: sticky `cpc use`, per-invocation `-a` on every command, top-level `cpc list` plus `account list/remove`
- `cpc init -a <name>` 创建新账户并自动切换，SSH 别名自动派生为 `cpolar-<name>` 且全局唯一性校验 / `init -a` creates an account and switches to it; alias derived as `cpolar-<name>` with global uniqueness check
- 新增短入口 `cpc`（与 `cpolar-connect` 等价）/ New short entry point `cpc`
- 账户解析优先级 `-a` > `CPOLAR_ACCOUNT` > 当前账户 > `default` / Resolution: `-a` > `CPOLAR_ACCOUNT` > current > `default`
- 未找到隧道时提示需要在服务器上执行的命令（连接与 status 均生效）/ When no tunnel is found, show the exact commands to run on the server (both connect and status)

### 🔒 安全 / Security
- 账户名四入口统一白名单校验（防路径穿越与 SSH 配置注入）/ Account names validated at all entry points (path traversal & ssh_config injection prevention)
- `ssh_host_alias` 增加格式校验 / `ssh_host_alias` now validated

### 🔧 改进 / Improvements
- 旧版单账户布局自动迁移为 `default` 账户（幂等、可中断续迁、同步改写 ~/.ssh/config 中的 known_hosts 路径）/ Legacy layout migrates automatically into the `default` account (idempotent, interruption-safe, rewrites known_hosts path in ~/.ssh/config)
- ⚠️ 输出契约变化：`config show -f json` 的 `config_dir` 现指向账户目录；`status -f json` 新增顶层 `account` 键 / Contract change: `config_dir` now points at the account dir; `status -f json` gains a top-level `account` key

## [0.2.4] - 2026-07-10

### ✨ 新特性 / New Features
- 主机密钥校验：首次连接记录服务器主机密钥（按 SSH 别名存储于 `~/.cpolar_connect/known_hosts`），之后每次连接校验，防止中间人攻击 / Host key verification: recorded on first connection (keyed by SSH alias in `~/.cpolar_connect/known_hosts`), verified on every connection to prevent MITM attacks
- 新增 `config clear-hostkey` 命令：服务器重装后重置已存主机密钥 / New `config clear-hostkey` command to reset the stored host key after server reinstall
- 首次连接自动尝试已有 SSH 密钥（ssh-agent/默认密钥）上传公钥，成功则无需输入服务器密码 / First connection tries existing SSH keys (agent/default) to install the public key — no server password needed if accepted

### 🔒 安全 / Security
- 生成的 SSH 配置改用 `StrictHostKeyChecking accept-new` + `HostKeyAlias`，不再使用 `StrictHostKeyChecking no` / Generated SSH config now uses `StrictHostKeyChecking accept-new` + `HostKeyAlias` instead of disabling host key checks
- 密码文件以 600 权限原子创建，配置目录收紧为 700 / Password file created atomically with mode 600; config directory tightened to 700
- 公钥上传检查远程命令退出码，失败立即报错并附带原因 / Public key upload now checks remote command exit status and fails fast with the actual error

### 🐛 修复 / Fixes
- 修复 `config set` 传入非法值或未知键时崩溃输出堆栈的问题 / Fix `config set` crashing with a traceback on invalid values or unknown keys
- 修复本地端口为 22xx 的隧道被误判为 SSH 隧道的问题 / Fix tunnels with local port 22xx being misdetected as the SSH tunnel
- 修复登录时网络错误被误报为认证错误的问题 / Fix network errors during login being misreported as authentication errors
- 修复确认提示按 Ctrl+C 被当作接受默认值的问题，现在视为取消 / Fix Ctrl+C at confirmation prompts being treated as accepting the default; now cancels
- 补充缺失的 i18n 文案并新增完整性测试防止再次遗漏 / Add missing i18n messages and a completeness test to prevent regressions

### 🔧 改进 / Improvements
- 移除未使用的 questionary 依赖 / Remove unused questionary dependency
- 登录逻辑去重：init 凭据验证复用 CpolarAuth，支持自定义 base_url / Deduplicate login logic: init credential verification reuses CpolarAuth and respects custom base_url
- doctor 在 Windows 上不再误报私钥权限警告，修正过时的密码提示文案 / doctor no longer false-warns about key permissions on Windows; stale password hint corrected

## [0.2.3] - 2026-01-29

### 🔧 改进 / Improvements
- 移除 keyring 依赖，改用独立密码文件存储 / Remove keyring dependency, use separate password file
- 密码存储于 `~/.cpolar_connect/.password`（权限 600）/ Password stored in `~/.cpolar_connect/.password` (mode 600)

## [0.2.2] - 2026-01-29

### 🐛 修复 / Fixes
- 修复 PyPI 打包配置导致模块无法导入的问题 / Fix PyPI packaging config causing module import failure
- 修复 README 徽章渲染问题 / Fix badge rendering in README

## [0.2.0] - 2026-01-28

### ✨ 新特性 / New Features
- Clack 风格 CLI：全新的步骤式输出风格，更清晰的交互体验 / Clack-style step output for clearer CLI interaction
- init 凭据验证：配置账户时自动验证用户名密码有效性 / Credential verification during init before saving config
- 完整 i18n 支持：`config show`、`config path`、连接摘要等全部支持中英文 / Full i18n support for all commands and outputs

### 🔧 改进 / Improvements
- init 流程优化：密码输入移至步骤1，端口输入错误可重试而非退出 / Improved init UX: password in step 1, port input retry on error
- auto_connect 修复：设置为 true 时跳过连接确认提示 / auto_connect=true now skips confirmation prompt
- CJK 对齐：中英文混合显示时标签自动对齐 / CJK character alignment for mixed language display
- 统一帮助文本：所有命令的 --help 显示中英双语说明 / Bilingual help text for all commands
- 架构优化：输出逻辑统一到 CLI 层，业务模块返回数据 / Output logic unified to CLI layer, business modules return data
- 语言优先级：环境变量 CPOLAR_LANG 优先于配置文件 / CPOLAR_LANG env var takes priority over config file

### 🐛 修复 / Fixes
- 修复 SSH 空闲超时断开问题（添加 ServerAliveInterval） / Fix SSH idle timeout disconnection
- 修复远程桌面隧道被误识别为 SSH 隧道的问题 / Fix remoteDesktop tunnel being detected as SSH tunnel

## [0.1.2] - 2025-12-12

### 🐛 修复 / Fixes
- 修复每次更新 SSH 配置时空行累积的问题 (#1) / Fix empty line accumulation when updating SSH config (#1)
- 修复更新时 Match 块被误删的问题 / Fix Match blocks being incorrectly deleted during updates
- 修复块间空行被吞掉的问题 / Fix blank lines between blocks being consumed

## [0.1.1] - 2025-09-16

### ✨ 改进 / Improvements
- 📊 **状态命令**：`status` 支持“离线（仅本地）”模式；当缺少密码、认证失败或网络异常时，不再报错退出，而是展示本地 SSH 配置与端口转发信息。/ The `status` command now falls back to "offline (local-only)" when password is missing, auth fails, or network issues occur, showing local SSH config instead of exiting with error.
- 🧰 **集中日志**：增加滚动日志，默认写入 `~/.cpolar_connect/logs/cpolar.log`，支持 `CPOLAR_LOG_LEVEL` 和配置项 `log_level`。/ Centralized rotating logging to `~/.cpolar_connect/logs/cpolar.log`, honoring `CPOLAR_LOG_LEVEL` and config `log_level`.
- 🌏 **帮助与提示统一**：命令描述与参数占位（`KEY`/`VALUE`/`LANG`）统一为中英简短风格。/ Unified bilingual help strings and argument placeholders across commands.
- 🪟 **跨平台改进**：`doctor` 的命令检测改为 `shutil.which`，提升 Windows 兼容性。/ `doctor` now uses `shutil.which` for better Windows compatibility.
- 🐛 **调试文件路径**：隧道解析失败时的 HTML 调试文件写入日志目录并带时间戳。/ Tunnel status debug HTML is now saved under the logs directory with timestamps.
- 📝 **编辑器回退**：`config edit` 在未设置 `$EDITOR` 时按平台回退（macOS: `open -e`，Windows: `notepad`，Linux: `nano`）。/ `config edit` falls back to a platform-appropriate editor when `$EDITOR` is unset.
- 🌐 **语言选项精简**：语言仅支持 `zh/en`。/ Language selection simplified to `zh/en` only.

## [0.1.0] - 2025-01-19

### 🎉 发布 / Release
- 首个稳定版本 / First stable release

### ✨ 主要特性 / Key Features
- 🚀 cpolar 隧道自动管理与 SSH 连接 / cpolar tunnel automation and SSH integration
- 🌏 双语界面（zh/en）/ Bilingual UI (zh/en)
- 🏥 诊断工具 `doctor` / Diagnostic tool `doctor`
- 🔐 密码管理（环境变量与系统密钥环）/ Password management (env var + keyring)
- ⚙️ 配置管理命令集 / Full config management commands

### 🔧 改进 / Improvements
- 🚨 更清晰的错误提示（SSH 认证失败给出修复建议）/ Clearer error messages with actionable hints for SSH auth failures
- ⏱️ SSH 连接超时提升至 30 秒 / SSH connection timeout increased to 30s
- 📊 状态显示优化，减少不必要提示 / Status display improvements
- 🔧 配置输入解析增强（端口、布尔值）/ Config input parsing hardening (ports, booleans)
- 📝 修复密码输入被 spinner 覆盖的问题 / Fixed spinner obscuring password prompt

## [0.1.0.dev1] - 2025-01-19

### ✨ 改进 / Improvements
- 🔐 密码管理优化：优先使用环境变量，避免 macOS 钥匙串弹窗 / Prefer env var to avoid macOS keychain prompts
- 🚨 错误提示增强：SSH 认证失败提供更明确指引 / Clearer, actionable SSH auth errors
- ⏱️ 超时提升：SSH 连接超时调至 30s / SSH connection timeout increased to 30s
- 📊 状态显示优化：减少不必要的权限提示 / Status display tuned to reduce keychain prompts

### 🐛 修复 / Fixes
- 用户名错误时的提示更清晰 / Clearer message when server username is incorrect
- 降低 macOS 钥匙串反复授权的频率 / Reduced repeated keychain authorization prompts on macOS

## [0.1.0.dev0] - 2025-01-18

### 🎉 初始发布 / Initial Release
- 🚀 cpolar 隧道自动管理与 SSH 连接 / cpolar tunnel automation and SSH integration
- 🌏 双语支持（zh/en）/ Bilingual support (zh/en)
- 🏥 诊断工具 `doctor` / Diagnostic tool `doctor`
- 🔑 密码管理（环境变量 + 系统密钥环）/ Password management (env var + keyring)
- ⚙️ 配置管理命令集 / Config management commands
