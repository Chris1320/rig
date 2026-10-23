import io
import json
import os
import shutil
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Self

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from rig.config import HarnessEntryConfig, ProfileEntry, RigConfig, save_config
from rig.core.harnesses import HarnessSpec, get_harness
from rig.core.isolation import (
    activate_profile,
    deactivate_harness,
    read_active_marker,
    verify_no_home_conflicts,
)
from rig.core.profiles import (
    profile_exists,
    resolve_existing_profile,
    validate_profile_name,
)
from rig.core.runner import harness_lock
from rig.exceptions import ArchiveError, ProfileError, RunnerError
from rig.info import (
    ARCHIVE_MANIFEST_FILENAME,
    CURRENT_ARCHIVE_VERSION,
    MIN_SUPPORTED_ARCHIVE_VERSION,
    VERSION,
)
from rig.misc import atomic_temp_path, utc_now_iso, validate_iso_timestamp
from rig.models import HarnessKey


class ArchiveManifest(BaseModel):
    """Metadata stored inside `manifest.json` at the root of a profile archive."""

    version: float = CURRENT_ARCHIVE_VERSION
    rig_version: str = VERSION
    harness: HarnessKey
    profile_name: str
    description: str = ""
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    exported_at: str = Field(default_factory=utc_now_iso)
    caches_excluded: bool = False

    @field_validator("created_at", "updated_at", "exported_at", mode="after")
    @classmethod
    def _validate_iso_timestamp(cls, value: str) -> str:
        return validate_iso_timestamp(value)

    @field_validator("profile_name", mode="after")
    @classmethod
    def _validate_profile_name_field(cls, value: str) -> str:
        try:
            return validate_profile_name(value)

        except ProfileError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def _validate_version(self) -> Self:
        if not MIN_SUPPORTED_ARCHIVE_VERSION <= self.version <= CURRENT_ARCHIVE_VERSION:
            msg = (
                f"Unsupported archive version {self.version} "
                + f"(supported: {MIN_SUPPORTED_ARCHIVE_VERSION}..{CURRENT_ARCHIVE_VERSION})"
            )
            raise ValueError(msg)

        return self


