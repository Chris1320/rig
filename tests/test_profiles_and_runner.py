import fcntl
import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rig.cli import app
from rig.config import RigConfig, load_config, save_config
from rig.core.harnesses import get_harness
from rig.core.isolation import read_active_marker
from rig.core.profiles import (
    create_profile,
    delete_profile,
    list_profiles,
    use_profile,
    validate_profile_name,
)
from rig.core.runner import lockfile_path, run_harness_profile
from rig.exceptions import ProfileError, RunnerError

runner = CliRunner()


@pytest.fixture(name="isolated_env")
def fixture_isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    res = runner.invoke(app, ["-c", str(config_dir), "setup", "-d", str(data_dir)])
    assert res.exit_code == 0, res.stdout
    return home_dir, config_dir, data_dir


def test_validate_profile_name_rejects_unsafe_names() -> None:
    assert validate_profile_name("work-1_a.b") == "work-1_a.b"

    for invalid in ("", ".rig_active", ".hidden", "../escape", "a/b", "space name"):
        with pytest.raises(ProfileError, match="Invalid profile name"):
            _ = validate_profile_name(invalid)


def test_profile_crud_core_and_cli(isolated_env: tuple[Path, Path, Path]) -> None:
    _, config_dir, _ = isolated_env

    # 1. Create profile via CLI with --default and --desc
    res_create = runner.invoke(
        app,
        [
            "-c",
            str(config_dir),
            "--json",
            "profile",
            "create",
            "claude-code",
            "work",
            "--desc",
            "Work account",
            "--default",
        ],
    )
    assert res_create.exit_code == 0, res_create.stdout
    created_payload: dict[str, object] = json.loads(res_create.stdout)  # pyright: ignore[reportAny]
    assert created_payload["is_default"] is True

    # Duplicate creation fails
    res_dup = runner.invoke(app, ["-c", str(config_dir), "profile", "create", "claude-code", "work"])
    assert res_dup.exit_code == 1

    # 2. Create a second profile without --default
    res_p2 = runner.invoke(
        app,
        ["-c", str(config_dir), "profile", "create", "claude-code", "personal", "-d", "Personal"],
    )
    assert res_p2.exit_code == 0

    # 3. List profiles (JSON and Rich)
    res_list_json = runner.invoke(app, ["-c", str(config_dir), "--json", "profile", "list", "claude-code"])
    assert res_list_json.exit_code == 0
    list_payload: dict[str, list[dict[str, object]]] = json.loads(res_list_json.stdout)  # pyright: ignore[reportAny]
    assert len(list_payload["profiles"]) == 2

    res_list_rich = runner.invoke(app, ["-c", str(config_dir), "profile", "list"])
    assert res_list_rich.exit_code == 0
    assert "work" in res_list_rich.stdout
    assert "personal" in res_list_rich.stdout

    # 4. Switch active profile with `use` and strategy override (`move`)
    res_use = runner.invoke(
        app,
        ["-c", str(config_dir), "--json", "profile", "use", "claude-code", "personal", "--strategy", "move"],
    )
    assert res_use.exit_code == 0, res_use.stdout
    cfg = load_config(config_dir / "config.json")
    assert cfg.harnesses["claude-code"].default_profile == "personal"
    assert cfg.harnesses["claude-code"].strategy == "move"
    assert read_active_marker(cfg.datapath, "claude-code") == "personal"

    # 5. Delete active profile without --force fails
    res_del_fail = runner.invoke(app, ["-c", str(config_dir), "profile", "delete", "claude-code", "personal"])
    assert res_del_fail.exit_code == 1

    # 6. Delete active profile with --force succeeds, purges $HOME, and resets default_profile
    res_del_force = runner.invoke(
        app,
        ["-c", str(config_dir), "--json", "profile", "delete", "claude-code", "personal", "--force"],
    )
    assert res_del_force.exit_code == 0, res_del_force.stdout
    cfg = load_config(config_dir / "config.json")
    assert cfg.harnesses["claude-code"].default_profile is None
    assert read_active_marker(cfg.datapath, "claude-code") is None
    claude = get_harness("claude-code")
    for home_path in claude.paths.values():
        assert not home_path.exists()


