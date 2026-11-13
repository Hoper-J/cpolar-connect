"""
Tests for SSHManager connections: the key pre-check, key upload (exit-status
checking, cleanup), passwordless bootstrap via existing keys (agent/default),
and how connection failures are told apart from rejected credentials.
"""

import base64
import hashlib
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import paramiko
import pytest
from cryptography.hazmat.primitives import serialization

from cpolar_connect import ssh as ssh_module
from cpolar_connect.config import CpolarConfig
from cpolar_connect.exceptions import (
    HostKeyChangedError,
    PasswordLoginUnavailableError,
    ServerUnreachableError,
    SSHError,
    WindowsServerKeyError,
)
from cpolar_connect.ssh import SSHManager, _is_authorized
from cpolar_connect.ssh import _ssh_offers_agent_keys as real_ssh_offers_agent_keys

# What the fake server presents once the SSH handshake completes
HOST_KEY = paramiko.ECDSAKey.generate()


class FakeChannel:
    def __init__(self, exit_status):
        self._exit_status = exit_status
        self.status_event = threading.Event()
        self.status_event.set()  # the command has finished

    def recv_exit_status(self):
        return self._exit_status


class FakeStream:
    def __init__(self, data=b"", exit_status=0):
        self._data = data
        self.channel = FakeChannel(exit_status)

    def read(self):
        return self._data


LINUX_SERVER = "SSH-2.0-OpenSSH_9.6p1 Ubuntu-3ubuntu13"
WINDOWS_SERVER = "SSH-2.0-OpenSSH_for_Windows_9.5"


class FakeTransport:
    def __init__(self, remote_version):
        self.remote_version = remote_version


def make_fake_client_class(
    exec_results=None,
    connect_error=None,
    reached=True,
    exec_error=None,
    server_version=LINUX_SERVER,
):
    """Build a scripted SSHClient class; exec results keyed by command substring.

    As in paramiko, the host key policy is consulted when the handshake
    completes, before authentication. reached=False fails earlier, the way
    an unreachable server does; connect_error is then the connection error,
    otherwise it is what authentication raises.
    """

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
            if reached:
                self.policy.missing_host_key(self, kwargs["hostname"], HOST_KEY)
            if connect_error is not None:
                raise connect_error

        def exec_command(self, command, timeout=None):
            self.commands.append(command)
            if exec_error is not None:
                raise exec_error
            for substring, (status, out, err) in (exec_results or {}).items():
                if substring in command:
                    return (
                        None,
                        FakeStream(out, status),
                        FakeStream(err, status),
                    )
            return (None, FakeStream(b"", 0), FakeStream(b"", 0))

        def get_transport(self):
            return FakeTransport(server_version)

        def close(self):
            self.closed = True

    return FakeSSHClient


# The account's key pair: the upload installs the public half of exactly this
OUR_KEY = paramiko.ECDSAKey.generate()
OUR_LINE = f"{OUR_KEY.get_name()} {OUR_KEY.get_base64()} cpolar-connect"


def _use_key(manager, key, comment="cpolar-connect") -> str:
    """Make `key` the manager's key pair; returns the line in its .pub file."""
    key.write_private_key_file(str(manager.private_key_path))
    line = f"{key.get_name()} {key.get_base64()} {comment}".rstrip()
    manager.public_key_path.write_text(line + "\n", encoding="utf-8")
    return line


