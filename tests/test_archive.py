import fcntl
import io
import json
import tarfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rig.cli import app
from rig.config import load_config
from rig.core.archive import ArchiveManifest, export_profile, import_profile
from rig.core.harnesses import get_harness
from rig.core.isolation import read_active_marker
from rig.core.profiles import create_profile, use_profile
from rig.core.runner import lockfile_path
from rig.exceptions import ArchiveError, IsolationError, ProfileError
from rig.info import ARCHIVE_MANIFEST_FILENAME

runner = CliRunner()


def _build_tar_gz(path: Path, entries: list[tuple[tarfile.TarInfo, bytes | None]]) -> Path:
    with tarfile.open(path, mode="w:gz") as tar:
        for info, data in entries:
            if data is not None:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            else:
                tar.addfile(info)

    return path


def _file_info(name: str, payload: bytes) -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name=name)
    info.mode = 0o644
    return info, payload


def _dir_info(name: str) -> tuple[tarfile.TarInfo, None]:
    info = tarfile.TarInfo(name=name)
    info.type = tarfile.DIRTYPE
    info.mode = 0o755
    return info, None


def _valid_manifest_bytes(
    harness: str = "claude-code",
    profile_name: str = "sample",
    version: float = 1.0,
    created_at: str = "2026-01-01T00:00:00+00:00",
) -> bytes:
    payload = {
        "version": version,
        "rig_version": "0.1.0",
        "harness": harness,
        "profile_name": profile_name,
        "description": "Sample",
        "created_at": created_at,
        "updated_at": created_at,
        "exported_at": created_at,
        "caches_excluded": False,
    }
    return json.dumps(payload).encode("utf-8")


