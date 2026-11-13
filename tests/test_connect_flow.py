"""
Tests for the connect flow's passwordless bootstrap:
pre-check fails -> try existing keys -> only prompt for password if that fails.
"""

import json
import socket
from pathlib import Path

import paramiko
import pytest
from click.testing import CliRunner

from cpolar_connect import cli as cli_module
from cpolar_connect.config import ConfigManager
from cpolar_connect.tunnel import TunnelInfo


class FakeAuth:
    def __init__(self, config_manager=None, base_url=None):
        pass

    def login(self, username=None, password=None):
        return object()

    def logout(self):
        pass


class FakeTunnelManager:
    requested_name = None
    tunnel_name = None  # set per-test: the dashboard name of the only tunnel
    other_candidates = []  # set per-test to simulate several SSH tunnels
    address = ("1.tcp.cpolar.top", 12345)  # set per-test: where the tunnel leads

    def __init__(self, session, base_url=None):
        pass

    def get_tunnel_info(self, tunnel_name=None):
        FakeTunnelManager.requested_name = tunnel_name
        hostname, port = FakeTunnelManager.address
        return TunnelInfo(
            url=f"tcp://{hostname}:{port}",
            hostname=hostname,
            port=port,
            name=FakeTunnelManager.tunnel_name or tunnel_name or "default",
            other_candidates=FakeTunnelManager.other_candidates,
        )


class FakeSSHManager:
    """Scripted SSHManager: key auth fails, existing-keys result is configurable."""

    existing_keys_result = None  # set per-test
    connect_calls = []

    def __init__(self, config, known_hosts_path=None):
        self.private_key_path = Path("/fake/id_rsa_cpolar")
        self.host_alias = config.ssh_host_alias
        self.known_hosts_path = known_hosts_path
        self._test_results = iter([False, True])  # pre-check fails, retest passes

    def test_ssh_connection(self, hostname, port, timeout=10):
        return next(self._test_results, True)

    def generate_ssh_key(self, force=False):
        return False

    def upload_public_key_with_existing_keys(self, hostname, port):
        return FakeSSHManager.existing_keys_result

    def upload_public_key(self, hostname, port, password):
        FakeSSHManager.password_used = password
        return True

    def update_ssh_config(self, tunnel_info, ports=None):
        pass

    def connect(self, tunnel_info=None, ports=None):
        FakeSSHManager.connect_calls.append((tunnel_info, ports))
        return 0


