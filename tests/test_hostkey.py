"""
Tests for host key verification (TOFU keyed by SSH alias).

The tunnel hostname/port change on every cpolar restart, so host keys are
recorded under the stable ssh_host_alias in a dedicated known_hosts file.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path, PurePosixPath

import paramiko
import pytest

from cpolar_connect.config import CpolarConfig
from cpolar_connect.exceptions import HostKeyChangedError, SSHError
from cpolar_connect.ssh import (
    AliasHostKeyPolicy,
    SSHManager,
    _config_path,
    _config_token,
)
from cpolar_connect.tunnel import TunnelInfo

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

    @pytest.mark.posix_only
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

    def test_key_of_a_type_not_on_record_is_a_changed_key(self, tmp_path):
        """Accepting it would let anyone on the tunnel's path in, simply by
        presenting a key of another type than the one on record. `ssh` treats
        it as a changed key as well."""
        known_hosts = tmp_path / "known_hosts"
        rsa_key = _make_key()
        AliasHostKeyPolicy(ALIAS, known_hosts).missing_host_key(None, "h", rsa_key)
        before = known_hosts.read_text()

        with pytest.raises(HostKeyChangedError):
            AliasHostKeyPolicy(ALIAS, known_hosts).missing_host_key(
                None, "h", paramiko.ECDSAKey.generate()
            )

        assert known_hosts.read_text() == before

    def test_every_key_on_record_is_accepted(self, tmp_path):
        """Files written by earlier versions can hold a key per type."""
        known_hosts = tmp_path / "known_hosts"
        rsa_key = _make_key()
        ecdsa_key = paramiko.ECDSAKey.generate()
        known_hosts.write_text(
            f"{ALIAS} {rsa_key.get_name()} {rsa_key.get_base64()}\n"
            f"{ALIAS} {ecdsa_key.get_name()} {ecdsa_key.get_base64()}\n"
        )

        for key in (rsa_key, ecdsa_key):
            policy = AliasHostKeyPolicy(ALIAS, known_hosts)
            policy.missing_host_key(None, "h", key)
            assert policy.accepted

    @pytest.mark.parametrize(
        "damaged",
        [
            f"{ALIAS} ssh-ed25519",  # cut short
            f"{ALIAS} ssh-ed25519 AAAA",  # decodes, but is no key
            f"{ALIAS} ssh-nonsense AAAA",
        ],
    )
    def test_damaged_record_is_never_skipped(self, tmp_path, damaged):
        """paramiko passes over a line it cannot parse. For the alias's own
        record that would mean trusting whatever key comes next."""
        known_hosts = tmp_path / "known_hosts"
        known_hosts.write_text(damaged + "\n")

        with pytest.raises(SSHError, match="host key file") as failure:
            AliasHostKeyPolicy(ALIAS, known_hosts).missing_host_key(
                None, "h", _make_key()
            )

        assert not isinstance(failure.value, HostKeyChangedError)
        assert known_hosts.read_text() == damaged + "\n"

    def test_damaged_hashed_record_is_reported_as_a_problem_with_the_file(
        self, tmp_path
    ):
        """`ssh` writes hashed names when HashKnownHosts is on. Looking one up
        fails if its salt is damaged; that is not a failed handshake."""
        known_hosts = tmp_path / "known_hosts"
        key = _make_key()
        known_hosts.write_text(f"|1|abc|def {key.get_name()} {key.get_base64()}\n")

        with pytest.raises(SSHError, match="host key file"):
            AliasHostKeyPolicy(ALIAS, known_hosts).missing_host_key(None, "h", key)


class TestHostKeyOverARealHandshake:
    """Which key a server presents is settled in the handshake, by what the
    client asks for. These run that handshake for real."""

    @pytest.fixture
    def manager(self, tmp_path):
        return SSHManager(
            _make_config(tmp_path), known_hosts_path=tmp_path / "known_hosts"
        )

    @staticmethod
    def _connect(manager, port, password="right"):
        client = manager._open_client(
            "127.0.0.1",
            port,
            10,
            password=password,
            allow_agent=False,
            look_for_keys=False,
        )
        if client is not None:
            client.close()
        return client

    @staticmethod
    def _record(manager, key):
        manager.known_hosts_path.write_text(
            f"{ALIAS} {key.get_name()} {key.get_base64()}\n"
        )

    def test_first_connection_records_the_one_key_presented(self, manager, ssh_server):
        port, _server = ssh_server([_make_key(), paramiko.ECDSAKey.generate()])

        assert self._connect(manager, port) is not None

        assert len(manager.known_hosts_path.read_text().splitlines()) == 1

    def test_server_is_asked_for_the_key_type_on_record(self, manager, ssh_server):
        """A server holds a key per type. Left to the defaults it would
        present its ECDSA key, which is not the one on record."""
        rsa_key = _make_key()
        port, _server = ssh_server([paramiko.ECDSAKey.generate(), rsa_key])
        self._record(manager, rsa_key)
        before = manager.known_hosts_path.read_text()

        assert self._connect(manager, port) is not None

        assert manager.known_hosts_path.read_text() == before

    def test_impostor_with_a_key_of_another_type_gets_no_password(
        self, manager, ssh_server
    ):
        """It cannot present the recorded key, so it offers one of a type
        that is not on record. That must end the connection before the
        server password is typed in for it."""
        self._record(manager, paramiko.ECDSAKey.generate())  # the real server's
        port, impostor = ssh_server([_make_key()])
        before = manager.known_hosts_path.read_text()

        with pytest.raises(HostKeyChangedError):
            self._connect(manager, port, password="the-server-password")

        assert impostor.passwords == []
        assert manager.known_hosts_path.read_text() == before

    def test_wrong_password_is_still_just_rejected(self, manager, ssh_server):
        port, server = ssh_server([paramiko.ECDSAKey.generate()])

        assert self._connect(manager, port, password="wrong") is None

        assert server.passwords == ["wrong"]


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
        # The path is quoted when the temp dir needs it (e.g. a space)
        assert _option(command, "UserKnownHostsFile") == str(manager.known_hosts_path)
        assert "StrictHostKeyChecking=no" not in command
        assert "UserKnownHostsFile=/dev/null" not in command


def _option(command, name):
    """Value of an `-o name=value` option, as ssh reads a pytest temp path."""
    (value,) = [c.split("=", 1)[1] for c in command if c.startswith(f"{name}=")]
    return value[1:-1] if value.startswith('"') else value


TUNNEL = TunnelInfo(
    url="tcp://1.tcp.cpolar.top:12345", hostname="1.tcp.cpolar.top", port=12345
)


class TestConfigTokens:
    """How values are rendered for ssh_config and `ssh -o`."""

    @pytest.mark.parametrize(
        "value",
        [
            "/home/me/.ssh/id_rsa_cpolar",
            "ubuntu",
            "/Users/张三/.ssh/id_rsa_cpolar",
            # A lone backslash is literal to OpenSSH: Windows values need nothing
            r"C:\Users\zhang\.ssh\id_rsa_cpolar",
            r"C:\Users\张三\.cpolar_connect\accounts\default\known_hosts",
            r"DOMAIN\user",
            "user@corp",
        ],
    )
    def test_value_that_always_worked_is_written_unchanged(self, value):
        """No change from earlier versions where they were already right:
        on platforms that cannot be tested here, that is the guarantee."""
        assert _config_token(value) == value

    @pytest.mark.parametrize(
        "value, token",
        [
            ("/Users/John Smith/id", '"/Users/John Smith/id"'),
            (r"C:\Users\John Smith\.ssh\id", r'"C:\Users\John Smith\.ssh\id"'),
            ("/Users/o'brien/id", '"/Users/o\'brien/id"'),
            ('/tmp/say "hi"/id', '"/tmp/say \\"hi\\"/id"'),
            ("/tmp/a#b/id", '"/tmp/a#b/id"'),
            ("/tmp/a=b/id", '"/tmp/a=b/id"'),
            # \\ and a backslash before a quote act as escapes: double them
            (r"\\server\share\id", r'"\\\server\share\id"'),
            ("C:\\dir\\'x\\id", '"C:\\dir\\\\\'x\\id"'),
            # ...as does one that would otherwise swallow the closing quote
            ("C:\\my dir\\", '"C:\\my dir\\\\"'),
            ("", '""'),
        ],
    )
    def test_value_that_used_to_break_the_config_is_quoted(self, value, token):
        assert _config_token(value) == token

    def test_path_doubles_percent_signs(self):
        """IdentityFile/UserKnownHostsFile expand %-tokens."""
        path = PurePosixPath("/tmp/50%off/id")  # same text on every platform
        assert _config_path(path) == "/tmp/50%%off/id"


@pytest.mark.skipif(shutil.which("ssh") is None, reason="needs the OpenSSH client")
class TestConfigReadBackByOpenSSH:
    """The generated Host block must mean to ssh what was meant."""

    def _read_back(self, home, server_user="ubuntu"):
        config = CpolarConfig(
            username="user@example.com",
            server_user=server_user,
            ssh_key_path=str(home / "id_rsa_cpolar"),
        )
        manager = SSHManager(config, known_hosts_path=home / "known_hosts")
        manager.update_ssh_config(TUNNEL, ports=[8888])
        result = subprocess.run(
            ["ssh", "-G", "-F", str(manager.ssh_config_path), ALIAS],
            capture_output=True,
            encoding="utf-8",  # what ssh writes, whatever the locale
        )
        assert result.returncode == 0, result.stderr
        options = dict(
            line.split(" ", 1) for line in result.stdout.splitlines() if " " in line
        )
        return manager, options

    @pytest.mark.parametrize("dirname", ["plain", "John Smith", "o'brien", "张三"])
    def test_paths(self, monkeypatch, tmp_path, dirname):
        home = tmp_path / dirname
        monkeypatch.setattr(Path, "home", lambda: home)

        manager, options = self._read_back(home)

        assert options["identityfile"] == str(manager.private_key_path)
        assert options["userknownhostsfile"] == str(manager.known_hosts_path)

    @pytest.mark.parametrize("user", ["ubuntu", "John Smith", r"CORP\jane"])
    def test_user(self, tmp_path, user):
        _manager, options = self._read_back(tmp_path, server_user=user)

        assert options["user"] == user

    @pytest.mark.parametrize(
        "key_path",
        [
            r"C:\Users\zhang\.ssh\id_rsa_cpolar",
            r"C:\Users\张三\.ssh\id_rsa_cpolar",
            r"C:\Users\John Smith\.ssh\id_rsa_cpolar",
            r"C:\Users\O'Brien\.ssh\id_rsa_cpolar",
            r"\\fileserver\home\zhang\.ssh\id_rsa_cpolar",
        ],
    )
    def test_windows_style_paths(self, tmp_path, key_path):
        """The config tokenizer is the same code on every platform, so how it
        reads a Windows path can be checked wherever ssh is available."""
        config = CpolarConfig(username="u", server_user="ubuntu", ssh_key_path=key_path)
        manager = SSHManager(config, known_hosts_path=tmp_path / "known_hosts")
        manager.update_ssh_config(TUNNEL)

        result = subprocess.run(
            ["ssh", "-G", "-F", str(manager.ssh_config_path), ALIAS],
            capture_output=True,
            encoding="utf-8",  # what ssh writes, whatever the locale
        )

        assert result.returncode == 0, result.stderr
        assert f"identityfile {key_path}\n" in result.stdout


class TestDirectCommand:
    """`ssh` invoked directly must get the same options as the Host block."""

    @pytest.fixture
    def manager(self, monkeypatch, tmp_path):
        home = tmp_path / "John Smith"
        monkeypatch.setattr(Path, "home", lambda: home)
        return SSHManager(_make_config(home), known_hosts_path=home / "known_hosts")

    def test_paths_are_quoted_like_in_the_host_block(self, manager):
        command = manager.build_ssh_command(TUNNEL)

        assert f'IdentityFile="{manager.private_key_path}"' in command
        assert f'UserKnownHostsFile="{manager.known_hosts_path}"' in command
        # -i cannot express a percent sign in the path; IdentityFile can
        assert "-i" not in command

    def test_host_block_and_direct_command_set_the_same_options(self, manager):
        """Two ways to the same server: they must not drift apart."""
        manager.update_ssh_config(TUNNEL, ports=[8888])
        content = manager.ssh_config_path.read_text(encoding="utf-8")
        block = content.split(f"Host {ALIAS}\n")[1]
        in_block = [tuple(line.strip().split(" ", 1)) for line in block.splitlines()]
        where_to = {"HostName", "Port", "User", "LocalForward"}

        command = manager.build_ssh_command(TUNNEL, ports=[8888])
        on_the_command_line = [
            tuple(value.split("=", 1))
            for flag, value in zip(command, command[1:])
            if flag == "-o"
        ]

        assert len(on_the_command_line) == 7
        assert [o for o in in_block if o[0] not in where_to] == on_the_command_line

    def test_config_block_quotes_paths(self, manager):
        manager.update_ssh_config(TUNNEL)
        content = manager.ssh_config_path.read_text(encoding="utf-8")

        assert f'\tIdentityFile "{manager.private_key_path}"\n' in content
        assert f'\tUserKnownHostsFile "{manager.known_hosts_path}"\n' in content


class TestServerUserSafety:
    """The user name lands in ~/.ssh/config and in `user@host` on the argv."""

    @pytest.mark.parametrize(
        "bad", ["-oProxyCommand=x", "a\nProxyCommand x", "a\x00b", "a\tb"]
    )
    def test_validator_rejects_injection(self, bad):
        with pytest.raises(ValidationError):
            CpolarConfig(username="u", server_user=bad)

    @pytest.mark.parametrize("user", ["ubuntu", "John Smith", r"CORP\jane", "a@b"])
    def test_validator_keeps_legitimate_names(self, user):
        assert CpolarConfig(username="u", server_user=f" {user} ").server_user == user

    def test_user_with_space_is_one_config_argument(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = CpolarConfig(username="u", server_user="John Smith")
        manager = SSHManager(config, known_hosts_path=tmp_path / "known_hosts")

        manager.update_ssh_config(TUNNEL)

        content = manager.ssh_config_path.read_text(encoding="utf-8")
        assert '\tUser "John Smith"\n' in content


class TestConfigThatIsNotUtf8:
    """~/.ssh/config is the user's file. OpenSSH does not care how its
    comments are encoded; an editor on Chinese Windows saves them as GBK."""

    THEIRS = "# 公司的服务器\nHost office\n\tHostName 10.0.0.8\n".encode("gbk")

    @pytest.fixture
    def manager(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        (tmp_path / ".ssh").mkdir()
        (tmp_path / ".ssh" / "config").write_bytes(self.THEIRS)
        return SSHManager(
            _make_config(tmp_path), known_hosts_path=tmp_path / "known_hosts"
        )

    @staticmethod
    def _bytes(manager):
        return manager.ssh_config_path.read_bytes().replace(b"\r\n", b"\n")

    def test_host_block_is_added_and_their_bytes_are_untouched(self, manager):
        with pytest.raises(UnicodeDecodeError):
            self.THEIRS.decode("utf-8")  # what used to stop the run

        manager.update_ssh_config(TUNNEL)
        manager.update_ssh_config(TUNNEL)  # an update in place, too

        content = self._bytes(manager)
        assert content.startswith(self.THEIRS)
        assert content.count(f"Host {ALIAS}\n".encode()) == 1

    def test_host_block_is_removed_and_their_bytes_are_untouched(self, manager):
        manager.update_ssh_config(TUNNEL)

        assert manager.remove_host_block() is True

        assert self._bytes(manager).rstrip(b"\n") == self.THEIRS.rstrip(b"\n")


class TestConfigThatCannotBeWritten:
    """~/.ssh/config is the user's file and may be anything: read-only, a
    directory, someone else's. That has to end as a message that names the
    file, not as a traceback."""

    @pytest.fixture
    def manager(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        (tmp_path / ".ssh").mkdir()
        return SSHManager(
            _make_config(tmp_path), known_hosts_path=tmp_path / "known_hosts"
        )

    def test_update_reports_a_directory_in_place_of_the_file(self, manager):
        manager.ssh_config_path.mkdir()

        with pytest.raises(SSHError, match="SSH config file") as failure:
            manager.update_ssh_config(TUNNEL)

        assert str(manager.ssh_config_path) in str(failure.value)

    def test_removal_reports_it_the_same_way(self, manager):
        """`account remove` goes on without the cleanup when told so."""
        manager.ssh_config_path.mkdir()

        with pytest.raises(SSHError, match="SSH config file") as failure:
            manager.remove_host_block()

        assert str(manager.ssh_config_path) in str(failure.value)

    @pytest.mark.posix_only
    @pytest.mark.skipif(
        getattr(os, "geteuid", lambda: 1)() == 0, reason="root may write anything"
    )
    def test_read_only_file_is_reported_and_left_as_it_was(self, manager):
        theirs = "Host office\n\tHostName 10.0.0.8\n"
        manager.ssh_config_path.write_text(theirs, encoding="utf-8")
        manager.ssh_config_path.chmod(0o400)

        with pytest.raises(SSHError, match="Permission denied") as failure:
            manager.update_ssh_config(TUNNEL)

        # The path once, not a second time inside the system's own wording
        assert str(failure.value).count(str(manager.ssh_config_path)) == 1
        assert manager.ssh_config_path.read_text(encoding="utf-8") == theirs


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

    @pytest.mark.posix_only
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
