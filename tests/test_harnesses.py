import json
from pathlib import Path

import pytest

from rig.core.harnesses import (
    HARNESSES,
    HarnessSpec,
    TrackedItem,
    get_harness,
)
from rig.exceptions import UnknownHarnessError


def test_supported_harnesses_registry() -> None:
    assert set(HARNESSES.keys()) == {"antigravity", "claude-code", "opencode"}
    assert HARNESSES["antigravity"].binary == "agy"
    assert HARNESSES["claude-code"].binary == "claude"
    assert HARNESSES["opencode"].binary == "opencode"


def test_get_harness_valid_and_unknown() -> None:
    spec = get_harness("claude-code")
    assert isinstance(spec, HarnessSpec)
    assert spec.key == "claude-code"

    with pytest.raises(UnknownHarnessError) as exc_info:
        _ = get_harness("nonexistent")
    assert exc_info.value.key == "nonexistent"


def test_harness_absolute_paths_respect_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    resolved_home = tmp_path.resolve()

    agy_paths = get_harness("antigravity").paths
    assert agy_paths == {
        "antigravity-cli": resolved_home / ".gemini/antigravity-cli",
        "config": resolved_home / ".gemini/config",
    }

    claude_paths = get_harness("claude-code").paths
    assert claude_paths == {
        "config": resolved_home / ".claude",
        "config.json": resolved_home / ".claude.json",
        "data": resolved_home / ".local/share/claude",
    }

    opencode_paths = get_harness("opencode").paths
    assert opencode_paths == {
        "config": resolved_home / ".config/opencode",
        "data": resolved_home / ".local/share/opencode",
        "cache": resolved_home / ".cache/opencode",
    }


def test_cache_keys() -> None:
    assert get_harness("antigravity").cache_keys == frozenset()
    assert get_harness("claude-code").cache_keys == frozenset()
    assert get_harness("opencode").cache_keys == frozenset({"cache"})


def test_init_profile_dir_creates_dirs_and_json_files(tmp_path: Path) -> None:
    claude = get_harness("claude-code")
    profile_dir = claude.init_profile_dir(tmp_path, "work")

    assert profile_dir == tmp_path.resolve() / "profiles" / "claude-code" / "work"
    item_paths = claude.profile_item_paths(tmp_path, "work")
    assert item_paths["config"].is_dir()
    assert item_paths["data"].is_dir()
    assert item_paths["config.json"].is_file()
    assert json.loads(item_paths["config.json"].read_text(encoding="utf-8")) == {}

    # Calling init_profile_dir again preserves existing json_file contents
    _ = item_paths["config.json"].write_text('{"theme": "dark"}\n', encoding="utf-8")
    _ = claude.init_profile_dir(tmp_path, "work")
    assert json.loads(item_paths["config.json"].read_text(encoding="utf-8")) == {"theme": "dark"}


def test_binary_path_and_is_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bin = tmp_path / "opencode"
    _ = fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")

    spec = HarnessSpec(
        key="opencode",
        binary="opencode",
        items=(TrackedItem(key="config", target=".config/opencode"),),
    )

    def fake_found(_binary: str) -> str:
        return str(fake_bin)

    def fake_missing(_binary: str) -> str | None:
        return None

    monkeypatch.setattr("rig.core.harnesses.shutil.which", fake_found)
    assert spec.is_installed() is True
    assert spec.binary_path() == fake_bin.resolve()

    monkeypatch.setattr("rig.core.harnesses.shutil.which", fake_missing)
    assert spec.is_installed() is False
    assert spec.binary_path() is None
