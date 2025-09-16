#!/usr/bin/env python3
"""
Cpolar Connect - CLI Entry Point
"""

import click
import logging
from logging.handlers import RotatingFileHandler
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
import sys
import os
from getpass import getpass

from .config import ConfigManager, ConfigError
from .exceptions import AuthenticationError, TunnelError, SSHError, NetworkError
from .auth import CpolarAuth
from .tunnel import TunnelManager
from .ssh import SSHManager
from .i18n import _, get_i18n, Language
from . import __version__

console = Console()

def _setup_logging(config_manager: ConfigManager):
    """Configure rotating file logging under ~/.cpolar_connect/logs.

    Priority for level: env CPOLAR_LOG_LEVEL > config.log_level > INFO
    """
    # Avoid duplicate handlers if CLI is re-entered
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return

    level_name = os.environ.get("CPOLAR_LOG_LEVEL")
    level = None
    if level_name:
        level = getattr(logging, level_name.upper(), logging.INFO)
    else:
        try:
            cfg = config_manager.get_config()
            level = getattr(logging, cfg.log_level.upper(), logging.INFO)
        except Exception:
            level = logging.INFO

    log_path = config_manager.logs_path / "cpolar.log"
    handler = RotatingFileHandler(str(log_path), maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    root.setLevel(level)
    root.addHandler(handler)


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx):
    """🚀 Manage cpolar tunnels and SSH / 管理 cpolar 隧道与 SSH"""
    ctx.ensure_object(dict)
    ctx.obj['config_manager'] = ConfigManager()
    # Configure logging as early as possible
    _setup_logging(ctx.obj['config_manager'])
    
    # If no command is provided, run the default action (connect)
    if ctx.invoked_subcommand is None:
        # Default behavior: update and connect
        config_manager = ctx.obj['config_manager']
        
        if not config_manager.config_exists():
            console.print(f"[yellow]⚠️ {_('cli.no_config')}[/yellow]")
            sys.exit(1)
        
        try:
            config = config_manager.get_config()
            console.print(f"[cyan]🔗 {_('cli.connecting_server')}[/cyan]")
            
            # Check password availability
            password = config_manager.get_password(config.username)
            if not password:
                console.print(f"[yellow]⚠️ {_('auth.password_required')}[/yellow]")
                sys.exit(1)
            
            # Execute full connection flow
            try:
                # 1. Authenticate with cpolar
                with console.status(f"[yellow]{_('auth.csrf_token')}[/yellow]"):
                    auth = CpolarAuth(config_manager)
                    session = auth.login()
                
                # 2. Get tunnel information  
                with console.status(f"[yellow]{_('tunnel.fetching')}[/yellow]"):
                    tunnel_manager = TunnelManager(session, config.base_url)
                    tunnel_info = tunnel_manager.get_tunnel_info()
                
                # 3. Test SSH connection
                ssh_manager = SSHManager(config)
                
                with console.status(f"[yellow]{_('ssh.testing_connection')}[/yellow]"):
                    can_connect = ssh_manager.test_ssh_connection(tunnel_info.hostname, tunnel_info.port)
                
                # 4. Get server password if needed (outside of status context)
                server_password = None
                if not can_connect:
                    console.print(f"\n[yellow]{_('warning.first_connection')}[/yellow]")
                    # Stop status before getting password input
                    server_password = getpass(f"Enter password for {config.server_user}@{tunnel_info.hostname}: ")
                
                # 5. Setup and connect
                ssh_manager.setup_and_connect(tunnel_info, server_password)
                
            except (AuthenticationError, TunnelError, SSHError, NetworkError) as e:
                console.print(f"[red]❌ {_('error.connection_failed', error=e)}[/red]")
                sys.exit(1)
            finally:
                # Clean logout
                if 'auth' in locals():
                    auth.logout()
            
        except ConfigError as e:
            console.print(f"[red]❌ {_('error.config', error=e)}[/red]")
            sys.exit(1)

