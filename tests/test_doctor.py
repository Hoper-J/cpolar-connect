"""
Tests for doctor.py - diagnostic checks.
"""

from pathlib import Path

import pytest

from cpolar_connect import doctor as doctor_module
from cpolar_connect.config import ConfigManager


@pytest.fixture
def doctor_with_key(monkeypatch, tmp_path: Path):
    """Doctor under a temp home, with a config pointing at a 0o644 key pair."""
    monkeypatch.setenv("CPOLAR_LANG", "en")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    key_path = tmp_path / "id_rsa_cpolar"
    key_path.write_text("private key")
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
