import fcntl
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rig import main
from rig.cli import app
from rig.cli.misc import vprint
from rig.config import RigConfig, load_config, runtime_config, save_config
from rig.core.harnesses import get_harness
from rig.core.isolation import lockfile_path
from rig.core.profiles import create_profile, delete_profile, use_profile
from rig.core.runner import run_harness_profile
from rig.exceptions import ConfigError, IsolationError, ProfileError, RunnerError
from rig.info import VERSION
from rig.misc import atomic_temp_path

runner = CliRunner()


def test_entrypoints_main_and_dunder_main(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(runtime_config, "json_mode", False)
    monkeypatch.setattr(runtime_config, "verbose", False)
    monkeypatch.setattr(sys, "argv", ["rig", "--json", "version"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    assert VERSION in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["rig", "-v", "version"])
    with pytest.raises(SystemExit) as mod_exc:
        _ = runpy.run_module("rig", run_name="__main__")
    assert mod_exc.value.code == 0
    out = capsys.readouterr().out
    assert VERSION in out
    assert "[VERBOSE]" in out


def test_vprint_and_require_setup_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(runtime_config, "json_mode", False)
    monkeypatch.setattr(runtime_config, "verbose", False)
    vprint("silent")
    assert capsys.readouterr().out == ""

    vprint("forced-plain", use_rich=False, force_enable=True)
    assert "forced-plain" in capsys.readouterr().out

    vprint("forced-rich", use_rich=True, force_enable=True)
    assert "forced-rich" in capsys.readouterr().out

    # Combining --json and --verbose keeps stdout valid JSON without [VERBOSE] lines
    res_json_verbose = runner.invoke(app, ["--json", "--verbose", "version"])
    assert res_json_verbose.exit_code == 0
    assert "[VERBOSE]" not in res_json_verbose.stdout

    empty_cfg = tmp_path / "unconfigured"
    res_rich = runner.invoke(app, ["-c", str(empty_cfg), "status"])
    assert res_rich.exit_code == 1
    assert "Setup is not complete" in res_rich.stdout

    res_json = runner.invoke(app, ["-c", str(empty_cfg), "--json", "status"])
    assert res_json.exit_code == 1
    assert '"error":' in res_json.stdout


def test_atomic_temp_path_and_save_config_rollback_on_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "atomic" / "data.json"
    with (
        pytest.raises(RuntimeError, match="abort write"),
        atomic_temp_path(target, prefix=".test-", suffix=".tmp") as tmp_file,
    ):
        _ = tmp_file.write_text("partial", encoding="utf-8")
        raise RuntimeError("abort write")

    assert not target.exists()
    assert not list((tmp_path / "atomic").iterdir())

    def fail_mkstemp(*_args: object, **_kwargs: object) -> tuple[int, str]:
        raise OSError("disk full")

    monkeypatch.setattr("rig.misc.tempfile.mkstemp", fail_mkstemp)
    with pytest.raises(ConfigError, match="Failed to write configuration file"):
        save_config(RigConfig(datapath=tmp_path / "data"), path=tmp_path / "cfg" / "config.json")


def test_create_profile_rolls_back_directory_on_activation_conflict(
    isolated_env: tuple[Path, Path, Path],
) -> None:
    _, config_dir, data_dir = isolated_env
    cfg = load_config(config_dir / "config.json")
    claude = get_harness("claude-code")

    # Create an untracked directory in $HOME to trigger IsolationError on set_default=True
    claude.paths["config"].mkdir(parents=True)
    with pytest.raises(IsolationError, match="Conflicting untracked path"):
        _ = create_profile(cfg, "claude-code", "broken-default", set_default=True)

    assert not claude.profile_dir(data_dir, "broken-default").exists()
    assert cfg.harnesses["claude-code"].get_profile("broken-default") is None
    claude.paths["config"].rmdir()

    # Held harness lock blocks create_profile, use_profile, and delete_profile
    _ = create_profile(cfg, "claude-code", "existing")
    lpath = lockfile_path(data_dir, "claude-code")
    with lpath.open("w", encoding="utf-8") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ProfileError, match="already locked"):
            _ = create_profile(cfg, "claude-code", "locked-new")
        with pytest.raises(ProfileError, match="already locked"):
            _ = use_profile(cfg, "claude-code", "existing")
        with pytest.raises(ProfileError, match="already locked"):
            delete_profile(cfg, "claude-code", "existing")
        fcntl.flock(held.fileno(), fcntl.LOCK_UN)


def test_runner_error_paths_and_cli_nonzero_exit(
    isolated_env: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, config_dir, data_dir = isolated_env
    cfg = load_config(config_dir / "config.json")
    _ = create_profile(cfg, "opencode", "work")

    # 1. Missing binary on PATH
    def missing_which(_binary: str) -> None:
        return None

    monkeypatch.setattr("rig.core.harnesses.shutil.which", missing_which)
    res_missing_bin = runner.invoke(app, ["-c", str(config_dir), "run", "opencode", "work"])
    assert res_missing_bin.exit_code == 1
    assert "not found on PATH" in res_missing_bin.stdout

    # 2. Fake binary present, subprocess returns non-zero code 42 via CLI `rig run`
    fake_bin = data_dir / "fake-opencode"
    _ = fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")

    def found_which(_binary: str) -> str:
        return str(fake_bin)

    def run_exit_42(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess[bytes]:
        _ = check
        return subprocess.CompletedProcess(args=cmd, returncode=42)

    monkeypatch.setattr("rig.core.harnesses.shutil.which", found_which)
    monkeypatch.setattr("rig.core.runner.subprocess.run", run_exit_42)
    res_42 = runner.invoke(app, ["-c", str(config_dir), "run", "opencode", "work"])
    assert res_42.exit_code == 42

    # 3. subprocess.run raises OSError -> RunnerError
    def run_oserror(_cmd: list[str], check: bool = False) -> subprocess.CompletedProcess[bytes]:
        _ = check
        raise OSError("exec format error")

    monkeypatch.setattr("rig.core.runner.subprocess.run", run_oserror)
    with pytest.raises(RunnerError, match="Failed to execute"):
        _ = run_harness_profile(cfg, "opencode", "work", [])

    # 4. Untracked $HOME conflict during run_harness_profile -> RunnerError
    get_harness("opencode").paths["config"].mkdir(parents=True)
    with pytest.raises(RunnerError, match="Conflicting untracked path"):
        _ = run_harness_profile(cfg, "opencode", "work", [])


def test_cli_rich_outputs_and_error_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home_dir = tmp_path / "home"
    (home_dir / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home_dir))

    cfg_dir = tmp_path / "cfg"
    data_dir = tmp_path / "data"

    # Rich setup output with migrated harness
    res_setup = runner.invoke(app, ["-c", str(cfg_dir), "setup", "-d", str(data_dir)])
    assert res_setup.exit_code == 0
    assert "Migrated existing configurations" in res_setup.stdout

    # Rich create --default, use, delete, list error, use error, export error
    assert (
        runner.invoke(
            app,
            ["-c", str(cfg_dir), "profile", "create", "opencode", "p1", "--default"],
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["-c", str(cfg_dir), "profile", "create", "opencode", "p2"]).exit_code == 0
    assert runner.invoke(app, ["-c", str(cfg_dir), "profile", "use", "opencode", "p2"]).exit_code == 0
    assert runner.invoke(app, ["-c", str(cfg_dir), "profile", "delete", "opencode", "p1"]).exit_code == 0

    assert runner.invoke(app, ["-c", str(cfg_dir), "profile", "list", "bogus"]).exit_code == 1
    assert runner.invoke(app, ["-c", str(cfg_dir), "profile", "use", "opencode", "missing"]).exit_code == 1
    assert runner.invoke(app, ["-c", str(cfg_dir), "profile", "export", "opencode", "missing"]).exit_code == 1

    # Corrupt config.json error branch on `rig status` and `rig config`
    _ = (cfg_dir / "config.json").write_text("{corrupt", encoding="utf-8")
    assert runner.invoke(app, ["-c", str(cfg_dir), "status"]).exit_code == 1
    assert runner.invoke(app, ["-c", str(cfg_dir), "config"]).exit_code == 1
