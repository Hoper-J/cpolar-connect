"""
Diagnostic tool for Cpolar Connect
"""

import os
import socket
import subprocess
from pathlib import Path
import shutil
from typing import Dict, List, Tuple, Optional
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .config import ConfigManager, ConfigError
from .auth import CpolarAuth
from .tunnel import TunnelManager
from .i18n import _
from .exceptions import AuthenticationError, NetworkError, TunnelError

console = Console()


class Doctor:
    """Diagnose connection problems"""
    
    def __init__(self):
        """Initialize doctor"""
        self.config_manager = ConfigManager()
        self.checks: List[Tuple[str, bool, str]] = []
        self.has_error = False
        self.has_warning = False
    
    def add_check(self, name: str, passed: bool, message: str = "", level: str = "error"):
        """Add a check result"""
        self.checks.append((name, passed, message, level))
        if not passed:
            if level == "error":
                self.has_error = True
            elif level == "warning":
                self.has_warning = True
    
    def check_config(self) -> bool:
        """Check configuration"""
        try:
            if not self.config_manager.config_exists():
                self.add_check(
                    _('doctor.check.config'),
                    False,
                    _('doctor.config.not_found')
                )
                return False
            
            config = self.config_manager.get_config()
            
            # Check required fields
            if not config.username:
                self.add_check(
                    _('doctor.check.username'),
                    False,
                    _('doctor.config.no_username')
                )
                return False
            
            if not config.server_user:
                self.add_check(
                    _('doctor.check.server_user'),
                    False,
                    _('doctor.config.no_server_user')
                )
                return False
            
            self.add_check(
                _('doctor.check.config'),
                True,
                _('doctor.config.valid')
            )
            return True
            
        except Exception as e:
            self.add_check(
                _('doctor.check.config'),
                False,
                str(e)
            )
            return False
    
    def check_password(self) -> bool:
        """Check password availability"""
        try:
            config = self.config_manager.get_config()
            password = self.config_manager.get_password(config.username)
            
            if password:
                self.add_check(
                    _('doctor.check.password'),
                    True,
                    _('doctor.password.found')
                )
                return True
            else:
                # Check environment variable
                if os.environ.get('CPOLAR_PASSWORD'):
                    self.add_check(
                        _('doctor.check.password'),
                        True,
                        _('doctor.password.env')
                    )
                    return True
                else:
                    self.add_check(
                        _('doctor.check.password'),
                        False,
                        _('doctor.password.not_found'),
                        level="warning"
                    )
                    return False
        except Exception as e:
            self.add_check(
                _('doctor.check.password'),
                False,
                str(e)
            )
            return False
    
    def check_network(self) -> bool:
        """Check network connectivity"""
        try:
            # Check cpolar.com
            response = requests.get('https://www.cpolar.com', timeout=5)
            if response.status_code == 200:
                self.add_check(
                    _('doctor.check.network'),
                    True,
                    _('doctor.network.ok')
                )
                return True
            else:
                self.add_check(
                    _('doctor.check.network'),
                    False,
                    _('doctor.network.http_error', status=response.status_code),
                    level="warning"
                )
                return False
        except requests.exceptions.Timeout:
            self.add_check(
                _('doctor.check.network'),
                False,
                _('doctor.network.timeout')
            )
            return False
        except Exception as e:
            self.add_check(
                _('doctor.check.network'),
                False,
                _('doctor.network.error', error=str(e))
            )
            return False
    
    def check_cpolar_auth(self) -> bool:
        """Check cpolar authentication"""
        try:
            config = self.config_manager.get_config()
            password = self.config_manager.get_password(config.username)
            
            if not password:
                password = os.environ.get('CPOLAR_PASSWORD')
                
            if not password:
                self.add_check(
                    _('doctor.check.cpolar_auth'),
                    False,
                    _('doctor.cpolar.no_password'),
                    level="warning"
                )
                return False
            
            auth = CpolarAuth(self.config_manager)
            session = auth.login(config.username, password)
            
            self.add_check(
                _('doctor.check.cpolar_auth'),
                True,
                _('doctor.cpolar.auth_success')
            )
            
            # Try to get tunnel info
            tunnel_manager = TunnelManager(session, config.base_url)
            try:
                tunnel_info = tunnel_manager.get_tunnel_info()
                self.add_check(
                    _('doctor.check.tunnel'),
                    True,
                    _('doctor.tunnel.found', url=tunnel_info.url)
                )
            except TunnelError:
                self.add_check(
                    _('doctor.check.tunnel'),
                    False,
                    _('doctor.tunnel.not_found'),
                    level="warning"
                )
            
            return True
            
        except AuthenticationError as e:
            self.add_check(
                _('doctor.check.cpolar_auth'),
                False,
                _('doctor.cpolar.auth_failed', error=str(e))
            )
            return False
        except Exception as e:
            self.add_check(
                _('doctor.check.cpolar_auth'),
                False,
                str(e)
            )
            return False
    
    def check_ssh_key(self) -> bool:
        """Check SSH key"""
        try:
            config = self.config_manager.get_config()
            ssh_key_path = Path(config.ssh_key_path).expanduser()
            
            if ssh_key_path.exists():
                # Check permissions
                stat_info = ssh_key_path.stat()
                mode = oct(stat_info.st_mode)[-3:]
                
                if mode != '600':
                    self.add_check(
                        _('doctor.check.ssh_key'),
                        False,
                        _('doctor.ssh.key_permission', mode=mode),
                        level="warning"
                    )
                else:
                    self.add_check(
                        _('doctor.check.ssh_key'),
                        True,
                        _('doctor.ssh.key_exists')
                    )
                
                # Check public key
                pub_key_path = ssh_key_path.with_suffix(ssh_key_path.suffix + '.pub')
                if not pub_key_path.exists():
                    self.add_check(
                        _('doctor.check.ssh_pubkey'),
                        False,
                        _('doctor.ssh.pubkey_missing'),
                        level="warning"
                    )
                else:
                    self.add_check(
                        _('doctor.check.ssh_pubkey'),
                        True,
                        _('doctor.ssh.pubkey_exists')
                    )
                
                return True
            else:
                self.add_check(
                    _('doctor.check.ssh_key'),
                    True,
                    _('doctor.ssh.key_will_create')
                )
                return True
                
        except Exception as e:
            self.add_check(
                _('doctor.check.ssh_key'),
                False,
                str(e)
            )
            return False
    
    def check_ssh_config(self) -> bool:
        """Check SSH config"""
        try:
            ssh_config_path = Path.home() / '.ssh' / 'config'
            
            if ssh_config_path.exists():
                config = self.config_manager.get_config()
                with open(ssh_config_path, 'r') as f:
                    content = f.read()
                    if config.ssh_host_alias in content:
                        self.add_check(
                            _('doctor.check.ssh_config'),
                            True,
                            _('doctor.ssh.config_exists')
                        )
                    else:
                        self.add_check(
                            _('doctor.check.ssh_config'),
                            True,
                            _('doctor.ssh.config_will_update')
                        )
            else:
                self.add_check(
                    _('doctor.check.ssh_config'),
                    True,
                    _('doctor.ssh.config_will_create')
                )
            
            return True
            
        except Exception as e:
            self.add_check(
                _('doctor.check.ssh_config'),
                False,
                str(e)
            )
            return False
    
    def check_command(self, command: str, name: str) -> bool:
        """Check if a command exists (cross-platform)"""
        try:
            if shutil.which(command):
                self.add_check(
                    name,
                    True,
                    _('doctor.command.found', command=command)
                )
                return True
            else:
                self.add_check(
                    name,
                    False,
                    _('doctor.command.not_found', command=command),
                    level="warning"
                )
                return False
        except Exception as e:
            self.add_check(
                name,
                False,
                str(e)
            )
            return False
    
    def display_results(self):
        """Display diagnosis results"""
        # Create results table
        table = Table(
            title=_('doctor.title'),
            show_header=True,
            header_style="bold magenta"
        )
        table.add_column(_('doctor.column.check'), style="cyan", width=30)
        table.add_column(_('doctor.column.status'), justify="center", width=10)
        table.add_column(_('doctor.column.message'), style="white")
        
        for name, passed, message, level in self.checks:
            if passed:
                status = "[green]✅ OK[/green]"
            elif level == "warning":
                status = "[yellow]⚠️ WARN[/yellow]"
            else:
                status = "[red]❌ FAIL[/red]"
            
            table.add_row(name, status, message)
        
        console.print("\n")
        console.print(table)
        
        # Show summary
        console.print("\n")
        if self.has_error:
            console.print(Panel.fit(
                _('doctor.summary.has_errors'),
                style="red",
                title=_('doctor.summary.title')
            ))
        elif self.has_warning:
            console.print(Panel.fit(
                _('doctor.summary.has_warnings'),
                style="yellow",
                title=_('doctor.summary.title')
            ))
        else:
            console.print(Panel.fit(
                _('doctor.summary.all_good'),
                style="green",
                title=_('doctor.summary.title')
            ))
        
        # Show recommendations
        if self.has_error or self.has_warning:
            console.print(f"\n[bold]{_('doctor.recommendations')}:[/bold]\n")
            
            # Check specific issues and give recommendations
            shown_recommendations = set()
            for name, passed, message, level in self.checks:
                if not passed:
                    if _('doctor.check.config') in name and 'config' not in shown_recommendations:
                        console.print(f"  [cyan]•[/cyan] {_('doctor.recommend.run_init')}")
                        console.print(f"    [dim]{_('doctor.cmd.init')}[/dim]")
                        shown_recommendations.add('config')
                    elif _('doctor.check.password') in name and 'password' not in shown_recommendations:
                        console.print(f"  [cyan]•[/cyan] {_('doctor.recommend.set_password')}")
                        # Add OS-specific instructions
                        import platform
                        if platform.system() == 'Windows':
                            console.print(f"    [dim]{_('doctor.cmd.option1')} {_('doctor.cmd.password.win')}[/dim]")
                        else:
                            console.print(f"    [dim]{_('doctor.cmd.option1')} {_('doctor.cmd.password.unix')}[/dim]")
                        console.print(f"    [dim]{_('doctor.cmd.option2')} {_('doctor.cmd.password.save')}[/dim]")
                        shown_recommendations.add('password')
                    elif _('doctor.check.network') in name and 'network' not in shown_recommendations:
                        console.print(f"  [cyan]•[/cyan] {_('doctor.recommend.check_network')}")
                        console.print(f"    [dim]{_('doctor.cmd.network.ping')}[/dim]")
                        console.print(f"    [dim]{_('doctor.cmd.network.curl')}[/dim]")
                        console.print(f"    [dim]{_('doctor.cmd.network.check')}[/dim]")
                        shown_recommendations.add('network')
                    elif _('doctor.check.cpolar_auth') in name and 'auth' not in shown_recommendations:
                        console.print(f"  [cyan]•[/cyan] {_('doctor.recommend.check_credentials')}")
                        console.print(f"    [dim]{_('doctor.cmd.auth.check1')}[/dim]")
                        console.print(f"    [dim]{_('doctor.cmd.auth.check2')}[/dim]")
                        console.print(f"    [dim]{_('doctor.cmd.auth.check3')}[/dim]")
                        shown_recommendations.add('auth')
                    elif _('doctor.check.tunnel') in name and 'tunnel' not in shown_recommendations:
                        console.print(f"  [cyan]•[/cyan] {_('doctor.recommend.check_server')}")
                        console.print(f"    [dim]{_('doctor.cmd.server.status')}[/dim]")
                        console.print(f"    [dim]{_('doctor.cmd.server.start')}[/dim]")
                        console.print(f"    [dim]{_('doctor.cmd.server.tunnel')}[/dim]")
                        shown_recommendations.add('tunnel')
    
    def run(self) -> bool:
        """Run all diagnostics"""
        console.print(f"[bold cyan]{_('doctor.running')}[/bold cyan]\n")
        
        # Run checks
        self.check_config()
        if self.config_manager.config_exists():
            self.check_password()
            self.check_network()
            self.check_ssh_key()
            self.check_ssh_config()
            self.check_command('ssh', _('doctor.check.ssh_command'))
            
            # Only check cpolar auth if password is available
            if self.config_manager.get_config() and (
                self.config_manager.get_password(self.config_manager.get_config().username) or
                os.environ.get('CPOLAR_PASSWORD')
            ):
                self.check_cpolar_auth()
        
        # Display results
        self.display_results()
        
        return not self.has_error
