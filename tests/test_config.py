import json
from pathlib import Path

import pytest

from rig.config import (
    HarnessEntryConfig,
    ProfileEntry,
    RigConfig,
    RuntimeConfig,
    load_config,
    save_config,
)
from rig.exceptions import ConfigError
from rig.info import CURRENT_CONFIG_VERSION


def test_runtime_config_resolves_absolute_config_file(tmp_path: Path) -> None:
    rc = RuntimeConfig(configpath=tmp_path / "cfg")
    assert rc.config_file == (tmp_path / "cfg" / "config.json").resolve()


def test_default_rig_config_populates_all_harnesses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = RigConfig()
    assert cfg.version == CURRENT_CONFIG_VERSION
    assert cfg.datapath == (tmp_path / ".local" / "share" / "rig").resolve()
    assert set(cfg.harnesses.keys()) == {"antigravity", "claude-code", "opencode"}
    for entry in cfg.harnesses.values():
        assert entry.strategy == "move"
        assert entry.default_profile is None
        assert entry.profiles == []


def test_harness_entry_profile_crud_preserves_created_at() -> None:
    entry = HarnessEntryConfig()
    p1 = ProfileEntry(
        name="work",
        description="Work account",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    entry.upsert_profile(p1)
    assert entry.get_profile("work") == p1
    assert entry.get_profile("personal") is None

    p1_updated = ProfileEntry(
        name="work",
        description="Updated work account",
        created_at="2026-06-01T00:00:00+00:00",
        updated_at="2026-06-01T00:00:00+00:00",
    )
    entry.upsert_profile(p1_updated)
    assert len(entry.profiles) == 1
    stored = entry.get_profile("work")
    assert stored is not None
    assert stored.description == "Updated work account"
    assert stored.created_at == "2026-01-01T00:00:00+00:00"
    assert stored.updated_at == "2026-06-01T00:00:00+00:00"

    entry.default_profile = "work"
    assert entry.remove_profile("nonexistent") is False
    assert entry.remove_profile("work") is True
    assert entry.default_profile is None
    assert entry.profiles == []


def test_save_and_load_config_roundtrip(tmp_path: Path) -> None:
    config_file = tmp_path / "rig" / "config.json"
    datadir = tmp_path / "rig-data"

    cfg = RigConfig(datapath=datadir)
    cfg.harnesses["claude-code"].strategy = "move"
    cfg.harnesses["claude-code"].default_profile = "work"
    cfg.harnesses["claude-code"].upsert_profile(ProfileEntry(name="work", description="Claude work profile"))

    save_config(cfg, path=config_file)
    assert config_file.is_file()

    loaded = load_config(path=config_file)
    assert loaded.version == CURRENT_CONFIG_VERSION
    assert loaded.datapath == datadir.resolve()
    assert loaded.harnesses["claude-code"].strategy == "move"
    assert loaded.harnesses["claude-code"].default_profile == "work"
    profile = loaded.harnesses["claude-code"].get_profile("work")
    assert profile is not None
    assert profile.description == "Claude work profile"


def test_load_config_backfills_missing_harnesses(tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    _ = config_file.write_text(
        json.dumps(
            {
                "version": CURRENT_CONFIG_VERSION,
                "datapath": str(tmp_path / "data"),
                "harnesses": {
                    "opencode": {
                        "strategy": "symlink",
                        "default_profile": None,
                        "profiles": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    loaded = load_config(path=config_file)
    assert set(loaded.harnesses.keys()) == {"antigravity", "claude-code", "opencode"}


def test_load_config_errors(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.json"
    with pytest.raises(ConfigError, match="Configuration file not found"):
        _ = load_config(path=missing_file)

    bad_json_file = tmp_path / "bad.json"
    _ = bad_json_file.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ConfigError, match="Failed to read configuration file"):
        _ = load_config(path=bad_json_file)

    unsupported_version_file = tmp_path / "version.json"
    _ = unsupported_version_file.write_text(
        json.dumps({"version": 99.0, "datapath": str(tmp_path), "harnesses": {}}),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Unsupported config version"):
        _ = load_config(path=unsupported_version_file)

    unknown_harness_file = tmp_path / "unknown_harness.json"
    _ = unknown_harness_file.write_text(
        json.dumps(
            {
                "version": CURRENT_CONFIG_VERSION,
                "datapath": str(tmp_path),
                "harnesses": {"bogus": {}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Unknown harness keys in config: bogus"):
        _ = load_config(path=unknown_harness_file)

    bad_timestamp_file = tmp_path / "bad_timestamp.json"
    _ = bad_timestamp_file.write_text(
        json.dumps(
            {
                "version": CURRENT_CONFIG_VERSION,
                "datapath": str(tmp_path),
                "harnesses": {
                    "opencode": {
                        "profiles": [
                            {
                                "name": "work",
                                "created_at": "not-a-timestamp",
                            }
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Invalid timestamp"):
        _ = load_config(path=bad_timestamp_file)
