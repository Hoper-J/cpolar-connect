"""
Tests for doctor.py - diagnostic checks.
"""

import socket
from pathlib import Path

import pytest

from cpolar_connect import doctor as doctor_module
from cpolar_connect.config import ConfigManager
from cpolar_connect.exceptions import TunnelNameNotFoundError
from cpolar_connect.i18n import _
from cpolar_connect.tunnel import TunnelInfo


@pytest.fixture
def doctor_with_key(monkeypatch, tmp_path: Path, write_private_key):
    """Doctor under a temp home, with a config pointing at a 0o644 key pair."""
    monkeypatch.setenv("CPOLAR_LANG", "en")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    key_path = tmp_path / "id_rsa_cpolar"
    write_private_key(key_path)
    key_path.chmod(0o644)
    (tmp_path / "id_rsa_cpolar.pub").write_text("public key")

    cm = ConfigManager()
    cm.create_config(
        {
            "username": "user@example.com",
            "server_user": "ubuntu",
            "ssh_key_path": str(key_path),
        }
    )
    return doctor_module.Doctor()


def _permission_warnings(doctor):
    return [
        (name, passed, message, level)
        for name, passed, message, level in doctor.checks
        if not passed and level == "warning"
    ]


@pytest.mark.posix_only
def test_check_ssh_key_warns_on_loose_permissions_posix(doctor_with_key):
    """On POSIX a 644 private key must produce a permission warning."""
    doctor_with_key.check_ssh_key()
    assert _permission_warnings(doctor_with_key)


def test_check_ssh_key_skips_permission_check_on_windows(doctor_with_key, monkeypatch):
    """POSIX permission bits are meaningless on Windows; no warning there."""
    monkeypatch.setattr("platform.system", lambda: "Windows")
    doctor_with_key.check_ssh_key()
    assert not _permission_warnings(doctor_with_key)


def test_doctor_warns_env_password_with_multiple_accounts(doctor_with_key, monkeypatch):
    from cpolar_connect.config import ConfigManager

    ConfigManager(account="second").create_config(
        {
            "username": "b@e.com",
            "server_user": "u",
            "ssh_host_alias": "cpolar-second",
        }
    )
    monkeypatch.setenv("CPOLAR_PASSWORD", "x")
    doctor_with_key.check_password()
    warnings = [c for c in doctor_with_key.checks if not c[1] and c[3] == "warning"]
    assert warnings


@pytest.mark.parametrize(
    "unusable, reason",
    [
        ("passphrase", "passphrase-protected"),
        ("pkcs8 passphrase", "passphrase-protected"),
        ("garbage", "not a usable SSH private key"),
    ],
)
def test_check_ssh_key_fails_for_a_key_connect_cannot_load(
    doctor_with_key, tmp_path, write_private_key, unusable, reason
):
    """Connecting hard-fails on such a key; "SSH key exists: OK" would mislead."""
    key_path = tmp_path / "id_rsa_cpolar"
    if unusable == "garbage":
        key_path.write_text("not a key")
    else:
        write_private_key(key_path, passphrase=b"pw", pkcs8="pkcs8" in unusable)

    assert doctor_with_key.check_ssh_key() is False
    ((name, passed, message, level),) = doctor_with_key.checks
    assert (name, passed, level) == ("SSH private key", False, "error")
    assert reason in message


class FakeAuth:
    def __init__(self, config_manager=None, base_url=None):
        pass

    def login(self, username=None, password=None):
        return object()


def _doctor_with_tunnel_lookup(doctor, monkeypatch, lookup, dns_error=None):
    """Run the cpolar check with tunnel discovery replaced by lookup().

    The tunnel's host name resolves on this network, unless dns_error is
    what the resolver raises instead.
    """

    def getaddrinfo(host, *args, **kwargs):
        if dns_error is not None:
            raise dns_error
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.7", 0))]

    monkeypatch.setattr(doctor_module.socket, "getaddrinfo", getaddrinfo)

    class FakeTunnelManager:
        def __init__(self, session, base_url=None):
            pass

        def get_tunnel_info(self, tunnel_name=None):
            return lookup()

    monkeypatch.setattr(doctor_module, "CpolarAuth", FakeAuth)
    monkeypatch.setattr(doctor_module, "TunnelManager", FakeTunnelManager)
    doctor.config_manager.set_password("user@example.com", "pw")
    doctor.check_cpolar_auth()
    return [
        (name, level, message)
        for name, passed, message, level in doctor.checks
        if not passed
    ]


def _tunnel(name, others):
    return TunnelInfo(
        url="tcp://1.tcp.cpolar.top:12345",
        hostname="1.tcp.cpolar.top",
        port=12345,
        name=name,
        other_candidates=others,
    )