@pytest.fixture
def connect_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CPOLAR_LANG", "en")
    monkeypatch.delenv("CPOLAR_PASSWORD", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    cm = ConfigManager()
    cm.create_config(
        {
            "username": "user@example.com",
            "server_user": "ubuntu",
            "auto_connect": True,
        }
    )
    cm.set_password("user@example.com", "cpolar-pass")

    monkeypatch.setattr(cli_module, "CpolarAuth", FakeAuth)
    monkeypatch.setattr(cli_module, "TunnelManager", FakeTunnelManager)
    monkeypatch.setattr(cli_module, "SSHManager", FakeSSHManager)
    FakeSSHManager.connect_calls = []
    FakeSSHManager.password_used = None
    FakeTunnelManager.requested_name = None
    FakeTunnelManager.tunnel_name = None
    FakeTunnelManager.other_candidates = []
    FakeTunnelManager.address = ("1.tcp.cpolar.top", 12345)
    return cm


def _fail_if_prompted(self, message):
    raise AssertionError("password prompt must not appear")


def test_existing_keys_success_skips_password_prompt(connect_env, monkeypatch):
    FakeSSHManager.existing_keys_result = True  # uploaded via existing keys
    monkeypatch.setattr(cli_module.Prompts, "password", _fail_if_prompted)

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 0, result.output
    assert FakeSSHManager.connect_calls  # proceeded to connect
    assert FakeSSHManager.password_used is None  # password path never used
    # ...and nothing along the way claims that a password is needed
    assert "password" not in result.output.lower()


def test_existing_keys_failure_falls_back_to_password(connect_env, monkeypatch):
    FakeSSHManager.existing_keys_result = None  # auth with existing keys failed

    monkeypatch.setattr(
        cli_module.Prompts, "password", lambda self, message: "server-pass"
    )

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 0, result.output
    assert FakeSSHManager.password_used == "server-pass"
    assert FakeSSHManager.connect_calls


def test_tunnel_not_found_shows_server_commands(connect_env, monkeypatch):
    """When no tunnel exists, tell the user what to run on the server."""
    from cpolar_connect.exceptions import TunnelNotFoundError

    def raise_not_found(self, tunnel_name=None):
        raise TunnelNotFoundError("No active tunnel found")

    monkeypatch.setattr(FakeTunnelManager, "get_tunnel_info", raise_not_found)
    result = CliRunner().invoke(cli_module.cli, ["-y"])
    assert result.exit_code == 1
    assert "systemctl start cpolar" in result.output
    assert "cpolar tcp 22" in result.output


def test_status_tunnel_not_found_shows_server_commands(connect_env, monkeypatch):
    from cpolar_connect.exceptions import TunnelNotFoundError

    def raise_not_found(self, tunnel_name=None):
        raise TunnelNotFoundError("No active tunnel found")

    monkeypatch.setattr(FakeTunnelManager, "get_tunnel_info", raise_not_found)
    result = CliRunner().invoke(cli_module.cli, ["status"])
    assert result.exit_code == 0, result.output
    assert "systemctl start cpolar" in result.output


def test_empty_server_password_is_tried_not_skipped(connect_env, monkeypatch):
    """Enter means "empty password", which servers may accept; never skip it."""
    FakeSSHManager.existing_keys_result = None
    monkeypatch.setattr(cli_module.Prompts, "password", lambda self, message: "")

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 0, result.output
    assert FakeSSHManager.password_used == ""


def test_unreachable_ssh_aborts_without_password_prompt(connect_env, monkeypatch):
    """A network fault must not be mistaken for a first connection."""
    from cpolar_connect.exceptions import SSHError

    def unreachable(self, hostname, port, timeout=10):
        raise SSHError("Cannot reach the SSH service")

    monkeypatch.setattr(FakeSSHManager, "test_ssh_connection", unreachable)
    monkeypatch.setattr(cli_module.Prompts, "password", _fail_if_prompted)

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 1
    assert "Cannot reach the SSH service" in result.output
    assert not FakeSSHManager.connect_calls


def test_configured_tunnel_name_is_requested(connect_env):
    """Each account can target its own machine's tunnel by name."""
    FakeSSHManager.existing_keys_result = True
    connect_env.set("tunnel.name", "ssh")

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 0, result.output
    assert FakeTunnelManager.requested_name == "ssh"


def test_multiple_ssh_tunnels_warn_with_fix_command(connect_env):
    """Auto-picking among several SSH tunnels must not happen silently."""
    FakeSSHManager.existing_keys_result = True
    FakeTunnelManager.other_candidates = ["ssh"]

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 0, result.output
    assert "several SSH tunnels" in result.output
    assert "cpolar-connect -a default config set tunnel.name" in result.output


def test_same_named_tunnels_warn_without_tunnel_name_advice(connect_env):
    """tunnel.name cannot tell two tunnels called "ssh" apart."""
    FakeSSHManager.existing_keys_result = True
    connect_env.set("tunnel.name", "ssh")
    FakeTunnelManager.other_candidates = ["ssh"]

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 0, result.output
    assert "2 tunnels are named 'ssh'" in result.output
    assert "config set tunnel.name" not in result.output


def _raise_from_tunnel_lookup(monkeypatch, error):
    def raise_error(self, tunnel_name=None):
        raise error

    monkeypatch.setattr(FakeTunnelManager, "get_tunnel_info", raise_error)


def test_wrong_tunnel_name_gets_both_possible_fixes(connect_env, monkeypatch):
    """Not online by that name: a typo, or that machine's cpolar is down."""
    from cpolar_connect.exceptions import TunnelNameNotFoundError

    _raise_from_tunnel_lookup(
        monkeypatch,
        TunnelNameNotFoundError("No online TCP tunnel named 'winpc'. Online: ssh"),
    )

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 1
    assert "Online: ssh" in result.output
    assert "cpolar-connect -a default config set tunnel.name" in result.output
    assert "systemctl start cpolar" in result.output


def test_status_wrong_tunnel_name_gets_both_possible_fixes(connect_env, monkeypatch):
    from cpolar_connect.exceptions import TunnelNameNotFoundError

    _raise_from_tunnel_lookup(
        monkeypatch,
        TunnelNameNotFoundError("No online TCP tunnel named 'winpc'. Online: ssh"),
    )

    result = CliRunner().invoke(cli_module.cli, ["status"])

    assert result.exit_code == 0, result.output
    assert "cpolar-connect -a default config set tunnel.name" in result.output
    assert "systemctl start cpolar" in result.output


@pytest.mark.parametrize("name", ["ssh[home]", "lab[/]"])
def test_status_shows_tunnel_names_literally(connect_env, name):
    """Dashboard names are data, not Rich markup."""
    FakeTunnelManager.tunnel_name = name

    result = CliRunner().invoke(cli_module.cli, ["status"])

    assert result.exit_code == 0, result.output
    assert name in result.output


def test_changed_host_key_hint_names_the_account(monkeypatch, connect_env):
    """The reset command must work as printed for a non-current account."""
    from cpolar_connect.exceptions import HostKeyChangedError

    work = ConfigManager(account="work")
    work.create_config(
        {
            "username": "user@example.com",
            "server_user": "ubuntu",
            "ssh_host_alias": "cpolar-work",
        }
    )
    work.set_password("user@example.com", "cpolar-pass")

    def changed(self, hostname, port, timeout=10):
        raise HostKeyChangedError("Server host key has changed!")

    monkeypatch.setattr(FakeSSHManager, "test_ssh_connection", changed)
    monkeypatch.setattr(cli_module.Prompts, "password", _fail_if_prompted)

    result = CliRunner().invoke(cli_module.cli, ["-a", "work", "-y"])

    assert result.exit_code == 1
    assert "Server host key has changed!" in result.output
    assert "cpolar-connect -a work config clear-hostkey" in result.output
    assert not FakeSSHManager.connect_calls


def _host_key_changed(self, hostname, port, timeout=10):
    from cpolar_connect.exceptions import HostKeyChangedError

    raise HostKeyChangedError("Server host key has changed!")


def test_quiet_mode_still_says_how_to_recover_from_a_changed_host_key(
    monkeypatch, connect_env
):
    """-q drops progress output, not the way out of an error."""
    monkeypatch.setattr(FakeSSHManager, "test_ssh_connection", _host_key_changed)

    result = CliRunner().invoke(cli_module.cli, ["-q", "-y"])

    assert result.exit_code == 1
    assert "Server host key has changed!" in result.output
    assert "cpolar-connect -a default config clear-hostkey" in result.output


def test_changed_host_key_with_automatic_tunnel_choice_suggests_pinning_the_tunnel(
    monkeypatch, connect_env
):
    """Without tunnel.name the account takes the first SSH tunnel listed: when
    the usual machine is off, that is another machine, with another key.
    Clearing the recorded key would then quietly re-point the account."""
    FakeTunnelManager.tunnel_name = "office-pc"
    monkeypatch.setattr(FakeSSHManager, "test_ssh_connection", _host_key_changed)

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 1
    assert "'office-pc'" in result.output
    assert "cpolar-connect -a default config set tunnel.name" in result.output
    assert "cpolar-connect -a default config clear-hostkey" in result.output


def test_changed_host_key_with_a_pinned_tunnel_does_not_suggest_pinning_it(
    monkeypatch, connect_env
):
    connect_env.set("tunnel.name", "office-pc")
    monkeypatch.setattr(FakeSSHManager, "test_ssh_connection", _host_key_changed)

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 1
    assert "config set tunnel.name" not in result.output
    assert "cpolar-connect -a default config clear-hostkey" in result.output


def test_server_without_password_logins_gets_the_way_out(monkeypatch, connect_env):
    """After the password was asked for in vain, say what does work."""
    from cpolar_connect.exceptions import PasswordLoginUnavailableError

    public_key = Path("/fake/id_rsa_cpolar.pub")
    FakeSSHManager.existing_keys_result = None

    def refused(self, hostname, port, password):
        raise PasswordLoginUnavailableError(
            "The server does not accept password logins (it offers: publickey)",
            public_key,
        )

    monkeypatch.setattr(FakeSSHManager, "upload_public_key", refused)
    monkeypatch.setattr(cli_module.Prompts, "password", lambda self, message: "typed")

    result = CliRunner().invoke(cli_module.cli, ["-q", "-y"])

    assert result.exit_code == 1
    assert "does not accept password logins" in result.output
    assert "cpolar-connect -a default config set ssh.key_path" in result.output
    assert f"add the line in {public_key} to" in result.output
    assert not FakeSSHManager.connect_calls


def test_key_the_server_accepts_is_left_alone(monkeypatch, connect_env):
    """Nothing to install: the key pair is not touched, so a user's own key
    gets no .pub written next to it and a read-only key directory is fine."""
    generate_calls = []
    monkeypatch.setattr(
        FakeSSHManager, "test_ssh_connection", lambda self, h, p, timeout=10: True
    )
    monkeypatch.setattr(
        FakeSSHManager,
        "generate_ssh_key",
        lambda self, force=False: generate_calls.append(force) or False,
    )

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 0, result.output
    assert generate_calls == []
    assert FakeSSHManager.connect_calls


def test_first_connection_reports_the_new_key_once(monkeypatch, connect_env):
    FakeSSHManager.existing_keys_result = True
    generated = iter([True])  # a second call would find the key in place
    monkeypatch.setattr(
        FakeSSHManager,
        "generate_ssh_key",
        lambda self, force=False: next(generated, False),
    )

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 0, result.output
    assert result.output.count("SSH key pair generated") == 1
    assert "SSH key already exists" not in result.output


def test_first_connection_to_unreachable_server_never_asks_for_a_password(
    connect_env, monkeypatch, tmp_path
):
    """No key yet and nothing listening: say so instead of starting a bootstrap."""
    import paramiko

    from cpolar_connect.ssh import SSHManager

    class UnreachableClient:
        def set_missing_host_key_policy(self, policy):
            pass

        def connect(self, **kwargs):
            raise ConnectionRefusedError(61, "Connection refused")

        def close(self):
            pass

    monkeypatch.setattr(cli_module, "SSHManager", SSHManager)  # the real one
    monkeypatch.setattr(paramiko, "SSHClient", UnreachableClient)
    monkeypatch.setattr(cli_module.Prompts, "password", _fail_if_prompted)

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 1
    assert "Cannot reach the SSH service at 1.tcp.cpolar.top:12345" in result.output
    assert "First time connection" not in result.output
    # The error gets its own line instead of trailing the "testing..." spinner
    assert not [
        line for line in result.output.split("\n") if "◌" in line and "✗" in line
    ]
    assert not (tmp_path / ".ssh" / "id_rsa_cpolar").exists()


def test_agent_key_suffices_when_the_configured_key_is_not_installed(
    connect_env, monkeypatch, tmp_path, write_private_key
):
    """A server that only accepts an ssh-agent key and cannot take our upload
    (e.g. Windows): ssh will get in through the agent, so must the pre-check."""
    import paramiko

    from cpolar_connect.ssh import SSHManager

    key_path = tmp_path / ".ssh" / "id_rsa_cpolar"
    key_path.parent.mkdir()
    write_private_key(key_path)
    host_key = paramiko.ECDSAKey.generate()
    ran = []

    class AgentOnlyServer:
        def set_missing_host_key_policy(self, policy):
            self.policy = policy

        def connect(self, **kwargs):
            self.policy.missing_host_key(self, kwargs["hostname"], host_key)
            if not kwargs.get("allow_agent"):
                raise paramiko.AuthenticationException("key not authorized")

        def exec_command(self, command, timeout=None):
            ran.append(command)
            raise AssertionError("nothing may be run on the server")

        def close(self):
            pass

    connected = []
    monkeypatch.setattr(cli_module, "SSHManager", SSHManager)  # the real one
    monkeypatch.setattr(
        SSHManager, "connect", lambda self, *args: connected.append(args) or 0
    )
    monkeypatch.setattr(paramiko, "SSHClient", AgentOnlyServer)
    monkeypatch.setattr(cli_module.Prompts, "password", _fail_if_prompted)

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 0, result.output
    assert ran == []
    assert connected
    assert "Host cpolar-server" in (tmp_path / ".ssh" / "config").read_text()


def test_status_json_reports_the_tunnel(connect_env):
    FakeTunnelManager.tunnel_name = "office"
    FakeTunnelManager.other_candidates = ["home"]

    result = CliRunner().invoke(cli_module.cli, ["-f", "json", "status"])

    assert result.exit_code == 0, result.output
    tunnel = json.loads(result.output)["tunnel"]
    assert list(tunnel.items()) == [
        ("name", "office"),
        ("url", "tcp://1.tcp.cpolar.top:12345"),
        ("hostname", "1.tcp.cpolar.top"),
        ("port", 12345),
        ("other_candidates", ["home"]),
    ]


def test_missing_config_names_the_account_in_the_command(connect_env):
    """As printed, `cpolar-connect init` would set up the current account."""
    result = CliRunner().invoke(cli_module.cli, ["-a", "work", "-y"])

    assert result.exit_code == 1
    assert "cpolar-connect -a work init" in result.output


def test_missing_password_names_the_account_in_the_command(connect_env):
    work = ConfigManager(account="work")
    work.create_config(
        {
            "username": "work@example.com",
            "server_user": "ubuntu",
            "ssh_host_alias": "cpolar-work",
        }
    )

    result = CliRunner().invoke(cli_module.cli, ["-a", "work", "-y"])

    assert result.exit_code == 1
    assert "cpolar-connect -a work init" in result.output


def _set_up_without_connecting(account_args):
    return CliRunner().invoke(cli_module.cli, [*account_args, "-y"])


def test_closing_message_gives_the_plain_command_for_the_current_account(connect_env):
    """The everyday case stays short: no `-a default` to puzzle over."""
    connect_env.set("server.auto_connect", "false")

    result = _set_up_without_connecting([])

    assert result.exit_code == 0, result.output
    assert "Run 'cpolar-connect' to connect" in result.output


def test_closing_message_names_an_account_that_is_not_the_current_one(connect_env):
    work = ConfigManager(account="work")
    work.create_config(
        {
            "username": "user@example.com",
            "server_user": "ubuntu",
            "ssh_host_alias": "cpolar-work",
            "auto_connect": False,
        }
    )
    work.set_password("user@example.com", "cpolar-pass")

    result = _set_up_without_connecting(["-a", "work"])

    assert result.exit_code == 0, result.output
    assert "Run 'cpolar-connect -a work' to connect" in result.output


# What a run that does not get through leaves in ~/.ssh/config (issue #3).
# These run the real SSHManager; where a server answers, it is the loopback
# server of conftest.py and the handshake is real.

YESTERDAY = ("HostName 3.tcp.cpolar.top", "Port 11111")
ADDRESS_RECORDED = "SSH config was updated with the tunnel's current address"


@pytest.fixture
def real_ssh(connect_env, monkeypatch):
    """The real SSHManager, on an account that connected yesterday: its Host
    block still holds the address the tunnel had then."""
    from cpolar_connect.ssh import SSHManager

    monkeypatch.setattr(cli_module, "SSHManager", SSHManager)
    monkeypatch.setattr(
        SSHManager,
        "connect",
        lambda self, *args: FakeSSHManager.connect_calls.append(args) or 0,
    )
    manager = SSHManager(
        connect_env.get_config(), known_hosts_path=connect_env.known_hosts_file
    )
    manager.update_ssh_config(
        TunnelInfo(
            url="tcp://3.tcp.cpolar.top:11111", hostname="3.tcp.cpolar.top", port=11111
        )
    )
    return manager


def _host_block(manager):
    """The (HostName, Port) lines of the account's Host block, if it has one."""
    if not manager.ssh_config_path.is_file():
        return None
    content = manager.ssh_config_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines()]
    if f"Host {manager.host_alias}" not in lines:
        return None
    return (
        next(line for line in lines if line.startswith("HostName ")),
        next(line for line in lines if line.startswith("Port ")),
    )