@cli.command()
@click.option('--force', '-f', is_flag=True, help='Overwrite existing configuration / 覆盖现有配置')
@click.pass_context
def init(ctx, force):
    """🔧 Initialize configuration / 初始化配置"""
    config_manager = ctx.obj['config_manager']
    
    if config_manager.config_exists() and not force:
        if not Confirm.ask(_('warning.config_exists')):
            console.print(f"[yellow]{_('warning.config_cancelled')}[/yellow]")
            return
    
    console.print(Panel.fit("🔧 [bold]Cpolar Connect Setup[/bold]", border_style="blue"))
    
    # Collect basic configuration
    console.print(f"\n[bold cyan]{_('cli.basic_configuration')}[/bold cyan]")
    
    username = Prompt.ask(_('cli.enter_username'))
    server_user = Prompt.ask(_('cli.enter_server_user')) 
    
    # Parse ports
    ports_input = Prompt.ask(_('cli.enter_ports'), default="8888,6666")
    try:
        ports = [int(p.strip()) for p in ports_input.split(',')]
    except ValueError:
        console.print(f"[red]❌ {_('warning.invalid_port_format')}[/red]")
        sys.exit(1)
    
    auto_connect = Confirm.ask(_("cli.auto_connect"), default=True)
    
    # Create configuration
    config_data = {
        'username': username,
        'server_user': server_user,
        'ports': ports,
        'auto_connect': auto_connect
    }
    
    try:
        config_manager.create_config(config_data)
        console.print(f"\n[green]{_('cli.config_created')}[/green]")
        console.print(f"📁 { _('cli.config_saved_path', path=config_manager.config_path)}")
        
        # Prompt for password storage
        store_password = Confirm.ask(_('cli.store_password'), default=True)
        if store_password:
            password = getpass(f"{_('cli.enter_password')}: ")
            if password:
                config_manager.set_password(username, password)
        
        console.print(f"\n[yellow]💡 {_('info.env_password_tip')}[/yellow]")
        console.print(f"[yellow]💡 {_('info.config_show_tip')}[/yellow]")
        
    except ConfigError as e:
        console.print(f"[red]❌ {_('error.config_create_failed', error=e)}[/red]")
        sys.exit(1)

# TODO: Implement after creating auth, tunnel, and ssh modules
# @cli.command() 
# def connect():
#     """🔗 Connect to server via SSH"""
#     pass

# @cli.command()
# def update():
#     """🔄 Update tunnel information and SSH configuration"""
#     pass

# @cli.command()
# def status():
#     """📊 Show current tunnel status"""
#     pass

@cli.group()
def config():
    """⚙️ Configuration management / 配置管理"""
    pass

@config.command('get')
@click.argument('key', metavar='KEY')
@click.pass_context
def config_get(ctx, key):
    """🔹 Get configuration value / 读取配置项

    KEY: dot-notation, e.g. `server.user` / 点号路径，如 `server.user`
    """
    config_manager = ctx.obj['config_manager']
    try:
        value = config_manager.get(key)
        console.print(f"[cyan]{key}[/cyan]: [white]{value}[/white]")
    except KeyError:
        console.print(f"[red]❌ {_('error.config_key_not_found', key=key)}[/red]")
        sys.exit(1)
    except ConfigError as e:
        console.print(f"[red]❌ {_('error.config', error=e)}[/red]")
        sys.exit(1)

@config.command('set')
@click.argument('key', metavar='KEY')
@click.argument('value', metavar='VALUE')
@click.pass_context
def config_set(ctx, key, value):
    """🔹 Set configuration value / 写入配置项

    KEY: dot-notation, e.g. `server.ports` / 点号路径，如 `server.ports`
    VALUE: string; ports accept comma list / 字符串；端口可用逗号分隔
    """
    config_manager = ctx.obj['config_manager']
    try:
        config_manager.set(key, value)
        console.print(f"[green]{_('cli.config_updated', key=key, value=value)}[/green]")
    except ConfigError as e:
        console.print(f"[red]❌ {_('error.config', error=e)}[/red]")
        sys.exit(1)

@config.command('edit')
@click.pass_context
def config_edit(ctx):
    """🔹 Edit configuration file / 编辑配置文件"""
    config_manager = ctx.obj['config_manager']
    try:
        config_manager.edit()
        console.print(f"[green]✅ {_('info.config_opened')}[/green]")
    except ConfigError as e:
        console.print(f"[red]❌ {_('error.config_edit_failed', error=e)}[/red]")
        sys.exit(1)

@config.command('show')
@click.pass_context
def config_show(ctx):
    """🔹 Show current configuration / 显示当前配置"""
    config_manager = ctx.obj['config_manager']
    try:
        config_manager.display()
    except ConfigError as e:
        console.print(f"[red]❌ {_('error.config', error=e)}[/red]")
        console.print(f"[yellow]💡 {_('info.run_init')}[/yellow]")
        sys.exit(1)

@config.command('path')
@click.pass_context  
def config_path(ctx):
    """🔹 Show config and logs path / 显示配置与日志路径"""
    config_manager = ctx.obj['config_manager']
    console.print(f"📁 Config file: [cyan]{config_manager.config_path}[/cyan]")
    console.print(f"📁 Logs directory: [cyan]{config_manager.logs_path}[/cyan]")

