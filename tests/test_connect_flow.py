"""
Tests for the connect flow's passwordless bootstrap:
pre-check fails -> try existing keys -> only prompt for password if that fails.
"""

from pathlib import Path

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
    def __init__(self, session, base_url=None):
        pass

    def get_tunnel_info(self):
        return TunnelInfo(
            url="tcp://1.tcp.cpolar.top:12345",
            hostname="1.tcp.cpolar.top",
            port=12345,
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
    return cm


def test_existing_keys_success_skips_password_prompt(connect_env, monkeypatch):
    FakeSSHManager.existing_keys_result = True  # uploaded via existing keys

    def fail_if_prompted(self, message):
        raise AssertionError("password prompt must not appear")

    monkeypatch.setattr(cli_module.Prompts, "password", fail_if_prompted)

    result = CliRunner().invoke(cli_module.cli, ["-y"])

    assert result.exit_code == 0, result.output
    assert FakeSSHManager.connect_calls  # proceeded to connect
    assert FakeSSHManager.password_used is None  # password path never used


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

    def raise_not_found(self):
        raise TunnelNotFoundError("No active tunnel found")

    monkeypatch.setattr(FakeTunnelManager, "get_tunnel_info", raise_not_found)
    result = CliRunner().invoke(cli_module.cli, ["-y"])
    assert result.exit_code == 1
    assert "systemctl start cpolar" in result.output
    assert "cpolar tcp 22" in result.output


def test_status_tunnel_not_found_shows_server_commands(connect_env, monkeypatch):
    from cpolar_connect.exceptions import TunnelNotFoundError

    def raise_not_found(self):
        raise TunnelNotFoundError("No active tunnel found")

    monkeypatch.setattr(FakeTunnelManager, "get_tunnel_info", raise_not_found)
    result = CliRunner().invoke(cli_module.cli, ["status"])
    assert result.exit_code == 0, result.output
    assert "systemctl start cpolar" in result.output