def _export_tar_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Keep only regular files and directories when archiving a profile.

    Args:
        tarinfo: Candidate archive member metadata.

    Returns:
        The unmodified `tarinfo` for regular files and directories, or None to skip links and special files.
    """

    if tarinfo.isfile() or tarinfo.isdir():
        return tarinfo

    return None


def _write_bytes_member(tar: tarfile.TarFile, arcname: str, payload: bytes) -> None:
    """Write an in-memory regular file entry into `tar`.

    Args:
        tar: Open destination archive.
        arcname: Archive member name.
        payload: File content bytes.
    """

    info = tarfile.TarInfo(name=arcname)
    info.size = len(payload)
    info.mode = 0o644
    info.mtime = int(time.time())
    tar.addfile(info, io.BytesIO(payload))


def _write_empty_dir_member(tar: tarfile.TarFile, arcname: str) -> None:
    """Write an empty directory entry into `tar`.

    Args:
        tar: Open destination archive.
        arcname: Directory member name.
    """

    info = tarfile.TarInfo(name=arcname)
    info.type = tarfile.DIRTYPE
    info.mode = 0o755
    info.mtime = int(time.time())
    tar.addfile(info)


def _add_tracked_items_to_tar(
    tar: tarfile.TarFile,
    spec: HarnessSpec,
    source_paths: dict[str, Path],
    *,
    exclude_caches: bool,
) -> None:
    """Add tracked harness items under their canonical `<key>` names to `tar`.

    Args:
        tar: Open destination archive.
        spec: Harness specification.
        source_paths: Mapping of tracked item keys to live source filesystem paths.
        exclude_caches: Whether to skip tracked items marked `is_cache=True`.
    """

    for item in spec.items:
        if exclude_caches and item.is_cache:
            continue

        src_path = source_paths[item.key]
        if src_path.exists():
            tar.add(src_path, arcname=item.key, recursive=True, filter=_export_tar_filter)

        elif item.kind == "dir":
            _write_empty_dir_member(tar, item.key)

        else:
            _write_bytes_member(tar, item.key, b"{}\n")


def _build_manifest_bytes(spec: HarnessSpec, profile: ProfileEntry, *, exclude_caches: bool) -> bytes:
    """Construct serialized UTF-8 `manifest.json` bytes for `profile`.

    Args:
        spec: Harness specification.
        profile: Profile metadata entry.
        exclude_caches: Whether cache exclusion was requested.

    Returns:
        UTF-8 encoded JSON bytes for `manifest.json`.
    """

    manifest = ArchiveManifest(
        harness=spec.key,
        profile_name=profile.name,
        description=profile.description,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        caches_excluded=exclude_caches and bool(spec.cache_keys),
    )
    return (json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n").encode("utf-8")


def export_profile(
    config: RigConfig,
    harness: str,
    name: str,
    output_path: Path | None = None,
    *,
    exclude_caches: bool = True,
) -> Path:
    """Export profile `name` for `harness` into a `.tar.gz` archive.

    Args:
        config: Loaded RigConfig instance.
        harness: Target harness key.
        name: Profile name to export.
        output_path: Optional destination `.tar.gz` path. Defaults to `./<harness>-<name>.tar.gz`.
        exclude_caches: Whether to omit tracked items marked with `is_cache=True`.

    Returns:
        Resolved path to the generated `.tar.gz` archive.

    Raises:
        UnknownHarnessError: If `harness` is not supported.
        ProfileError: If `name` is invalid or does not exist.
        ArchiveError: If writing the archive fails or `output_path` is a directory.
    """

    spec, _, profile = resolve_existing_profile(config, harness, name)
    raw_target = output_path if output_path is not None else Path.cwd() / f"{spec.key}-{name}.tar.gz"
    target = raw_target.expanduser().resolve()

    if target.exists() and target.is_dir():
        raise ArchiveError(f"Output path '{target}' is a directory.")

    is_live_in_home = read_active_marker(config.datapath, spec.key) == name
    source_paths = spec.paths if is_live_in_home else spec.profile_item_paths(config.datapath, name)
    manifest_bytes = _build_manifest_bytes(spec, profile, exclude_caches=exclude_caches)

    try:
        with (
            atomic_temp_path(target, prefix=".export-", suffix=".tar.gz.tmp") as tmp_path,
            tarfile.open(tmp_path, mode="w:gz") as tar,
        ):
            _write_bytes_member(tar, ARCHIVE_MANIFEST_FILENAME, manifest_bytes)
            _add_tracked_items_to_tar(tar, spec, source_paths, exclude_caches=exclude_caches)

    except (OSError, tarfile.TarError) as exc:
        raise ArchiveError(f"Failed to export profile '{name}' to '{target}': {exc}") from exc

    return target


def _normalize_member_parts(member: tarfile.TarInfo) -> tuple[str, ...]:
    """Validate path and type safety for `member` and return normalized POSIX path parts.

    Args:
        member: Archive member to validate.

    Returns:
        Tuple of normalized path components.

    Raises:
        ArchiveError: If `member` has an unsafe path or unsupported entry type.
    """

    if not member.name or member.name.startswith(("/", "\\")):
        raise ArchiveError(f"Unsafe archive member path '{member.name}'.")

    posix_path = PurePosixPath(member.name)
    if posix_path.is_absolute() or ".." in posix_path.parts or ".." in member.name.replace("\\", "/").split("/"):
        raise ArchiveError(f"Unsafe archive member path '{member.name}'.")

    if not (member.isfile() or member.isdir()):
        raise ArchiveError(
            f"Unsupported archive member type for '{member.name}'. Only regular files and directories are allowed."
        )

    return posix_path.parts


def _read_manifest_from_tar(tar: tarfile.TarFile, members: list[tarfile.TarInfo]) -> ArchiveManifest:
    """Validate all archive members and parse `manifest.json`.

    Args:
        tar: Open source archive.
        members: All `TarInfo` entries in `tar`.

    Returns:
        Parsed and validated `ArchiveManifest`.

    Raises:
        ArchiveError: If any member is unsafe or `manifest.json` is missing or invalid.
    """

    manifest_member: tarfile.TarInfo | None = None
    for member in members:
        parts = _normalize_member_parts(member)
        if parts == (ARCHIVE_MANIFEST_FILENAME,):
            manifest_member = member

    if manifest_member is None:
        raise ArchiveError(f"Archive is missing '{ARCHIVE_MANIFEST_FILENAME}'.")

    if not manifest_member.isfile():
        raise ArchiveError(f"Archive '{ARCHIVE_MANIFEST_FILENAME}' must be a regular file.")

    extracted = tar.extractfile(manifest_member)
    if extracted is None:
        raise ArchiveError(f"Failed to read '{ARCHIVE_MANIFEST_FILENAME}' from archive.")

    try:
        raw_text = extracted.read().decode("utf-8")
        data: object = json.loads(raw_text)  # pyright: ignore[reportAny]
        return ArchiveManifest.model_validate(data)

    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ArchiveError(f"Invalid archive manifest: {exc}") from exc


def _validate_members_for_spec(members: list[tarfile.TarInfo], spec: HarnessSpec) -> None:
    """Verify that every non-manifest entry belongs to a valid tracked item for `spec`.

    Args:
        members: All `TarInfo` entries in the archive.
        spec: Target harness specification.

    Raises:
        ArchiveError: If an entry does not match `spec`'s tracked keys or item kinds.
    """

    items_by_key = {item.key: item for item in spec.items}
    for member in members:
        parts = PurePosixPath(member.name).parts
        if not parts:
            if member.isdir():
                continue

            raise ArchiveError(f"Invalid root entry '{member.name}' in archive.")

        if parts == (ARCHIVE_MANIFEST_FILENAME,):
            continue

        top_key = parts[0]
        tracked = items_by_key.get(top_key)
        if tracked is None:
            raise ArchiveError(f"Archive contains unexpected top-level entry '{top_key}' for harness '{spec.key}'.")

        if tracked.kind == "dir" and len(parts) == 1 and not member.isdir():
            raise ArchiveError(f"Archive entry '{top_key}' must be a directory for harness '{spec.key}'.")

        if tracked.kind == "json_file" and (len(parts) > 1 or not member.isfile()):
            raise ArchiveError(f"Archive entry '{top_key}' must be a regular file for harness '{spec.key}'.")


def _extract_to_profile_dir(
    tar: tarfile.TarFile,
    spec: HarnessSpec,
    datapath: Path,
    target_name: str,
    entry_cfg: HarnessEntryConfig,
) -> None:
    """Safely extract `tar` into `<datapath>/profiles/<harness>/<target_name>/` via a staging directory.

    Args:
        tar: Open source archive.
        spec: Target harness specification.
        datapath: Root data directory path.
        target_name: Target profile name.
        entry_cfg: Harness configuration entry.

    Raises:
        ArchiveError: If the harness lock is held or filesystem extraction fails.
        IsolationError: If `$HOME` conflicts block re-activating an active default profile.
    """

    try:
        lock_ctx = harness_lock(datapath, spec.key)

    except RunnerError as exc:
        raise ArchiveError(str(exc)) from exc

    try:
        with lock_ctx:
            harness_dir = spec.harness_profiles_dir(datapath)
            harness_dir.mkdir(parents=True, exist_ok=True)
            staging_dir = Path(tempfile.mkdtemp(dir=harness_dir, prefix=".import-", suffix=".tmp"))
            try:
                tar.extractall(path=staging_dir, filter="data")
                manifest_copy = staging_dir / ARCHIVE_MANIFEST_FILENAME
                if manifest_copy.exists():
                    manifest_copy.unlink()

                was_active_default = entry_cfg.default_profile == target_name
                if was_active_default:
                    verify_no_home_conflicts(spec, datapath)

                owns_home = was_active_default or read_active_marker(datapath, spec.key) == target_name
                if owns_home:
                    deactivate_harness(spec, datapath)

                prof_dir = spec.profile_dir(datapath, target_name)
                if prof_dir.exists():
                    shutil.rmtree(prof_dir)

                os.replace(staging_dir, prof_dir)
                _ = spec.init_profile_dir(datapath, target_name)
                if was_active_default:
                    activate_profile(spec, datapath, target_name, entry_cfg.strategy)

            except (tarfile.TarError, OSError) as exc:
                raise ArchiveError(f"Failed to extract archive for '{spec.key}/{target_name}': {exc}") from exc

            finally:
                if staging_dir.exists():
                    shutil.rmtree(staging_dir)

    except RunnerError as exc:
        raise ArchiveError(str(exc)) from exc


def _persist_imported_profile(
    config: RigConfig,
    entry_cfg: HarnessEntryConfig,
    target_name: str,
    manifest: ArchiveManifest,
) -> ProfileEntry:
    """Upsert the imported profile metadata into `entry_cfg` and persist `config`.

    Args:
        config: Loaded RigConfig instance.
        entry_cfg: Target harness configuration entry.
        target_name: Imported profile name.
        manifest: Validated archive manifest.

    Returns:
        The persisted ProfileEntry.
    """

    imported_entry = ProfileEntry(
        name=target_name,
        description=manifest.description,
        created_at=manifest.created_at,
        updated_at=utc_now_iso(),
    )
    entry_cfg.upsert_profile(imported_entry)
    save_config(config)
    saved = entry_cfg.get_profile(target_name)
    return saved if saved is not None else imported_entry


def import_profile(
    config: RigConfig,
    archive_path: Path,
    *,
    harness: str | None = None,
    name: str | None = None,
    overwrite: bool = False,
) -> tuple[HarnessKey, ProfileEntry]:
    """Import a profile archive into `config.datapath` and register it in `config`.

    Args:
        config: Loaded RigConfig instance.
        archive_path: Path to the `.tar.gz` archive to import.
        harness: Optional target harness override.
        name: Optional target profile name override.
        overwrite: Whether to replace an existing profile with the same name.

    Returns:
        Tuple of `(harness_key, ProfileEntry)` for the imported profile.

    Raises:
        ArchiveError: If the archive is missing, corrupt, unsafe, locked, or incompatible.
        UnknownHarnessError: If `harness` override is not supported.
        ProfileError: If target profile name is invalid or already exists without `overwrite`.
        IsolationError: If re-activating an overwritten active profile fails.
    """

    resolved_archive = archive_path.expanduser().resolve()
    if not resolved_archive.exists() or not resolved_archive.is_file():
        raise ArchiveError(f"Archive file not found at '{resolved_archive}'.")

    try:
        with tarfile.open(resolved_archive, mode="r:gz") as tar:
            members = tar.getmembers()
            manifest = _read_manifest_from_tar(tar, members)
            spec = get_harness(harness if harness is not None else manifest.harness)
            target_name = validate_profile_name(name if name is not None else manifest.profile_name)
            _validate_members_for_spec(members, spec)

            entry_cfg = config.harnesses[spec.key]
            if profile_exists(entry_cfg, spec, config.datapath, target_name) and not overwrite:
                raise ProfileError(
                    f"Profile '{target_name}' already exists for harness '{spec.key}'. Pass --overwrite to replace it."
                )

            _extract_to_profile_dir(tar, spec, config.datapath, target_name, entry_cfg)

    except (OSError, tarfile.TarError) as exc:
        raise ArchiveError(f"Invalid or corrupt archive '{resolved_archive}': {exc}") from exc

    return spec.key, _persist_imported_profile(config, entry_cfg, target_name, manifest)
