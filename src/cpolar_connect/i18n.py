"""
Internationalization support for Cpolar Connect
"""

import json
import os
from enum import Enum
from pathlib import Path
from typing import Dict, Optional


class Language(Enum):
    """Supported languages"""

    EN = "en"
    ZH = "zh"


class Messages:
    """Message translations"""

    # English messages
    EN = {
        # General
        "welcome": "Welcome to Cpolar Connect",
        "version": "Version",
        "help": "Help",
        # Authentication
        "auth.csrf_token": "Obtaining CSRF token...",
        "auth.logging_in": "Logging in as {username}...",
        "auth.login_success": "Successfully logged in to cpolar",
        "auth.login_failed": "Login failed. Please check your username and password.",
        "auth.password_required": "Password not found. Set CPOLAR_PASSWORD environment variable or run 'cpolar-connect -a {account} init' to store password",
        "auth.logout": "Logged out from cpolar",
        # Tunnel
        "tunnel.fetching": "Fetching tunnel information...",
        "tunnel.found": "Found tunnel: {url}",
        "tunnel.not_found": "No active tunnel found. Please ensure cpolar is running on your server.",
        "tunnel.server_hint": "Run on the server:",
        "tunnel.parsing_error": "Failed to parse tunnel information",
        # SSH
        "ssh.generating_key": "Generating SSH key pair...",
        "ssh.key_generated": "SSH key pair generated: {path}",
        "ssh.key_exists": "SSH key already exists: {path}",
        "ssh.uploading_key": "Uploading public key to server...",
        "ssh.need_password_for_key_upload": "Need password to upload SSH key to server",
        "ssh.trying_connect": "Attempting SSH connection as {username}@{hostname}...",
        "ssh.testing_connection": "Testing SSH connection...",
        "ssh.key_uploaded": "Public key uploaded successfully",
        "ssh.trying_existing_keys": "Trying existing SSH keys (agent/default keys)...",
        "ssh.existing_keys_failed": "Existing keys not accepted, server password required",
        "ssh.key_uploaded_via_existing": "Public key installed using existing SSH keys",
        "ssh.updating_config": "Updating SSH config...",
        "ssh.config_updated": "SSH config updated",
        "ssh.connecting": "Connecting to server via SSH...",
        "ssh.connected": "Connected to server",
        "ssh.connection_failed": "SSH connection failed: {error}",
        # CLI
        "cli.initializing": "Initializing Cpolar Connect...",
        "cli.config_exists": "Configuration already exists. Use --force to overwrite.",
        "cli.enter_username": "Enter your cpolar username",
        "cli.enter_password": "Enter your cpolar password",
        "cli.enter_server_user": "Enter server username",
        "cli.enter_ssh_alias": "Enter SSH alias",
        "cli.enter_ports": "Enter ports to forward (comma-separated)",
        "cli.auto_connect": "Auto-connect after update?",
        "cli.basic_configuration": "Basic Configuration",
        "cli.connecting_server": "Connecting to server...",
        "cli.no_config": "No configuration found. Please run 'cpolar-connect -a {account} init' first.",
        "cli.config_created": "Configuration created successfully",
        "cli.config_updated": "Configuration updated: {key} = {value}",
        "cli.config_unset": "Configuration cleared: {key}",
        "cli.config_saved_path": "Configuration saved to: {path}",
        # Status
        "status.title": "Cpolar Connect Status",
        "status.mode.remote": "Online",
        "status.mode.local": "Offline (local-only)",
        "status.auth_missing": "Password not available; showing local configuration only",
        "status.auth_failed": "Authentication failed; showing local configuration only: {error}",
        "status.network_failed": "Network error; showing local configuration only: {error}",
        "status.tunnel.unknown": "Unknown (not authenticated)",
        # Status table
        "status.column.field": "Field",
        "status.column.value": "Value",
        "status.field.tunnel": "Tunnel",
        "status.field.tunnel_name": "Tunnel Name",
        "status.field.host": "Host",
        "status.field.port": "Port",
        "status.field.ssh_alias": "SSH Alias",
        "status.field.ssh_key": "SSH Key",
        "status.field.auto_connect": "Auto Connect",
        "status.field.forward_ports": "Forward Ports",
        # Config
        "config.loading": "Loading configuration...",
        "config.saving": "Saving configuration...",
        "config.saved": "Configuration saved",
        "config.invalid": "Invalid configuration: {error}",
        # Config display
        "config.title": "Cpolar Connect Configuration",
        "config.column_setting": "Setting",
        "config.column_value": "Value",
        "config.username": "Username",
        "config.base_url": "Base URL",
        "config.tunnel_name": "Tunnel Name",
        "config.tunnel_name_auto": "auto (first SSH tunnel)",
        "config.value_unset": "(not set)",
        "config.server_user": "Server User",
        "config.ports": "Ports",
        "config.auto_connect": "Auto Connect",
        "config.ssh_key_path": "SSH Key Path",
        "config.ssh_host_alias": "SSH Host Alias",
        "config.ssh_key_size": "SSH Key Size",
        "config.log_level": "Log Level",
        "config.language": "Language",
        "config.password_status": "Password Status",
        "config.config_dir": "Config Dir",
        "config.config_file": "Config File",
        "config.logs_dir": "Logs Dir",
        "config.password_env": "Stored (env var)",
        "config.password_file": "Stored (.password file)",
        "config.password_none": "Not stored",
        # Errors
        "error.network": "Network error: {error}",
        "error.auth": "Authentication error: {error}",
        "error.tunnel": "Tunnel error: {error}",
        "error.ssh": "SSH error: {error}",
        "error.config": "Configuration error: {error}",
        "error.unknown": "Unknown error: {error}",
        "error.connection_failed": "Connection failed: {error}",
        "error.session_expired": "Session expired. Please re-authenticate.",
        "error.csrf_token_empty": "CSRF token is empty",
        "error.csrf_token_not_found": "Unable to find CSRF token. The login page structure may have changed.",
        "error.invalid_port": "Invalid port: {port}. Must be between 1-65535",
        "error.invalid_key_size": "SSH key size must be at least 1024 bits",
        "error.invalid_log_level": "Invalid log level: {level}",
        "error.invalid_language": "Invalid language: {lang}. Must be 'zh' or 'en'",
        "error.config_not_found": "Configuration file not found: {path}",
        "error.config_invalid_json": "Invalid JSON in config file: {error}",
        "error.config_load_failed": "Failed to load configuration: {error}",
        "error.config_save_failed": "Failed to save configuration: {error}",
        "error.config_create_failed": "Failed to create configuration: {error}",
        "error.config_key_not_found": "Configuration key '{key}' not found",
        "error.config_key_required": "'{key}' is required and cannot be unset. To change it: cpolar-connect -a {account} config set {key} <value>",
        "error.config_edit_failed": "Failed to open editor: {error}",
        "error.editor_not_found": "Editor '{editor}' not found. Set EDITOR environment variable.",
        "error.ssh_dir_failed": "Cannot create SSH directory: {error}",
        "error.ssh_key_gen_failed": "Failed to generate SSH key: {error}",
        "error.ssh_pubkey_regen_failed": "Failed to regenerate public key: {error}",
        "error.ssh_pubkey_not_found": "Public key not found: {path}",
        "error.ssh_pubkey_invalid": "Public key file {path} is not a valid public key. Delete it to have it rebuilt from the private key",
        "error.ssh_upload_failed": "Failed to upload public key: {error}",
        "error.ssh_remote_timeout": "The server stopped answering while the public key was being installed (no reply for {seconds} seconds). Check the connection and run this again",
        "error.reason_connection_closed": "the server closed the connection",
        "error.ssh_connect_failed": "Failed to connect: {error}",
        "error.ssh_auth_failed": "Failed to establish SSH key authentication",
        "error.ssh_auth_failed_detail": "SSH authentication failed for user '{username}' on {hostname}",
        "error.ssh_unreachable": "Cannot reach the SSH service at {hostname}:{port}: {error}. Make sure sshd is running on the server and the cpolar tunnel points to its SSH port",
        "error.ssh_handshake_failed": "SSH handshake with {hostname}:{port} failed: {error}. Make sure sshd is running on the server and the cpolar tunnel points to its SSH port",
        "error.ssh_host_unresolved": "Cannot resolve the tunnel's host name {hostname} here ({error}). That is a matter of this network's DNS, not of the server; some networks do not resolve tunnel host names. Try another network or DNS server, or map the name to its address in the hosts file",
        "error.ssh_key_load_failed": "Cannot read SSH private key {path}: {error}",
        "error.ssh_key_passphrase": "SSH private key {path} is passphrase-protected and cannot be used. Point ssh.key_path at a key without a passphrase",
        "error.ssh_key_unsupported": "{path} is not a usable SSH private key (an RSA, Ed25519 or ECDSA key without a passphrase is required)",
        "error.ssh_key_too_open": "SSH private key {path} can be read by other users (mode {mode}), and ssh refuses to use such a key. Make it yours alone: {command}",
        "error.ssh_key_path_empty": "ssh.key_path cannot be empty",
        "error.ssh_key_pkcs8_ed25519": "{path} is an Ed25519 key in PKCS#8 form (BEGIN PRIVATE KEY), which most versions of ssh cannot read. Use a key written by ssh-keygen instead",
        "error.tunnel_name_not_found": "No online TCP tunnel named '{name}'. Online TCP tunnels: {available}",
        "hint.set_tunnel_name_command": "cpolar-connect -a {account} config set tunnel.name <tunnel name>",
        "hint.tunnel_name_wrong": "If the tunnel name is wrong, use one of the names listed above: {command}",
        "hint.tunnel_machine_down": "If that machine is off or cpolar is not running on it, run there:",
        "hint.check_username_password": "Please verify: 1) Server username is correct (run 'whoami' on server), 2) Password is correct",
        "error.tunnel_url_invalid": "Invalid tunnel URL format: {url}",
        "error.password_clear_failed": "Failed to clear password: {error}",
        "error.hostkey_clear_failed": "Failed to clear host key: {error}",
        "error.invalid_account_name": "Invalid account name: '{name}'. Use letters, digits, '.', '_' or '-' (max 64 chars)",
        "error.account_not_found": "Account '{name}' not found",
        "error.host_key_changed": "Server host key has changed! This could indicate a man-in-the-middle attack.",
        "hint.host_key_changed_auto_tunnel": "This account has no tunnel.name and takes the first SSH tunnel listed on the dashboard, this time '{tunnel}'. If several machines share this cpolar login, the tunnel may simply lead to another machine than before; in that case pin the one you mean: {command}",
        "hint.host_key_changed": "If you reinstalled the server, or pointed this account at a different machine (for example by changing tunnel.name), clear the recorded key and retry: cpolar-connect -a {account} config clear-hostkey",
        "hint.address_recorded": "The SSH config was updated with the tunnel's current address all the same (Host {alias})",
        "error.known_hosts_unusable": "Cannot read or update the host key file {path}: {error}. Fix or remove that file, then retry (removing it records the server key anew)",
        "error.ssh_config_unusable": "Cannot read or update the SSH config file {path}: {error}",
        "error.ssh_remote_command_failed": "Remote command failed ({command}): {error}",
        "error.ssh_pubkey_mismatch": "Public key file {path} does not belong to the private key {key}. Delete it to have it rebuilt from the private key",
        "error.ssh_connection_lost": "The connection to {hostname}:{port} was lost during authentication: {error}. Try again",
        "error.ssh_password_login_unavailable": "The server does not accept password logins (it offers: {methods})",
        "hint.password_login_unavailable": "No password can install the key there. Point this account at a key the server already accepts: cpolar-connect -a {account} config set ssh.key_path <private key>. Or add the line in {public_key} to that account's authorized_keys file on the server yourself, then run this again",
        "error.password_store_failed": "Failed to store password: {error}",
        # Warnings
        "warning.config_exists": "Configuration already exists. Overwrite?",
        "warning.no_password": "No stored password found",
        "warning.no_hostkey": "No stored server host key found",
        "warning.ssh_key_exists": "Public key already exists in authorized_keys",
        "warning.ssh_auth_failed": "SSH key authentication failed, uploading public key...",
        "warning.connection_interrupted": "Connection interrupted by user",
        "warning.first_connection": "First time connection - need to upload SSH key",
        "warning.ssh_key_missing": "No key file at {path}: the next connection will generate a new RSA key pair there. To use an existing key, check the path",
        "warning.multiple_ssh_tunnels": "This cpolar account has several SSH tunnels; using the first one '{chosen}' (others: {others}). To choose one: {command}",
        "warning.multiple_tcp_tunnels": "No tunnel of this cpolar account leads to local port 22; using the first TCP tunnel '{chosen}' (others: {others}). To choose one: {command}",
        "warning.duplicate_tunnel_name": "{count} tunnels are named '{name}'; using the first one ({url}). tunnel.name cannot tell them apart: give the tunnel a different name on one of the machines (in its cpolar configuration)",
        "warning.tunnel_changed_hostkey": "This account has a recorded server host key. If the tunnel now leads to a different machine, clear it first: cpolar-connect -a {account} config clear-hostkey (otherwise the next connection reports a changed host key)",
        "warning.config_cancelled": "Configuration initialization cancelled",
        "warning.config_exists_skip": "Configuration already exists, skipping. Use --force to overwrite.",
        "warning.invalid_port_format": "Invalid port format",
        # Info/Tips
        "info.password_cleared": "Password cleared",
        "info.hostkey_cleared": "Stored server host key cleared",
        "info.account_switched": "Switched to account '{name}'",
        "info.available_accounts": "Available accounts: {names}",
        "info.no_accounts": "No accounts yet. Run 'cpolar-connect init' first",
        "account.removed": "Account '{name}' removed",
        "account.confirm_remove": "Remove account '{name}' and its stored password/host keys?",
        "account.list_title": "Cpolar Connect Accounts",
        "account.column.name": "Account",
        "account.column.username": "Username",
        "account.column.alias": "SSH Alias",
        "account.column.current": "Current",
        "error.alias_conflict": "SSH alias '{alias}' is already used by account '{other}'",
        "hint.alias_conflict": "Two accounts cannot share an alias. Give one of them another: cpolar-connect -a {account} config set ssh.host_alias <alias>",
        "warning.hostblock_cleanup_skipped": "Could not clean SSH config block: {error}",
        "config.account": "Account",
        "status.field.account": "Account",
        "info.config_opened": "Configuration file opened in editor",
        "info.run_init": "Run 'cpolar-connect -a {account} init' to create configuration",
        "info.env_password_tip": "You can also set CPOLAR_PASSWORD environment variable",
        "info.init_kept_settings": "Other settings of this account were kept (e.g. tunnel.name, ssh.key_path); see 'cpolar-connect -a {account} config show'",
        # Doctor
        "doctor.title": "Diagnosis Results",
        "doctor.running": "Running diagnostics...",
        "doctor.column.check": "Check Item",
        "doctor.column.status": "Status",
        "doctor.column.message": "Details",
        "doctor.summary.title": "Summary",
        "doctor.summary.all_good": "All checks passed! Ready to connect.",
        "doctor.summary.has_warnings": "Some warnings found, but should still work.",
        "doctor.summary.has_errors": "Critical issues found. Please fix them before connecting.",
        "doctor.recommendations": "Recommendations",
        # Doctor checks
        "doctor.check.config": "Configuration file",
        "doctor.check.username": "Cpolar username",
        "doctor.check.server_user": "Server username",
        "doctor.check.password": "Password storage",
        "doctor.check.network": "Network connectivity",
        "doctor.check.cpolar_auth": "Cpolar authentication",
        "doctor.check.tunnel": "Tunnel status",
        "doctor.check.tunnel_selection": "Tunnel selection",
        "doctor.check.tunnel_name": "Tunnel name",
        "doctor.check.tunnel_dns": "Tunnel DNS",
        "doctor.recommend.pick_tunnel": "Pick this account's tunnel by its name on the cpolar dashboard",
        "doctor.check.ssh_key": "SSH private key",
        "doctor.check.ssh_pubkey": "SSH public key",
        "doctor.check.ssh_config": "SSH config",
        "doctor.check.ssh_command": "SSH command",
        # Doctor messages
        "doctor.config.not_found": "Configuration not found. Run 'cpolar-connect -a {account} init'",
        "doctor.config.no_username": "Cpolar username not configured",
        "doctor.config.no_server_user": "Server username not configured",
        "doctor.config.valid": "Configuration is valid",
        "doctor.password.found": "Password stored in .password file",
        "doctor.password.env": "Password found in environment variable",
        "doctor.password.not_found": "No password configured. Set CPOLAR_PASSWORD or run 'cpolar-connect -a {account} init'",
        "doctor.password.env_multi_account": "CPOLAR_PASSWORD applies to ALL accounts; unset it if accounts use different passwords",
        "doctor.network.ok": "Network connection is good",
        "doctor.network.timeout": "Connection timeout - check your internet",
        "doctor.network.http_error": "HTTP error {status}",
        "doctor.network.error": "Network error: {error}",
        "doctor.cpolar.no_password": "Cannot test authentication without password",
        "doctor.cpolar.auth_success": "Successfully authenticated with cpolar",
        "doctor.cpolar.auth_failed": "Authentication failed: {error}",
        "doctor.tunnel.found": "Active tunnel found: {url}",
        "doctor.tunnel.not_found": "No active tunnel (server may need to run cpolar)",
        "doctor.tunnel_dns.ok": "{hostname} resolves on this network",
        "doctor.tunnel_dns.failed": "{hostname} does not resolve on this network ({error})",
        "doctor.ssh.key_exists": "SSH key exists",
        "doctor.ssh.key_will_create": "SSH key will be created on first connection",
        "doctor.ssh.key_permission": "SSH key has wrong permissions: {mode} (should be 600)",
        "doctor.ssh.pubkey_exists": "SSH public key exists",
        "doctor.ssh.pubkey_missing": "SSH public key missing (will regenerate)",
        "doctor.ssh.config_exists": "SSH config entry exists",
        "doctor.ssh.config_will_update": "SSH config will be updated on connection",
        "doctor.ssh.config_will_create": "SSH config will be created on connection",
        "doctor.check.hostkey": "Server host key",
        "doctor.hostkey.recorded": "Host key recorded (verified on each connection)",
        "doctor.hostkey.none": "Will be recorded on first connection",
        "doctor.command.found": "Command '{command}' is available",
        "doctor.command.not_found": "Command '{command}' not found",
        # Doctor recommendations
        "doctor.recommend.run_init": "Initialize configuration",
        "doctor.recommend.set_password": "Set password for cpolar authentication",
        "doctor.recommend.check_network": "Check network connectivity",
        "doctor.recommend.check_credentials": "Verify cpolar credentials",
        "doctor.recommend.check_server": "Check cpolar service on server",
        "doctor.recommend.tunnel_dns": "This network's DNS does not resolve the tunnel's host name, so connecting fails here whatever the server does. Try another network or DNS server, or map the name to its address in the hosts file",
        # Doctor command examples
        "doctor.cmd.init": "cpolar-connect -a {account} init",
        "doctor.cmd.password.win": "set CPOLAR_PASSWORD=your_password",
        "doctor.cmd.password.unix": "export CPOLAR_PASSWORD=your_password",
        "doctor.cmd.password.save": "cpolar-connect -a {account} init  # Save password permanently",
        "doctor.cmd.network.ping": "ping cpolar.com",
        "doctor.cmd.network.curl": "curl -I https://dashboard.cpolar.com",
        "doctor.cmd.network.check": "Check firewall/proxy settings",
        "doctor.cmd.auth.check1": "1. Username should be your email",
        "doctor.cmd.auth.check2": "2. Try logging in at https://dashboard.cpolar.com",
        "doctor.cmd.auth.check3": "3. Reset password if needed",
        "doctor.cmd.server.status": "sudo systemctl status cpolar",
        "doctor.cmd.server.start": "sudo systemctl start cpolar   # If not running",
        "doctor.cmd.server.tunnel": "cpolar tcp 22                 # Start SSH tunnel",
        "doctor.cmd.option1": "Option 1:",
        "doctor.cmd.option2": "Option 2:",
        # Prompts (step-style CLI)
        "prompts.setup_title": "Cpolar Connect Setup",
        "prompts.step_auth": "Authenticating",
        "prompts.step_tunnel": "Fetching tunnel",
        "prompts.step_ssh": "Testing SSH",
        "prompts.step_connect": "Connecting",
        "prompts.step_account": "Step 1: Cpolar Account",
        "prompts.step_server": "Step 2: Server Configuration",
        "prompts.step_options": "Step 3: Connection Options",
        "prompts.tunnel_found": "Found: {url}",
        "prompts.first_connection": "The server does not accept this machine's key yet",
        "prompts.enter_server_password": "Enter password for {user}",
        "prompts.summary_connection": "Connection Summary",
        "prompts.summary_config": "Configuration Summary",
        "prompts.summary_change": "Change Summary",
        "prompts.confirm_connect": "Continue with SSH config update?",
        "prompts.confirm_save": "Save this configuration?",
        "prompts.confirm_change": "Apply this change?",
        "prompts.cancelled": "Operation cancelled",
        "prompts.connected": "Connection established!",
        "prompts.setup_complete": "Configuration complete! Run '{command}' to connect.",
        "prompts.username_set": "Username: {username}",
        "prompts.server_user_set": "Server user: {user}",
        "prompts.ports_set": "Ports: {ports}",
        "prompts.auto_connect_set": "Auto connect: {enabled}",
        "prompts.password_set": "Password saved",
        "prompts.verifying_account": "Verifying account...",
        "prompts.account_verified": "Account verified",
        "prompts.account_invalid": "Verification failed",
        "prompts.network_warning": "Network unavailable, skipping verification",
        "prompts.password_skipped": "Password storage skipped",
        "prompts.config_exists_skip": "Configuration exists, skipping",
        "prompts.yes": "Yes",
        "prompts.no": "No",
        # Summary labels
        "label.host": "Host",
        "label.user": "User",
        "label.alias": "Alias",
        "label.ports": "Ports",
        "label.username": "Username",
        "label.password": "Password",
        "label.server_user": "Server User",
        "label.auto_connect": "Auto Connect",
        "label.current": "Current",
        "label.new": "New",
        "label.key": "Key",
        "ssh.connection_ok": "SSH connection OK",
    }

    # Chinese messages
    ZH = {
        # 通用
        "welcome": "欢迎使用 Cpolar Connect",
        "version": "版本",
        "help": "帮助",
        # 认证
        "auth.csrf_token": "正在获取 CSRF 令牌...",
        "auth.logging_in": "正在以 {username} 身份登录...",
        "auth.login_success": "成功登录 cpolar",
        "auth.login_failed": "登录失败，请检查用户名和密码。",
        "auth.password_required": "未找到密码。请设置 CPOLAR_PASSWORD 环境变量或运行 'cpolar-connect -a {account} init' 存储密码",
        "auth.logout": "已从 cpolar 登出",
        # 隧道
        "tunnel.fetching": "正在获取隧道信息...",
        "tunnel.found": "找到隧道：{url}",
        "tunnel.not_found": "未找到活动隧道。请确保服务器上 cpolar 正在运行。",
        "tunnel.server_hint": "请在服务器上执行：",
        "tunnel.parsing_error": "解析隧道信息失败",
        # SSH
        "ssh.generating_key": "正在生成 SSH 密钥对...",
        "ssh.key_generated": "SSH 密钥对已生成：{path}",
        "ssh.key_exists": "SSH 密钥已存在：{path}",
        "ssh.uploading_key": "正在上传公钥到服务器...",
        "ssh.need_password_for_key_upload": "需要密码来上传 SSH 密钥到服务器",
        "ssh.trying_connect": "正在尝试以 {username}@{hostname} 进行 SSH 连接...",
        "ssh.testing_connection": "正在测试 SSH 连接...",
        "ssh.key_uploaded": "公钥上传成功",
        "ssh.trying_existing_keys": "正在尝试已有 SSH 密钥（agent/默认密钥）...",
        "ssh.existing_keys_failed": "已有密钥未被接受，需要输入服务器密码",
        "ssh.key_uploaded_via_existing": "已通过已有 SSH 密钥安装公钥",
        "ssh.updating_config": "正在更新 SSH 配置...",
        "ssh.config_updated": "SSH 配置已更新",
        "ssh.connecting": "正在通过 SSH 连接服务器...",
        "ssh.connected": "已连接到服务器",
        "ssh.connection_failed": "SSH 连接失败：{error}",
        # CLI
        "cli.initializing": "正在初始化 Cpolar Connect...",
        "cli.config_exists": "配置已存在。使用 --force 覆盖。",
        "cli.enter_username": "请输入 cpolar 用户名",
        "cli.enter_password": "请输入 cpolar 密码",
        "cli.enter_server_user": "请输入服务器用户名",
        "cli.enter_ssh_alias": "请输入 SSH 别名",
        "cli.enter_ports": "请输入要转发的端口（逗号分隔）",
        "cli.auto_connect": "更新后自动连接？",
        "cli.basic_configuration": "基础配置",
        "cli.connecting_server": "正在连接服务器...",
        "cli.no_config": "未找到配置。请先运行 'cpolar-connect -a {account} init'。",
        "cli.config_created": "配置创建成功",
        "cli.config_updated": "配置已更新：{key} = {value}",
        "cli.config_unset": "配置已清除：{key}",
        "cli.config_saved_path": "配置已保存到：{path}",
        # Status
        "status.title": "Cpolar 状态",
        "status.mode.remote": "在线",
        "status.mode.local": "离线（仅本地）",
        "status.auth_missing": "缺少密码，仅展示本地配置",
        "status.auth_failed": "认证失败，仅展示本地配置：{error}",
        "status.network_failed": "网络异常，仅展示本地配置：{error}",
        "status.tunnel.unknown": "未知（未认证）",
        # Status table
        "status.column.field": "字段",
        "status.column.value": "值",
        "status.field.tunnel": "隧道",
        "status.field.tunnel_name": "隧道名称",
        "status.field.host": "主机",
        "status.field.port": "端口",
        "status.field.ssh_alias": "SSH 别名",
        "status.field.ssh_key": "SSH 密钥",
        "status.field.auto_connect": "自动连接",
        "status.field.forward_ports": "转发端口",
        # 配置
        "config.loading": "正在加载配置...",
        "config.saving": "正在保存配置...",
        "config.saved": "配置已保存",
        "config.invalid": "配置无效：{error}",
        # 配置显示
        "config.title": "Cpolar Connect 配置",
        "config.column_setting": "设置项",
        "config.column_value": "值",
        "config.username": "用户名",
        "config.base_url": "基础 URL",
        "config.tunnel_name": "隧道名称",
        "config.tunnel_name_auto": "自动（第一条 SSH 隧道）",
        "config.value_unset": "（未设置）",
        "config.server_user": "服务器用户",
        "config.ports": "端口",
        "config.auto_connect": "自动连接",
        "config.ssh_key_path": "SSH 密钥路径",
        "config.ssh_host_alias": "SSH 主机别名",
        "config.ssh_key_size": "SSH 密钥大小",
        "config.log_level": "日志级别",
        "config.language": "语言",
        "config.password_status": "密码状态",
        "config.config_dir": "配置目录",
        "config.config_file": "配置文件",
        "config.logs_dir": "日志目录",
        "config.password_env": "已存储（环境变量）",
        "config.password_file": "已存储（.password 文件）",
        "config.password_none": "未存储",
        # 错误
        "error.network": "网络错误：{error}",
        "error.auth": "认证错误：{error}",
        "error.tunnel": "隧道错误：{error}",
        "error.ssh": "SSH 错误：{error}",
        "error.config": "配置错误：{error}",
        "error.unknown": "未知错误：{error}",
        "error.connection_failed": "连接失败：{error}",
        "error.session_expired": "会话已过期，请重新认证。",
        "error.csrf_token_empty": "CSRF 令牌为空",
        "error.csrf_token_not_found": "无法找到 CSRF 令牌。登录页面结构可能已更改。",
        "error.invalid_port": "无效端口：{port}。必须在 1-65535 之间",
        "error.invalid_key_size": "SSH 密钥大小必须至少为 1024 位",
        "error.invalid_log_level": "无效的日志级别：{level}",
        "error.invalid_language": "无效的语言：{lang}。必须是 'zh' 或 'en'",
        "error.config_not_found": "未找到配置文件：{path}",
        "error.config_invalid_json": "配置文件中的 JSON 无效：{error}",
        "error.config_load_failed": "加载配置失败：{error}",
        "error.config_save_failed": "保存配置失败：{error}",
        "error.config_create_failed": "创建配置失败：{error}",
        "error.config_key_not_found": "配置键 '{key}' 未找到",
        "error.config_key_required": "'{key}' 是必需的配置项，不能清除。如需修改：cpolar-connect -a {account} config set {key} <值>",
        "error.config_edit_failed": "打开编辑器失败：{error}",
        "error.editor_not_found": "未找到编辑器 '{editor}'。请设置 EDITOR 环境变量。",
        "error.ssh_dir_failed": "无法创建 SSH 目录：{error}",
        "error.ssh_key_gen_failed": "生成 SSH 密钥失败：{error}",
        "error.ssh_pubkey_regen_failed": "重新生成公钥失败：{error}",
        "error.ssh_pubkey_not_found": "未找到公钥：{path}",
        "error.ssh_pubkey_invalid": "公钥文件 {path} 不是有效的公钥。可以删除它，工具会根据私钥重新生成",
        "error.ssh_upload_failed": "上传公钥失败：{error}",
        "error.ssh_remote_timeout": "安装公钥时服务器停止响应（{seconds} 秒内没有回应）。请检查连接后重新运行",
        "error.reason_connection_closed": "服务器关闭了连接",
        "error.ssh_connect_failed": "连接失败：{error}",
        "error.ssh_auth_failed": "建立 SSH 密钥认证失败",
        "error.ssh_auth_failed_detail": "SSH 认证失败：用户 '{username}' 在主机 {hostname} 上认证失败",
        "error.ssh_unreachable": "无法连接到 {hostname}:{port} 上的 SSH 服务：{error}。请确认服务器上的 sshd 正在运行，且 cpolar 隧道指向 SSH 端口",
        "error.ssh_handshake_failed": "与 {hostname}:{port} 的 SSH 握手失败：{error}。请确认服务器上的 sshd 正在运行，且 cpolar 隧道指向它的 SSH 端口",
        "error.ssh_host_unresolved": "本机无法解析隧道域名 {hostname}（{error}）。这是当前网络的 DNS 问题，与服务器无关；有些网络不解析隧道域名。请更换网络或 DNS 服务器，或在 hosts 文件中为该域名指定地址",
        "error.ssh_key_load_failed": "无法读取 SSH 私钥 {path}：{error}",
        "error.ssh_key_passphrase": "SSH 私钥 {path} 设有口令，无法使用。请将 ssh.key_path 指向一把没有口令的密钥",
        "error.ssh_key_unsupported": "{path} 不是可用的 SSH 私钥（需要无口令的 RSA、Ed25519 或 ECDSA 密钥）",
        "error.ssh_key_too_open": "SSH 私钥 {path} 可以被其他用户读取（权限 {mode}），ssh 会拒绝使用这样的密钥。请改为仅本人可读写：{command}",
        "error.ssh_key_path_empty": "ssh.key_path 不能为空",
        "error.ssh_key_pkcs8_ed25519": "{path} 是 PKCS#8 格式（BEGIN PRIVATE KEY）的 Ed25519 密钥，多数版本的 ssh 无法读取。请改用 ssh-keygen 生成的密钥",
        "error.tunnel_name_not_found": "未找到名为 '{name}' 的在线 TCP 隧道。当前在线的 TCP 隧道：{available}",
        "hint.set_tunnel_name_command": "cpolar-connect -a {account} config set tunnel.name <隧道名>",
        "hint.tunnel_name_wrong": "如果是隧道名写错了，请改成上面列出的名称之一：{command}",
        "hint.tunnel_machine_down": "如果是那台机器没开机或 cpolar 没有运行，请在那台机器上执行：",
        "hint.check_username_password": "请检查：1) 服务器用户名是否正确（在服务器运行 'whoami' 查看），2) 密码是否正确",
        "error.tunnel_url_invalid": "无效的隧道 URL 格式：{url}",
        "error.password_clear_failed": "清除密码失败：{error}",
        "error.hostkey_clear_failed": "清除主机密钥失败：{error}",
        "error.invalid_account_name": "无效的账户名：'{name}'。仅允许字母、数字、'.'、'_'、'-'（最长 64 字符）",
        "error.account_not_found": "账户 '{name}' 不存在",
        "error.host_key_changed": "服务器主机密钥已变更！可能存在中间人攻击。",
        "hint.host_key_changed_auto_tunnel": "该账户没有设置 tunnel.name，每次取控制台上列出的第一条 SSH 隧道，这次是 '{tunnel}'。如果有多台机器共用这个 cpolar 账号，这条隧道可能只是通向了另一台机器；如果是这样，请指定要连接的那一条：{command}",
        "hint.host_key_changed": "如果你重装过服务器，或让该账户改连了另一台机器（例如修改了 tunnel.name），请清除已记录的主机密钥后重试：cpolar-connect -a {account} config clear-hostkey",
        "hint.address_recorded": "SSH 配置仍已更新为隧道的当前地址（Host {alias}）",
        "error.known_hosts_unusable": "无法读取或更新主机密钥文件 {path}：{error}。请修复或删除该文件后重试（删除后会重新记录服务器密钥）",
        "error.ssh_config_unusable": "无法读取或更新 SSH 配置文件 {path}：{error}",
        "error.ssh_remote_command_failed": "远程命令执行失败（{command}）：{error}",
        "error.ssh_pubkey_mismatch": "公钥文件 {path} 与私钥 {key} 不匹配。删除该文件后会根据私钥重新生成",
        "error.ssh_connection_lost": "与 {hostname}:{port} 的连接在认证过程中中断：{error}。请重试",
        "error.ssh_password_login_unavailable": "服务器不接受密码登录（它只提供：{methods}）",
        "hint.password_login_unavailable": "在这台服务器上无法用密码安装公钥。请让该账户改用服务器已接受的密钥：cpolar-connect -a {account} config set ssh.key_path <私钥路径>；或者手动把 {public_key} 里的那一行加到服务器上该账户的 authorized_keys 文件，然后重新运行",
        "error.password_store_failed": "存储密码失败：{error}",
        # 警告
        "warning.config_exists": "配置已存在，是否覆盖？",
        "warning.no_password": "未找到存储的密码",
        "warning.no_hostkey": "未找到存储的服务器主机密钥",
        "warning.ssh_key_exists": "公钥已存在于 authorized_keys 中",
        "warning.ssh_auth_failed": "SSH 密钥认证失败，正在上传公钥...",
        "warning.connection_interrupted": "用户中断连接",
        "warning.first_connection": "首次连接 - 需要上传 SSH 密钥",
        "warning.ssh_key_missing": "{path} 处没有密钥文件：下次连接时会在该路径生成一对新的 RSA 密钥。如果想使用已有密钥，请检查路径",
        "warning.multiple_ssh_tunnels": "该 cpolar 账号下有多条 SSH 隧道，已使用第一条 '{chosen}'（另有：{others}）。如需指定：{command}",
        "warning.multiple_tcp_tunnels": "该 cpolar 账号下没有指向本地 22 端口的隧道，已使用第一条 TCP 隧道 '{chosen}'（另有：{others}）。如需指定：{command}",
        "warning.duplicate_tunnel_name": "有 {count} 条隧道都叫 '{name}'，已使用第一条（{url}）。tunnel.name 无法区分同名隧道，请在其中一台机器的 cpolar 配置里给隧道换个名字",
        "warning.tunnel_changed_hostkey": "该账户已记录了服务器主机密钥。如果隧道现在指向另一台机器，请先清除：cpolar-connect -a {account} config clear-hostkey（否则下次连接会提示主机密钥已变更）",
        "warning.config_cancelled": "配置初始化已取消",
        "warning.config_exists_skip": "配置已存在，跳过。使用 --force 覆盖。",
        "warning.invalid_port_format": "无效的端口格式",
        # 信息/提示
        "info.password_cleared": "密码已清除",
        "info.hostkey_cleared": "已清除存储的服务器主机密钥",
        "info.account_switched": "已切换到账户 '{name}'",
        "info.available_accounts": "现有账户：{names}",
        "info.no_accounts": "尚无账户。请先运行 'cpolar-connect init'",
        "account.removed": "账户 '{name}' 已删除",
        "account.confirm_remove": "删除账户 '{name}' 及其密码与主机密钥记录？",
        "account.list_title": "Cpolar Connect 账户",
        "account.column.name": "账户",
        "account.column.username": "用户名",
        "account.column.alias": "SSH 别名",
        "account.column.current": "当前",
        "error.alias_conflict": "SSH 别名 '{alias}' 已被账户 '{other}' 占用",
        "hint.alias_conflict": "两个账户不能共用同一个别名。请给其中一个换个别名：cpolar-connect -a {account} config set ssh.host_alias <别名>",
        "warning.hostblock_cleanup_skipped": "无法清理 SSH 配置块：{error}",
        "config.account": "账户",
        "status.field.account": "账户",
        "info.config_opened": "配置文件已在编辑器中打开",
        "info.run_init": "运行 'cpolar-connect -a {account} init' 创建配置",
        "info.env_password_tip": "您也可以设置 CPOLAR_PASSWORD 环境变量",
        "info.init_kept_settings": "已保留该账户的其他设置（如 tunnel.name、ssh.key_path），可用 'cpolar-connect -a {account} config show' 查看",
        # 诊断工具
        "doctor.title": "诊断结果",
        "doctor.running": "正在运行诊断...",
        "doctor.column.check": "检查项",
        "doctor.column.status": "状态",
        "doctor.column.message": "详情",
        "doctor.summary.title": "总结",
        "doctor.summary.all_good": "所有检查通过！可以连接。",
        "doctor.summary.has_warnings": "发现一些警告，但应该仍可工作。",
        "doctor.summary.has_errors": "发现严重问题。请先修复后再连接。",
        "doctor.recommendations": "建议",
        # 诊断检查项
        "doctor.check.config": "配置文件",
        "doctor.check.username": "Cpolar 用户名",
        "doctor.check.server_user": "服务器用户名",
        "doctor.check.password": "密码存储",
        "doctor.check.network": "网络连接",
        "doctor.check.cpolar_auth": "Cpolar 认证",
        "doctor.check.tunnel": "隧道状态",
        "doctor.check.tunnel_selection": "隧道选择",
        "doctor.check.tunnel_name": "隧道名称",
        "doctor.check.tunnel_dns": "隧道域名解析",
        "doctor.recommend.pick_tunnel": "按 cpolar 控制台上的隧道名称，为该账户指定隧道",
        "doctor.check.ssh_key": "SSH 私钥",
        "doctor.check.ssh_pubkey": "SSH 公钥",
        "doctor.check.ssh_config": "SSH 配置",
        "doctor.check.ssh_command": "SSH 命令",
        # 诊断消息
        "doctor.config.not_found": "未找到配置。运行 'cpolar-connect -a {account} init'",
        "doctor.config.no_username": "未配置 Cpolar 用户名",
        "doctor.config.no_server_user": "未配置服务器用户名",
        "doctor.config.valid": "配置有效",
        "doctor.password.found": "密码已存储在 .password 文件中",
        "doctor.password.env": "在环境变量中找到密码",
        "doctor.password.not_found": "未配置密码。请设置 CPOLAR_PASSWORD 或运行 'cpolar-connect -a {account} init'",
        "doctor.password.env_multi_account": "CPOLAR_PASSWORD 对所有账户生效；各账户密码不同时请勿使用",
        "doctor.network.ok": "网络连接正常",
        "doctor.network.timeout": "连接超时 - 检查互联网连接",
        "doctor.network.http_error": "HTTP 错误 {status}",
        "doctor.network.error": "网络错误：{error}",
        "doctor.cpolar.no_password": "没有密码无法测试认证",
        "doctor.cpolar.auth_success": "成功认证 cpolar",
        "doctor.cpolar.auth_failed": "认证失败：{error}",
        "doctor.tunnel.found": "找到活动隧道：{url}",
        "doctor.tunnel.not_found": "没有活动隧道（服务器可能需要运行 cpolar）",
        "doctor.tunnel_dns.ok": "{hostname} 在当前网络可以解析",
        "doctor.tunnel_dns.failed": "{hostname} 在当前网络无法解析（{error}）",
        "doctor.ssh.key_exists": "SSH 密钥存在",
        "doctor.ssh.key_will_create": "首次连接时将创建 SSH 密钥",
        "doctor.ssh.key_permission": "SSH 密钥权限错误：{mode}（应为 600）",
        "doctor.ssh.pubkey_exists": "SSH 公钥存在",
        "doctor.ssh.pubkey_missing": "SSH 公钥缺失（将重新生成）",
        "doctor.ssh.config_exists": "SSH 配置项存在",
        "doctor.ssh.config_will_update": "连接时将更新 SSH 配置",
        "doctor.ssh.config_will_create": "连接时将创建 SSH 配置",
        "doctor.check.hostkey": "服务器主机密钥",
        "doctor.hostkey.recorded": "已记录主机密钥（每次连接时校验）",
        "doctor.hostkey.none": "首次连接时将自动记录",
        "doctor.command.found": "命令 '{command}' 可用",
        "doctor.command.not_found": "命令 '{command}' 未找到",
        # 诊断建议
        "doctor.recommend.run_init": "初始化配置",
        "doctor.recommend.set_password": "设置 cpolar 认证密码",
        "doctor.recommend.check_network": "检查网络连接",
        "doctor.recommend.check_credentials": "验证 cpolar 凭据",
        "doctor.recommend.check_server": "检查服务器上的 cpolar 服务",
        "doctor.recommend.tunnel_dns": "当前网络的 DNS 不解析隧道域名，因此在这里无法连接，与服务器无关。请更换网络或 DNS 服务器，或在 hosts 文件中为该域名指定地址",
        # 诊断命令示例
        "doctor.cmd.init": "cpolar-connect -a {account} init",
        "doctor.cmd.password.win": "set CPOLAR_PASSWORD=你的密码",
        "doctor.cmd.password.unix": "export CPOLAR_PASSWORD=你的密码",
        "doctor.cmd.password.save": "cpolar-connect -a {account} init  # 永久保存密码",
        "doctor.cmd.network.ping": "ping cpolar.com",
        "doctor.cmd.network.curl": "curl -I https://dashboard.cpolar.com",
        "doctor.cmd.network.check": "检查防火墙/代理设置",
        "doctor.cmd.auth.check1": "1. 用户名应该是您的邮箱",
        "doctor.cmd.auth.check2": "2. 尝试在 https://dashboard.cpolar.com 登录",
        "doctor.cmd.auth.check3": "3. 如需要，重置密码",
        "doctor.cmd.server.status": "sudo systemctl status cpolar",
        "doctor.cmd.server.start": "sudo systemctl start cpolar   # 如果未运行",
        "doctor.cmd.server.tunnel": "cpolar tcp 22                 # 启动 SSH 隧道",
        "doctor.cmd.option1": "方式1:",
        "doctor.cmd.option2": "方式2:",
        # 步骤式 CLI 提示
        "prompts.setup_title": "Cpolar Connect 配置向导",
        "prompts.step_auth": "正在认证",
        "prompts.step_tunnel": "获取隧道",
        "prompts.step_ssh": "测试 SSH",
        "prompts.step_connect": "正在连接",
        "prompts.step_account": "步骤 1: Cpolar 账户",
        "prompts.step_server": "步骤 2: 服务器配置",
        "prompts.step_options": "步骤 3: 连接选项",
        "prompts.tunnel_found": "找到: {url}",
        "prompts.first_connection": "服务器还没有接受本机的密钥",
        "prompts.enter_server_password": "请输入 {user} 的密码",
        "prompts.summary_connection": "连接摘要",
        "prompts.summary_config": "配置摘要",
        "prompts.summary_change": "变更摘要",
        "prompts.confirm_connect": "是否继续更新 SSH 配置？",
        "prompts.confirm_save": "是否保存此配置？",
        "prompts.confirm_change": "是否应用此变更？",
        "prompts.cancelled": "操作已取消",
        "prompts.connected": "连接已建立！",
        "prompts.setup_complete": "配置完成！运行 '{command}' 开始连接。",
        "prompts.username_set": "用户名: {username}",
        "prompts.server_user_set": "服务器用户: {user}",
        "prompts.ports_set": "端口: {ports}",
        "prompts.auto_connect_set": "自动连接: {enabled}",
        "prompts.password_set": "密码已保存",
        "prompts.verifying_account": "正在验证账户...",
        "prompts.account_verified": "账户验证成功",
        "prompts.account_invalid": "验证失败",
        "prompts.network_warning": "网络不可用，跳过验证",
        "prompts.password_skipped": "已跳过密码存储",
        "prompts.config_exists_skip": "配置已存在，跳过",
        "prompts.yes": "是",
        "prompts.no": "否",
        # Summary labels
        "label.host": "主机",
        "label.user": "用户",
        "label.alias": "别名",
        "label.ports": "端口",
        "label.username": "用户名",
        "label.password": "密码",
        "label.server_user": "服务器用户",
        "label.auto_connect": "自动连接",
        "label.current": "当前值",
        "label.new": "新值",
        "label.key": "键",
        "ssh.connection_ok": "SSH 连接正常",
    }


