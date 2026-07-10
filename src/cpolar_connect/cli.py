#!/usr/bin/env python3
"""
Cpolar Connect - CLI Entry Point
"""

import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from . import __version__
from .auth import CpolarAuth
from .config import (
    DEFAULT_ACCOUNT,
    ConfigError,
    ConfigManager,
    read_current_account,
    resolve_account,
    validate_account_name,
    write_current_account,
)
from .exceptions import (
    AuthenticationError,
    NetworkError,
    SSHError,
    TunnelError,
    TunnelNotFoundError,
)
from .i18n import _
from .prompts import Prompts
from .ssh import SSHManager
from .tunnel import TunnelManager

console = Console()


def _display_width(text: str) -> int:
    """Calculate display width considering CJK characters"""
    width = 0
    for char in text:
        # CJK Unified Ideographs range
        if "\u4e00" <= char <= "\u9fff":
            width += 2
        # CJK Extension A
        elif "\u3400" <= char <= "\u4dbf":
            width += 2
        # Fullwidth ASCII variants
        elif "\uff00" <= char <= "\uffef":
            width += 2
        else:
            width += 1
    return width


def _pad_label(label: str, target_width: int) -> str:
    """Pad label to target display width"""
    current_width = _display_width(label)
    padding = target_width - current_width
    return label + " " * max(0, padding)


