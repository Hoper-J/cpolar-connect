"""
Tests for legacy single-account layout migration into accounts/default.
"""

import stat
from pathlib import Path

import pytest

from cpolar_connect.config import ConfigManager, read_current_account

OLD_FILES = ["config.json", ".password", "known_hosts"]


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CPOLAR_LANG", "en")
    monkeypatch.delenv("CPOLAR_ACCOUNT", raising=False)
    monkeypatch.delenv("CPOLAR_PASSWORD", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def _old_layout(home: Path, files=OLD_FILES):
    root = home / ".cpolar_connect"
    root.mkdir(parents=True, exist_ok=True)
    contents = {
        "config.json": '{"username": "old@x.com", "server_user": "ubuntu"}',
        ".password": "secret",
        "known_hosts": "cpolar-server ssh-rsa AAAA\n",
    }
    for f in files:
        (root / f).write_text(contents[f], encoding="utf-8")
    return root


def test_full_migration(isolated_home):
    root = _old_layout(isolated_home)
    assert ConfigManager().ensure_migrated() is True
    dst = root / "accounts" / "default"
    for f in OLD_FILES:
        assert (dst / f).exists()
        assert not (root / f).exists()
    assert stat.S_IMODE((dst / ".password").stat().st_mode) == 0o600
    assert stat.S_IMODE(dst.stat().st_mode) == 0o700
    assert read_current_account() == "default"
    assert (dst / ".password").read_text(encoding="utf-8") == "secret"
    # Idempotent: a second run does nothing
    assert ConfigManager().ensure_migrated() is False


@pytest.mark.parametrize(
    "remaining",
    [
        [".password"],
        ["known_hosts"],
        [".password", "known_hosts"],
        ["config.json"],
        ["config.json", ".password"],
    ],
)
def test_interrupted_migration_converges(isolated_home, remaining):
    """Any half-migrated state converges on rerun: all three files end up moved."""
    root = _old_layout(isolated_home, files=remaining)
    dst = root / "accounts" / "default"
    dst.mkdir(parents=True)
    for f in OLD_FILES:
        if f not in remaining:
            (dst / f).write_text("already-migrated", encoding="utf-8")
    ConfigManager().ensure_migrated()
    for f in OLD_FILES:
        assert (dst / f).exists()
        assert not (root / f).exists()


def test_existing_target_never_overwritten(isolated_home):
    root = _old_layout(isolated_home)
    dst = root / "accounts" / "default"
    dst.mkdir(parents=True)
    (dst / "config.json").write_text("PRECIOUS", encoding="utf-8")
    ConfigManager().ensure_migrated()
    assert (dst / "config.json").read_text(encoding="utf-8") == "PRECIOUS"
    baks = list(root.glob("config.json.pre-migration.bak"))
    assert len(baks) == 1


def test_migration_rewrites_ssh_config_known_hosts_path(isolated_home):
    root = _old_layout(isolated_home)
    ssh_dir = isolated_home / ".ssh"
    ssh_dir.mkdir()
    old_path = root / "known_hosts"
    (ssh_dir / "config").write_text(
        f"Host cpolar-server\n\tHostName x\n\tUserKnownHostsFile {old_path}\n",
        encoding="utf-8",
    )
    ConfigManager().ensure_migrated()
    content = (ssh_dir / "config").read_text(encoding="utf-8")
    assert str(root / "accounts" / "default" / "known_hosts") in content
    assert f"UserKnownHostsFile {old_path}\n" not in content


def test_concurrent_rename_tolerated(isolated_home, monkeypatch):
    _old_layout(isolated_home)
    original_rename = Path.rename
    calls = []

    def racy_rename(self, target):
        if not calls:
            calls.append(1)
            original_rename(self, target)
            raise FileNotFoundError("simulated: other process moved it first")
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", racy_rename)
    ConfigManager().ensure_migrated()  # must not raise


def test_no_old_layout_no_migration(isolated_home):
    assert ConfigManager().ensure_migrated() is False


def test_language_survives_migration(isolated_home, monkeypatch):
    """After migration the account config's language must still be honored."""
    monkeypatch.delenv("CPOLAR_LANG", raising=False)
    root = isolated_home / ".cpolar_connect"
    (root / "accounts" / "default").mkdir(parents=True)
    (root / "accounts" / "default" / "config.json").write_text(
        '{"username": "u", "server_user": "s", "language": "en"}',
        encoding="utf-8",
    )
    (root / "current").write_text("default\n", encoding="utf-8")
    from cpolar_connect.i18n import I18n, Language

    assert I18n.load_from_config().language is Language.EN
