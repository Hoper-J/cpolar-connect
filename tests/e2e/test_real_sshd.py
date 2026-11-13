"""
End-to-end tests against a real sshd.

The connect flow runs with real SSH, a real key upload and the real `ssh`
client; only cpolar login and tunnel discovery are replaced. The server may
be a POSIX one or OpenSSH for Windows: the tool has to find out by itself.
Skipped unless CPOLAR_E2E_SSH_KEY is set. The tests add keys to the target
accounts, so point them only at a throwaway machine. CI does: see
.github/workflows/ci.yml.

    CPOLAR_E2E_SSH_KEY          private key (ed25519, no passphrase) that logs in
    CPOLAR_E2E_SSH_USER         account to log in as
    CPOLAR_E2E_SSH_HOST         default 127.0.0.1
    CPOLAR_E2E_SSH_PORT         default 22
    CPOLAR_E2E_AUTHORIZED_KEYS  the file sshd reads that account's keys from,
                                when the server is this machine
    CPOLAR_E2E_PASSWORD_USER    another account, which logs in with a
    CPOLAR_E2E_PASSWORD         password and has no key installed
    CPOLAR_E2E_NO_PASSWORD_USER an account with an empty password, on a
                                server that permits those
    CPOLAR_E2E_ADMIN_PASSWORD_USER  on a Windows server: an administrator
                                with that same password and no key
"""

import base64
import codecs
import os
import shutil
import socket
import subprocess
from pathlib import Path

import paramiko
import pytest
from click.testing import CliRunner

from cpolar_connect import cli as cli_module
from cpolar_connect.config import ConfigManager
from cpolar_connect.ssh import SSHManager, load_private_key
from cpolar_connect.tunnel import TunnelInfo

KEY = os.environ.get("CPOLAR_E2E_SSH_KEY", "")
USER = os.environ.get("CPOLAR_E2E_SSH_USER", "")
HOST = os.environ.get("CPOLAR_E2E_SSH_HOST", "127.0.0.1")
PORT = int(os.environ.get("CPOLAR_E2E_SSH_PORT", "22"))
AUTHORIZED_KEYS = os.environ.get("CPOLAR_E2E_AUTHORIZED_KEYS")
PASSWORD_USER = os.environ.get("CPOLAR_E2E_PASSWORD_USER", "")
PASSWORD = os.environ.get("CPOLAR_E2E_PASSWORD", "")
NO_PASSWORD_USER = os.environ.get("CPOLAR_E2E_NO_PASSWORD_USER", "")
ADMIN_PASSWORD_USER = os.environ.get("CPOLAR_E2E_ADMIN_PASSWORD_USER", "")

pytestmark = pytest.mark.skipif(
    not KEY, reason="set CPOLAR_E2E_SSH_KEY to run against a real sshd"
)
password_account = pytest.mark.skipif(
    not (PASSWORD_USER and PASSWORD),
    reason="set CPOLAR_E2E_PASSWORD_USER and CPOLAR_E2E_PASSWORD",
)

MARKER = "cpolar-e2e-ok"


class FakeAuth:
    def __init__(self, config_manager=None, base_url=None):
        pass

    def login(self, username=None, password=None):
        return object()

    def logout(self):
        pass


def _ssh(args):
    """Run the real ssh client with a harmless remote command."""
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", *args, f"echo {MARKER}"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"ssh {args} failed:\n{result.stderr}"
    return result.stdout