def _setup_logging(config_manager: Optional[ConfigManager] = None):
    """Configure rotating file logging under ~/.cpolar_connect/logs.

    Priority for level: env CPOLAR_LOG_LEVEL > config.log_level > INFO.
    Runs before account resolution, so config_manager is usually None;
    _get_config_manager raises the level from config afterwards.
    """
    # Avoid duplicate handlers if CLI is re-entered
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return

    level_name = os.environ.get("CPOLAR_LOG_LEVEL")
    level = logging.INFO
    if level_name:
        level = getattr(logging, level_name.upper(), logging.INFO)
    elif config_manager is not None:
        try:
            cfg = config_manager.get_config()
            level = getattr(logging, cfg.log_level.upper(), logging.INFO)
        except Exception:
            level = logging.INFO

    logs_dir = Path.home() / ".cpolar_connect" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "cpolar.log"
    handler = RotatingFileHandler(
        str(log_path), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    root.setLevel(level)
    root.addHandler(handler)


def _account_callback(ctx, param, value):
    if value is not None:
        # ctx.meta is shared across the context tree, so both spellings
        # (`cpc -a x cmd` and `cpc cmd -a x`) land in the same place
        ctx.meta["account"] = value
    return value


def account_option(f):
    """Register -a/--account on a command; the value lands in ctx.meta.

    click group options must precede the subcommand; registering the same
    option on every command makes both spellings work.
    """
    return click.option(
        "-a",
        "--account",
        expose_value=False,
        callback=_account_callback,
        metavar="NAME",
        help="Use account for this invocation / 本次调用使用指定账户",
    )(f)


def _get_config_manager(ctx) -> ConfigManager:
    """Lazily build the ConfigManager once -a/env/current are resolvable."""
    root = ctx.find_root()
    if root.obj.get("config_manager") is None:
        p: Prompts = root.obj["prompts"]
        try:
            name = resolve_account(ctx.meta.get("account"))
            config_manager = ConfigManager(account=name)
            config_manager.ensure_migrated()
        except ConfigError as e:
            p.log_error(_("error.config", error=e))
            sys.exit(1)
        # Honor the account's configured log level (env var still wins)
        if not os.environ.get("CPOLAR_LOG_LEVEL"):
            try:
                cfg = config_manager.get_config()
                level = getattr(logging, cfg.log_level.upper(), None)
                if level is not None:
                    logging.getLogger().setLevel(level)
            except ConfigError:
                pass
        root.obj["config_manager"] = config_manager
    return root.obj["config_manager"]


def _verify_cpolar_credentials(
    username: str, password: str, base_url: Optional[str] = None
) -> bool:
    """
    Verify cpolar credentials without requiring a saved config.

    Args:
        username: Cpolar username/email
        password: Cpolar password
        base_url: Dashboard base URL (defaults to the official dashboard)

    Returns:
        True if credentials are valid, False otherwise

    Raises:
        NetworkError: If network connection fails
    """
    auth = CpolarAuth(base_url=base_url)
    try:
        auth.login(username=username, password=password)
        return True
    except AuthenticationError:
        return False


def _print_server_hint(p: Prompts) -> None:
    """Tell the user which commands to run on the server to bring up cpolar."""
    p.log_info(_("tunnel.server_hint"))
    for key in (
        "doctor.cmd.server.status",
        "doctor.cmd.server.start",
        "doctor.cmd.server.tunnel",
    ):
        p.log_info(f"  {_(key)}")


def _run_connect(ctx):
    """Run the connection flow with step-style output."""
    config_manager = _get_config_manager(ctx)
    p: Prompts = ctx.obj["prompts"]
    skip_confirm = ctx.obj["skip_confirm"]
    output_format = ctx.obj["output_format"]

    if not config_manager.config_exists():
        p.log_error(_("cli.no_config"))
        sys.exit(1)

    try:
        config = config_manager.get_config()
    except ConfigError as e:
        p.log_error(_("error.config", error=e))
        sys.exit(1)

    # Check password availability
    password = config_manager.get_password(config.username)
    if not password:
        p.log_error(_("auth.password_required"))
        sys.exit(1)

    p.intro(_("cli.connecting_server"))

    auth = None
    try:
        # Step 1: Authenticate
        p.step(_("prompts.step_auth"))
        p.spinner_message(_("auth.csrf_token"))
        auth = CpolarAuth(config_manager)
        session = auth.login()
        p.spinner_done(_("auth.login_success"))

        # Step 2: Get tunnel info
        p.step(_("prompts.step_tunnel"))
        p.spinner_message(_("tunnel.fetching"))
        tunnel_manager = TunnelManager(session, config.base_url)
        tunnel_info = tunnel_manager.get_tunnel_info()
        p.spinner_done(_("prompts.tunnel_found", url=tunnel_info.url))

        # Show connection summary
        ports_str = ", ".join(str(port) for port in config.ports)

        # Calculate max label width for alignment (including colon)
        labels = [
            _("label.host") + ":",
            _("label.user") + ":",
            _("label.alias") + ":",
            _("label.ports") + ":",
        ]
        max_width = max(_display_width(label) for label in labels)

        summary = f"""\
{_pad_label(_('label.host') + ':', max_width)} {tunnel_info.hostname}:{tunnel_info.port}
{_pad_label(_('label.user') + ':', max_width)} {config.server_user}
{_pad_label(_('label.alias') + ':', max_width)} {config.ssh_host_alias}
{_pad_label(_('label.ports') + ':', max_width)} {ports_str}"""
        p.note(summary, _("prompts.summary_connection"))

        # Confirm connection (unless -y or auto_connect is enabled)
        if not skip_confirm and not config.auto_connect:
            if not p.confirm(_("prompts.confirm_connect"), default=True):
                p.outro_cancel(_("prompts.cancelled"))
                return

        # Step 3: Test SSH connection
        p.step(_("prompts.step_ssh"))
        ssh_manager = SSHManager(
            config, known_hosts_path=config_manager.known_hosts_file
        )
        p.spinner_message(_("ssh.testing_connection"))
        can_connect = ssh_manager.test_ssh_connection(
            tunnel_info.hostname, tunnel_info.port
        )

        # Bootstrap key access if needed (first connection)
        server_password = None
        bootstrapped_via_existing = False
        if not can_connect:
            p.spinner_done(_("prompts.first_connection"), success=False)
            p.log_warn(_("warning.first_connection"))

            # Our key pair must exist before any upload attempt
            if ssh_manager.generate_ssh_key():
                p.log_success(_("ssh.key_generated"))

            # Try existing keys (agent/default) before asking for a password
            p.spinner_message(_("ssh.trying_existing_keys"))
            existing_result = ssh_manager.upload_public_key_with_existing_keys(
                tunnel_info.hostname, tunnel_info.port
            )
            if existing_result is not None:
                bootstrapped_via_existing = True
                p.spinner_done(_("ssh.key_uploaded_via_existing"))
            else:
                p.spinner_done(_("ssh.existing_keys_failed"), success=False)
                server_password = p.password(
                    _("prompts.enter_server_password", user=config.server_user)
                )
                if server_password is None:
                    p.outro_cancel(_("prompts.cancelled"))
                    return
        else:
            p.spinner_done(_("ssh.connection_ok"))

        # Step 4: Setup and Connect
        p.step(_("prompts.step_connect"))

        # Generate SSH key if needed
        key_generated = ssh_manager.generate_ssh_key()
        if key_generated:
            p.log_success(_("ssh.key_generated"))
        else:
            p.log_info(_("ssh.key_exists", path=ssh_manager.private_key_path))

        # Upload public key with password (existing keys didn't work)
        if server_password:
            p.spinner_message(_("ssh.uploading_key"))
            key_uploaded = ssh_manager.upload_public_key(
                tunnel_info.hostname, tunnel_info.port, server_password
            )
            if key_uploaded:
                p.spinner_done(_("ssh.key_uploaded"))
            else:
                p.spinner_done(_("warning.ssh_key_exists"))

        # Verify connection after any upload
        if server_password or bootstrapped_via_existing:
            if not ssh_manager.test_ssh_connection(
                tunnel_info.hostname, tunnel_info.port
            ):
                raise SSHError(_("error.ssh_auth_failed"))

        # Update SSH config
        ssh_manager.update_ssh_config(tunnel_info, config.ports)
        p.log_success(_("ssh.config_updated"))

        # Connect if auto_connect is enabled
        if config.auto_connect:
            p.outro(_("prompts.connected"))
            ssh_manager.connect(tunnel_info, config.ports)
        else:
            p.log_info(f"ssh {ssh_manager.host_alias}")
            p.outro(_("prompts.setup_complete"))

    except TunnelNotFoundError as e:
        p.log_error(_("error.connection_failed", error=e))
        _print_server_hint(p)
        sys.exit(1)
    except (AuthenticationError, TunnelError, SSHError, NetworkError) as e:
        p.log_error(_("error.connection_failed", error=e))
        sys.exit(1)
    except ConfigError as e:
        p.log_error(_("error.config", error=e))
        sys.exit(1)
    finally:
        if auth:
            try:
                auth.logout()
            except Exception:
                pass


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, help="Show version / 显示版本")
@click.option(
    "-y", "--yes", is_flag=True, help="Skip confirmation prompts / 跳过确认提示"
)
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format / 输出格式",
)
@click.option("-q", "--quiet", is_flag=True, help="Quiet mode / 静默模式")
@account_option
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def cli(ctx, yes, output_format, quiet):
    """Manage cpolar tunnels and SSH / 管理 cpolar 隧道与 SSH"""
    ctx.ensure_object(dict)
    # Built lazily by _get_config_manager: the subcommand's own -a option
    # is not parsed yet when this callback runs
    ctx.obj["config_manager"] = None
    ctx.obj["skip_confirm"] = yes
    ctx.obj["output_format"] = output_format
    ctx.obj["quiet"] = quiet
    ctx.obj["prompts"] = Prompts(skip_confirm=yes, quiet=quiet)

    # Configure logging as early as possible
    _setup_logging()

    # If no command is provided, run the default action (connect)
    if ctx.invoked_subcommand is None:
        _run_connect(ctx)


