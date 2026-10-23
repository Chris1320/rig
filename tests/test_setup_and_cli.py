import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rig.cli import app
from rig.config import load_config
from rig.core.harnesses import get_harness

runner = CliRunner()


@pytest.fixture(name="isolated_home")
def fixture_isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    return home_dir


def test_setup_migrates_existing_home_files_and_ignores_unused_harnesses(tmp_path: Path, isolated_home: Path) -> None:
    # Populate existing non-symlink directory and a symlinked file for claude-code
    claude_dir = isolated_home / ".claude"
    claude_dir.mkdir(parents=True)
    _ = (claude_dir / "credentials.json").write_text('{"token": "abc"}\n', encoding="utf-8")

    external_cfg = tmp_path / "external_claude.json"
    _ = external_cfg.write_text('{"linked": true}\n', encoding="utf-8")
    (isolated_home / ".claude.json").symlink_to(external_cfg)

    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"

    result = runner.invoke(
        app,
        ["-c", str(config_dir), "--json", "setup", "--data-dir", str(data_dir)],
    )
    assert result.exit_code == 0, result.stdout
    payload: dict[str, object] = json.loads(result.stdout)  # pyright: ignore[reportAny]
    assert payload["migrated_harnesses"] == ["claude-code"]

    cfg = load_config(config_dir / "config.json")
    assert cfg.harnesses["claude-code"].default_profile == "default"
    assert len(cfg.harnesses["claude-code"].profiles) == 1
    assert cfg.harnesses["opencode"].default_profile is None
    assert cfg.harnesses["opencode"].profiles == []
    assert cfg.harnesses["antigravity"].default_profile is None
    assert cfg.harnesses["antigravity"].profiles == []

    # Verify migrated data (including dereferenced symlink content) is preserved under default `move` strategy
    claude = get_harness("claude-code")
    assert cfg.harnesses["claude-code"].strategy == "move"
    assert claude.paths["config"].is_dir() and not claude.paths["config"].is_symlink()
    assert (claude.paths["config"] / "credentials.json").read_text(encoding="utf-8") == '{"token": "abc"}\n'
    assert json.loads(claude.paths["config.json"].read_text(encoding="utf-8")) == {"linked": True}


def test_setup_exit_codes_when_directories_exist(tmp_path: Path, isolated_home: Path) -> None:
    _ = isolated_home
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"

    # First setup succeeds
    res1 = runner.invoke(app, ["-c", str(config_dir), "setup", "-d", str(data_dir)])
    assert res1.exit_code == 0

    # Second setup fails with exit code 2 (config exists)
    res2 = runner.invoke(app, ["-c", str(config_dir), "setup", "-d", str(tmp_path / "other_data")])
    assert res2.exit_code == 2

    # Fresh config dir but non-empty data dir fails with exit code 3
    non_empty_data = tmp_path / "non_empty_data"
    non_empty_data.mkdir()
    _ = (non_empty_data / "dummy.txt").write_text("x", encoding="utf-8")
    res3 = runner.invoke(app, ["-c", str(tmp_path / "fresh_cfg"), "--json", "setup", "-d", str(non_empty_data)])
    assert res3.exit_code == 3
    err_payload: dict[str, object] = json.loads(res3.stdout)  # pyright: ignore[reportAny]
    assert err_payload["exit_code"] == 3


def test_status_command_json_and_rich(tmp_path: Path, isolated_home: Path) -> None:
    _ = isolated_home
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"

    # Status before setup fails with exit code 1
    uninit = runner.invoke(app, ["-c", str(config_dir), "--json", "status"])
    assert uninit.exit_code == 1
    assert "error" in json.loads(uninit.stdout)

    # Run setup
    assert runner.invoke(app, ["-c", str(config_dir), "setup", "-d", str(data_dir)]).exit_code == 0

    # Status JSON and Rich
    status_json = runner.invoke(app, ["-c", str(config_dir), "--json", "status"])
    assert status_json.exit_code == 0
    status_payload: dict[str, list[object]] = json.loads(status_json.stdout)  # pyright: ignore[reportAny]
    assert len(status_payload["harnesses"]) == 3

    status_rich = runner.invoke(app, ["-c", str(config_dir), "status"])
    assert status_rich.exit_code == 0
    assert "Agent Harness Status" in status_rich.stdout


def test_config_and_version_commands_json_and_rich(tmp_path: Path, isolated_home: Path) -> None:
    _ = isolated_home
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    assert runner.invoke(app, ["-c", str(config_dir), "setup", "-d", str(data_dir)]).exit_code == 0

    cfg_json = runner.invoke(app, ["-c", str(config_dir), "--json", "config"])
    assert cfg_json.exit_code == 0
    assert json.loads(cfg_json.stdout)["config"]["datapath"] == str(data_dir.resolve())

    cfg_rich = runner.invoke(app, ["-c", str(config_dir), "config"])
    assert cfg_rich.exit_code == 0
    assert "Persisted Configuration:" in cfg_rich.stdout

    # Corrupt config.json and verify rig config exits with code 1
    _ = (config_dir / "config.json").write_text("{corrupt", encoding="utf-8")
    corrupt_res = runner.invoke(app, ["-c", str(config_dir), "--json", "config"])
    assert corrupt_res.exit_code == 1

    ver_json = runner.invoke(app, ["--json", "version"])
    assert ver_json.exit_code == 0
    assert json.loads(ver_json.stdout)["name"] == "rig"

    ver_rich = runner.invoke(app, ["version"])
    assert ver_rich.exit_code == 0
    assert "Version:" in ver_rich.stdout
