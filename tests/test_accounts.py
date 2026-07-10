"""
Tests for account name validation, resolution, and the current-account file.
"""

from pathlib import Path

import pytest

from cpolar_connect.config import (
    ConfigError,
    read_current_account,
    resolve_account,
    validate_account_name,
    write_current_account,
)


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CPOLAR_LANG", "en")
    monkeypatch.delenv("CPOLAR_ACCOUNT", raising=False)
    monkeypatch.delenv("CPOLAR_PASSWORD", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.mark.parametrize(
    "bad",
    [
        "../evil",
        "a/b",
        "a\\b",
        "..",
        ".",
        "",
        "-x",
        "a b",
        "a\nb",
        "a\x00b",
        "current",
        "logs",
        "accounts",
        "config.json",
        ".password",
        "known_hosts",
        "x" * 65,
        "/etc/x",
    ],
)
def test_invalid_account_names_rejected(bad):
    with pytest.raises(ConfigError):
        validate_account_name(bad)


@pytest.mark.parametrize("good", ["default", "work", "Work-2", "a.b_c", "x"])
def test_valid_account_names_accepted(good):
    assert validate_account_name(good) == good


def test_resolve_priority_explicit_over_env_over_current(monkeypatch):
    write_current_account("fromfile")
    monkeypatch.setenv("CPOLAR_ACCOUNT", "fromenv")
    assert resolve_account("explicit") == "explicit"
    assert resolve_account(None) == "fromenv"
    monkeypatch.delenv("CPOLAR_ACCOUNT")
    assert resolve_account(None) == "fromfile"


def test_resolve_falls_back_to_default(isolated_home):
    assert resolve_account(None) == "default"


def test_current_file_stripped_and_empty_means_unset(isolated_home):
    current = isolated_home / ".cpolar_connect" / "current"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text("work\n")
    assert read_current_account() == "work"
    current.write_text("  \n")
    assert read_current_account() is None
    assert resolve_account(None) == "default"


def test_resolve_validates_all_sources(monkeypatch, isolated_home):
    with pytest.raises(ConfigError):
        resolve_account("../evil")
    monkeypatch.setenv("CPOLAR_ACCOUNT", "../evil")
    with pytest.raises(ConfigError):
        resolve_account(None)
    monkeypatch.delenv("CPOLAR_ACCOUNT")
    current = isolated_home / ".cpolar_connect" / "current"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text("../evil")
    with pytest.raises(ConfigError):
        resolve_account(None)


def test_write_current_is_atomic(monkeypatch, isolated_home):
    write_current_account("old")

    def boom(self, target):
        raise OSError("interrupted")

    with monkeypatch.context() as m:
        m.setattr(Path, "replace", boom)
        with pytest.raises(OSError):
            write_current_account("new")
    assert read_current_account() == "old"


# ---------- Task 2: ConfigManager per-account paths ----------

import stat

from cpolar_connect.config import ConfigManager


def _mk(account, username=None, alias=None):
    cm = ConfigManager(account=account)
    data = {"username": username or f"{account}@e.com", "server_user": "ubuntu"}
    if alias:
        data["ssh_host_alias"] = alias
    cm.create_config(data)
    return cm


def test_paths_land_in_account_dir(isolated_home):
    cm = _mk("work")
    assert cm.config_file == (
        isolated_home / ".cpolar_connect" / "accounts" / "work" / "config.json"
    )
    assert cm.config_file.exists()
    assert stat.S_IMODE(cm.account_dir.stat().st_mode) == 0o700


def test_constructor_rejects_bad_name(isolated_home):
    with pytest.raises(ConfigError):
        ConfigManager(account="../evil")


def test_default_account_used_when_unset(isolated_home):
    assert ConfigManager().account == "default"


def test_list_accounts_marks_current(isolated_home):
    _mk("work", alias="cpolar-work")
    _mk("home", alias="cpolar-home")
    write_current_account("home")
    listed = {a["name"]: a for a in ConfigManager().list_accounts()}
    assert listed["home"]["is_current"] is True
    assert listed["work"]["is_current"] is False
    assert listed["work"]["ssh_host_alias"] == "cpolar-work"


def test_list_accounts_skips_invalid_dirs(isolated_home):
    _mk("work")
    (isolated_home / ".cpolar_connect" / "accounts" / "bad name").mkdir()
    names = [a["name"] for a in ConfigManager().list_accounts()]
    assert names == ["work"]


def test_remove_account_deletes_dir_and_rejects_traversal(isolated_home):
    cm = _mk("work")
    victim = isolated_home / "victim"
    victim.mkdir()
    with pytest.raises(ConfigError):
        cm.remove_account("../../victim")
    assert victim.exists()
    cm.remove_account("work")
    assert not (isolated_home / ".cpolar_connect" / "accounts" / "work").exists()


def test_find_alias_conflict(isolated_home):
    _mk("work", alias="cpolar-x")
    cm = ConfigManager(account="home")
    assert cm.find_alias_conflict("cpolar-x") == "work"
    assert cm.find_alias_conflict("cpolar-free") is None


def test_config_set_alias_conflict_rejected(isolated_home):
    """config set must not bypass cross-account alias uniqueness."""
    _mk("work", alias="cpolar-work")
    cm = _mk("home", alias="cpolar-home")
    with pytest.raises(ConfigError):
        cm.set("ssh.host_alias", "cpolar-work")
    with pytest.raises(ConfigError):
        cm.set("ssh_host_alias", "cpolar-work")  # underscore spelling too
    assert cm.get("ssh.host_alias") == "cpolar-home"