@cli.command()
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite existing configuration / 覆盖现有配置",
)
@click.option("--username", help="Cpolar username / Cpolar 用户名")
@click.option("--server-user", help="Server username / 服务器用户名")
@click.option(
    "--ports", help="Ports to forward (comma-separated) / 转发端口（逗号分隔）"
)
@account_option
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def init(ctx, force, username, server_user, ports):
    """Initialize configuration / 初始化配置

    With -a NAME, creates/reinitializes that account and switches to it
    / 配合 -a 可创建新账户并切换过去
    """
    config_manager = _get_config_manager(ctx)
    p: Prompts = ctx.obj["prompts"]
    skip_confirm = ctx.obj["skip_confirm"]

    # Derived alias must be unique across accounts (host key trust model)
    derived_alias = (
        "cpolar-server"
        if config_manager.account == DEFAULT_ACCOUNT
        else f"cpolar-{config_manager.account}"
    )
    conflict = config_manager.find_alias_conflict(derived_alias)
    if conflict:
        p.log_error(_("error.alias_conflict", alias=derived_alias, other=conflict))
        sys.exit(1)
    previous_current = read_current_account() or DEFAULT_ACCOUNT

    # Check existing config
    if config_manager.config_exists() and not force:
        if skip_confirm:
            p.log_warn(_("warning.config_exists_skip"))
            return
        elif not p.confirm(_("warning.config_exists"), default=False):
            p.outro_cancel(_("warning.config_cancelled"))
            return

    p.intro(_("prompts.setup_title"))

    # Respect a custom base_url from an existing config when re-initializing
    base_url = None
    if config_manager.config_exists():
        try:
            base_url = config_manager.get_config().base_url
        except ConfigError:
            base_url = None

    # Step 1: Cpolar Account (username + password + verification)
    p.step(_("prompts.step_account"))

    while True:
        # Get username
        if username:
            p.log_success(_("prompts.username_set", username=username))
        else:
            username = p.text(_("cli.enter_username"), required=True)
            if username is None:
                p.outro_cancel(_("prompts.cancelled"))
                return
            p.log_success(_("prompts.username_set", username=username))

        # Get password
        password = p.password(_("cli.enter_password"))
        if password:
            p.log_success(_("prompts.password_set"))

            # Verify credentials
            p.spinner_message(_("prompts.verifying_account"))
            try:
                verified = _verify_cpolar_credentials(
                    username, password, base_url=base_url
                )
                if verified:
                    p.spinner_done(_("prompts.account_verified"))
                    break
                else:
                    p.spinner_done(_("prompts.account_invalid"), success=False)
                    p.log_error(_("auth.login_failed"))
                    # Reset username to allow re-entry
                    username = None
                    continue
            except NetworkError as e:
                p.spinner_done(_("prompts.network_warning"), success=False)
                p.log_warn(_("error.network", error=str(e)))
                # Network error - allow to continue without verification
                break
        else:
            p.log_info(_("prompts.password_skipped"))
            break

    # Step 2: Server Configuration
    p.step(_("prompts.step_server"))
    if server_user:
        p.log_success(_("prompts.server_user_set", user=server_user))
    else:
        server_user = p.text(_("cli.enter_server_user"), required=True)
        if server_user is None:
            p.outro_cancel(_("prompts.cancelled"))
            return
        p.log_success(_("prompts.server_user_set", user=server_user))

    # Parse ports
    if ports:
        try:
            ports_list = [int(pt.strip()) for pt in ports.split(",")]
        except ValueError:
            p.log_error(_("warning.invalid_port_format"))
            sys.exit(1)
    else:
        while True:
            ports_input = p.text(_("cli.enter_ports"), default="8888,6666")
            if ports_input is None:
                p.outro_cancel(_("prompts.cancelled"))
                return
            try:
                ports_list = [int(pt.strip()) for pt in ports_input.split(",")]
                break
            except ValueError:
                p.log_error(_("warning.invalid_port_format"))
    p.log_success(_("prompts.ports_set", ports=", ".join(str(pt) for pt in ports_list)))

    # Step 3: Connection Options
    p.step(_("prompts.step_options"))
    if skip_confirm:
        auto_connect = True
    else:
        auto_connect = p.confirm(_("cli.auto_connect"), default=True)
    yes_no = _("prompts.yes") if auto_connect else _("prompts.no")
    p.log_success(_("prompts.auto_connect_set", enabled=yes_no))

    # Show summary
    password_status = _("prompts.yes") if password else _("prompts.no")
    labels = [
        _("label.username") + ":",
        _("label.password") + ":",
        _("label.server_user") + ":",
        _("label.ports") + ":",
        _("label.auto_connect") + ":",
    ]
    max_width = max(_display_width(label) for label in labels)

    summary = f"""\
{_pad_label(_('label.username') + ':', max_width)} {username}
{_pad_label(_('label.password') + ':', max_width)} {password_status}
{_pad_label(_('label.server_user') + ':', max_width)} {server_user}
{_pad_label(_('label.ports') + ':', max_width)} {", ".join(str(pt) for pt in ports_list)}
{_pad_label(_('label.auto_connect') + ':', max_width)} {yes_no}"""
    p.note(summary, _("prompts.summary_config"))

    # Create configuration and store password
    config_data = {
        "username": username,
        "server_user": server_user,
        "ports": ports_list,
        "auto_connect": auto_connect,
    }
    if config_manager.account != DEFAULT_ACCOUNT:
        config_data["ssh_host_alias"] = derived_alias

    try:
        config_manager.create_config(config_data)
        if password:
            config_manager.set_password(username, password)

        # A freshly initialized account is almost certainly the one to use
        if config_manager.account != previous_current:
            write_current_account(config_manager.account)
            p.log_success(_("info.account_switched", name=config_manager.account))

        p.log("")
        p.log_info(_("info.env_password_tip"))
        p.log_info(_("cli.config_saved_path", path=config_manager.config_path))

        p.outro(_("prompts.setup_complete"))

    except ConfigError as e:
        p.log_error(_("error.config_create_failed", error=e))
        sys.exit(1)