def test_export_and_import_roundtrip_claude_code(
    isolated_env: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    _, config_dir, data_dir = isolated_env
    cfg = load_config(config_dir / "config.json")
    claude = get_harness("claude-code")

    created = create_profile(cfg, "claude-code", "work", description="Work Claude")
    items = claude.profile_item_paths(data_dir, "work")
    _ = items["config.json"].write_text('{"theme": "dark"}\n', encoding="utf-8")
    _ = (items["config"] / "settings.json").write_text('{"model": "opus"}\n', encoding="utf-8")
    _ = (items["data"] / "history.txt").write_text("hello\n", encoding="utf-8")

    out_archive = tmp_path / "claude-work.tar.gz"
    res_export = runner.invoke(
        app,
        ["-c", str(config_dir), "--json", "profile", "export", "claude-code", "work", "-o", str(out_archive)],
    )
    assert res_export.exit_code == 0, res_export.stdout
    export_payload: dict[str, object] = json.loads(res_export.stdout)  # pyright: ignore[reportAny]
    assert export_payload["archive"] == str(out_archive.resolve())
    assert export_payload["caches_excluded"] is False

    res_import = runner.invoke(
        app,
        ["-c", str(config_dir), "--json", "profile", "import", str(out_archive), "--name", "restored"],
    )
    assert res_import.exit_code == 0, res_import.stdout

    restored_entry = load_config(config_dir / "config.json").harnesses["claude-code"].get_profile("restored")
    assert restored_entry is not None
    assert restored_entry.description == "Work Claude"
    assert restored_entry.created_at == created.created_at

    restored_items = claude.profile_item_paths(data_dir, "restored")
    assert restored_items["config.json"].read_text(encoding="utf-8") == '{"theme": "dark"}\n'
    assert (restored_items["config"] / "settings.json").read_text(encoding="utf-8") == '{"model": "opus"}\n'
    assert (restored_items["data"] / "history.txt").read_text(encoding="utf-8") == "hello\n"
    assert not (claude.profile_dir(data_dir, "restored") / ARCHIVE_MANIFEST_FILENAME).exists()


def test_export_archive_structure_matches_between_datapath_and_home_move(
    isolated_env: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    _, config_dir, data_dir = isolated_env
    cfg = load_config(config_dir / "config.json")
    opencode = get_harness("opencode")

    _ = create_profile(cfg, "opencode", "portable", description="Portable")
    items = opencode.profile_item_paths(data_dir, "portable")
    _ = (items["config"] / "opencode.json").write_text('{"ok": true}\n', encoding="utf-8")
    _ = (items["data"] / "auth.json").write_text('{"token": "xyz"}\n', encoding="utf-8")
    _ = (items["cache"] / "index.bin").write_text("cached-bytes", encoding="utf-8")

    arc_from_datapath = export_profile(
        cfg,
        "opencode",
        "portable",
        tmp_path / "from-datapath.tar.gz",
        exclude_caches=False,
    )

    _ = use_profile(cfg, "opencode", "portable", strategy="move")
    assert read_active_marker(data_dir, "opencode") == "portable"
    arc_from_home = export_profile(
        cfg,
        "opencode",
        "portable",
        tmp_path / "from-home.tar.gz",
        exclude_caches=False,
    )

    with tarfile.open(arc_from_datapath, "r:gz") as t_data, tarfile.open(arc_from_home, "r:gz") as t_home:
        assert sorted(t_data.getnames()) == sorted(t_home.getnames())
        for member_name in ("config/opencode.json", "data/auth.json", "cache/index.bin"):
            f_data = t_data.extractfile(member_name)
            f_home = t_home.extractfile(member_name)
            assert f_data is not None and f_home is not None
            assert f_data.read() == f_home.read()


def test_export_cache_exclusion_interactive_and_default_path(
    isolated_env: tuple[Path, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, config_dir, data_dir = isolated_env
    opencode = get_harness("opencode")

    _ = create_profile(load_config(config_dir / "config.json"), "opencode", "dev")
    items = opencode.profile_item_paths(data_dir, "dev")
    _ = (items["config"] / "cfg.txt").write_text("cfg", encoding="utf-8")
    _ = (items["cache"] / "big.cache").write_text("heavy", encoding="utf-8")

    cwd_dir = tmp_path / "cwd"
    cwd_dir.mkdir()
    monkeypatch.chdir(cwd_dir)

    assert (
        runner.invoke(
            app,
            ["-c", str(config_dir), "profile", "export", "opencode", "dev", "--non-interactive"],
        ).exit_code
        == 0
    )
    default_archive = cwd_dir / "opencode-dev.tar.gz"
    with tarfile.open(default_archive, "r:gz") as tar:
        assert "cache/big.cache" not in tar.getnames()
        raw_manifest = tar.extractfile(ARCHIVE_MANIFEST_FILENAME)
        assert raw_manifest is not None
        assert ArchiveManifest.model_validate(json.loads(raw_manifest.read().decode("utf-8"))).caches_excluded is True

    included_archive = tmp_path / "with-cache.tar.gz"
    assert (
        runner.invoke(
            app,
            ["-c", str(config_dir), "profile", "export", "opencode", "dev", "-o", str(included_archive)],
            input="n\n",
        ).exit_code
        == 0
    )
    with tarfile.open(included_archive, "r:gz") as tar:
        assert "cache/big.cache" in tar.getnames()

    assert (
        runner.invoke(
            app,
            ["-c", str(config_dir), "profile", "import", str(default_archive), "-n", "dev-clean"],
        ).exit_code
        == 0
    )
    clean_cache = opencode.profile_item_paths(data_dir, "dev-clean")["cache"]
    assert clean_cache.is_dir() and not (clean_cache / "big.cache").exists()


def test_import_overwrite_active_move_profile_and_harness_override(
    isolated_env: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    _, config_dir, data_dir = isolated_env
    cfg = load_config(config_dir / "config.json")
    opencode = get_harness("opencode")

    orig = create_profile(cfg, "opencode", "live", description="v1")
    _ = (opencode.profile_item_paths(data_dir, "live")["config"] / "ver.txt").write_text("v1", encoding="utf-8")
    v1_archive = export_profile(cfg, "opencode", "live", tmp_path / "v1.tar.gz", exclude_caches=True)

    _ = use_profile(cfg, "opencode", "live", strategy="move")
    _ = (opencode.paths["config"] / "ver.txt").write_text("v2", encoding="utf-8")

    with pytest.raises(ProfileError, match="already exists"):
        _ = import_profile(load_config(config_dir / "config.json"), v1_archive)

    res_ovr = runner.invoke(
        app,
        ["-c", str(config_dir), "profile", "import", str(v1_archive), "--overwrite"],
    )
    assert res_ovr.exit_code == 0, res_ovr.stdout
    assert (opencode.paths["config"] / "ver.txt").read_text(encoding="utf-8") == "v1"
    assert read_active_marker(data_dir, "opencode") == "live"
    updated_cfg = load_config(config_dir / "config.json")
    live_prof = updated_cfg.harnesses["opencode"].get_profile("live")
    assert live_prof is not None and live_prof.created_at == orig.created_at

    h_key, cross_entry = import_profile(updated_cfg, v1_archive, harness="claude-code", name="cross")
    assert h_key == "claude-code" and cross_entry.name == "cross"
    assert get_harness("claude-code").profile_item_paths(data_dir, "cross")["config.json"].is_file()

    _ = create_profile(updated_cfg, "antigravity", "agy-prof")
    agy_archive = export_profile(updated_cfg, "antigravity", "agy-prof", tmp_path / "agy.tar.gz")
    with pytest.raises(ArchiveError, match="unexpected top-level entry 'antigravity-cli'"):
        _ = import_profile(updated_cfg, agy_archive, harness="claude-code", name="bad-cross")


def test_archive_rejects_missing_corrupt_and_invalid_manifests(
    isolated_env: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    _, config_dir, _ = isolated_env
    cfg = load_config(config_dir / "config.json")
    _ = create_profile(cfg, "claude-code", "valid")

    existing_dir = tmp_path / "out-dir"
    existing_dir.mkdir()
    res_dir_err = runner.invoke(
        app,
        ["-c", str(config_dir), "profile", "export", "claude-code", "valid", "-o", str(existing_dir)],
    )
    assert res_dir_err.exit_code == 1

    res_missing = runner.invoke(
        app,
        ["-c", str(config_dir), "profile", "import", str(tmp_path / "nope.tar.gz")],
    )
    assert res_missing.exit_code == 1

    corrupt_path = tmp_path / "corrupt.tar.gz"
    _ = corrupt_path.write_bytes(b"not-a-gzip-stream")
    with pytest.raises(ArchiveError, match="Invalid or corrupt archive"):
        _ = import_profile(cfg, corrupt_path)

    no_manifest = _build_tar_gz(tmp_path / "no-manifest.tar.gz", [_dir_info("config")])
    with pytest.raises(ArchiveError, match="missing 'manifest.json'"):
        _ = import_profile(cfg, no_manifest)

    for filename, manifest_bytes, match in (
        ("bad-ver.tar.gz", _valid_manifest_bytes(version=99.0), "Unsupported archive version"),
        ("bad-ts.tar.gz", _valid_manifest_bytes(created_at="not-iso"), "Invalid archive manifest"),
        ("non-utc.tar.gz", _valid_manifest_bytes(created_at="2026-01-01T00:00:00+08:00"), "must be UTC"),
        ("bad-name.tar.gz", _valid_manifest_bytes(profile_name="../escape"), "Invalid archive manifest"),
    ):
        arc = _build_tar_gz(tmp_path / filename, [_file_info(ARCHIVE_MANIFEST_FILENAME, manifest_bytes)])
        with pytest.raises(ArchiveError, match=match):
            _ = import_profile(cfg, arc)


def test_export_skips_internal_symlinks_and_import_preserves_profile_on_conflict_or_lock(
    isolated_env: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    _, config_dir, data_dir = isolated_env
    cfg = load_config(config_dir / "config.json")
    claude = get_harness("claude-code")

    _ = create_profile(cfg, "claude-code", "active-sym", set_default=True)
    items = claude.profile_item_paths(data_dir, "active-sym")
    _ = (items["config"] / "keep.txt").write_text("original", encoding="utf-8")
    (items["config"] / "debug-latest").symlink_to(items["config"] / "keep.txt")

    arc = export_profile(cfg, "claude-code", "active-sym", tmp_path / "sym-filtered.tar.gz")
    _ = import_profile(cfg, arc, name="restored-sym")
    restored_cfg = claude.profile_item_paths(data_dir, "restored-sym")["config"]
    assert (restored_cfg / "keep.txt").read_text(encoding="utf-8") == "original"
    assert not (restored_cfg / "debug-latest").exists()

    # Replace $HOME symlink with an untracked directory; overwrite must fail WITHOUT deleting original profile
    claude.paths["config"].unlink()
    claude.paths["config"].mkdir(parents=True)
    with pytest.raises(IsolationError, match="Conflicting untracked path"):
        _ = import_profile(cfg, arc, name="active-sym", overwrite=True)
    assert (items["config"] / "keep.txt").read_text(encoding="utf-8") == "original"

    # Restore $HOME symlink and verify held harness lock blocks overwrite
    claude.paths["config"].rmdir()
    claude.paths["config"].symlink_to(items["config"])
    lpath = lockfile_path(data_dir, "claude-code")
    with lpath.open("w", encoding="utf-8") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ArchiveError, match="already locked"):
            _ = import_profile(cfg, arc, name="active-sym", overwrite=True)
        fcntl.flock(held.fileno(), fcntl.LOCK_UN)


def test_archive_rejects_unsafe_paths_links_and_kind_mismatches(
    isolated_env: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    _, config_dir, _ = isolated_env
    cfg = load_config(config_dir / "config.json")

    for unsafe_member in ("../evil.txt", "config/../../evil.txt", "/etc/passwd"):
        unsafe_arc = _build_tar_gz(
            tmp_path / "unsafe.tar.gz",
            [
                _file_info(ARCHIVE_MANIFEST_FILENAME, _valid_manifest_bytes()),
                _file_info(unsafe_member, b"boom"),
            ],
        )
        with pytest.raises(ArchiveError, match="Unsafe archive member path"):
            _ = import_profile(cfg, unsafe_arc)

    sym_info = tarfile.TarInfo(name="config/link")
    sym_info.type = tarfile.SYMTYPE
    sym_info.linkname = "/etc/hosts"
    sym_arc = _build_tar_gz(
        tmp_path / "sym.tar.gz",
        [
            _file_info(ARCHIVE_MANIFEST_FILENAME, _valid_manifest_bytes()),
            (sym_info, None),
        ],
    )
    with pytest.raises(ArchiveError, match="Unsupported archive member type"):
        _ = import_profile(cfg, sym_arc)

    file_as_dir_key = _build_tar_gz(
        tmp_path / "kind1.tar.gz",
        [
            _file_info(ARCHIVE_MANIFEST_FILENAME, _valid_manifest_bytes()),
            _file_info("config", b"not-a-dir"),
        ],
    )
    with pytest.raises(ArchiveError, match="must be a directory"):
        _ = import_profile(cfg, file_as_dir_key)

    dir_as_file_key = _build_tar_gz(
        tmp_path / "kind2.tar.gz",
        [
            _file_info(ARCHIVE_MANIFEST_FILENAME, _valid_manifest_bytes()),
            _dir_info("config.json"),
        ],
    )
    with pytest.raises(ArchiveError, match="must be a regular file"):
        _ = import_profile(cfg, dir_as_file_key)