def _dns_refuses(monkeypatch, name):
    """A network whose DNS will not resolve `name` (as Windows reports it)."""
    resolve = socket.getaddrinfo

    def getaddrinfo(host, *args, **kwargs):
        if host == name:
            raise socket.gaierror(11001, "getaddrinfo failed")
        return resolve(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


@pytest.mark.parametrize("flags", [["-y"], ["-q", "-y"]])
def test_tunnel_whose_name_does_not_resolve_is_still_written_to_the_ssh_config(
    real_ssh, monkeypatch, flags
):
    """Issue #3: a campus network that will not resolve tunnel host names.
    The user resolves the name by other means, and reads it from the Host
    block: it has to be there although nothing could be tested."""
    _dns_refuses(monkeypatch, "1.tcp.cpolar.top")
    monkeypatch.setattr(cli_module.Prompts, "password", _fail_if_prompted)

    result = CliRunner().invoke(cli_module.cli, flags)

    assert result.exit_code == 1, result.output
    assert "Cannot resolve the tunnel's host name 1.tcp.cpolar.top" in result.output
    assert "sshd" not in result.output  # the server is not what to look at
    assert _host_block(real_ssh) == ("HostName 1.tcp.cpolar.top", "Port 12345")
    # ...and the run says so, in quiet mode too: scripts go on from here
    assert f"{ADDRESS_RECORDED} all the same (Host cpolar-server)" in result.output
    assert not FakeSSHManager.connect_calls


def test_server_that_does_not_answer_is_still_written_to_the_ssh_config(
    real_ssh, monkeypatch
):
    """sshd down, or the port blocked on this network: where the tunnel is
    has not become wrong for that."""
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    FakeTunnelManager.address = ("127.0.0.1", port)
    monkeypatch.setattr(cli_module.Prompts, "password", _fail_if_prompted)

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 1, result.output
    assert f"Cannot reach the SSH service at 127.0.0.1:{port}" in result.output
    assert _host_block(real_ssh) == ("HostName 127.0.0.1", f"Port {port}")
    assert ADDRESS_RECORDED in result.output


def test_tunnel_that_was_one_of_several_does_not_replace_the_address(
    real_ssh, monkeypatch
):
    """Several machines on one cpolar login and no tunnel.name: the tunnel
    picked this time may be the other machine's. That it cannot be reached
    says nothing against the address in the Host block, which may still be
    the right one."""
    FakeTunnelManager.other_candidates = ["office-pc"]
    _dns_refuses(monkeypatch, "1.tcp.cpolar.top")

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 1, result.output
    assert "Cannot resolve the tunnel's host name" in result.output
    assert _host_block(real_ssh) == YESTERDAY
    assert ADDRESS_RECORDED not in result.output
    # How to make the choice certain was said when the tunnel was picked
    assert "cpolar-connect -a default config set tunnel.name" in result.output


def test_server_with_another_host_key_never_takes_over_the_alias(
    real_ssh, monkeypatch, ssh_server
):
    """Several machines on one cpolar login and no tunnel.name: this time the
    other machine was picked. Yesterday's address may well still work, and a
    server that failed the identity check is the last thing to point the
    alias at."""
    known = paramiko.ECDSAKey.generate()
    real_ssh.known_hosts_path.write_text(
        f"{real_ssh.host_alias} {known.get_name()} {known.get_base64()}\n",
        encoding="utf-8",
    )
    port, _server = ssh_server([paramiko.ECDSAKey.generate()])
    FakeTunnelManager.address = ("127.0.0.1", port)
    monkeypatch.setattr(cli_module.Prompts, "password", _fail_if_prompted)

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 1, result.output
    assert "Server host key has changed!" in result.output
    assert _host_block(real_ssh) == YESTERDAY
    assert ADDRESS_RECORDED not in result.output


def test_first_connection_given_up_at_the_password_prompt_leaves_no_host_block(
    connect_env, monkeypatch, tmp_path, ssh_server, write_private_key
):
    """The server was there; the user backed out. Nothing was set up, so
    nothing is left behind."""
    from cpolar_connect.ssh import SSHManager

    monkeypatch.setattr(cli_module, "SSHManager", SSHManager)
    key_path = tmp_path / ".ssh" / "id_rsa_cpolar"
    key_path.parent.mkdir()
    write_private_key(key_path)
    port, _server = ssh_server([paramiko.ECDSAKey.generate()])
    FakeTunnelManager.address = ("127.0.0.1", port)
    monkeypatch.setattr(cli_module.Prompts, "password", lambda self, message: None)

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert "Operation cancelled" in result.output
    assert not (tmp_path / ".ssh" / "config").exists()


def _config_file_is_unusable(manager):
    """A directory where the file should be: no reading it, no writing it."""
    manager.ssh_config_path.unlink()
    manager.ssh_config_path.mkdir()


def test_ssh_config_that_cannot_be_written_is_a_message_not_a_traceback(
    real_ssh, monkeypatch
):
    """Found with issue #3: this used to end the run in a PermissionError."""
    from cpolar_connect.ssh import SSHManager

    _config_file_is_unusable(real_ssh)
    monkeypatch.setattr(
        SSHManager, "test_ssh_connection", lambda self, hostname, port: True
    )

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit), repr(result.exception)
    assert "Cannot read or update the SSH config file" in result.output
    assert str(real_ssh.ssh_config_path) in result.output
    assert not FakeSSHManager.connect_calls


def test_ssh_config_that_cannot_be_written_does_not_hide_why_the_run_failed(
    real_ssh, monkeypatch
):
    """Two things are wrong. The one that ends the run is the server that
    cannot be reached; the config file is mentioned, not put in its place."""
    _config_file_is_unusable(real_ssh)
    _dns_refuses(monkeypatch, "1.tcp.cpolar.top")

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit), repr(result.exception)
    assert "Connection failed: Cannot resolve the tunnel's host name" in result.output
    assert "Cannot read or update the SSH config file" in result.output
    assert ADDRESS_RECORDED not in result.output