@cli.group()
@click.help_option("--help", "-h", help="Show help / 显示帮助")
def config():
    """Configuration management / 配置管理"""
    pass


@config.command("get")
@click.argument("key", metavar="KEY")
@account_option
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def config_get(ctx, key):
    """Get configuration value / 读取配置项

    KEY: dot-notation, e.g. `server.user` / 点号路径，如 `server.user`
    """
    config_manager = _get_config_manager(ctx)
    p: Prompts = ctx.obj["prompts"]
    try:
        value = config_manager.get(key)
        p.log(f"{key}: {value}")
    except KeyError:
        p.log_error(_("error.config_key_not_found", key=key))
        sys.exit(1)
    except ConfigError as e:
        p.log_error(_("error.config", error=e))
        sys.exit(1)


@config.command("set")
@click.argument("key", metavar="KEY")
@click.argument("value", metavar="VALUE")
@account_option
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def config_set(ctx, key, value):
    """Set configuration value / 写入配置项

    KEY: dot-notation, e.g. `server.ports` / 点号路径，如 `server.ports`
    VALUE: string; ports accept comma list / 字符串；端口可用逗号分隔
    """
    config_manager = _get_config_manager(ctx)
    p: Prompts = ctx.obj["prompts"]
    skip_confirm = ctx.obj["skip_confirm"]

    try:
        # Get current value for comparison
        try:
            current_value = config_manager.get(key)
        except (KeyError, ConfigError):
            current_value = "(not set)"

        # Show change summary
        if not skip_confirm:
            labels = [
                _("label.key") + ":",
                _("label.current") + ":",
                _("label.new") + ":",
            ]
            max_width = max(_display_width(label) for label in labels)

            summary = f"""\
{_pad_label(_('label.key') + ':', max_width)} {key}
{_pad_label(_('label.current') + ':', max_width)} {current_value}
{_pad_label(_('label.new') + ':', max_width)} {value}"""
            p.note(summary, _("prompts.summary_change"))

            if not p.confirm(_("prompts.confirm_change"), default=True):
                p.outro_cancel(_("prompts.cancelled"))
                return

        config_manager.set(key, value)
        p.log_success(_("cli.config_updated", key=key, value=value))
    except KeyError:
        p.log_error(_("error.config_key_not_found", key=key))
        sys.exit(1)
    except ConfigError as e:
        p.log_error(_("error.config", error=e))
        sys.exit(1)