def _logs_in(key_path, user=USER) -> bool:
    """Whether sshd accepts this key, and nothing else, for the account."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            HOST,
            port=PORT,
            username=user,
            pkey=load_private_key(Path(key_path)),
            allow_agent=False,
            look_for_keys=False,
            timeout=20,
        )
        return True
    except paramiko.AuthenticationException:
        return False
    finally:
        client.close()


class Flow:
    """`cpolar-connect -y` for an account whose tunnel leads to the sshd.

    password is what gets typed when the server password is asked for; None
    cancels the prompt.
    """

    def __init__(self, monkeypatch, port=PORT, user=USER, password=None):
        self.endpoint = TunnelInfo(url=f"tcp://{HOST}:{port}", hostname=HOST, port=port)
        endpoint = self.endpoint

        class FakeTunnelManager:
            def __init__(self, session, base_url=None):
                pass

            def get_tunnel_info(self, tunnel_name=None):
                return endpoint

        def answer_password_prompt(prompts, message):
            self.prompts.append(message)
            return password

        self.prompts = []
        self.sessions = []
        monkeypatch.setattr(cli_module, "CpolarAuth", FakeAuth)
        monkeypatch.setattr(cli_module, "TunnelManager", FakeTunnelManager)
        monkeypatch.setattr(cli_module.Prompts, "password", answer_password_prompt)
        # The interactive session is not opened; ssh_direct() runs the same
        # command line for real with a command instead of a shell
        monkeypatch.setattr(
            SSHManager, "connect", lambda manager, *args: self.sessions.append(args)
        )
        self.config_manager = ConfigManager()
        self.config_manager.create_config(
            {"username": "u@example.com", "server_user": user, "ports": [18888]}
        )
        self.config_manager.set_password("u@example.com", "not-used")

    @property
    def manager(self) -> SSHManager:
        return SSHManager(
            self.config_manager.get_config(),
            known_hosts_path=self.config_manager.known_hosts_file,
        )

    def run(self):
        result = CliRunner().invoke(cli_module.cli, ["-y"])
        print(result.output)  # shown by `pytest -rA`, also for passing tests
        return result

    def ssh_via_host_block(self) -> str:
        """What `ssh <alias>` does with the generated Host block."""
        manager = self.manager
        return _ssh(
            [
                "-F",
                str(manager.ssh_config_path),
                "-o",
                "ClearAllForwardings=yes",
                manager.host_alias,
            ]
        )

    def ssh_direct(self) -> str:
        """The command line the tool itself runs to connect. It carries all
        it needs, so the ssh configuration of whoever runs the tests is kept
        out of it (`-F none`)."""
        return _ssh(["-F", "none", *self.manager.build_ssh_command(self.endpoint)[1:]])


@pytest.fixture
def existing_key(tmp_path):
    """The user's own everyday key, where ssh and paramiko look by default."""
    target = tmp_path / ".ssh" / "id_ed25519"
    target.parent.mkdir(exist_ok=True)
    shutil.copyfile(KEY, target)
    target.chmod(0o600)
    return target


@pytest.fixture(autouse=True)
def authorized_keys():
    """The file sshd reads the account's keys from, put back afterwards."""
    if not AUTHORIZED_KEYS:
        yield None
        return
    path = Path(AUTHORIZED_KEYS)
    original = path.read_bytes()
    yield path
    path.write_bytes(original)


def test_first_connection_installs_the_key_then_needs_nothing_else(
    monkeypatch, existing_key
):
    flow = Flow(monkeypatch)
    dedicated = flow.manager.private_key_path

    first = flow.run()

    assert first.exit_code == 0, first.output
    assert flow.prompts == []  # installed through the existing key
    assert _logs_in(dedicated)

    existing_key.unlink()
    second = flow.run()

    assert second.exit_code == 0, second.output
    assert MARKER in flow.ssh_via_host_block()
    assert MARKER in flow.ssh_direct()


@pytest.mark.parametrize("comment", ["someone@laptop", ""])
def test_key_lands_on_its_own_line_after_an_unterminated_entry(
    monkeypatch, existing_key, authorized_keys, comment
):
    """The last line has no newline. Appending blindly would glue the new key
    onto it: sshd would not see the new key and, when the entry has no
    comment, would stop accepting the existing one as well."""
    if authorized_keys is None:
        pytest.skip("set CPOLAR_E2E_AUTHORIZED_KEYS (server on this machine)")
    ours = load_private_key(Path(KEY))
    entry = f"{ours.get_name()} {ours.get_base64()} {comment}".rstrip()
    authorized_keys.write_text(entry)  # the only entry, unterminated
    assert _logs_in(KEY), "sshd itself is fine with such a file"

    flow = Flow(monkeypatch)
    result = flow.run()

    assert result.exit_code == 0, result.output
    assert _logs_in(KEY), "the existing key must keep working"
    assert _logs_in(flow.manager.private_key_path)
    assert authorized_keys.read_text().count("\n") == 2


def test_running_again_adds_nothing(monkeypatch, existing_key, authorized_keys):
    if authorized_keys is None:
        pytest.skip("set CPOLAR_E2E_AUTHORIZED_KEYS (server on this machine)")
    flow = Flow(monkeypatch)

    assert flow.run().exit_code == 0
    after_first = authorized_keys.read_bytes()
    assert flow.run().exit_code == 0

    assert authorized_keys.read_bytes() == after_first


@pytest.mark.parametrize("options", ["", 'no-pty,command="echo cpolar e2e" '])
def test_upload_recognizes_a_key_that_is_already_installed(
    monkeypatch, existing_key, authorized_keys, options
):
    """Asked to install the key again, the server side must find the entry
    rather than add a second one, also when options stand before the key."""
    if authorized_keys is None:
        pytest.skip("set CPOLAR_E2E_AUTHORIZED_KEYS (server on this machine)")
    flow = Flow(monkeypatch)
    assert flow.run().exit_code == 0
    ours = flow.manager.public_key_path.read_text(encoding="utf-8").strip()
    installed = authorized_keys.read_text(encoding="utf-8")
    assert ours in installed
    authorized_keys.write_text(
        installed.replace(ours, options + ours), encoding="utf-8"
    )
    after_first = authorized_keys.read_bytes()

    assert flow.manager.upload_public_key_with_existing_keys(HOST, PORT) is False

    assert authorized_keys.read_bytes() == after_first


