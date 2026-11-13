"""
Diagnostic tool for Cpolar Connect
"""

import os
import platform
import shutil
import socket
from pathlib import Path
from typing import List, Tuple

import requests
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from .auth import CpolarAuth
from .config import ConfigManager
from .exceptions import (
    AuthenticationError,
    SSHError,
    TunnelError,
    TunnelNameNotFoundError,
)
from .i18n import _
from .ssh import load_private_key
from .tunnel import TunnelInfo, TunnelManager, selection_warnings

console = Console()


class Doctor:
    """Diagnose connection problems"""

    def __init__(self, config_manager=None):
        """Initialize doctor with the (account-resolved) config manager"""
        self.config_manager = config_manager or ConfigManager()
        self.checks: List[Tuple[str, bool, str, str]] = []
        self.has_error = False
        self.has_warning = False

    def add_check(
        self, name: str, passed: bool, message: str = "", level: str = "error"
    ):
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
                    _("doctor.check.config"),
                    False,
                    _("doctor.config.not_found", account=self.config_manager.account),
                )
                return False

            config = self.config_manager.get_config()

            # Check required fields
            if not config.username:
                self.add_check(
                    _("doctor.check.username"), False, _("doctor.config.no_username")
                )
                return False

            if not config.server_user:
                self.add_check(
                    _("doctor.check.server_user"),
                    False,
                    _("doctor.config.no_server_user"),
                )
                return False

            self.add_check(_("doctor.check.config"), True, _("doctor.config.valid"))
            return True

        except Exception as e:
            self.add_check(_("doctor.check.config"), False, str(e))
            return False

    def check_password(self) -> bool:
        """Check password availability"""
        try:
            config = self.config_manager.get_config()
            password = self.config_manager.get_password(config.username)

            if password:
                # get_password prefers CPOLAR_PASSWORD; report the actual source
                if os.environ.get("CPOLAR_PASSWORD"):
                    self.add_check(
                        _("doctor.check.password"), True, _("doctor.password.env")
                    )
                    # The env var is account-agnostic: warn multi-account users
                    if len(self.config_manager.list_accounts()) > 1:
                        self.add_check(
                            _("doctor.check.password"),
                            False,
                            _("doctor.password.env_multi_account"),
                            level="warning",
                        )
                else:
                    self.add_check(
                        _("doctor.check.password"), True, _("doctor.password.found")
                    )
                return True
            else:
                self.add_check(
                    _("doctor.check.password"),
                    False,
                    _(
                        "doctor.password.not_found",
                        account=self.config_manager.account,
                    ),
                    level="warning",
                )
                return False
        except Exception as e:
            self.add_check(_("doctor.check.password"), False, str(e))
            return False

    def check_network(self) -> bool:
        """Check network connectivity"""
        try:
            # Check cpolar.com
            response = requests.get("https://www.cpolar.com", timeout=5)
            if response.status_code == 200:
                self.add_check(_("doctor.check.network"), True, _("doctor.network.ok"))
                return True
            else:
                self.add_check(
                    _("doctor.check.network"),
                    False,
                    _("doctor.network.http_error", status=response.status_code),
                    level="warning",
                )
                return False
        except requests.exceptions.Timeout:
            self.add_check(
                _("doctor.check.network"), False, _("doctor.network.timeout")
            )
            return False
        except Exception as e:
            self.add_check(
                _("doctor.check.network"),
                False,
                _("doctor.network.error", error=str(e)),
            )
            return False

    def check_cpolar_auth(self) -> bool:
        """Check cpolar authentication"""
        try:
            config = self.config_manager.get_config()
            password = self.config_manager.get_password(config.username)

            if not password:
                self.add_check(
                    _("doctor.check.cpolar_auth"),
                    False,
                    _("doctor.cpolar.no_password"),
                    level="warning",
                )
                return False

            auth = CpolarAuth(self.config_manager)
            session = auth.login(config.username, password)

            self.add_check(
                _("doctor.check.cpolar_auth"), True, _("doctor.cpolar.auth_success")
            )

            # Try to get tunnel info
            tunnel_manager = TunnelManager(session, config.base_url)
            try:
                tunnel_info = tunnel_manager.get_tunnel_info(config.tunnel_name)
                self.add_check(
                    _("doctor.check.tunnel"),
                    True,
                    _("doctor.tunnel.found", url=tunnel_info.url),
                )
                for warning in selection_warnings(
                    tunnel_info, self.config_manager.account
                ):
                    self.add_check(
                        _("doctor.check.tunnel_selection"),
                        False,
                        warning,
                        level="warning",
                    )
                self.check_tunnel_dns(tunnel_info)
            except TunnelNameNotFoundError as e:
                # Other tunnels are online: a wrong tunnel.name, or that
                # machine's cpolar is down (the message lists what is online)
                self.add_check(
                    _("doctor.check.tunnel_name"), False, str(e), level="warning"
                )
            except TunnelError:
                self.add_check(
                    _("doctor.check.tunnel"),
                    False,
                    _("doctor.tunnel.not_found"),
                    level="warning",
                )

            return True

        except AuthenticationError as e:
            self.add_check(
                _("doctor.check.cpolar_auth"),
                False,
                _("doctor.cpolar.auth_failed", error=str(e)),
            )
            return False
        except Exception as e:
            self.add_check(_("doctor.check.cpolar_auth"), False, str(e))
            return False

    def check_tunnel_dns(self, tunnel_info: TunnelInfo) -> bool:
        """Check that the tunnel's host name resolves on this network.

        Login and tunnel can be in order while connecting still fails: some
        networks (campus ones, say) do not resolve tunnel host names.
        """
        hostname = tunnel_info.hostname
        try:
            socket.getaddrinfo(hostname, tunnel_info.port, type=socket.SOCK_STREAM)
        except (OSError, UnicodeError) as e:
            self.add_check(
                _("doctor.check.tunnel_dns"),
                False,
                _("doctor.tunnel_dns.failed", hostname=hostname, error=e),
            )
            return False
        self.add_check(
            _("doctor.check.tunnel_dns"),
            True,
            _("doctor.tunnel_dns.ok", hostname=hostname),
        )
        return True

    def check_ssh_key(self) -> bool:
        """Check SSH key"""
        try:
            config = self.config_manager.get_config()
            ssh_key_path = Path(config.ssh_key_path).expanduser()

            if ssh_key_path.exists():
                # Connecting fails outright with a key that cannot be loaded
                # (passphrase-protected, unsupported type, unreadable)
                try:
                    load_private_key(ssh_key_path)
                except SSHError as e:
                    self.add_check(_("doctor.check.ssh_key"), False, str(e))
                    return False

                # Check permissions (POSIX only; mode bits are meaningless on Windows)
                stat_info = ssh_key_path.stat()
                mode = oct(stat_info.st_mode)[-3:]

                if platform.system() != "Windows" and mode != "600":
                    self.add_check(
                        _("doctor.check.ssh_key"),
                        False,
                        _("doctor.ssh.key_permission", mode=mode),
                        level="warning",
                    )
                else:
                    self.add_check(
                        _("doctor.check.ssh_key"), True, _("doctor.ssh.key_exists")
                    )

                # Check public key
                pub_key_path = ssh_key_path.with_suffix(ssh_key_path.suffix + ".pub")
                if not pub_key_path.exists():
                    self.add_check(
                        _("doctor.check.ssh_pubkey"),
                        False,
                        _("doctor.ssh.pubkey_missing"),
                        level="warning",
                    )
                else:
                    self.add_check(
                        _("doctor.check.ssh_pubkey"),
                        True,
                        _("doctor.ssh.pubkey_exists"),
                    )

                return True
            else:
                self.add_check(
                    _("doctor.check.ssh_key"), True, _("doctor.ssh.key_will_create")
                )
                return True

        except Exception as e:
            self.add_check(_("doctor.check.ssh_key"), False, str(e))
            return False

    def check_ssh_config(self) -> bool:
        """Check SSH config"""
        try:
            ssh_config_path = Path.home() / ".ssh" / "config"

            if ssh_config_path.exists():
                config = self.config_manager.get_config()
                with open(ssh_config_path, "r") as f:
                    content = f.read()
                    if config.ssh_host_alias in content:
                        self.add_check(
                            _("doctor.check.ssh_config"),
                            True,
                            _("doctor.ssh.config_exists"),
                        )
                    else:
                        self.add_check(
                            _("doctor.check.ssh_config"),
                            True,
                            _("doctor.ssh.config_will_update"),
                        )
            else:
                self.add_check(
                    _("doctor.check.ssh_config"),
                    True,
                    _("doctor.ssh.config_will_create"),
                )

            return True

        except Exception as e:
            self.add_check(_("doctor.check.ssh_config"), False, str(e))
            return False

    def check_host_key(self) -> bool:
        """Report host key recording status (informational)"""
        if self.config_manager.known_hosts_file.exists():
            self.add_check(
                _("doctor.check.hostkey"), True, _("doctor.hostkey.recorded")
            )
        else:
            self.add_check(_("doctor.check.hostkey"), True, _("doctor.hostkey.none"))
        return True

    def check_command(self, command: str, name: str) -> bool:
        """Check if a command exists (cross-platform)"""
        try:
            if shutil.which(command):
                self.add_check(name, True, _("doctor.command.found", command=command))
                return True
            else:
                self.add_check(
                    name,
                    False,
                    _("doctor.command.not_found", command=command),
                    level="warning",
                )
                return False
        except Exception as e:
            self.add_check(name, False, str(e))
            return False

    def display_results(self):
        """Display diagnosis results"""
        # Create results table
        table = Table(
            title=_("doctor.title"), show_header=True, header_style="bold magenta"
        )
        table.add_column(_("doctor.column.check"), style="cyan", width=30)
        table.add_column(_("doctor.column.status"), justify="center", width=10)
        table.add_column(_("doctor.column.message"), style="white")

        for name, passed, message, level in self.checks:
            if passed:
                status = "[green]OK[/green]"
            elif level == "warning":
                status = "[yellow]WARN[/yellow]"
            else:
                status = "[red]FAIL[/red]"

            # Messages embed error text and tunnel names: not Rich markup
            table.add_row(escape(name), status, escape(message))

        console.print("\n")
        console.print(table)

        # Show summary
        console.print("\n")
        if self.has_error:
            console.print(
                Panel.fit(
                    _("doctor.summary.has_errors"),
                    style="red",
                    title=_("doctor.summary.title"),
                )
            )
        elif self.has_warning:
            console.print(
                Panel.fit(
                    _("doctor.summary.has_warnings"),
                    style="yellow",
                    title=_("doctor.summary.title"),
                )
            )
        else:
            console.print(
                Panel.fit(
                    _("doctor.summary.all_good"),
                    style="green",
                    title=_("doctor.summary.title"),
                )
            )

        # Show recommendations (some findings explain their own remedy)
        recommendations = self._recommendations()
        if recommendations:
            console.print(f"\n[bold]{_('doctor.recommendations')}:[/bold]\n")
            for line in recommendations:
                console.print(line)

    def _recommendations(self) -> List[str]:
        """Rich-markup lines advising how to fix the failed checks."""
        lines: List[str] = []
        shown = set()

        def bullet(key: str) -> None:
            lines.append(f"  [cyan]•[/cyan] {_(key)}")

        def command(text: str) -> None:
            lines.append(f"    [dim]{escape(text)}[/dim]")

        def server_commands() -> None:
            bullet("doctor.recommend.check_server")
            command(_("doctor.cmd.server.status"))
            command(_("doctor.cmd.server.start"))
            command(_("doctor.cmd.server.tunnel"))

        for name, passed, _message, _level in self.checks:
            if passed:
                continue
            if _("doctor.check.config") in name and "config" not in shown:
                bullet("doctor.recommend.run_init")
                command(_("doctor.cmd.init", account=self.config_manager.account))
                shown.add("config")
            elif _("doctor.check.password") in name and "password" not in shown:
                bullet("doctor.recommend.set_password")
                # Add OS-specific instructions
                if platform.system() == "Windows":
                    password_cmd = _("doctor.cmd.password.win")
                else:
                    password_cmd = _("doctor.cmd.password.unix")
                command(f"{_('doctor.cmd.option1')} {password_cmd}")
                save_command = _(
                    "doctor.cmd.password.save", account=self.config_manager.account
                )
                command(f"{_('doctor.cmd.option2')} {save_command}")
                shown.add("password")
            elif _("doctor.check.network") in name and "network" not in shown:
                bullet("doctor.recommend.check_network")
                command(_("doctor.cmd.network.ping"))
                command(_("doctor.cmd.network.curl"))
                command(_("doctor.cmd.network.check"))
                shown.add("network")
            elif _("doctor.check.cpolar_auth") in name and "auth" not in shown:
                bullet("doctor.recommend.check_credentials")
                command(_("doctor.cmd.auth.check1"))
                command(_("doctor.cmd.auth.check2"))
                command(_("doctor.cmd.auth.check3"))
                shown.add("auth")
            elif _("doctor.check.tunnel_name") in name and "tunnel_name" not in shown:
                bullet("doctor.recommend.pick_tunnel")
                command(
                    _(
                        "hint.set_tunnel_name_command",
                        account=self.config_manager.account,
                    )
                )
                if "tunnel" not in shown:
                    server_commands()
                    shown.add("tunnel")
                shown.add("tunnel_name")
            elif _("doctor.check.tunnel_dns") in name and "tunnel_dns" not in shown:
                # Not the server's doing: nothing to run there
                bullet("doctor.recommend.tunnel_dns")
                shown.add("tunnel_dns")
            elif _("doctor.check.tunnel") in name and "tunnel" not in shown:
                server_commands()
                shown.add("tunnel")
        return lines

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
            self.check_host_key()
            self.check_command("ssh", _("doctor.check.ssh_command"))

            # Only check cpolar auth if password is available
            if self.config_manager.get_config() and (
                self.config_manager.get_password(
                    self.config_manager.get_config().username
                )
                or os.environ.get("CPOLAR_PASSWORD")
            ):
                self.check_cpolar_auth()

        # Display results
        self.display_results()

        return not self.has_error