@config.command("edit")
@account_option
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def config_edit(ctx):
    """Edit configuration file / 编辑配置文件"""
    config_manager = _get_config_manager(ctx)
    p: Prompts = ctx.obj["prompts"]
    try:
        config_manager.edit()
        p.log_success(_("info.config_opened"))
    except ConfigError as e:
        p.log_error(_("error.config_edit_failed", error=e))
        sys.exit(1)


@config.command("show")
@account_option
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def config_show(ctx):
    """Show current configuration / 显示当前配置"""
    config_manager = _get_config_manager(ctx)
    output_format = ctx.obj["output_format"]
    p: Prompts = ctx.obj["prompts"]

    try:
        data = config_manager.get_display_data()

        if output_format == "json":
            print(json.dumps(data, indent=2))
        else:
            from rich.table import Table

            table = Table(
                title=_("config.title"), show_header=True, header_style="bold magenta"
            )
            table.add_column(_("config.column_setting"), style="cyan", width=20)
            table.add_column(_("config.column_value"), style="white")

            # Add rows
            yes_no = _("prompts.yes") if data["auto_connect"] else _("prompts.no")
            lang_display = (
                _("config.language")
                + ": "
                + ("中文" if data["language"] == "zh" else "English")
            )

            table.add_row(_("config.account"), config_manager.account)
            table.add_row(_("config.username"), data["username"])
            table.add_row(_("config.base_url"), data["base_url"])
            table.add_row(_("config.server_user"), data["server_user"])
            table.add_row(_("config.ports"), ", ".join(str(p) for p in data["ports"]))
            table.add_row(_("config.auto_connect"), yes_no)
            table.add_row(_("config.ssh_key_path"), data["ssh_key_path"])
            table.add_row(_("config.ssh_host_alias"), data["ssh_host_alias"])
            table.add_row(_("config.ssh_key_size"), f"{data['ssh_key_size']} bits")
            table.add_row(_("config.log_level"), data["log_level"])
            table.add_row(
                _("config.language"), "中文" if data["language"] == "zh" else "English"
            )

            console.print(table)

            # Password status
            status_key = f"config.password_{data['password_status']}"
            console.print(f"\n{_('config.password_status')}: {_(status_key)}")
            console.print(f"{_('config.config_dir')}: {data['config_dir']}")

    except ConfigError as e:
        p.log_error(_("error.config", error=e))
        p.log_info(_("info.run_init"))
        sys.exit(1)