def test_runner_swaps_and_restores_previous_profile(
    isolated_env: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, config_dir, data_dir = isolated_env
    cfg_file = config_dir / "config.json"
    cfg = load_config(cfg_file)

    opencode = get_harness("opencode")
    _ = create_profile(cfg, "opencode", "default-prof", set_default=True)
    _ = create_profile(cfg, "opencode", "temp-prof", set_default=False)

    # Write distinct marker files in each profile's config directory
    _ = (opencode.profile_item_paths(data_dir, "default-prof")["config"] / "who.txt").write_text(
        "default-prof", encoding="utf-8"
    )
    _ = (opencode.profile_item_paths(data_dir, "temp-prof")["config"] / "who.txt").write_text(
        "temp-prof", encoding="utf-8"
    )

    fake_bin = data_dir / "fake-opencode"
    _ = fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")

    def fake_which_opencode(_binary: str) -> str:
        return str(fake_bin)

    monkeypatch.setattr("rig.core.harnesses.shutil.which", fake_which_opencode)

    observed_during_run: list[str] = []
    observed_args: list[list[str]] = []

    def fake_subprocess_run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess[bytes]:
        _ = check
        observed_args.append(cmd)
        who = (opencode.paths["config"] / "who.txt").read_text(encoding="utf-8")
        observed_during_run.append(who)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr("rig.core.runner.subprocess.run", fake_subprocess_run)

    res = runner.invoke(
        app,
        ["-c", str(config_dir), "run", "opencode", "temp-prof", "--flag", "value"],
    )
    assert res.exit_code == 0, res.stdout
    assert observed_during_run == ["temp-prof"]
    assert observed_args[0][1:] == ["--flag", "value"]

    # After run exits, default-prof is restored in $HOME
    assert (opencode.paths["config"] / "who.txt").read_text(encoding="utf-8") == "default-prof"


def test_runner_deactivates_on_exit_when_no_previous_default_and_checks_lock(
    isolated_env: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, config_dir, data_dir = isolated_env
    cfg = load_config(config_dir / "config.json")
    agy = get_harness("antigravity")
    _ = create_profile(cfg, "antigravity", "solo", set_default=False)

    fake_bin = data_dir / "fake-agy"
    _ = fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")

    def fake_which_agy(_binary: str) -> str:
        return str(fake_bin)

    def fake_run_exit_7(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess[bytes]:
        _ = check
        return subprocess.CompletedProcess(args=cmd, returncode=7)

    monkeypatch.setattr("rig.core.harnesses.shutil.which", fake_which_agy)
    monkeypatch.setattr("rig.core.runner.subprocess.run", fake_run_exit_7)

    code = run_harness_profile(cfg, "antigravity", "solo", [])
    assert code == 7
    for home_path in agy.paths.values():
        assert not home_path.exists()
        assert not home_path.is_symlink()

    # Hold the lockfile and verify concurrent run_harness_profile raises RunnerError
    lpath = lockfile_path(data_dir, "antigravity")
    with lpath.open("w", encoding="utf-8") as held_lock:
        fcntl.flock(held_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RunnerError, match="already locked"):
            _ = run_harness_profile(cfg, "antigravity", "solo", [])
        fcntl.flock(held_lock.fileno(), fcntl.LOCK_UN)


def test_direct_profile_helpers_edge_cases(isolated_env: tuple[Path, Path, Path]) -> None:
    _, config_dir, _ = isolated_env
    cfg: RigConfig = load_config(config_dir / "config.json")

    with pytest.raises(ProfileError, match="does not exist"):
        _ = use_profile(cfg, "opencode", "missing")

    with pytest.raises(ProfileError, match="does not exist"):
        delete_profile(cfg, "opencode", "missing")

    _ = create_profile(cfg, "opencode", "p1", set_default=True)
    save_config(cfg, config_dir / "config.json")
    assert len(list_profiles(cfg, "opencode")) == 1
