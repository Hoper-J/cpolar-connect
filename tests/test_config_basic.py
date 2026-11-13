import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from cpolar_connect.config import ConfigError, ConfigManager


def test_config_set_and_get_ports_and_flags(monkeypatch, tmp_path: Path):
    # Isolate ~/.cpolar_connect under a temp home
    monkeypatch.setenv("CPOLAR_LANG", "en")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    cm = ConfigManager()

    # Create minimal config
    cfg = cm.create_config(
        {
            "username": "user@example.com",
            "server_user": "ubuntu",
            "ports": [8888, 6666],
            "auto_connect": True,
        }
    )

    assert cm.config_path.exists()

    # Set ports via comma-separated string
    cm.set("server.ports", "8080,3000")
    assert cm.get("server.ports") == [8080, 3000]

    # Set boolean via string
    cm.set("server.auto_connect", "false")
    assert cm.get("server.auto_connect") is False

    # Log level normalization
    cm.set("log_level", "debug")
    assert cm.get("log_level") == "DEBUG"


@pytest.fixture
def config_manager(monkeypatch, tmp_path: Path) -> ConfigManager:
    """ConfigManager isolated under a temp home with a minimal config."""
    monkeypatch.setenv("CPOLAR_LANG", "en")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cm = ConfigManager()
    cm.create_config({"username": "user@example.com", "server_user": "ubuntu"})
    return cm


def test_config_set_out_of_range_port_raises_config_error(config_manager):
    """Validation failures must surface as ConfigError, not raw ValidationError."""
    with pytest.raises(ConfigError):
        config_manager.set("server.ports", "99999")


def test_config_set_invalid_key_size_raises_config_error(config_manager):
    with pytest.raises(ConfigError):
        config_manager.set("ssh.key_size", "512")


def test_config_get_unknown_key_with_explicit_default_returns_it(config_manager):
    """An explicitly passed default must be returned, even if it is None."""
    assert config_manager.get("no.such.key", None) is None
    assert config_manager.get("no.such.key", "fallback") == "fallback"


def test_config_get_unknown_key_without_default_raises(config_manager):
    with pytest.raises(KeyError):
        config_manager.get("no.such.key")


def test_cli_config_set_unknown_key_shows_friendly_error(config_manager):
    """`config set` with an unknown key must not crash with a traceback."""
    from cpolar_connect.cli import cli

    result = CliRunner().invoke(cli, ["-y", "config", "set", "no.such.key", "foo"])
    assert result.exit_code == 1
    assert not isinstance(result.exception, KeyError)
    assert "no.such.key" in result.output


def test_cli_config_set_invalid_value_shows_friendly_error(config_manager):
    """`config set` with an invalid value must not crash with a traceback."""
    from cpolar_connect.cli import cli

    result = CliRunner().invoke(cli, ["-y", "config", "set", "server.ports", "99999"])
    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_tunnel_name_defaults_to_auto_and_can_be_cleared(config_manager):
    """Blank tunnel.name means "first SSH tunnel", like a fresh config."""
    assert config_manager.get("tunnel.name") is None

    config_manager.set("tunnel.name", " ssh ")
    assert config_manager.get("tunnel.name") == "ssh"

    config_manager.set("tunnel.name", "")
    assert config_manager.get("tunnel.name") is None


def test_cli_config_show_includes_tunnel_name(config_manager, monkeypatch):
    from cpolar_connect.cli import cli

    monkeypatch.delenv("CPOLAR_ACCOUNT", raising=False)
    config_manager.set("tunnel.name", "winpc")

    result = CliRunner().invoke(cli, ["config", "show"])

    assert result.exit_code == 0, result.output
    assert "winpc" in result.output


@pytest.mark.posix_only
def test_password_file_created_with_600_even_under_permissive_umask(config_manager):
    """The password file must never be world-readable, not even transiently."""
    import stat

    old_umask = os.umask(0o022)
    try:
        config_manager.set_password("user@example.com", "secret")
    finally:
        os.umask(old_umask)

    mode = stat.S_IMODE(config_manager.password_file.stat().st_mode)
    assert mode == 0o600
    assert config_manager.password_file.read_text(encoding="utf-8") == "secret"