@config.command("path")
@account_option
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def config_path(ctx):
    """Show config and logs path / 显示配置与日志路径"""
    config_manager = _get_config_manager(ctx)
    p: Prompts = ctx.obj["prompts"]
    p.log(f"{_('config.config_file')}: {config_manager.config_path}")
    p.log(f"{_('config.logs_dir')}: {config_manager.logs_path}")


@config.command("clear-password")
@account_option
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def config_clear_password(ctx):
    """Clear stored password / 清除已存密码"""
    config_manager = _get_config_manager(ctx)
    p: Prompts = ctx.obj["prompts"]
    try:
        config = config_manager.get_config()
        cleared = config_manager.clear_password(config.username)
        if cleared:
            p.log_success(_("info.password_cleared"))
        else:
            p.log_warn(_("warning.no_password"))
    except ConfigError as e:
        p.log_error(_("error.config", error=e))
        sys.exit(1)


@config.command("clear-hostkey")
@account_option
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def config_clear_hostkey(ctx):
    """Clear stored server host key / 清除已存的服务器主机密钥"""
    config_manager = _get_config_manager(ctx)
    p: Prompts = ctx.obj["prompts"]
    try:
        cleared = config_manager.clear_host_keys()
        if cleared:
            p.log_success(_("info.hostkey_cleared"))
        else:
            p.log_warn(_("warning.no_hostkey"))
    except ConfigError as e:
        p.log_error(_("error.config", error=e))
        sys.exit(1)


@cli.command("use")
@click.argument("name", metavar="NAME")
@account_option
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def use_account(ctx, name):
    """Switch current account / 切换当前账户"""
    p: Prompts = ctx.obj["prompts"]
    try:
        validate_account_name(name)
        config_manager = ConfigManager()
        config_manager.ensure_migrated()
        accounts = {a["name"] for a in config_manager.list_accounts()}
        if name not in accounts:
            p.log_error(_("error.account_not_found", name=name))
            if accounts:
                p.log_info(
                    _("info.available_accounts", names=", ".join(sorted(accounts)))
                )
            sys.exit(1)
        write_current_account(name)
        p.log_success(_("info.account_switched", name=name))
    except ConfigError as e:
        p.log_error(_("error.config", error=e))
        sys.exit(1)


@cli.group("account")
@click.help_option("--help", "-h", help="Show help / 显示帮助")
def account_group():
    """Account management / 账户管理"""
    pass


@account_group.command("list")
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def account_list(ctx):
    """List accounts / 列出账户"""
    output_format = ctx.obj["output_format"]
    p: Prompts = ctx.obj["prompts"]
    config_manager = ConfigManager()
    config_manager.ensure_migrated()
    accounts = config_manager.list_accounts()

    if output_format == "json":
        print(json.dumps(accounts, indent=2))
        return

    if not accounts:
        p.log_info(_("info.no_accounts"))
        return

    from rich.table import Table

    table = Table(
        title=_("account.list_title"), show_header=True, header_style="bold magenta"
    )
    table.add_column(_("account.column.name"), style="cyan")
    table.add_column(_("account.column.username"), style="white")
    table.add_column(_("account.column.alias"), style="white")
    table.add_column(_("account.column.current"), justify="center")
    for info in accounts:
        table.add_row(
            info["name"],
            info["username"],
            info["ssh_host_alias"],
            "✓" if info["is_current"] else "",
        )
    console.print(table)


