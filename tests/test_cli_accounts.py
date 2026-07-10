"""
Tests for the multi-account CLI surface: -a flag, use, account group, init -a.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cpolar_connect import cli as cli_module
from cpolar_connect.config import ConfigManager, read_current_account


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CPOLAR_LANG", "en")
    monkeypatch.delenv("CPOLAR_ACCOUNT", raising=False)
    monkeypatch.delenv("CPOLAR_PASSWORD", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def _mk(account, alias=None):
    cm = ConfigManager(account=account)
    data = {"username": f"{account}@e.com", "server_user": "ubuntu"}
    if alias:
        data["ssh_host_alias"] = alias
    cm.create_config(data)
    return cm


def test_use_switches_and_is_idempotent(isolated_home):
    _mk("work")
    r = CliRunner().invoke(cli_module.cli, ["use", "work"])
    assert r.exit_code == 0, r.output
    assert read_current_account() == "work"
    r2 = CliRunner().invoke(cli_module.cli, ["use", "work"])
    assert r2.exit_code == 0


def test_use_unknown_account_lists_existing(isolated_home):
    _mk("work")
    r = CliRunner().invoke(cli_module.cli, ["use", "nosuch"])
    assert r.exit_code == 1
    assert "work" in r.output


def test_account_flag_works_in_both_positions(isolated_home):
    _mk("work")
    r1 = CliRunner().invoke(
        cli_module.cli, ["-a", "work", "config", "get", "server.user"]
    )
    r2 = CliRunner().invoke(
        cli_module.cli, ["config", "get", "server.user", "-a", "work"]
    )
    assert r1.exit_code == 0, r1.output
    assert r2.exit_code == 0, r2.output
    assert r1.output == r2.output


def test_account_flag_does_not_change_current(isolated_home):
    _mk("work")
    _mk("home")
    CliRunner().invoke(cli_module.cli, ["use", "home"])
    CliRunner().invoke(cli_module.cli, ["-a", "work", "config", "get", "server.user"])
    assert read_current_account() == "home"


def test_account_list_json_and_empty_state(isolated_home):
    r = CliRunner().invoke(cli_module.cli, ["-f", "json", "account", "list"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == []
    _mk("work")
    r2 = CliRunner().invoke(cli_module.cli, ["-f", "json", "account", "list"])
    data = json.loads(r2.output)
    assert data[0]["name"] == "work"


def test_account_bare_invocation_click_version_agnostic(isolated_home):
    r = CliRunner().invoke(cli_module.cli, ["account"])
    assert r.exit_code in (0, 2)


def test_account_remove_confirm_and_hostblock_cleanup(isolated_home):
    _mk("work", alias="cpolar-work")
    ssh_dir = isolated_home / ".ssh"
    ssh_dir.mkdir()
    (ssh_dir / "config").write_text(
        "Host cpolar-work\n\tHostName x\n\nHost keep\n\tHostName y\n",
        encoding="utf-8",
    )
    r = CliRunner().invoke(cli_module.cli, ["account", "remove", "work", "-y"])
    assert r.exit_code == 0, r.output
    assert not (isolated_home / ".cpolar_connect" / "accounts" / "work").exists()
    content = (ssh_dir / "config").read_text(encoding="utf-8")
    assert "cpolar-work" not in content
    assert "Host keep" in content


def test_remove_current_falls_back_to_default(isolated_home):
    _mk("default")
    _mk("work")
    CliRunner().invoke(cli_module.cli, ["use", "work"])
    CliRunner().invoke(cli_module.cli, ["account", "remove", "work", "-y"])
    assert read_current_account() == "default"


def test_init_a_creates_account_and_switches(isolated_home):
    r = CliRunner().invoke(
        cli_module.cli,
        [
            "-y",
            "init",
            "-a",
            "work",
            "--username",
            "u@e.com",
            "--server-user",
            "ubuntu",
            "--ports",
            "8888",
        ],
        input="\n",
    )
    assert r.exit_code == 0, r.output
    cfg_path = isolated_home / ".cpolar_connect" / "accounts" / "work" / "config.json"
    assert cfg_path.exists()
    assert read_current_account() == "work"
    assert json.loads(cfg_path.read_text())["ssh_host_alias"] == "cpolar-work"


def test_init_derived_alias_conflict_rejected(isolated_home):
    _mk("default", alias="cpolar-server")
    r = CliRunner().invoke(
        cli_module.cli,
        [
            "-y",
            "init",
            "-a",
            "server",
            "--username",
            "u@e.com",
            "--server-user",
            "ubuntu",
            "--ports",
            "8888",
        ],
        input="\n",
    )
    assert r.exit_code == 1
    assert not (isolated_home / ".cpolar_connect" / "accounts" / "server").exists()


def test_migration_runs_before_subcommand(isolated_home):
    root = isolated_home / ".cpolar_connect"
    root.mkdir(parents=True)
    (root / "config.json").write_text(
        '{"username": "old@x.com", "server_user": "ubuntu"}', encoding="utf-8"
    )
    r = CliRunner().invoke(cli_module.cli, ["config", "get", "server.user"])
    assert r.exit_code == 0, r.output
    assert (root / "accounts" / "default" / "config.json").exists()


def test_cpc_entry_point_registered():
    from importlib.metadata import entry_points

    eps = entry_points()
    scripts = (
        eps.select(group="console_scripts")
        if hasattr(eps, "select")
        else eps.get("console_scripts", [])
    )
    names = {e.name for e in scripts}
    assert {"cpc", "cpolar-connect"} <= names


def test_config_show_json_config_dir_points_at_account_dir(isolated_home):
    _mk("work")
    r = CliRunner().invoke(
        cli_module.cli, ["-a", "work", "-f", "json", "config", "show"]
    )
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["config_dir"].endswith("accounts/work")
    assert data["account"] == "work"


def test_top_level_list_is_alias_of_account_list(isolated_home):
    _mk("work")
    r1 = CliRunner().invoke(cli_module.cli, ["list"])
    r2 = CliRunner().invoke(cli_module.cli, ["account", "list"])
    assert r1.exit_code == 0, r1.output
    assert r1.output == r2.output
    rj = CliRunner().invoke(cli_module.cli, ["-f", "json", "list"])
    assert json.loads(rj.output)[0]["name"] == "work"
