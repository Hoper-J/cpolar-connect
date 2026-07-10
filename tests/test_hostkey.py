"""
Tests for host key verification (TOFU keyed by SSH alias).

The tunnel hostname/port change on every cpolar restart, so host keys are
recorded under the stable ssh_host_alias in a dedicated known_hosts file.
"""

import stat
from pathlib import Path

import paramiko
import pytest

from cpolar_connect.config import CpolarConfig
from cpolar_connect.exceptions import HostKeyChangedError
from cpolar_connect.ssh import AliasHostKeyPolicy, SSHManager

try:
    from pydantic import ValidationError
except ImportError:  # pragma: no cover
    ValidationError = Exception

ALIAS = "cpolar-server"


def _make_key():
    return paramiko.RSAKey.generate(1024)


def _make_config(tmp_path: Path) -> CpolarConfig:
    return CpolarConfig(
        username="user@example.com",
        server_user="ubuntu",
        ssh_key_path=str(tmp_path / "id_rsa_cpolar"),
    )


class TestAliasHostKeyPolicy:
    """TOFU record / match / mismatch semantics, keyed by alias."""

    def test_first_contact_records_key_under_alias(self, tmp_path):
        known_hosts = tmp_path / "known_hosts"
        policy = AliasHostKeyPolicy(ALIAS, known_hosts)
        key = _make_key()

        policy.missing_host_key(None, "1.tcp.cpolar.top", key)

        recorded = paramiko.HostKeys(str(known_hosts))
        entry = recorded.lookup(ALIAS)
        assert entry is not None
        assert entry[key.get_name()].asbytes() == key.asbytes()

    def test_known_hosts_created_with_600_permissions(self, tmp_path):
        known_hosts = tmp_path / "known_hosts"
        policy = AliasHostKeyPolicy(ALIAS, known_hosts)

        policy.missing_host_key(None, "1.tcp.cpolar.top", _make_key())

        mode = stat.S_IMODE(known_hosts.stat().st_mode)
        assert mode == 0o600

    def test_same_key_accepted_on_reconnect(self, tmp_path):
        known_hosts = tmp_path / "known_hosts"
        policy = AliasHostKeyPolicy(ALIAS, known_hosts)
        key = _make_key()

        policy.missing_host_key(None, "1.tcp.cpolar.top", key)
        # Tunnel host changed, same server key: must not raise
        policy.missing_host_key(None, "9.tcp.cpolar.top", key)

    def test_changed_key_rejected(self, tmp_path):
        known_hosts = tmp_path / "known_hosts"
        policy = AliasHostKeyPolicy(ALIAS, known_hosts)

        policy.missing_host_key(None, "1.tcp.cpolar.top", _make_key())

        with pytest.raises(HostKeyChangedError):
            policy.missing_host_key(None, "1.tcp.cpolar.top", _make_key())

    def test_changed_key_does_not_overwrite_recorded_key(self, tmp_path):
        known_hosts = tmp_path / "known_hosts"
        policy = AliasHostKeyPolicy(ALIAS, known_hosts)
        original = _make_key()

        policy.missing_host_key(None, "1.tcp.cpolar.top", original)
        with pytest.raises(HostKeyChangedError):
            policy.missing_host_key(None, "1.tcp.cpolar.top", _make_key())

        recorded = paramiko.HostKeys(str(known_hosts))
        assert recorded.lookup(ALIAS)[original.get_name()].asbytes() == (
            original.asbytes()
        )

    def test_different_key_type_added_alongside(self, tmp_path):
        """A host legitimately has one key per type; a new type is not a change."""
        known_hosts = tmp_path / "known_hosts"
        policy = AliasHostKeyPolicy(ALIAS, known_hosts)
        rsa_key = _make_key()
        ecdsa_key = paramiko.ECDSAKey.generate()

        policy.missing_host_key(None, "1.tcp.cpolar.top", rsa_key)
        policy.missing_host_key(None, "1.tcp.cpolar.top", ecdsa_key)

        entry = paramiko.HostKeys(str(known_hosts)).lookup(ALIAS)
        assert entry[rsa_key.get_name()].asbytes() == rsa_key.asbytes()
        assert entry[ecdsa_key.get_name()].asbytes() == ecdsa_key.asbytes()