# `use` lives at top level; give its natural companion the same treatment
cli.add_command(account_list, "list")


@account_group.command("remove")
@click.argument("name", metavar="NAME")
@click.option(
    "-y", "--yes", "yes_flag", is_flag=True, help="Skip confirmation / 跳过确认"
)
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def account_remove(ctx, name, yes_flag):
    """Remove an account / 删除账户"""
    p: Prompts = ctx.obj["prompts"]
    skip = yes_flag or ctx.obj["skip_confirm"]
    try:
        validate_account_name(name)
        config_manager = ConfigManager()
        config_manager.ensure_migrated()
        existing = {a["name"] for a in config_manager.list_accounts()}
        if name not in existing:
            p.log_error(_("error.account_not_found", name=name))
            sys.exit(1)

        if not skip and not p.confirm(
            _("account.confirm_remove", name=name), default=False
        ):
            p.outro_cancel(_("prompts.cancelled"))
            return

        # Clean the account's Host block before its config disappears
        try:
            account_cm = ConfigManager(account=name)
            cfg = account_cm.get_config()
            SSHManager(
                cfg, known_hosts_path=account_cm.known_hosts_file
            ).remove_host_block()
        except (ConfigError, SSHError) as e:
            p.log_warn(_("warning.hostblock_cleanup_skipped", error=e))

        config_manager.remove_account(name)

        # Fall back if the current account was removed
        if (read_current_account() or DEFAULT_ACCOUNT) == name:
            if (config_manager.accounts_dir / DEFAULT_ACCOUNT).is_dir():
                write_current_account(DEFAULT_ACCOUNT)
            else:
                current_file = config_manager.config_dir / "current"
                if current_file.exists():
                    current_file.unlink()

        p.log_success(_("account.removed", name=name))
    except ConfigError as e:
        p.log_error(_("error.config", error=e))
        sys.exit(1)


@cli.command("language")
@click.argument("lang", metavar="LANG", type=click.Choice(["zh", "en"]))
@account_option
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def set_language(ctx, lang):
    """Set interface language / 设置界面语言

    LANG: zh/en / 语言：zh/en
    """
    config_manager = _get_config_manager(ctx)
    p: Prompts = ctx.obj["prompts"]

    # Normalize language code
    lang_code = "zh" if lang == "zh" else "en"
    lang_name = "中文" if lang_code == "zh" else "English"

    try:
        # Load config
        config = config_manager.get_config()

        # Update language
        config.language = lang_code
        config_manager.save_config(config)

        # Apply immediately
        from .i18n import Language, set_language

        set_language(Language.ZH if lang_code == "zh" else Language.EN)

        # Show success message in new language
        if lang_code == "zh":
            p.log_success(f"界面语言已设置为 {lang_name}")
            p.log_info("重新运行命令以使用新语言")
        else:
            p.log_success(f"Interface language set to {lang_name}")
            p.log_info("Restart the command to use the new language")

    except ConfigError as e:
        p.log_error(_("error.config", error=e))
        sys.exit(1)


@cli.command("doctor")
@account_option
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def doctor_cmd(ctx):
    """Diagnose connection issues / 诊断连接问题"""
    from .doctor import Doctor

    doctor = Doctor(config_manager=_get_config_manager(ctx))
    success = doctor.run()

    if not success:
        sys.exit(1)