class I18n:
    """Internationalization manager"""

    def __init__(self, language: Optional[Language] = None):
        """
        Initialize i18n with specified language

        Args:
            language: Language to use, auto-detect if None
        """
        if language is None:
            language = self._detect_language()

        self.language = language
        self.messages = self._get_messages(language)

    def _detect_language(self) -> Language:
        """
        Auto-detect language from environment

        Priority:
        1. CPOLAR_LANG environment variable
        2. LANG environment variable
        3. Default to Chinese
        """
        # Check CPOLAR_LANG first (only zh/en)
        cpolar_lang = os.environ.get("CPOLAR_LANG", "").lower()
        if cpolar_lang == "en":
            return Language.EN
        elif cpolar_lang == "zh":
            return Language.ZH

        # Check system LANG
        system_lang = os.environ.get("LANG", "").lower()
        if "zh" in system_lang:
            return Language.ZH
        elif "en" in system_lang:
            return Language.EN

        # Default to Chinese for Chinese users
        return Language.ZH

    def _get_messages(self, language: Language) -> Dict[str, str]:
        """Get messages for specified language"""
        if language == Language.EN:
            return Messages.EN
        elif language == Language.ZH:
            return Messages.ZH
        else:
            return Messages.ZH  # Default

    def get(self, message_key: str, **kwargs) -> str:
        """
        Get translated message

        Args:
            message_key: Message key (e.g., 'auth.login_success')
            **kwargs: Format parameters

        Returns:
            Translated and formatted message
        """
        message = self.messages.get(message_key, message_key)

        # Format message with parameters
        if kwargs:
            try:
                message = message.format(**kwargs)
            except KeyError as e:
                # If formatting fails, return message with error indication
                message = f"{message} [Format error: {e}]"

        return message

    def set_language(self, language: Language) -> None:
        """
        Change language at runtime

        Args:
            language: New language to use
        """
        self.language = language
        self.messages = self._get_messages(language)

    @classmethod
    def load_from_config(cls, config_path: Optional[Path] = None) -> "I18n":
        """
        Load language preference with priority: env > config > default

        Priority:
            1. CPOLAR_LANG environment variable (highest)
            2. Config file language setting
            3. Default (Chinese)

        Args:
            config_path: Path to config file

        Returns:
            I18n instance with configured language
        """
        # 1. Check environment variable first (highest priority)
        cpolar_lang = os.environ.get("CPOLAR_LANG", "").lower()
        if cpolar_lang == "en":
            return cls(Language.EN)
        elif cpolar_lang == "zh":
            return cls(Language.ZH)

        # 2. Read from config file: current account > default account >
        #    legacy pre-migration root path (no import of config module
        #    to avoid a circular dependency)
        if config_path is None:
            root = Path.home() / ".cpolar_connect"
            account = None
            current_file = root / "current"
            if current_file.exists():
                try:
                    account = current_file.read_text(encoding="utf-8").strip() or None
                except OSError:
                    account = None
            candidates = []
            if account:
                candidates.append(root / "accounts" / account / "config.json")
            candidates.append(root / "accounts" / "default" / "config.json")
            candidates.append(root / "config.json")  # legacy layout
            config_path = next((c for c in candidates if c.exists()), candidates[-1])

        language = None
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    lang_str = config.get("language", "").lower()
                    if lang_str in ["en", "english"]:
                        language = Language.EN
                    elif lang_str in ["zh", "chinese", "cn"]:
                        language = Language.ZH
            except Exception:
                pass

        return cls(language)


# Global i18n instance
_i18n: Optional[I18n] = None


def get_i18n() -> I18n:
    """Get or create global i18n instance"""
    global _i18n
    if _i18n is None:
        _i18n = I18n.load_from_config()
    return _i18n


def set_language(language: Language) -> None:
    """Set global language"""
    i18n = get_i18n()
    i18n.set_language(language)


def _(message_key: str, **kwargs) -> str:
    """
    Shortcut for getting translated message

    Usage:
        from cpolar_connect.i18n import _
        print(_('auth.login_success'))
        print(_('auth.logging_in', username='user@example.com'))
    """
    i18n = get_i18n()
    return i18n.get(message_key, **kwargs)
