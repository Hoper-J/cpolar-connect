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
