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


def test_account_remove_goes_on_when_the_ssh_config_cannot_be_read(isolated_home):
    """Tidying up the Host block is a courtesy; the account still has to go."""
    _mk("work", alias="cpolar-work")
    (isolated_home / ".ssh" / "config").mkdir(parents=True)  # not a file

    r = CliRunner().invoke(cli_module.cli, ["account", "remove", "work", "-y"])

    assert r.exit_code == 0, r.output
    assert "Could not clean SSH config block" in r.output
    assert not (isolated_home / ".cpolar_connect" / "accounts" / "work").exists()


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
    # The new account is the current one now: the plain command connects it
    assert "Run 'cpolar-connect' to connect" in r.output


def test_init_names_the_account_when_the_plain_command_means_another(
    isolated_home, monkeypatch
):
    """CPOLAR_ACCOUNT outranks the current account that init has just set."""
    _mk("home")
    monkeypatch.setenv("CPOLAR_ACCOUNT", "home")

    r = _reinit("-a", "work")

    assert r.exit_code == 0, r.output
    assert "Run 'cpolar-connect -a work' to connect" in r.output


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
    assert Path(data["config_dir"]).parts[-2:] == ("accounts", "work")
    assert data["account"] == "work"


def test_top_level_list_is_alias_of_account_list(isolated_home):
    _mk("work")
    r1 = CliRunner().invoke(cli_module.cli, ["list"])
    r2 = CliRunner().invoke(cli_module.cli, ["account", "list"])
    assert r1.exit_code == 0, r1.output
    assert r1.output == r2.output
    rj = CliRunner().invoke(cli_module.cli, ["-f", "json", "list"])
    assert json.loads(rj.output)[0]["name"] == "work"


def _reinit(*account_args):
    return CliRunner().invoke(
        cli_module.cli,
        [
            "-y",
            "init",
            "--force",
            *account_args,
            "--username",
            "new@e.com",
            "--server-user",
            "root",
            "--ports",
            "9999",
        ],
        input="\n",
    )


def test_reinit_keeps_settings_it_does_not_ask_about(isolated_home):
    """Re-running init (e.g. to store the password again) must not silently
    point the account at another tunnel or back at the default key."""
    cm = _mk("work", alias="cpolar-work")
    cm.set("tunnel.name", "work-pc")
    cm.set("ssh.key_path", "~/.ssh/id_ed25519")
    cm.set("cpolar.base_url", "https://dashboard.example.com")
    cm.set("log_level", "DEBUG")

    r = _reinit("-a", "work")

    assert r.exit_code == 0, r.output
    config = ConfigManager(account="work").get_config()
    # What init asked about is replaced...
    assert (config.username, config.server_user, config.ports) == (
        "new@e.com",
        "root",
        [9999],
    )
    # ...and everything else is left alone
    assert config.tunnel_name == "work-pc"
    assert config.ssh_key_path == "~/.ssh/id_ed25519"
    assert config.base_url == "https://dashboard.example.com"
    assert config.log_level == "DEBUG"
    assert config.ssh_host_alias == "cpolar-work"
    assert "Other settings of this account were kept" in r.output
    assert "cpolar-connect -a work config show" in r.output


def test_reinit_keeps_a_customized_alias(isolated_home):
    _mk("default", alias="my-box")

    r = _reinit()

    assert r.exit_code == 0, r.output
    assert ConfigManager().get_config().ssh_host_alias == "my-box"


def test_first_init_does_not_mention_kept_settings(isolated_home):
    r = _reinit("-a", "fresh")

    assert r.exit_code == 0, r.output
    assert "were kept" not in r.output
    assert ConfigManager(account="fresh").get_config().tunnel_name is None


def test_list_shows_an_account_whose_config_has_null_fields(isolated_home):
    """The list reads the raw files so that a broken account still shows up."""
    _mk("work")
    broken = isolated_home / ".cpolar_connect" / "accounts" / "broken"
    broken.mkdir(parents=True)
    (broken / "config.json").write_text(
        '{"username": null, "ssh_host_alias": 5}', encoding="utf-8"
    )

    r = CliRunner().invoke(cli_module.cli, ["list"])

    assert r.exit_code == 0, r.output
    assert "work@e.com" in r.output
    assert "broken" in r.output


def _same_alias_for(*accounts):
    """Two accounts cannot get the same alias through the CLI; a copied
    account directory or a hand-edited config.json can."""
    for name in accounts:
        cm = _mk(name)
        data = json.loads(cm.config_file.read_text(encoding="utf-8"))
        data["ssh_host_alias"] = "cpolar-same"
        cm.config_file.write_text(json.dumps(data), encoding="utf-8")


def test_reinit_with_a_duplicated_alias_says_how_to_get_out_of_it(isolated_home):
    _same_alias_for("a", "b")

    r = _reinit("-a", "b")

    assert r.exit_code == 1
    assert "'cpolar-same' is already used by account 'a'" in r.output
    assert "cpolar-connect -a b config set ssh.host_alias" in r.output


def test_new_account_whose_alias_is_taken_points_at_the_account_that_has_it(
    isolated_home,
):
    """The new account does not exist yet, so only the other one can change."""
    _mk("old", alias="cpolar-work")

    r = _reinit("-a", "work")

    assert r.exit_code == 1
    assert "cpolar-connect -a old config set ssh.host_alias" in r.output