@pytest.mark.posix_only
def test_config_dir_tightened_to_700(config_manager):
    import stat

    mode = stat.S_IMODE(config_manager.config_dir.stat().st_mode)
    assert mode == 0o700


def test_clear_host_keys_removes_file(config_manager):
    known_hosts = config_manager.known_hosts_file
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    known_hosts.write_text("cpolar-server ssh-rsa AAAA\n")

    assert config_manager.clear_host_keys() is True
    assert not known_hosts.exists()
    assert config_manager.clear_host_keys() is False


def test_cli_config_clear_hostkey(config_manager):
    from cpolar_connect.cli import cli

    known_hosts = config_manager.known_hosts_file
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    known_hosts.write_text("cpolar-server ssh-rsa AAAA\n")

    result = CliRunner().invoke(cli, ["config", "clear-hostkey"])
    assert result.exit_code == 0
    assert not known_hosts.exists()

    # Second run: nothing to clear, still exits cleanly with a warning
    result = CliRunner().invoke(cli, ["config", "clear-hostkey"])
    assert result.exit_code == 0


# --- tunnel.name: the first optional setting ---------------------------------


def _run(*args):
    from cpolar_connect.cli import cli

    return CliRunner().invoke(cli, list(args))


def test_cli_config_get_does_not_print_none_for_an_unset_value(config_manager):
    """ "None" reads like a value to type back in; it would be stored as text."""
    result = _run("config", "get", "tunnel.name")

    assert result.exit_code == 0, result.output
    assert "tunnel.name: (not set)" in result.output
    assert "None" not in result.output


# `config get` and `config set` take both spellings of a key, so the rest must
@pytest.mark.parametrize("key", ["tunnel.name", "tunnel_name"])
def test_cli_config_unset_restores_automatic_tunnel_selection(config_manager, key):
    config_manager.set("tunnel.name", "ssh")

    result = _run("config", "unset", key)

    assert result.exit_code == 0, result.output
    assert ConfigManager().get("tunnel.name") is None


def test_cli_config_set_blank_tunnel_name_reports_unset(config_manager):
    config_manager.set("tunnel.name", "ssh")

    result = _run("-y", "config", "set", "tunnel.name", "")

    assert result.exit_code == 0, result.output
    assert "tunnel.name = (not set)" in result.output
    assert ConfigManager().get("tunnel.name") is None


@pytest.mark.parametrize("key", ["server.user", "cpolar.username", "server.ports"])
def test_cli_config_unset_refuses_required_settings(config_manager, key):
    before = config_manager.config_file.read_text(encoding="utf-8")

    result = _run("config", "unset", key)

    assert result.exit_code == 1
    assert "cannot be unset" in result.output
    # ...and what to do instead is a command that can be run as printed
    assert f"cpolar-connect -a default config set {key} <value>" in result.output
    assert config_manager.config_file.read_text(encoding="utf-8") == before


def test_cli_config_unset_unknown_key_shows_friendly_error(config_manager):
    result = _run("config", "unset", "no.such.key")

    assert result.exit_code == 1
    assert "no.such.key" in result.output
    assert not isinstance(result.exception, KeyError)


def _record_host_key(config_manager):
    known_hosts = config_manager.known_hosts_file
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    known_hosts.write_text("cpolar-server ssh-rsa AAAA\n")
    return known_hosts


@pytest.mark.parametrize(
    "args",
    [
        ("-y", "config", "set", "tunnel.name", "ssh"),
        ("config", "unset", "tunnel.name"),
        ("-y", "config", "set", "tunnel_name", "ssh"),
        ("config", "unset", "tunnel_name"),
    ],
)
def test_retargeting_an_account_points_at_its_recorded_host_key(config_manager, args):
    """Host keys are kept per account: another tunnel may be another machine."""
    config_manager.set("tunnel.name", "default")
    known_hosts = _record_host_key(config_manager)

    result = _run(*args)

    assert result.exit_code == 0, result.output
    assert "cpolar-connect -a default config clear-hostkey" in result.output
    # Only pointed out: trust is never reset behind the user's back
    assert known_hosts.exists()


