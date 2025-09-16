from pathlib import Path
from click.testing import CliRunner
import os

from cpolar_connect.config import ConfigManager
from cpolar_connect.cli import cli


def test_status_local_only_without_password(monkeypatch, tmp_path: Path):
    # Do not enforce language; accept zh/en output
    monkeypatch.delenv("CPOLAR_PASSWORD", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    cm = ConfigManager()
    cm.create_config({
        "username": "user@example.com",
        "server_user": "ubuntu",
        "ports": [8888],
        "auto_connect": True,
    })

    runner = CliRunner()
    result = runner.invoke(cli, ["status"])  # should degrade to local-only, not error

    assert result.exit_code == 0
    out = result.output
    assert (
        "Offline (local-only)" in out
        or "Password not available" in out
        or "离线（仅本地）" in out
        or "缺少密码" in out
    )
    # Field labels may be English regardless; table content should include these keywords
    assert "SSH Alias" in out or "SSH 别名" in out
    assert "Forward Ports" in out or "端口" in out