def test_key_with_an_awkward_comment_is_installed_as_it_is(
    monkeypatch, existing_key, authorized_keys
):
    """An existing key brings its own comment, and that is free text: the
    shell on the server (POSIX or PowerShell) must not read anything into it."""
    if authorized_keys is None:
        pytest.skip("set CPOLAR_E2E_AUTHORIZED_KEYS (server on this machine)")
    flow = Flow(monkeypatch)
    manager = flow.manager
    assert manager.generate_ssh_key() is True
    public_key = manager.public_key_path
    key_type, key_data = public_key.read_text(encoding="utf-8").split()[:2]
    comment = 'CORP\\nina\'s \u2019pc\u2019 "x" $HOME `id` %s ; & | > C:\\Users\\张三'
    line = f"{key_type} {key_data} {comment}"
    public_key.write_text(line + "\n", encoding="utf-8")

    result = flow.run()

    assert result.exit_code == 0, result.output
    assert _logs_in(manager.private_key_path)
    assert line in authorized_keys.read_text(encoding="utf-8").splitlines()


def test_key_the_server_already_accepts_connects_without_an_upload(
    monkeypatch, authorized_keys
):
    before = authorized_keys.read_bytes() if authorized_keys else None
    flow = Flow(monkeypatch)
    flow.config_manager.set("ssh.key_path", KEY)

    result = flow.run()

    assert result.exit_code == 0, result.output
    assert flow.prompts == []
    assert MARKER in flow.ssh_via_host_block()
    assert MARKER in flow.ssh_direct()
    if authorized_keys:
        assert authorized_keys.read_bytes() == before


@password_account
def test_first_connection_with_the_server_password_installs_the_key(monkeypatch):
    """No key the server knows: the password is asked for once, never again."""
    flow = Flow(monkeypatch, user=PASSWORD_USER, password=PASSWORD)

    first = flow.run()

    assert first.exit_code == 0, first.output
    assert len(flow.prompts) == 1
    assert _logs_in(flow.manager.private_key_path, PASSWORD_USER)

    second = flow.run()

    assert second.exit_code == 0, second.output
    assert len(flow.prompts) == 1
    assert MARKER in flow.ssh_via_host_block()


@password_account
def test_wrong_server_password_installs_nothing(monkeypatch):
    flow = Flow(monkeypatch, user=PASSWORD_USER, password=PASSWORD + "x")

    result = flow.run()

    assert result.exit_code == 1, result.output
    assert f"'{PASSWORD_USER}'" in result.output
    assert not _logs_in(flow.manager.private_key_path, PASSWORD_USER)


@pytest.mark.skipif(not NO_PASSWORD_USER, reason="set CPOLAR_E2E_NO_PASSWORD_USER")
def test_empty_server_password_is_an_answer(monkeypatch):
    """Just pressing Enter at the password prompt must be tried as the
    password: an account without one, on a server that permits that."""
    flow = Flow(monkeypatch, user=NO_PASSWORD_USER, password="")

    result = flow.run()

    assert result.exit_code == 0, result.output
    assert len(flow.prompts) == 1
    assert _logs_in(flow.manager.private_key_path, NO_PASSWORD_USER)


@pytest.mark.skipif(HOST != "127.0.0.1", reason="needs the server on this machine")
def test_closed_port_is_reported_before_any_bootstrap(monkeypatch, existing_key):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    flow = Flow(monkeypatch, port=closed_port)

    result = flow.run()

    assert result.exit_code == 1
    assert f"{HOST}:{closed_port}" in result.output
    assert flow.prompts == []
    assert not flow.manager.private_key_path.exists()


def _server_key(algorithms):
    """The host key the server presents when asked for one of these
    algorithms, or None if it has no such key."""
    transport = paramiko.Transport((HOST, PORT))
    try:
        transport.get_security_options().key_types = algorithms
        transport.start_client(timeout=20)
        return transport.get_remote_server_key()
    except paramiko.SSHException:
        return None
    finally:
        transport.close()


def _record_host_key(flow, key_type, key_data) -> str:
    known_hosts = flow.config_manager.known_hosts_file
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    record = f"{flow.manager.host_alias} {key_type} {key_data}\n"
    known_hosts.write_text(record)
    return record