def test_tunnel_name_change_without_recorded_host_key_is_silent(config_manager):
    result = _run("-y", "config", "set", "tunnel.name", "ssh")

    assert result.exit_code == 0, result.output
    assert "clear-hostkey" not in result.output


def test_setting_the_same_tunnel_name_again_is_silent(config_manager):
    config_manager.set("tunnel.name", "ssh")
    _record_host_key(config_manager)

    result = _run("-y", "config", "set", "tunnel.name", "ssh")

    assert result.exit_code == 0, result.output
    assert "clear-hostkey" not in result.output


@pytest.mark.parametrize("name", ["ssh[home]", "lab[/]"])
def test_cli_config_show_prints_tunnel_names_literally(config_manager, name):
    """Free-form values are data, not Rich markup (which could even crash)."""
    config_manager.set("tunnel.name", name)

    result = _run("config", "show")

    assert result.exit_code == 0, result.output
    assert name in result.output


# --- ssh.key_path pointing at the user's own key ------------------------------


@pytest.mark.parametrize("key", ["ssh.key_path", "ssh_key_path"])
def test_cli_config_set_key_path_warns_when_no_key_is_there(
    config_manager, tmp_path, key
):
    """Otherwise the next connection quietly generates a new key at that path."""
    missing = tmp_path / "id_ed25519"

    result = _run("-y", "config", "set", key, str(missing))

    assert result.exit_code == 0, result.output
    assert "No key file at" in result.output
    assert ConfigManager().get("ssh.key_path") == str(missing)


def test_cli_config_set_key_path_warns_about_an_unusable_key(config_manager, tmp_path):
    key = tmp_path / "id_whatever"
    key.write_text("not a key\n")

    result = _run("-y", "config", "set", "ssh.key_path", str(key))

    assert result.exit_code == 0, result.output
    assert "is not a usable SSH private key" in result.output


@pytest.mark.parametrize("kind, pkcs8", [("ed25519", False), ("ecdsa", True)])
def test_cli_config_set_key_path_accepts_a_usable_key_quietly(
    config_manager, tmp_path, write_private_key, kind, pkcs8
):
    key = tmp_path / f"id_{kind}"
    write_private_key(key, kind, pkcs8=pkcs8)

    result = _run("-y", "config", "set", "ssh.key_path", str(key))

    assert result.exit_code == 0, result.output
    assert "No key file" not in result.output
    assert "not a usable" not in result.output


def test_cli_config_set_reports_the_value_that_was_stored(config_manager):
    """Not the raw input: surrounding blanks are dropped, levels normalized."""
    result = _run("-y", "config", "set", "server.user", "  bob  ")

    assert result.exit_code == 0, result.output
    assert result.output.rstrip().endswith("server.user = bob")
    assert ConfigManager().get("server.user") == "bob"

    result = _run("-y", "config", "set", "log_level", "debug")

    assert result.output.rstrip().endswith("log_level = DEBUG")


def test_cli_config_set_still_echoes_lists_as_they_were_typed(config_manager):
    result = _run("-y", "config", "set", "server.ports", "8080,3000")

    assert result.exit_code == 0, result.output
    assert "server.ports = 8080,3000" in result.output


@pytest.mark.parametrize("key", ["ssh.key_path", "ssh_key_path"])
@pytest.mark.parametrize("value", ["", "   "])
def test_cli_config_set_refuses_an_empty_key_path(config_manager, key, value):
    """Stored, it would stand for the current directory."""
    before = config_manager.config_file.read_text(encoding="utf-8")

    result = _run("-y", "config", "set", key, value)

    assert result.exit_code == 1
    assert "cannot be empty" in result.output
    assert config_manager.config_file.read_text(encoding="utf-8") == before