@config.command('clear-password')
@click.pass_context
def config_clear_password(ctx):
    """🔹 Clear stored password / 清除已存密码"""
    config_manager = ctx.obj['config_manager']
    try:
        config = config_manager.get_config()
        config_manager.clear_password(config.username)
    except ConfigError as e:
        console.print(f"[red]❌ {_('error.config', error=e)}[/red]")
        sys.exit(1)

@cli.command('language')
@click.argument('lang', metavar='LANG', type=click.Choice(['zh', 'en']))
@click.pass_context
def set_language(ctx, lang):
    """🌏 Set interface language / 设置界面语言

    LANG: zh/en / 语言：zh/en
    """
    config_manager = ctx.obj['config_manager']
    
    # Normalize language code
    lang_code = 'zh' if lang == 'zh' else 'en'
    lang_name = '中文' if lang_code == 'zh' else 'English'
    
    try:
        # Load config
        config = config_manager.get_config()
        
        # Update language
        config.language = lang_code
        config_manager.save_config(config)
        
        # Apply immediately
        from .i18n import set_language, Language
        set_language(Language.ZH if lang_code == 'zh' else Language.EN)
        
        # Show success message in new language
        if lang_code == 'zh':
            console.print(f"[green]✅ 界面语言已设置为 {lang_name}[/green]")
            console.print("[dim]重新运行命令以使用新语言[/dim]")
        else:
            console.print(f"[green]✅ Interface language set to {lang_name}[/green]")
            console.print("[dim]Restart the command to use the new language[/dim]")
            
    except ConfigError as e:
        console.print(f"[red]❌ {_('error.config', error=e)}[/red]")
        sys.exit(1)

@cli.command('doctor')
@click.pass_context
def doctor_cmd(ctx):
    """🏥 Diagnose connection issues / 诊断连接问题"""
    from .doctor import Doctor
    
    doctor = Doctor()
    success = doctor.run()
    
    if not success:
        sys.exit(1)


@cli.command('status')
@click.pass_context
def status_cmd(ctx):
    """📊 Show tunnel & SSH status (no connection) / 显示隧道与 SSH 状态（不连接）"""
    from rich.table import Table
    from rich.panel import Panel
    config_manager: ConfigManager = ctx.obj['config_manager']

    if not config_manager.config_exists():
        console.print(f"[yellow]⚠️ {_('cli.no_config')}[/yellow]")
        sys.exit(1)

    def _render(config, tunnel_info=None, local_only=False, reason_msg: str | None = None):
        mode = _('status.mode.remote') if not local_only else _('status.mode.local')
        title = _('status.title')
        if reason_msg and local_only:
            console.print(Panel.fit(reason_msg, style="yellow", title=title))
        else:
            console.print(Panel.fit(mode, style=("green" if not local_only else "yellow"), title=title))

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Field", style="cyan", width=22)
        table.add_column("Value", style="white")
        if tunnel_info is not None:
            table.add_row("Tunnel", getattr(tunnel_info, 'url', ''))
            table.add_row("Host", getattr(tunnel_info, 'hostname', ''))
            table.add_row("Port", str(getattr(tunnel_info, 'port', '')))
        else:
            table.add_row("Tunnel", _('status.tunnel.unknown'))
            table.add_row("Host", "-")
            table.add_row("Port", "-")
        table.add_row("SSH Alias", config.ssh_host_alias)
        table.add_row("SSH Key", os.path.expanduser(config.ssh_key_path))
        table.add_row("Auto Connect", "Yes" if config.auto_connect else "No")
        table.add_row("Forward Ports", ",".join(str(p) for p in config.ports))
        console.print(table)

    try:
        config = config_manager.get_config()
        password = config_manager.get_password(config.username)
        if not password:
            # 无密码：离线展示
            _render(config, tunnel_info=None, local_only=True, reason_msg=_('status.auth_missing'))
            return

        # 有密码：尝试在线获取
        auth = CpolarAuth(config_manager)
        try:
            with console.status(f"[yellow]{_('auth.csrf_token')}[/yellow]"):
                session = auth.login()
            with console.status(f"[yellow]{_('tunnel.fetching')}[/yellow]"):
                tunnel_info = TunnelManager(session, config.base_url).get_tunnel_info()
            _render(config, tunnel_info=tunnel_info, local_only=False)
        except AuthenticationError as e:
            _render(config, tunnel_info=None, local_only=True, reason_msg=_('status.auth_failed', error=str(e)))
        except (TunnelError, NetworkError) as e:
            _render(config, tunnel_info=None, local_only=True, reason_msg=_('status.network_failed', error=str(e)))
        finally:
            try:
                auth.logout()
            except Exception:
                pass

    except ConfigError as e:
        console.print(f"[red]❌ {_('error.config', error=e)}[/red]")
        sys.exit(1)

def main():
    """Entry point for the CLI"""
    cli()

if __name__ == '__main__':
    main()
