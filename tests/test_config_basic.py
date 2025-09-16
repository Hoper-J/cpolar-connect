import os
from pathlib import Path

import pytest

from cpolar_connect.config import ConfigManager


def test_config_set_and_get_ports_and_flags(monkeypatch, tmp_path: Path):
    # Isolate ~/.cpolar_connect under a temp home
    monkeypatch.setenv("CPOLAR_LANG", "en")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    cm = ConfigManager()

    # Create minimal config
    cfg = cm.create_config({
        "username": "user@example.com",
        "server_user": "ubuntu",
        "ports": [8888, 6666],
        "auto_connect": True,
    })

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