def test_ambiguous_tunnel_is_a_selection_warning_not_a_down_tunnel(
    doctor_with_key, monkeypatch
):
    """Several SSH tunnels on one cpolar account: advise tunnel.name, not cpolar."""
    failed = _doctor_with_tunnel_lookup(
        doctor_with_key, monkeypatch, lambda: _tunnel("default", ["ssh"])
    )

    ((name, level, message),) = failed
    assert (name, level) == ("Tunnel selection", "warning")
    assert "cpolar-connect -a default config set tunnel.name" in message
    # The warning carries its own remedy: no separate (or empty) advice block
    assert doctor_with_key._recommendations() == []


def test_same_named_tunnels_are_reported(doctor_with_key, monkeypatch):
    failed = _doctor_with_tunnel_lookup(
        doctor_with_key, monkeypatch, lambda: _tunnel("ssh", ["ssh"])
    )

    ((name, level, message),) = failed
    assert (name, level) == ("Tunnel selection", "warning")
    assert "2 tunnels are named 'ssh'" in message


def test_wrong_tunnel_name_is_not_reported_as_cpolar_down_only(
    doctor_with_key, monkeypatch
):
    """Other tunnels are online: suggest fixing tunnel.name, then the server."""

    def not_found():
        raise TunnelNameNotFoundError("No online TCP tunnel named 'winpc'. Online: ssh")

    failed = _doctor_with_tunnel_lookup(doctor_with_key, monkeypatch, not_found)

    ((name, level, message),) = failed
    assert (name, level) == ("Tunnel name", "warning")
    assert "Online: ssh" in message
    advice = "\n".join(doctor_with_key._recommendations())
    assert "cpolar-connect -a default config set tunnel.name" in advice
    assert "systemctl start cpolar" in advice


def test_tunnel_whose_name_does_not_resolve_here_is_found(doctor_with_key, monkeypatch):
    """Issue #3: login works and the tunnel is online, yet connecting fails,
    because this network's DNS will not resolve tunnel host names. A doctor
    that says "all good" there is no help."""
    failed = _doctor_with_tunnel_lookup(
        doctor_with_key,
        monkeypatch,
        lambda: _tunnel("ssh", []),
        dns_error=socket.gaierror(11001, "getaddrinfo failed"),
    )

    ((name, level, message),) = failed
    assert (name, level) == ("Tunnel DNS", "error")
    assert "1.tcp.cpolar.top does not resolve on this network" in message
    assert "getaddrinfo failed" in message  # the system's words, to search for
    advice = "\n".join(doctor_with_key._recommendations())
    assert "DNS" in advice and "hosts file" in advice
    # ...and not what to do about a tunnel that is down, which this is not
    assert "systemctl" not in advice


def test_tunnel_whose_name_resolves_is_said_to(doctor_with_key, monkeypatch):
    failed = _doctor_with_tunnel_lookup(
        doctor_with_key, monkeypatch, lambda: _tunnel("ssh", [])
    )

    assert failed == []
    passed = {name: message for name, ok, message, _level in doctor_with_key.checks}
    assert passed["Tunnel DNS"] == "1.tcp.cpolar.top resolves on this network"


def test_no_tunnel_means_no_name_to_resolve(doctor_with_key, monkeypatch):
    def not_found():
        raise TunnelNameNotFoundError("No online TCP tunnel named 'winpc'. Online: ssh")

    _doctor_with_tunnel_lookup(doctor_with_key, monkeypatch, not_found)

    assert "Tunnel DNS" not in [name for name, *_rest in doctor_with_key.checks]


@pytest.mark.parametrize("name", ["ssh[home]", "lab[/]"])
def test_results_show_tunnel_names_literally(doctor_with_key, capsys, name):
    """Dashboard names are data, not Rich markup (which could even crash)."""
    doctor_with_key.add_check(
        "Tunnel selection", False, f"using the first one '{name}'", level="warning"
    )

    doctor_with_key.display_results()

    assert name in capsys.readouterr().out.replace("\n", "")


def test_advice_for_another_account_names_that_account(monkeypatch, tmp_path):
    """`cpolar-connect -a work doctor`: the commands it recommends are typed
    in as they stand, and without `-a work` they set up the current account."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    doctor = doctor_module.Doctor(ConfigManager(account="work"))

    assert doctor.check_config() is False
    doctor.add_check(_("doctor.check.password"), False, "missing")
    (_name, _passed, message, _level), _password = doctor.checks
    advice = "\n".join(doctor._recommendations())

    assert "cpolar-connect -a work init" in message
    assert advice.count("cpolar-connect -a work init") == 2
    assert "cpolar-connect init" not in advice
