# Changelog

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
