import json
from pathlib import Path

import pytest

from rig.config import ProfileEntry, RigConfig
from rig.core.harnesses import get_harness
from rig.core.isolation import (
    activate_profile,
    check_harness_status,
    deactivate_harness,
    purge_active_home_items,
    read_active_marker,
    write_active_marker,
)
from rig.exceptions import IsolationError


@pytest.fixture(name="isolated_home")
def fixture_isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    return home_dir


def test_symlink_activation_switching_and_deactivation(tmp_path: Path, isolated_home: Path) -> None:
    _ = isolated_home
    datadir = tmp_path / "data"

    claude = get_harness("claude-code")
    activate_profile(claude, datadir, "work", "symlink")

    for key, home_path in claude.paths.items():
        assert home_path.is_symlink()
        assert home_path.resolve() == claude.profile_item_paths(datadir, "work")[key].resolve()

    # Write profile-specific data through $HOME
    _ = (claude.paths["config"] / "settings.json").write_text('{"env": "work"}\n', encoding="utf-8")

    # Switch to personal profile
    activate_profile(claude, datadir, "personal", "symlink")
    assert not (claude.paths["config"] / "settings.json").exists()
    assert (claude.profile_item_paths(datadir, "work")["config"] / "settings.json").is_file()

    # Deactivate
    deactivate_harness(claude, datadir)
    for home_path in claude.paths.values():
        assert not home_path.exists()
        assert not home_path.is_symlink()


def test_move_activation_switching_and_strategy_transitions(tmp_path: Path, isolated_home: Path) -> None:
    _ = isolated_home
    datadir = tmp_path / "data"

    opencode = get_harness("opencode")
    activate_profile(opencode, datadir, "work", "move")

    assert read_active_marker(datadir, "opencode") == "work"
    for home_path in opencode.paths.values():
        assert home_path.exists()
        assert not home_path.is_symlink()

    # Write data into live $HOME
    marker_file = opencode.paths["config"] / "token.txt"
    _ = marker_file.write_text("secret-work-token\n", encoding="utf-8")

    # Switch to personal under move strategy
    activate_profile(opencode, datadir, "personal", "move")
    assert read_active_marker(datadir, "opencode") == "personal"
    assert not (opencode.paths["config"] / "token.txt").exists()
    saved_work_token = opencode.profile_item_paths(datadir, "work")["config"] / "token.txt"
    assert saved_work_token.read_text(encoding="utf-8") == "secret-work-token\n"

    # Transition from move strategy back to symlink strategy on work profile
    activate_profile(opencode, datadir, "work", "symlink")
    assert read_active_marker(datadir, "opencode") is None
    assert opencode.paths["config"].is_symlink()
    assert (opencode.paths["config"] / "token.txt").read_text(encoding="utf-8") == "secret-work-token\n"


def test_conflict_safety_refuses_untracked_home_files(tmp_path: Path, isolated_home: Path) -> None:
    _ = isolated_home
    datadir = tmp_path / "data"

    claude = get_harness("claude-code")
    untracked_file = claude.paths["config.json"]
    _ = untracked_file.write_text('{"untracked": true}\n', encoding="utf-8")

    with pytest.raises(IsolationError, match="Conflicting untracked path exists"):
        activate_profile(claude, datadir, "work", "symlink")

    # Untracked file is untouched
    assert json.loads(untracked_file.read_text(encoding="utf-8")) == {"untracked": True}

    # Even if a stale .rig_active marker exists while profile dir also has the file, refuse
    _ = claude.init_profile_dir(datadir, "work")
    write_active_marker(datadir, "claude-code", "work")
    with pytest.raises(IsolationError, match="Conflicting path exists"):
        activate_profile(claude, datadir, "work", "symlink")


def test_purge_active_home_items_in_move_mode(tmp_path: Path, isolated_home: Path) -> None:
    _ = isolated_home
    datadir = tmp_path / "data"

    agy = get_harness("antigravity")
    activate_profile(agy, datadir, "temp", "move")
    assert read_active_marker(datadir, "antigravity") == "temp"

    purge_active_home_items(agy, datadir)
    assert read_active_marker(datadir, "antigravity") is None
    for home_path in agy.paths.values():
        assert not home_path.exists()


def test_check_harness_status_states(tmp_path: Path, isolated_home: Path) -> None:
    _ = isolated_home
    datadir = tmp_path / "data"

    cfg = RigConfig(datapath=datadir)
    claude = get_harness("claude-code")

    # 1. Inactive state (no default profile, no leftover links -> synced)
    status = check_harness_status(claude, cfg)
    assert status.synced is True
    assert status.default_profile is None

    # 2. Active symlink state -> synced
    cfg.harnesses["claude-code"].upsert_profile(ProfileEntry(name="work"))
    cfg.harnesses["claude-code"].default_profile = "work"
    activate_profile(claude, datadir, "work", "symlink")
    status = check_harness_status(claude, cfg)
    assert status.synced is True

    # 3. Missing symlink in $HOME -> not synced
    claude.paths["config.json"].unlink()
    status = check_harness_status(claude, cfg)
    assert status.synced is False

    # 4. Non-symlink placed at target path in symlink mode -> not synced
    _ = claude.paths["config.json"].write_text("{}\n", encoding="utf-8")
    status = check_harness_status(claude, cfg)
    assert status.synced is False

    # 5. Active move state -> synced, then mismatched marker -> not synced
    claude.paths["config.json"].unlink()
    cfg.harnesses["claude-code"].strategy = "move"
    activate_profile(claude, datadir, "work", "move")
    status = check_harness_status(claude, cfg)
    assert status.synced is True

    write_active_marker(datadir, "claude-code", "other")
    status = check_harness_status(claude, cfg)
    assert status.synced is False