@pytest.fixture
def manager(tmp_path: Path) -> SSHManager:
    config = CpolarConfig(
        username="user@example.com",
        server_user="ubuntu",
        ssh_key_path=str(tmp_path / "id_rsa_cpolar"),
    )
    m = SSHManager(config)
    m.public_key_path.parent.mkdir(parents=True, exist_ok=True)
    _use_key(m, OUR_KEY)
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

    def test_empty_password_is_sent_not_skipped(self, monkeypatch, manager):
        """Servers with PermitEmptyPasswords accept "", so it must be tried."""
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.upload_public_key("host", 22, "") is True
        kwargs = client_cls.instances[0].connect_kwargs
        assert kwargs["password"] == ""
        assert kwargs["allow_agent"] is False

    def test_wrong_password_names_user_and_host(self, monkeypatch, manager):
        client_cls = make_fake_client_class(
            connect_error=paramiko.AuthenticationException("Authentication failed.")
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(SSHError, match="'ubuntu' on host"):
            manager.upload_public_key("host", 22, "wrong")
        assert client_cls.instances[0].closed

    def test_connection_lost_during_password_login_is_not_a_wrong_password(
        self, monkeypatch, manager
    ):
        """A reset in the middle says nothing about what was typed."""
        client_cls = make_fake_client_class(
            connect_error=ConnectionResetError(54, "Connection reset by peer")
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(SSHError, match="lost during authentication") as failure:
            manager.upload_public_key("host", 22, "the-right-password")
        assert "Connection reset by peer" in str(failure.value)
        assert client_cls.instances[0].closed

    def test_server_without_password_logins_is_not_a_wrong_password_either(
        self, monkeypatch, manager
    ):
        """Typical for cloud servers: asking again would never help."""
        client_cls = make_fake_client_class(
            connect_error=paramiko.BadAuthenticationType(
                "Bad authentication type", ["publickey"]
            )
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(PasswordLoginUnavailableError, match="publickey") as e:
            manager.upload_public_key("host", 22, "secret")
        assert e.value.public_key_path == manager.public_key_path

    def test_password_refused_by_a_server_that_asks_interactively_is_just_wrong(
        self, monkeypatch, manager
    ):
        """paramiko answers keyboard-interactive with the password itself."""
        client_cls = make_fake_client_class(
            connect_error=paramiko.BadAuthenticationType(
                "Bad authentication type", ["publickey", "keyboard-interactive"]
            )
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(SSHError, match="'ubuntu' on host") as failure:
            manager.upload_public_key("host", 22, "wrong")
        assert not isinstance(failure.value, PasswordLoginUnavailableError)

    def test_existing_key_returns_false(self, monkeypatch, manager):
        pubkey = manager.public_key_path.read_text().strip()
        client_cls = make_fake_client_class(
            exec_results={"cat": (0, pubkey.encode(), b"")}
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.upload_public_key("host", 22, "secret") is False
        assert client_cls.instances[0].closed

    def test_unterminated_file_gets_the_line_break_and_the_key_in_one_write(
        self, monkeypatch, manager
    ):
        """One command: there is no moment with the line break but no key."""
        client_cls = make_fake_client_class(
            exec_results={"cat": (0, b"ssh-ed25519 AAAA someone", b"")}
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.upload_public_key("host", 22, "secret") is True

        appends = [c for c in client_cls.instances[0].commands if ">>" in c]
        assert appends == [f"printf '\\n%s\\n' '{OUR_LINE}' >> ~/.ssh/authorized_keys"]

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

    def test_channel_failure_after_login_is_an_upload_error(self, monkeypatch, manager):
        client_cls = make_fake_client_class(
            exec_error=paramiko.SSHException("Channel closed.")
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(SSHError, match="Channel closed"):
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

    @pytest.mark.parametrize(
        "error",
        [
            paramiko.AuthenticationException("no valid key"),
            # More agent keys than the server's MaxAuthTries
            paramiko.SSHException("Too many authentication failures"),
            # No agent and no default key files at all
            paramiko.SSHException("No authentication methods available"),
        ],
    )
    def test_rejected_keys_return_none(self, monkeypatch, manager, error):
        """The server was reached; a password can still get the key installed."""
        client_cls = make_fake_client_class(connect_error=error)
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.upload_public_key_with_existing_keys("host", 22) is None
        assert client_cls.instances[0].closed

    def test_unreachable_server_raises_instead_of_asking_for_a_password(
        self, monkeypatch, manager
    ):
        """On a first connection this is the first real contact with the server."""
        client_cls = make_fake_client_class(
            connect_error=ConnectionRefusedError(61, "Connection refused"),
            reached=False,
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(SSHError, match="host:22"):
            manager.upload_public_key_with_existing_keys("host", 22)
        assert client_cls.instances[0].closed

    def test_failed_remote_command_raises(self, monkeypatch, manager):
        """Logged in, but the server could not run the upload."""
        client_cls = make_fake_client_class(
            exec_results={"mkdir": (1, b"", b"Read-only file system")}
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(SSHError, match="Read-only file system") as failure:
            manager.upload_public_key_with_existing_keys("host", 22)
        assert failure.type is SSHError  # nothing Windows-specific about it

    def test_host_key_change_propagates(self, monkeypatch, manager):
        client_cls = make_fake_client_class(
            connect_error=HostKeyChangedError("host key changed")
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(HostKeyChangedError):
            manager.upload_public_key_with_existing_keys("host", 22)


def _windows_report(status: str, detail: str) -> bytes:
    """One report line, as the PowerShell installer prints it."""
    encoded = base64.b64encode(detail.encode("utf-8")).decode("ascii")
    return f"cpolar-connect: {status} {encoded}\r\n".encode("ascii")


def _powershell_script(command: str) -> str:
    """The script inside a `powershell.exe -EncodedCommand` command line."""
    prefix = "powershell.exe -NoProfile -NonInteractive -EncodedCommand "
    assert command.startswith(prefix)
    return base64.b64decode(command[len(prefix) :]).decode("utf-16-le")


ADMIN_KEYS = r"C:\ProgramData\ssh\administrators_authorized_keys"


class TestUploadToWindowsServer:
    """cmd and PowerShell cannot run the POSIX upload commands, and Windows
    keeps keys elsewhere: the server gets one PowerShell script instead."""

    def _server(self, monkeypatch, status=0, out=b"", err=b""):
        client_cls = make_fake_client_class(
            exec_results={"powershell.exe": (status, out, err)},
            server_version=WINDOWS_SERVER,
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)
        return client_cls

    @pytest.mark.parametrize("password", [None, "secret"])
    def test_key_is_installed_by_a_single_powershell_script(
        self, monkeypatch, manager, password
    ):
        client_cls = self._server(
            monkeypatch, out=_windows_report("installed", ADMIN_KEYS)
        )

        assert manager._upload_public_key("host", 22, password) is True

        client = client_cls.instances[0]
        (command,) = client.commands  # nothing else, no POSIX command
        script = _powershell_script(command)
        assert f"$key = '{OUR_LINE}'" in script
        assert "administrators_authorized_keys" in script
        assert r".ssh\authorized_keys" in script
        assert client.closed

    def test_command_line_has_nothing_for_the_default_shell_to_interpret(
        self, monkeypatch, manager
    ):
        """It must read the same to cmd, PowerShell and a POSIX shell."""
        client_cls = self._server(
            monkeypatch, out=_windows_report("installed", ADMIN_KEYS)
        )

        manager.upload_public_key("host", 22, "secret")

        (command,) = client_cls.instances[0].commands
        assert re.fullmatch(r"[A-Za-z0-9+/=. -]+", command)

    def test_key_that_is_already_there_is_not_added_again(self, monkeypatch, manager):
        self._server(monkeypatch, out=_windows_report("present", ADMIN_KEYS))

        assert manager.upload_public_key("host", 22, "secret") is False

    def test_failure_reported_by_the_script_names_the_key_to_install_by_hand(
        self, monkeypatch, manager
    ):
        client_cls = self._server(
            monkeypatch,
            status=1,
            out=_windows_report("failed", "对路径的访问被拒绝。"),
        )

        with pytest.raises(WindowsServerKeyError, match="对路径的访问被拒绝") as e:
            manager.upload_public_key("host", 22, "secret")
        assert e.value.public_key_path == manager.public_key_path
        assert client_cls.instances[0].closed

    def test_powershell_that_cannot_be_started_is_reported(self, monkeypatch, manager):
        self._server(
            monkeypatch,
            status=1,
            err=b"'powershell.exe' is not recognized as an internal or external command",
        )

        with pytest.raises(WindowsServerKeyError, match="is not recognized"):
            manager.upload_public_key_with_existing_keys("host", 22)

    def test_report_without_a_clean_exit_is_not_trusted(self, monkeypatch, manager):
        self._server(
            monkeypatch, status=1, out=_windows_report("installed", ADMIN_KEYS)
        )

        with pytest.raises(WindowsServerKeyError):
            manager.upload_public_key("host", 22, "secret")

    def test_quotes_in_the_key_comment_stay_inside_the_string(
        self, monkeypatch, manager
    ):
        """PowerShell also ends a string at the typographic single quotes."""
        _use_key(manager, OUR_KEY, "o'brien\u2019s $(laptop)")
        client_cls = self._server(
            monkeypatch, out=_windows_report("installed", ADMIN_KEYS)
        )

        manager.upload_public_key("host", 22, "secret")

        script = _powershell_script(client_cls.instances[0].commands[0])
        key = OUR_LINE.rsplit(" ", 1)[0]
        assert f"$key = '{key} o''brien\u2019\u2019s $(laptop)'\n" in script

    def test_key_too_long_for_a_cmd_command_line_is_refused_unsent(
        self, monkeypatch, manager
    ):
        _use_key(manager, OUR_KEY, "c" * 4000)  # as long as an 8192-bit RSA key
        client_cls = self._server(monkeypatch)

        with pytest.raises(WindowsServerKeyError, match="too long"):
            manager.upload_public_key("host", 22, "secret")
        assert client_cls.instances[0].commands == []

    def test_posix_server_still_gets_the_posix_commands(self, monkeypatch, manager):
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        manager.upload_public_key("host", 22, "secret")

        commands = client_cls.instances[0].commands
        assert commands[0] == "mkdir -p ~/.ssh && chmod 700 ~/.ssh"
        assert not any("powershell" in command for command in commands)


class TestConnectionTestHostKeySafety:
    @pytest.fixture
    def fake_key(self, monkeypatch):
        monkeypatch.setattr(
            paramiko.RSAKey, "from_private_key_file", lambda path: object()
        )

    def test_host_key_change_not_swallowed(self, monkeypatch, manager, fake_key):
        """A host key mismatch must abort, never masquerade as 'no key yet'."""
        other_key = paramiko.ECDSAKey.generate()
        manager.known_hosts_path.parent.mkdir(parents=True)
        manager.known_hosts_path.write_text(
            f"{manager.host_alias} {other_key.get_name()} {other_key.get_base64()}\n"
        )
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(HostKeyChangedError):
            manager.test_ssh_connection("host", 22)
        assert client_cls.instances[0].closed

    @pytest.mark.parametrize(
        "content",
        [
            # Broken base64: paramiko raises InvalidHostKey, not SSHException
            "cpolar-server ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI\n",
            None,  # not a file at all
        ],
    )
    def test_unusable_host_key_file_is_reported_as_such(
        self, monkeypatch, manager, fake_key, content
    ):
        """Neither a traceback nor "server unreachable"; the file is left alone."""
        manager.known_hosts_path.parent.mkdir(parents=True)
        if content is None:
            manager.known_hosts_path.mkdir()
        else:
            manager.known_hosts_path.write_text(content)
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(SSHError, match="host key file") as excinfo:
            manager.test_ssh_connection("host", 22)
        assert "sshd" not in str(excinfo.value)
        if content is not None:
            assert manager.known_hosts_path.read_text() == content


class TestConnectionTest:
    """The pre-check must offer what the generated ssh config will offer."""

    @pytest.fixture
    def fake_key(self, monkeypatch):
        key = object()
        monkeypatch.setattr(paramiko.RSAKey, "from_private_key_file", lambda path: key)
        return key

    def test_offers_configured_key_and_agent_but_no_default_key_files(
        self, monkeypatch, manager, fake_key
    ):
        """IdentityFile without IdentitiesOnly: ssh adds agent keys, but an
        explicit IdentityFile makes it skip ~/.ssh/id_*."""
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.test_ssh_connection("host", 22) is True
        kwargs = client_cls.instances[0].connect_kwargs
        assert kwargs["pkey"] is fake_key
        assert kwargs["allow_agent"] is True
        assert kwargs["look_for_keys"] is False

    def test_rejected_key_returns_false(self, monkeypatch, manager, fake_key):
        client_cls = make_fake_client_class(
            connect_error=paramiko.AuthenticationException("rejected")
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.test_ssh_connection("host", 22) is False
        assert client_cls.instances[0].closed

    def test_connection_lost_while_authenticating_counts_as_rejected(
        self, monkeypatch, manager, fake_key
    ):
        """After the handshake a failure is about credentials; the bootstrap
        opens a fresh connection and reports a server that is really gone."""
        client_cls = make_fake_client_class(connect_error=EOFError())
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.test_ssh_connection("host", 22) is False

    def test_agent_is_left_out_when_ssh_itself_would_not_use_it(
        self, monkeypatch, manager, fake_key
    ):
        """IdentitiesOnly in the user's own ssh configuration: a key that only
        the agent holds would pass the check here and then never be offered
        by `ssh`. Without it the check fails, and the key gets installed."""
        asked = []
        monkeypatch.setattr(
            ssh_module,
            "_ssh_offers_agent_keys",
            lambda user, hostname, port: asked.append((user, hostname, port)) or False,
        )
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.test_ssh_connection("host", 2222) is True

        assert asked == [("ubuntu", "host", 2222)]
        kwargs = client_cls.instances[0].connect_kwargs
        assert kwargs["pkey"] is fake_key
        assert kwargs["allow_agent"] is False

    def test_connection_closed_without_a_word_still_gets_a_reason(
        self, monkeypatch, manager, fake_key
    ):
        """paramiko raises a bare EOFError when the server hangs up during the
        handshake; the message must not end in an empty reason ("...: .")."""
        client_cls = make_fake_client_class(connect_error=EOFError(), reached=False)
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(SSHError) as failure:
            manager.test_ssh_connection("host", 22)

        assert "host:22: the server closed the connection. " in str(failure.value)

    def test_connection_reset_while_authenticating_is_reported_not_guessed_at(
        self, monkeypatch, manager, fake_key
    ):
        client_cls = make_fake_client_class(
            connect_error=ConnectionResetError(54, "Connection reset by peer")
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(SSHError, match="lost during authentication"):
            manager.test_ssh_connection("host", 22)

    def test_server_that_takes_no_keys_at_all_rejects_the_key(
        self, monkeypatch, manager, fake_key
    ):
        """Password-only server: the bootstrap goes on to ask for one."""
        client_cls = make_fake_client_class(
            connect_error=paramiko.BadAuthenticationType(
                "Bad authentication type", ["password"]
            )
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.test_ssh_connection("host", 22) is False

    def test_missing_key_only_probes_that_the_server_is_there(
        self, monkeypatch, manager
    ):
        client_cls = make_fake_client_class(
            connect_error=paramiko.SSHException("No authentication methods available")
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)
        manager.private_key_path.unlink()

        assert manager.test_ssh_connection("host", 22) is False
        kwargs = client_cls.instances[0].connect_kwargs
        assert kwargs.get("pkey") is None
        assert kwargs["allow_agent"] is False
        assert kwargs["look_for_keys"] is False

    def test_missing_key_and_unreachable_server_raises(self, monkeypatch, manager):
        """A first connection must not start by asking for a password."""
        client_cls = make_fake_client_class(
            connect_error=ConnectionRefusedError(61, "Connection refused"),
            reached=False,
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)
        manager.private_key_path.unlink()

        with pytest.raises(SSHError, match="host:22"):
            manager.test_ssh_connection("host", 22)

    @pytest.mark.parametrize(
        "error",
        [
            ConnectionRefusedError(61, "Connection refused"),
            socket.timeout("timed out"),
            EOFError(),
        ],
    )
    def test_unreachable_server_raises_instead_of_bootstrapping(
        self, monkeypatch, manager, fake_key, error
    ):
        """A network fault is not a key problem: never ask for a password."""
        client_cls = make_fake_client_class(connect_error=error, reached=False)
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(
            ServerUnreachableError, match="Cannot reach the SSH service at host:22"
        ):
            manager.test_ssh_connection("host", 22)
        assert client_cls.instances[0].closed

    @pytest.mark.parametrize(
        "error",
        [
            paramiko.SSHException("Error reading SSH protocol banner"),
            paramiko.ssh_exception.IncompatiblePeer("no acceptable ciphers"),
            # Types outside paramiko's hierarchy must not escape as tracebacks
            ValueError("p*q must equal modulus."),
        ],
    )
    def test_failed_handshake_is_reported_as_such(
        self, monkeypatch, manager, fake_key, error
    ):
        client_cls = make_fake_client_class(connect_error=error, reached=False)
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(
            ServerUnreachableError, match="SSH handshake with host:22 failed"
        ):
            manager.test_ssh_connection("host", 22)
        assert client_cls.instances[0].closed

    @pytest.mark.parametrize(
        "error",
        [
            socket.gaierror(11001, "getaddrinfo failed"),  # Windows
            socket.gaierror(8, "nodename nor servname provided, or not known"),
            socket.gaierror(-2, "Name or service not known"),  # Linux
            socket.gaierror(-3, "Temporary failure in name resolution"),
        ],
    )
    def test_name_that_does_not_resolve_is_not_blamed_on_the_server(
        self, monkeypatch, manager, fake_key, error
    ):
        """Some networks will not resolve tunnel host names. Sending the user
        to check sshd on the server would be sending them the wrong way."""
        client_cls = make_fake_client_class(connect_error=error, reached=False)
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(ServerUnreachableError) as failure:
            manager.test_ssh_connection("1.tcp.cpolar.top", 22)

        message = str(failure.value)
        assert "Cannot resolve the tunnel's host name 1.tcp.cpolar.top" in message
        assert error.strerror in message  # what the system said, to search for
        assert "DNS" in message
        assert "sshd" not in message
        assert client_cls.instances[0].closed

    def test_server_that_answered_and_then_went_quiet_was_not_unreachable(
        self, monkeypatch, manager
    ):
        """Its host key was checked, so this is the right server: what the
        connect flow does for a server it never reached does not apply."""
        client_cls = make_fake_client_class(
            connect_error=ConnectionResetError(54, "Connection reset by peer")
        )
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        with pytest.raises(SSHError, match="lost during authentication") as failure:
            manager.test_ssh_connection("host", 22)

        assert not isinstance(failure.value, ServerUnreachableError)

    @pytest.mark.parametrize(
        "content",
        [
            b"not a key\n",
            # e.g. a key saved by a PowerShell redirect: UnicodeDecodeError
            "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n".encode("utf-16"),
        ],
    )
    def test_unloadable_key_raises(self, manager, content):
        manager.private_key_path.write_bytes(content)

        with pytest.raises(SSHError, match="id_rsa_cpolar is not a usable SSH"):
            manager.test_ssh_connection("host", 22)

    def test_unreadable_key_path_raises(self, manager):
        manager.private_key_path.unlink()
        manager.private_key_path.mkdir()

        with pytest.raises(SSHError, match="Cannot read SSH private key"):
            manager.test_ssh_connection("host", 22)


class TestWhatSshWouldOffer:
    """`ssh -G` prints the configuration `ssh` would use, without connecting."""

    @staticmethod
    def _ssh_prints(monkeypatch, output=b"", returncode=0, error=None):
        commands = []

        def fake_run(command, **kwargs):
            commands.append(command)
            if error is not None:
                raise error
            return subprocess.CompletedProcess(command, returncode, output, b"")

        monkeypatch.setattr(ssh_module.subprocess, "run", fake_run)
        return commands

    @pytest.mark.parametrize(
        "output, offers",
        [
            (b"user ubuntu\nidentitiesonly no\nidentityfile ~/.ssh/id_rsa\n", True),
            (b"identitiesonly yes\n", False),
            (b"IdentitiesOnly yes\r\n", False),
            (b"identitiesonly no\nidentityagent none\n", False),
            (b"identitiesonly no\nidentityagent SSH_AUTH_SOCK\n", True),
            (b"identitiesonly no\nidentityagent ~/.1password/agent.sock\n", True),
            (b"", True),
        ],
    )
    def test_agent_keys_are_offered_unless_the_configuration_says_otherwise(
        self, monkeypatch, output, offers
    ):
        commands = self._ssh_prints(monkeypatch, output)

        assert real_ssh_offers_agent_keys("John Smith", "host", 2222) is offers
        assert commands == [["ssh", "-G", "-p", "2222", "John Smith@host"]]

    @pytest.mark.parametrize(
        "problem",
        [
            {"error": FileNotFoundError("ssh")},
            {"error": subprocess.TimeoutExpired("ssh", 10)},
            {"output": b"identitiesonly yes\n", "returncode": 255},
        ],
    )
    def test_default_of_ssh_is_assumed_when_it_cannot_be_asked(
        self, monkeypatch, problem
    ):
        self._ssh_prints(monkeypatch, **problem)

        assert real_ssh_offers_agent_keys("ubuntu", "host", 22) is True

    @pytest.mark.skipif(shutil.which("ssh") is None, reason="needs the OpenSSH client")
    def test_real_ssh_reports_the_option_under_the_name_that_is_read(self):
        """Its value depends on whose machine this is; the name must not."""
        result = subprocess.run(
            ["ssh", "-G", "-p", "22", "someone@host.invalid"],
            capture_output=True,
            stdin=subprocess.DEVNULL,
        )

        assert result.returncode == 0, result.stderr
        names = [line.split(b" ")[0] for line in result.stdout.splitlines()]
        assert b"identitiesonly" in names


class TestExistingKeyTypes:
    """ssh_key_path may point at a key the server already accepts."""

    @pytest.mark.parametrize(
        "kind, key_name",
        [
            ("ed25519", "ssh-ed25519"),
            ("ecdsa", "ecdsa-sha2-nistp256"),
            ("rsa", "ssh-rsa"),
        ],
    )
    def test_connection_test_offers_existing_key(
        self, monkeypatch, manager, write_private_key, kind, key_name
    ):
        write_private_key(manager.private_key_path, kind)
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.test_ssh_connection("host", 22) is True
        assert client_cls.instances[0].connect_kwargs["pkey"].get_name() == key_name

    @pytest.mark.parametrize("pkcs8", [False, True])
    @pytest.mark.parametrize("kind", ["ed25519", "ecdsa", "rsa"])
    def test_passphrase_protected_key_is_rejected_clearly(
        self, manager, write_private_key, kind, pkcs8
    ):
        write_private_key(manager.private_key_path, kind, b"pw", pkcs8=pkcs8)

        # Wording used only for this cause, unlike the generic load failure
        with pytest.raises(SSHError, match="is passphrase-protected"):
            manager.test_ssh_connection("host", 22)

    @pytest.mark.parametrize("kind", ["ecdsa", "rsa"])
    def test_pkcs8_key_is_loaded_like_any_other(
        self, monkeypatch, manager, write_private_key, kind
    ):
        """ "BEGIN PRIVATE KEY", as openssl writes keys: ssh takes such a file
        as IdentityFile, so the key check has to be able to offer it."""
        written = write_private_key(manager.private_key_path, kind, pkcs8=True)
        assert b"-----BEGIN PRIVATE KEY-----" in manager.private_key_path.read_bytes()
        expected = (
            written.public_key()
            .public_bytes(
                serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH
            )
            .decode()
            .split()
        )
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)

        assert manager.test_ssh_connection("host", 22) is True

        offered = client_cls.instances[0].connect_kwargs["pkey"]
        assert [offered.get_name(), offered.get_base64()] == expected

    def test_pkcs8_ed25519_key_is_refused_with_the_reason(
        self, manager, write_private_key
    ):
        """Most builds of ssh cannot read that combination (the one on macOS
        cannot, for one): accepting it here would end in ssh's "invalid
        format" after the check had said the connection was fine."""
        write_private_key(manager.private_key_path, "ed25519", pkcs8=True)

        with pytest.raises(SSHError, match="Ed25519 key in PKCS#8 form"):
            manager.test_ssh_connection("host", 22)

    @pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs ssh-keygen")
    @pytest.mark.parametrize("kind", ["ecdsa", "rsa"])
    def test_pkcs8_key_means_the_same_key_to_openssh(
        self, manager, write_private_key, kind
    ):
        write_private_key(manager.private_key_path, kind, pkcs8=True)

        theirs = subprocess.run(
            ["ssh-keygen", "-y", "-P", "", "-f", str(manager.private_key_path)],
            capture_output=True,
            text=True,
        )

        assert theirs.returncode == 0, theirs.stderr
        ours = ssh_module.load_private_key(manager.private_key_path)
        assert theirs.stdout.split()[:2] == [ours.get_name(), ours.get_base64()]

    def test_missing_public_key_is_rebuilt_for_ed25519(
        self, manager, write_private_key
    ):
        write_private_key(manager.private_key_path, "ed25519")
        manager.public_key_path.unlink()

        assert manager.generate_ssh_key() is False  # existing key is kept
        key = paramiko.Ed25519Key.from_private_key_file(str(manager.private_key_path))
        public = manager.public_key_path.read_text(encoding="utf-8").split()
        assert public[:2] == ["ssh-ed25519", key.get_base64()]

    def test_generated_key_pair_matches(self, manager):
        manager.private_key_path.unlink()
        manager.public_key_path.unlink()

        assert manager.generate_ssh_key() is True
        key = paramiko.RSAKey.from_private_key_file(str(manager.private_key_path))
        public = manager.public_key_path.read_text(encoding="utf-8").split()
        assert public == ["ssh-rsa", key.get_base64(), "cpolar-connect"]


class TestPrivateKeyAccess:
    """ssh ignores a private key that anyone but its owner can access."""

    @pytest.fixture
    def fresh(self, tmp_path):
        """A manager whose key directory does not exist yet."""
        config = CpolarConfig(
            username="user@example.com",
            server_user="ubuntu",
            ssh_key_path=str(tmp_path / "fresh" / ".ssh" / "id_rsa_cpolar"),
        )
        return SSHManager(config)

    @pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs ssh-keygen")
    def test_generated_key_is_accepted_by_openssh(self, fresh):
        """ssh-keygen applies the access check ssh does. On Windows it is
        about the access list: recent Python versions give a directory made
        with mode 0o700 (pytest's temp directory here, ~/.ssh in the tool
        before) an entry that its files inherit and that OpenSSH rejects."""
        assert fresh.generate_ssh_key() is True

        result = subprocess.run(
            ["ssh-keygen", "-y", "-f", str(fresh.private_key_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0 and sys.platform == "win32":
            listing = subprocess.run(
                ["icacls", str(fresh.private_key_path)], capture_output=True, text=True
            )
            pytest.fail(f"{result.stderr}\naccess list:\n{listing.stdout}")
        assert result.returncode == 0, result.stderr
        public = fresh.public_key_path.read_text(encoding="utf-8").split()
        assert result.stdout.split()[:2] == public[:2]

    def test_windows_key_is_left_to_the_user_system_and_administrators(
        self, monkeypatch, fresh
    ):
        commands = []

        def fake_run(command, **kwargs):
            commands.append(command)
            output = (
                b'"pc\\me","S-1-5-21-1-2-3-1001"\r\n' if "whoami" in command else b""
            )
            return subprocess.CompletedProcess(command, 0, output, b"")

        monkeypatch.setattr(ssh_module.platform, "system", lambda: "Windows")
        monkeypatch.setattr(ssh_module.subprocess, "run", fake_run)

        assert fresh.generate_ssh_key() is True

        assert commands[-1] == [
            "icacls",
            str(fresh.private_key_path),
            "/inheritance:r",
            "/grant:r",
            "*S-1-5-21-1-2-3-1001:F",
            "*S-1-5-18:F",
            "*S-1-5-32-544:F",
            "/remove",
            "*S-1-3-4",
        ]

    def test_windows_ssh_directory_is_not_created_with_mode_700(
        self, monkeypatch, fresh
    ):
        """That mode is what makes Python add the entry OpenSSH rejects."""
        modes = []
        real_mkdir = Path.mkdir

        def recording_mkdir(self, mode=0o777, parents=False, exist_ok=False):
            modes.append(mode)
            return real_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)

        monkeypatch.setattr(ssh_module.platform, "system", lambda: "Windows")
        monkeypatch.setattr(Path, "mkdir", recording_mkdir)

        fresh.ensure_ssh_directory()

        assert fresh.ssh_dir.is_dir()
        assert 0o700 not in modes

    def test_failing_to_set_the_access_list_does_not_lose_the_key(
        self, monkeypatch, fresh
    ):
        def failing_run(command, **kwargs):
            raise OSError("no such program")

        monkeypatch.setattr(ssh_module.platform, "system", lambda: "Windows")
        monkeypatch.setattr(ssh_module.subprocess, "run", failing_run)

        assert fresh.generate_ssh_key() is True
        assert fresh.public_key_path.exists()


def make_shell_backed_client_class(shell, server_home):
    """An SSHClient stand-in whose commands run in a real shell.

    The "server" is a scratch home directory, so what the upload leaves in
    authorized_keys is decided by an actual shell rather than by a script of
    expected commands.
    """

    class ShellBackedClient:
        def set_missing_host_key_policy(self, policy):
            self.policy = policy

        def connect(self, **kwargs):
            self.policy.missing_host_key(self, kwargs["hostname"], HOST_KEY)

        def exec_command(self, command, timeout=None):
            # -f: csh and tcsh skip their start-up files, which only cost time
            fast = ["-f"] if shell in ("csh", "tcsh") else []
            result = subprocess.run(
                [shell, *fast, "-c", command],
                env={"HOME": str(server_home), "PATH": os.environ["PATH"]},
                capture_output=True,
            )
            return (
                None,
                FakeStream(result.stdout, result.returncode),
                FakeStream(result.stderr, result.returncode),
            )

        def get_transport(self):
            return FakeTransport(LINUX_SERVER)

        def close(self):
            pass

    return ShellBackedClient


def _public_line(key, comment=""):
    return f"{key.get_name()} {key.get_base64()} {comment}".rstrip()


def _fingerprint(key):
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def _keys_openssh_sees(authorized_keys: Path):
    """Fingerprints of the entries OpenSSH recognizes in the file, in order."""
    result = subprocess.run(
        ["ssh-keygen", "-lf", str(authorized_keys)], capture_output=True, text=True
    )
    return [
        line.split()[1] for line in result.stdout.splitlines() if " SHA256:" in line
    ]


SHELLS = [s for s in ("sh", "dash", "bash", "zsh", "csh", "tcsh") if shutil.which(s)]


# The shell stands in for a POSIX server; on Windows it would be Git's
# emulation, which says nothing about one
@pytest.mark.posix_only
@pytest.mark.skipif(
    not SHELLS or shutil.which("ssh-keygen") is None,
    reason="needs a POSIX shell and ssh-keygen",
)
@pytest.mark.parametrize("shell", SHELLS)
class TestUploadIntoRealAuthorizedKeys:
    """What the upload leaves in authorized_keys, as OpenSSH itself reads it."""

    @pytest.fixture
    def our_key(self, manager):
        key = paramiko.ECDSAKey.generate()
        _use_key(manager, key)
        return key

    @pytest.fixture
    def authorized_keys(self, monkeypatch, tmp_path, shell):
        home = tmp_path / "server-home"
        (home / ".ssh").mkdir(parents=True)
        monkeypatch.setattr(
            paramiko, "SSHClient", make_shell_backed_client_class(shell, home)
        )
        return home / ".ssh" / "authorized_keys"

    def test_creates_the_file_with_owner_only_access(
        self, manager, our_key, authorized_keys
    ):
        assert manager.upload_public_key("host", 22, "secret") is True

        assert _keys_openssh_sees(authorized_keys) == [_fingerprint(our_key)]
        assert authorized_keys.stat().st_mode & 0o777 == 0o600
        assert authorized_keys.parent.stat().st_mode & 0o777 == 0o700

    def test_appends_after_a_complete_last_line(
        self, manager, our_key, authorized_keys
    ):
        theirs = paramiko.ECDSAKey.generate()
        authorized_keys.write_text(_public_line(theirs, "me@laptop") + "\n")

        assert manager.upload_public_key("host", 22, "secret") is True

        assert _keys_openssh_sees(authorized_keys) == [
            _fingerprint(theirs),
            _fingerprint(our_key),
        ]
        # No blank line is introduced when none is needed
        assert authorized_keys.read_text().count("\n") == 2

    @pytest.mark.parametrize("comment", ["me@laptop", ""])
    def test_last_line_without_a_newline_keeps_both_keys_usable(
        self, manager, our_key, authorized_keys, comment
    ):
        """A plain append would glue our key onto that line: sshd would not
        see it, and with no comment the existing key would break as well."""
        theirs = paramiko.ECDSAKey.generate()
        authorized_keys.write_text(_public_line(theirs, comment))  # no "\n"

        assert manager.upload_public_key("host", 22, "secret") is True

        assert _keys_openssh_sees(authorized_keys) == [
            _fingerprint(theirs),
            _fingerprint(our_key),
        ]

    @pytest.mark.parametrize(
        "comment",
        [
            r"CORP\nina@pc",  # \n, \t, \c ... are escapes to the echo of
            r"lab\tom",  # zsh, dash and sh, though not to bash's
            r"me\cut-here",
            r"C:\Users\me",
            "o'brien's \"laptop\"",
            "$HOME `id` %s ; rm x & | > y",
            "-n -e looks like an option",
        ],
    )
    def test_key_line_is_written_exactly_as_it_is(
        self, manager, authorized_keys, comment
    ):
        """An existing key brings its own comment, and that is free text."""
        key = paramiko.ECDSAKey.generate()
        line = _use_key(manager, key, comment)

        assert manager.upload_public_key("host", 22, "secret") is True

        assert authorized_keys.read_text() == line + "\n"
        assert _keys_openssh_sees(authorized_keys) == [_fingerprint(key)]

    def test_second_upload_changes_nothing(self, manager, our_key, authorized_keys):
        assert manager.upload_public_key("host", 22, "secret") is True
        content = authorized_keys.read_bytes()

        assert manager.upload_public_key("host", 22, "secret") is False
        assert authorized_keys.read_bytes() == content

    @pytest.mark.parametrize("last_line_ended_with", ["", " ", "\t"])
    def test_key_glued_onto_another_line_is_installed_properly(
        self, manager, our_key, authorized_keys, last_line_ended_with
    ):
        """What older versions left behind: our key inside another entry's
        comment. It must not count as installed, or it never gets fixed."""
        theirs = paramiko.ECDSAKey.generate()
        authorized_keys.write_text(
            _public_line(theirs, "me@laptop")
            + last_line_ended_with
            + _public_line(our_key, "cpolar-connect")
            + "\n"
        )
        assert _keys_openssh_sees(authorized_keys) == [_fingerprint(theirs)]

        assert manager.upload_public_key("host", 22, "secret") is True

        assert _fingerprint(our_key) in _keys_openssh_sees(authorized_keys)

    def test_commented_out_key_is_not_treated_as_installed(
        self, manager, our_key, authorized_keys
    ):
        authorized_keys.write_text(
            "# " + _public_line(our_key, "cpolar-connect") + "\n"
        )

        assert manager.upload_public_key("host", 22, "secret") is True

        assert _keys_openssh_sees(authorized_keys) == [_fingerprint(our_key)]


class TestIsAuthorized:
    OURS = "ssh-rsa BBBB cpolar-connect"

    @pytest.mark.parametrize(
        "content",
        [
            "ssh-rsa BBBB cpolar-connect\n",
            "ssh-ed25519 AAAA a\nssh-rsa BBBB another-comment\n",
            'command="echo hi",no-pty ssh-rsa BBBB cpolar-connect\r\n',
            'command="echo \\"hi there\\"",from="10.0.0.0/8" ssh-rsa BBBB c\n',
            " \tssh-rsa BBBB indented\n",
            "ssh-rsa\tBBBB\ttabs\n",
            "ssh-rsa BBBB\x00 what follows a NUL byte is not read\n",
            "ssh-rsa BBBB",  # no comment, no newline
        ],
    )
    def test_entry_is_recognized(self, content):
        assert _is_authorized(self.OURS, content) is True

    @pytest.mark.parametrize(
        "content",
        [
            "",
            "ssh-ed25519 AAAA a\n",
            "ssh-ed25519 AAAA me@laptopssh-rsa BBBB cpolar-connect\n",
            "ssh-ed25519 AAAAssh-rsa BBBB cpolar-connect\n",
            "# ssh-rsa BBBB cpolar-connect\n",
            "ssh-ed25519 BBBB cpolar-connect\n",  # same data under another type
            # Glued on after a blank: still only the first key's comment
            "ssh-ed25519 AAAA me@laptop ssh-rsa BBBB cpolar-connect\n",
            "ssh-ed25519 AAAA me@laptop\tssh-rsa BBBB cpolar-connect\n",
            # Blanks are space and tab to sshd, lines end at \n: nothing else
            "ssh-rsa\u00a0BBBB cpolar-connect\n",
            "ssh-ed25519 AAAA a\x0cssh-rsa BBBB cpolar-connect\n",
            "ssh-ed25519 AAAA a\u2028ssh-rsa BBBB cpolar-connect\n",
            "ssh-ed25519 AAAA a\x85ssh-rsa BBBB cpolar-connect\n",
            'command="never closed ssh-rsa BBBB cpolar-connect\n',
            "no-pty # ssh-rsa BBBB\n",
            # A line is a C string to sshd: nothing after a NUL byte counts.
            # This is our key after a line break of a UTF-16 file
            "s\x00s\x00h\x00\r\x00\n\x00ssh-rsa BBBB cpolar-connect\n",
        ],
    )
    def test_anything_else_is_not(self, content):
        assert _is_authorized(self.OURS, content) is False


class TestPublicKeyFile:
    """The .pub next to the key is what gets installed, so it is checked."""

    @pytest.mark.parametrize(
        "content",
        [
            b"garbage\n",
            b"",
            OUR_LINE.encode("utf-16"),  # PowerShell 5.1: ssh-keygen -y > key.pub
            "ssh-ed25519 AAAA \u516c\u53f8\n".encode("gbk"),
            b"---- BEGIN SSH2 PUBLIC KEY ----\nAAAA\n---- END SSH2 PUBLIC KEY ----\n",
        ],
    )
    def test_unusable_public_key_file_is_rejected_before_connecting(
        self, monkeypatch, manager, content
    ):
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)
        manager.public_key_path.write_bytes(content)

        with pytest.raises(SSHError, match="not a valid public key"):
            manager.upload_public_key("host", 22, "secret")
        assert client_cls.instances == []

    def test_public_key_path_that_cannot_be_read_is_rejected_the_same_way(
        self, monkeypatch, manager
    ):
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)
        manager.public_key_path.unlink()
        manager.public_key_path.mkdir()

        with pytest.raises(SSHError, match="not a valid public key"):
            manager.upload_public_key_with_existing_keys("host", 22)
        assert client_cls.instances == []

    def test_public_key_of_another_key_is_never_installed(self, monkeypatch, manager):
        """A stale .pub would authorize some other key on the server, and
        `ssh` refuses a key pair whose halves do not match anyway."""
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)
        other = paramiko.ECDSAKey.generate()
        manager.public_key_path.write_text(_public_line(other, "stale") + "\n")

        with pytest.raises(SSHError, match="does not belong to the private key"):
            manager.upload_public_key("host", 22, "secret")
        assert client_cls.instances == []

    def test_byte_order_mark_and_further_lines_are_not_installed(
        self, monkeypatch, manager
    ):
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)
        other = paramiko.ECDSAKey.generate()
        manager.public_key_path.write_bytes(
            b"\xef\xbb\xbf"
            + OUR_LINE.encode()
            + b"\r\n"
            + _public_line(other, "someone-else").encode()
            + b"\n"
        )

        assert manager.upload_public_key("host", 22, "secret") is True

        (append,) = [c for c in client_cls.instances[0].commands if "ecdsa-" in c]
        assert append == f"printf '%s\\n' '{OUR_LINE}' >> ~/.ssh/authorized_keys"


class TestServerThatStopsAnswering:
    """A tunnel can die without a word while the key is being installed."""

    def test_upload_gives_up_instead_of_waiting_forever(
        self, monkeypatch, manager, ssh_server
    ):
        monkeypatch.setattr(ssh_module, "_REMOTE_COMMAND_TIMEOUT", 1)
        port, server = ssh_server([paramiko.ECDSAKey.generate()], accept_commands=True)
        started = time.monotonic()

        with pytest.raises(SSHError, match="stopped answering"):
            manager.upload_public_key("127.0.0.1", port, "right")

        assert server.commands == ["mkdir -p ~/.ssh && chmod 700 ~/.ssh"]
        assert time.monotonic() - started < 20


@pytest.mark.posix_only
class TestKeyFileOthersCanRead:
    """ssh ignores a private key of the user's own that group or others can
    access; paramiko does not look. The key check must not say "OK" for a key
    that ssh will then refuse to use."""

    @pytest.fixture
    def server(self, monkeypatch):
        client_cls = make_fake_client_class()
        monkeypatch.setattr(paramiko, "SSHClient", client_cls)
        return client_cls

    @pytest.mark.parametrize("mode", [0o644, 0o640, 0o604])
    def test_key_ssh_would_refuse_is_reported_with_the_fix(self, manager, server, mode):
        manager.private_key_path.chmod(mode)

        with pytest.raises(SSHError, match="chmod 600") as failure:
            manager.test_ssh_connection("host", 22)

        assert str(manager.private_key_path) in str(failure.value)
        assert server.instances == []  # found before anything is sent

    @pytest.mark.parametrize("mode", [0o600, 0o400])
    def test_key_only_its_owner_can_read_is_used(self, manager, server, mode):
        manager.private_key_path.chmod(mode)

        assert manager.test_ssh_connection("host", 22) is True

    def test_key_that_belongs_to_someone_else_is_not_judged(
        self, monkeypatch, manager, server
    ):
        """ssh applies the rule to the user's own files only: a key shared
        through a group is owned by another account, and works."""
        manager.private_key_path.chmod(0o640)
        owner = manager.private_key_path.stat().st_uid
        monkeypatch.setattr(ssh_module.os, "getuid", lambda: owner + 1)

        assert manager.test_ssh_connection("host", 22) is True

    @pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs ssh-keygen")
    @pytest.mark.parametrize("mode, accepted", [(0o600, True), (0o644, False)])
    def test_openssh_draws_the_line_in_the_same_place(self, manager, mode, accepted):
        manager.private_key_path.chmod(mode)

        result = subprocess.run(
            ["ssh-keygen", "-y", "-P", "", "-f", str(manager.private_key_path)],
            capture_output=True,
            text=True,
        )

        assert (result.returncode == 0) is accepted, result.stderr
