"""
Tests for SSHManager key upload: exit-status checking, cleanup, and
passwordless bootstrap via existing keys (agent/default).
"""

from pathlib import Path

import paramiko
import pytest

from cpolar_connect.config import CpolarConfig
from cpolar_connect.exceptions import HostKeyChangedError, SSHError
from cpolar_connect.ssh import SSHManager


class FakeChannel:
    def __init__(self, exit_status):
        self._exit_status = exit_status

    def recv_exit_status(self):
        return self._exit_status


class FakeStream:
    def __init__(self, data=b"", exit_status=0):
        self._data = data
        self.channel = FakeChannel(exit_status)

    def read(self):
        return self._data


def make_fake_client_class(exec_results=None, connect_error=None):
    """Build a scripted SSHClient class; exec results keyed by command substring."""

    class FakeSSHClient:
        instances = []

        def __init__(self):
            self.closed = False
            self.connect_kwargs = None
            self.commands = []
            FakeSSHClient.instances.append(self)

        def set_missing_host_key_policy(self, policy):
            self.policy = policy

        def connect(self, **kwargs):
            self.connect_kwargs = kwargs
            if connect_error is not None:
                raise connect_error

        def exec_command(self, command):
            self.commands.append(command)
            for substring, (status, out, err) in (exec_results or {}).items():
                if substring in command:
                    return (
                        None,
                        FakeStream(out, status),
                        FakeStream(err, status),
                    )
            return (None, FakeStream(b"", 0), FakeStream(b"", 0))

        def close(self):
            self.closed = True

    return FakeSSHClient


@pytest.fixture
def manager(monkeypatch, tmp_path: Path) -> SSHManager:
    monkeypatch.setenv("CPOLAR_LANG", "en")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config = CpolarConfig(
        username="user@example.com",
        server_user="ubuntu",
        ssh_key_path=str(tmp_path / "id_rsa_cpolar"),
    )
    m = SSHManager(config)
    m.public_key_path.parent.mkdir(parents=True, exist_ok=True)
    m.public_key_path.write_text("ssh-rsa AAAAFAKE cpolar-connect\n")
    return m


class TestUploadWithPassword:
    def test_successful_upload_returns_true_and_closes(self, monkeypatch, manager):
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.upload_public_key("host", 22, "secret") is True
        client = client_cls.instances[0]
        assert client.closed
        assert client.connect_kwargs["password"] == "secret"
        assert client.connect_kwargs["allow_agent"] is False
        assert client.connect_kwargs["look_for_keys"] is False

    def test_existing_key_returns_false(self, monkeypatch, manager):
        pubkey = manager.public_key_path.read_text().strip()
        client_cls = make_fake_client_class(
            exec_results={"cat": (0, pubkey.encode(), b"")}
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.upload_public_key("host", 22, "secret") is False
        assert client_cls.instances[0].closed

    def test_failed_append_raises_with_stderr(self, monkeypatch, manager):
        client_cls = make_fake_client_class(
            exec_results={">>": (1, b"", b"disk quota exceeded")}
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(SSHError, match="disk quota exceeded"):
            manager.upload_public_key("host", 22, "secret")
        assert client_cls.instances[0].closed

    def test_failed_mkdir_raises(self, monkeypatch, manager):
        client_cls = make_fake_client_class(
            exec_results={"mkdir": (1, b"", b"permission denied")}
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(SSHError, match="permission denied"):
            manager.upload_public_key("host", 22, "secret")
        assert client_cls.instances[0].closed


class TestUploadWithExistingKeys:
    def test_success_uses_agent_and_default_keys(self, monkeypatch, manager):
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        result = manager.upload_public_key_with_existing_keys("host", 22)

        assert result is True
        kwargs = client_cls.instances[0].connect_kwargs
        assert kwargs["allow_agent"] is True
        assert kwargs["look_for_keys"] is True
        assert "password" not in kwargs or kwargs["password"] is None

    def test_auth_failure_returns_none(self, monkeypatch, manager):
        client_cls = make_fake_client_class(
            connect_error=paramiko.AuthenticationException("no valid key")
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.upload_public_key_with_existing_keys("host", 22) is None
        assert client_cls.instances[0].closed

    def test_too_many_auth_failures_returns_none(self, monkeypatch, manager):
        client_cls = make_fake_client_class(
            connect_error=paramiko.SSHException("Too many authentication failures")
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.upload_public_key_with_existing_keys("host", 22) is None

    def test_host_key_change_propagates(self, monkeypatch, manager):
        client_cls = make_fake_client_class(
            connect_error=HostKeyChangedError("host key changed")
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(HostKeyChangedError):
            manager.upload_public_key_with_existing_keys("host", 22)


class TestConnectionTestHostKeySafety:
    def test_host_key_change_not_swallowed(self, monkeypatch, manager):
        """A host key mismatch must abort, never masquerade as 'no key yet'."""
        client_cls = make_fake_client_class(
            connect_error=HostKeyChangedError("host key changed")
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)
        monkeypatch.setattr(
            paramiko.RSAKey, "from_private_key_file", lambda path: object()
        )

        with pytest.raises(HostKeyChangedError):
            manager.test_ssh_connection("host", 22)