def test_server_is_asked_for_the_key_type_on_record(monkeypatch, existing_key):
    """On record: the server's RSA key and nothing else. Left to the
    defaults, client and server settle on another of the server's keys,
    which must not look like a changed key, nor be added to the record."""
    rsa_key = _server_key(["rsa-sha2-512", "rsa-sha2-256"])
    if rsa_key is None:
        pytest.skip("the server has no RSA host key")
    flow = Flow(monkeypatch)
    record = _record_host_key(flow, rsa_key.get_name(), rsa_key.get_base64())
    known_hosts = flow.config_manager.known_hosts_file

    result = flow.run()

    assert result.exit_code == 0, result.output
    assert known_hosts.read_text() == record
    # `ssh` reads the same record and comes to the same conclusion
    assert MARKER in flow.ssh_via_host_block()
    assert known_hosts.read_text() == record


def test_key_of_a_type_that_is_not_on_record_is_refused(monkeypatch, existing_key):
    """On record: a key of a type this server has none of, so it presents
    one of another type. Taking that for a first contact would let anyone
    on the tunnel's path in."""
    other = paramiko.ECDSAKey.generate(bits=521)
    if _server_key([other.get_name()]) is not None:
        pytest.skip("the server has a host key of that type")
    flow = Flow(monkeypatch)
    record = _record_host_key(flow, other.get_name(), other.get_base64())

    result = flow.run()

    assert result.exit_code == 1, result.output
    assert "host key has changed" in result.output
    assert flow.prompts == []
    assert flow.config_manager.known_hosts_file.read_text() == record


def _another_key_of_the_servers_type():
    """Type and data of a host key that is not the server's, but of the type
    it presents by default."""
    transport = paramiko.Transport((HOST, PORT))
    try:
        transport.start_client(timeout=20)
        key_type = transport.get_remote_server_key().get_name()
    finally:
        transport.close()
    if key_type == "ssh-ed25519":
        message = paramiko.Message()
        message.add_string(key_type)
        message.add_string(os.urandom(32))
        return key_type, base64.b64encode(message.asbytes()).decode()
    other = (
        paramiko.RSAKey.generate(2048)
        if key_type == "ssh-rsa"
        else paramiko.ECDSAKey.generate()
    )
    return key_type, other.get_base64()


def test_changed_host_key_is_refused_and_the_hint_names_the_account(
    monkeypatch, existing_key
):
    flow = Flow(monkeypatch)
    _record_host_key(flow, *_another_key_of_the_servers_type())

    result = flow.run()

    assert result.exit_code == 1
    assert "host key has changed" in result.output
    assert "cpolar-connect -a default config clear-hostkey" in result.output
    assert flow.prompts == []


@pytest.mark.skipif(
    not (ADMIN_PASSWORD_USER and PASSWORD),
    reason="set CPOLAR_E2E_ADMIN_PASSWORD_USER (Windows servers)",
)
def test_key_added_to_a_utf16_file_is_one_that_sshd_reads(monkeypatch, authorized_keys):
    """PowerShell 5.1 writes UTF-16 with `>` and Out-File, the usual way such
    a file comes to be made by hand on Windows. sshd reads none of its lines;
    the key that is added must not share their fate."""
    if (
        authorized_keys is None
        or authorized_keys.name != "administrators_authorized_keys"
    ):
        pytest.skip("needs the administrators' shared key file on this machine")
    theirs = codecs.BOM_UTF16_LE + (
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFake someone@pc\r\n".encode("utf-16-le")
    )
    authorized_keys.write_bytes(theirs)
    flow = Flow(monkeypatch, user=ADMIN_PASSWORD_USER, password=PASSWORD)

    result = flow.run()

    assert result.exit_code == 0, result.output
    assert _logs_in(flow.manager.private_key_path, ADMIN_PASSWORD_USER)
    installed = authorized_keys.read_bytes()
    assert installed.startswith(theirs)  # what was there is left as it was
    # Asked again, the server side finds the key instead of adding it anew
    assert flow.manager.upload_public_key(HOST, PORT, PASSWORD) is False
    assert authorized_keys.read_bytes() == installed


# Keep this test last: it removes a file the other tests log in through
@pytest.mark.skipif(
    not (ADMIN_PASSWORD_USER and PASSWORD),
    reason="set CPOLAR_E2E_ADMIN_PASSWORD_USER (Windows servers)",
)
def test_first_key_of_a_windows_administrator(monkeypatch, authorized_keys):
    """A Windows machine on which nobody has set up key login yet: the file
    that holds the administrators' keys does not exist. It has to be created
    with access rights sshd accepts, or the new key is ignored."""
    shared = (
        authorized_keys is not None
        and authorized_keys.name == "administrators_authorized_keys"
    )
    if shared:
        authorized_keys.unlink()
    flow = Flow(monkeypatch, user=ADMIN_PASSWORD_USER, password=PASSWORD)

    result = flow.run()

    assert result.exit_code == 0, result.output
    assert len(flow.prompts) == 1
    assert _logs_in(flow.manager.private_key_path, ADMIN_PASSWORD_USER)
    if shared:
        assert authorized_keys.read_text().count("\n") == 1
