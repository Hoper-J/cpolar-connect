#!/usr/bin/env python3
"""
Cpolar Connect - CLI Entry Point
"""

import click
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

console = Console()

@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0")
@click.pass_context
def cli(ctx):
    """🚀 Cpolar Connect - Easy cpolar tunnel management and SSH connections"""
    ctx.ensure_object(dict)
    ctx.obj['config_manager'] = ConfigManager()
    
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
                with console.status("[yellow]Authenticating with cpolar...[/yellow]"):
                    auth = CpolarAuth(config_manager)
                    session = auth.login()
                
                # 2. Get tunnel information  
                with console.status("[yellow]Fetching tunnel information...[/yellow]"):
                    tunnel_manager = TunnelManager(session, config.base_url)
                    tunnel_info = tunnel_manager.get_tunnel_info()
                
                # 3. Test SSH connection
                ssh_manager = SSHManager(config)
                
                with console.status("[yellow]Testing SSH connection...[/yellow]"):
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
@click.option('--force', '-f', is_flag=True, help='Overwrite existing configuration')
@click.pass_context
def init(ctx, force):
    """🔧 Initialize configuration file"""
    config_manager = ctx.obj['config_manager']
    
    if config_manager.config_exists() and not force:
        if not Confirm.ask(_('warning.config_exists')):
            console.print(f"[yellow]{_('warning.config_cancelled')}[/yellow]")
            return
    
    console.print(Panel.fit("🔧 [bold]Cpolar Connect Setup[/bold]", border_style="blue"))
    
    # Collect basic configuration
    console.print("\n[bold cyan]Basic Configuration[/bold cyan]")
    
    username = Prompt.ask(_('cli.enter_username'))
    server_user = Prompt.ask(_('cli.enter_server_user')) 
    
    # Parse ports
    ports_input = Prompt.ask(_('cli.enter_ports'), default="8888,6666")
    try:
        ports = [int(p.strip()) for p in ports_input.split(',')]
    except ValueError:
        console.print(f"[red]❌ {_('warning.invalid_port_format')}[/red]")
        sys.exit(1)
    
    auto_connect = Confirm.ask("Auto-connect after update?", default=True)
    
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
        console.print(f"📁 Configuration saved to: {config_manager.config_path}")
        
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
    """⚙️ Configuration management"""
    pass

@config.command('get')
@click.argument('key')
@click.pass_context
def config_get(ctx, key):
    """Get configuration value"""
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
@click.argument('key')
@click.argument('value')
@click.pass_context
def config_set(ctx, key, value):
    """Set configuration value"""
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
    """Edit configuration file in default editor"""
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
    """Show current configuration"""
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
    """Show configuration file path"""
    config_manager = ctx.obj['config_manager']
    console.print(f"📁 Config file: [cyan]{config_manager.config_path}[/cyan]")
    console.print(f"📁 Logs directory: [cyan]{config_manager.logs_path}[/cyan]")

@config.command('clear-password')
@click.pass_context
def config_clear_password(ctx):
    """Clear stored password from keyring"""
    config_manager = ctx.obj['config_manager']
    try:
        config = config_manager.get_config()
        config_manager.clear_password(config.username)
    except ConfigError as e:
        console.print(f"[red]❌ {_('error.config', error=e)}[/red]")
        sys.exit(1)

@cli.command('language')
@click.argument('lang', type=click.Choice(['zh', 'en', 'chinese', 'english']))
@click.pass_context
def set_language(ctx, lang):
    """Set interface language / 设置界面语言
    
    Examples:
        cpolar-connect language zh      # 设置中文
        cpolar-connect language en      # Set English
    """
    config_manager = ctx.obj['config_manager']
    
    # Normalize language code
    if lang in ['chinese', 'zh']:
        lang_code = 'zh'
        lang_name = '中文'
    else:
        lang_code = 'en'
        lang_name = 'English'
    
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
    """🏥 Diagnose connection problems / 诊断连接问题
    
    This command checks:
    - Configuration validity
    - Network connectivity  
    - Cpolar authentication
    - SSH setup
    - Active tunnels
    
    Use this when you have connection issues.
    """
    from .doctor import Doctor
    
    doctor = Doctor()
    success = doctor.run()
    
    if not success:
        sys.exit(1)

def main():
    """Entry point for the CLI"""
    cli()

if __name__ == '__main__':
    main()