class TestSshConfigHostKeyDirectives:
    """Generated ~/.ssh/config must verify host keys via the alias."""

    @pytest.fixture
    def manager(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CPOLAR_LANG", "en")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        return SSHManager(_make_config(tmp_path))

    def _written_config(self, manager, tmp_path):
        from cpolar_connect.tunnel import TunnelInfo

        tunnel = TunnelInfo(
            url="tcp://1.tcp.cpolar.top:12345",
            hostname="1.tcp.cpolar.top",
            port=12345,
        )
        manager.update_ssh_config(tunnel, ports=[8888])
        return (tmp_path / ".ssh" / "config").read_text(encoding="utf-8")

    def test_config_block_enables_host_key_verification(self, manager, tmp_path):
        content = self._written_config(manager, tmp_path)
        assert f"HostKeyAlias {ALIAS}" in content
        assert "StrictHostKeyChecking accept-new" in content
        assert str(manager.known_hosts_path) in content

    def test_config_block_drops_insecure_directives(self, manager, tmp_path):
        content = self._written_config(manager, tmp_path)
        assert "StrictHostKeyChecking no" not in content
        assert "/dev/null" not in content

    def test_direct_ssh_command_enables_host_key_verification(self, manager):
        from cpolar_connect.tunnel import TunnelInfo

        tunnel = TunnelInfo(
            url="tcp://1.tcp.cpolar.top:12345",
            hostname="1.tcp.cpolar.top",
            port=12345,
        )
        command = manager.build_ssh_command(tunnel, ports=[8888])

        assert f"HostKeyAlias={ALIAS}" in command
        assert "StrictHostKeyChecking=accept-new" in command
        assert f"UserKnownHostsFile={manager.known_hosts_path}" in command
        assert "StrictHostKeyChecking=no" not in command
        assert "UserKnownHostsFile=/dev/null" not in command


class TestAliasSafety:
    """The alias is written verbatim into ~/.ssh/config; it must be inert."""

    @pytest.fixture
    def manager(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CPOLAR_LANG", "en")
        monkeypatch.delenv("CPOLAR_ACCOUNT", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        return SSHManager(_make_config(tmp_path))

    def _written_config(self, manager, tmp_path):
        from cpolar_connect.tunnel import TunnelInfo

        tunnel = TunnelInfo(
            url="tcp://1.tcp.cpolar.top:12345",
            hostname="1.tcp.cpolar.top",
            port=12345,
        )
        manager.update_ssh_config(tunnel, ports=[8888])
        return tmp_path / ".ssh" / "config"

    @pytest.mark.parametrize(
        "bad", ["a b", "a\nProxyCommand x", "-oProxyCommand=x", 'a"b', ""]
    )
    def test_alias_validator_rejects_injection(self, bad):
        with pytest.raises(ValidationError):
            CpolarConfig(username="u", server_user="s", ssh_host_alias=bad)

    def test_update_ssh_config_writes_single_host_line(self, manager, tmp_path):
        content = self._written_config(manager, tmp_path).read_text(encoding="utf-8")
        host_lines = [
            line for line in content.splitlines() if line.strip().startswith("Host ")
        ]
        assert len(host_lines) == 1

    def test_remove_host_block(self, manager, tmp_path):
        cfg = self._written_config(manager, tmp_path)
        cfg.write_text(
            cfg.read_text(encoding="utf-8") + "\nHost other\n\tHostName o\n",
            encoding="utf-8",
        )
        assert manager.remove_host_block() is True
        content = cfg.read_text(encoding="utf-8")
        assert f"Host {ALIAS}" not in content
        assert "Host other" in content
        assert manager.remove_host_block() is False

    def test_policy_creates_parent_dir_700(self, tmp_path):
        kh = tmp_path / "deep" / "known_hosts"
        AliasHostKeyPolicy(ALIAS, kh).missing_host_key(None, "h", _make_key())
        assert stat.S_IMODE(kh.parent.stat().st_mode) == 0o700

    def test_ssh_manager_uses_injected_known_hosts_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        m = SSHManager(_make_config(tmp_path), known_hosts_path=tmp_path / "kh")
        assert m.known_hosts_path == tmp_path / "kh"

    def test_ssh_manager_default_known_hosts_follows_account(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("CPOLAR_ACCOUNT", "work")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        m = SSHManager(_make_config(tmp_path))
        assert m.known_hosts_path == (
            tmp_path / ".cpolar_connect" / "accounts" / "work" / "known_hosts"
        )