@cli.command("status")
@account_option
@click.help_option("--help", "-h", help="Show help / 显示帮助")
@click.pass_context
def status_cmd(ctx):
    """Show tunnel & SSH status (no connection) / 显示隧道与 SSH 状态（不连接）"""
    from rich.panel import Panel
    from rich.table import Table

    config_manager: ConfigManager = _get_config_manager(ctx)
    p: Prompts = ctx.obj["prompts"]
    output_format = ctx.obj["output_format"]

    if not config_manager.config_exists():
        if output_format == "json":
            print(json.dumps({"error": "config_not_found"}))
        else:
            p.log_warn(_("cli.no_config"))
        sys.exit(1)

    def _output_json(config, tunnel_info=None, online=False, error=None):
        """Output status as JSON"""
        data = {
            "status": "online" if online else "offline",
            "account": config_manager.account,
            "tunnel": None,
            "config": {
                "username": config.username,
                "server_user": config.server_user,
                "ssh_alias": config.ssh_host_alias,
                "ssh_key": os.path.expanduser(config.ssh_key_path),
                "auto_connect": config.auto_connect,
                "ports": config.ports,
            },
        }
        if tunnel_info:
            data["tunnel"] = {
                "url": tunnel_info.url,
                "hostname": tunnel_info.hostname,
                "port": tunnel_info.port,
            }
        if error:
            data["error"] = str(error)
        print(json.dumps(data, indent=2))

    def _render(
        config, tunnel_info=None, local_only=False, reason_msg: Optional[str] = None
    ):
        mode = _("status.mode.remote") if not local_only else _("status.mode.local")
        title = _("status.title")
        if reason_msg and local_only:
            console.print(Panel.fit(reason_msg, style="yellow", title=title))
        else:
            console.print(
                Panel.fit(
                    mode, style=("green" if not local_only else "yellow"), title=title
                )
            )

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column(_("status.column.field"), style="cyan", width=22)
        table.add_column(_("status.column.value"), style="white")
        table.add_row(_("status.field.account"), config_manager.account)
        if tunnel_info is not None:
            table.add_row(_("status.field.tunnel"), getattr(tunnel_info, "url", ""))
            table.add_row(_("status.field.host"), getattr(tunnel_info, "hostname", ""))
            table.add_row(_("status.field.port"), str(getattr(tunnel_info, "port", "")))
        else:
            table.add_row(_("status.field.tunnel"), _("status.tunnel.unknown"))
            table.add_row(_("status.field.host"), "-")
            table.add_row(_("status.field.port"), "-")
        table.add_row(_("status.field.ssh_alias"), config.ssh_host_alias)
        table.add_row(
            _("status.field.ssh_key"), os.path.expanduser(config.ssh_key_path)
        )
        yes_no = _("prompts.yes") if config.auto_connect else _("prompts.no")
        table.add_row(_("status.field.auto_connect"), yes_no)
        table.add_row(
            _("status.field.forward_ports"), ",".join(str(p) for p in config.ports)
        )
        console.print(table)

    try:
        config = config_manager.get_config()
        password = config_manager.get_password(config.username)
        if not password:
            # 无密码：离线展示
            if output_format == "json":
                _output_json(config, online=False, error="auth_missing")
            else:
                _render(
                    config,
                    tunnel_info=None,
                    local_only=True,
                    reason_msg=_("status.auth_missing"),
                )
            return

        # 有密码：尝试在线获取
        auth = CpolarAuth(config_manager)
        try:
            if output_format != "json":
                with console.status(f"[yellow]{_('auth.csrf_token')}[/yellow]"):
                    session = auth.login()
                with console.status(f"[yellow]{_('tunnel.fetching')}[/yellow]"):
                    tunnel_info = TunnelManager(
                        session, config.base_url
                    ).get_tunnel_info()
            else:
                session = auth.login()
                tunnel_info = TunnelManager(session, config.base_url).get_tunnel_info()

            if output_format == "json":
                _output_json(config, tunnel_info=tunnel_info, online=True)
            else:
                _render(config, tunnel_info=tunnel_info, local_only=False)
        except AuthenticationError as e:
            if output_format == "json":
                _output_json(config, online=False, error=f"auth_failed: {e}")
            else:
                _render(
                    config,
                    tunnel_info=None,
                    local_only=True,
                    reason_msg=_("status.auth_failed", error=str(e)),
                )
        except TunnelNotFoundError as e:
            if output_format == "json":
                _output_json(config, online=False, error=f"tunnel_not_found: {e}")
            else:
                _render(config, tunnel_info=None, local_only=True, reason_msg=str(e))
                _print_server_hint(p)
        except (TunnelError, NetworkError) as e:
            if output_format == "json":
                _output_json(config, online=False, error=f"network_failed: {e}")
            else:
                _render(
                    config,
                    tunnel_info=None,
                    local_only=True,
                    reason_msg=_("status.network_failed", error=str(e)),
                )
        finally:
            try:
                auth.logout()
            except Exception:
                pass

    except ConfigError as e:
        if output_format == "json":
            print(json.dumps({"error": str(e)}))
        else:
            p.log_error(_("error.config", error=e))
        sys.exit(1)


def main():
    """Entry point for the CLI"""
    cli()


if __name__ == "__main__":
    main()
