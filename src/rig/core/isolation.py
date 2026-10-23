import shutil
from dataclasses import dataclass
from pathlib import Path

from rig.config import HarnessEntryConfig, RigConfig
from rig.core.harnesses import HarnessSpec, get_harness
from rig.exceptions import IsolationError
from rig.info import ACTIVE_MARKER_FILENAME
from rig.models import HarnessKey, IsolationStrategy


@dataclass(frozen=True)
class HarnessStatus:
    """Status report for a single harness."""

    spec: HarnessSpec
    strategy: IsolationStrategy
    default_profile: str | None
    profile_count: int
    synced: bool

    def to_dict(self) -> dict[str, object]:
        """Serialize the status report into a JSON-compatible dictionary."""

        b_path = self.spec.binary_path()
        return {
            "harness": self.spec.key,
            "binary": self.spec.binary,
            "installed": b_path is not None,
            "binary_path": str(b_path) if b_path is not None else None,
            "strategy": self.strategy,
            "default_profile": self.default_profile,
            "profile_count": self.profile_count,
            "synced": self.synced,
        }


def active_marker_path(datapath: Path, harness: HarnessKey) -> Path:
    """Return the path to the `.rig_active` marker file for a harness.

    Args:
        datapath: The root data directory path.
        harness: The harness identifier.

    Returns:
        The resolved path to `<datapath>/profiles/<harness_key>/.rig_active`.
    """

    return get_harness(harness).harness_profiles_dir(datapath) / ACTIVE_MARKER_FILENAME


def read_active_marker(datapath: Path, harness_key: HarnessKey) -> str | None:
    """Read the currently active profile name from `.rig_active` if present.

    Args:
        datapath: The root data directory path.
        harness_key: The harness identifier.

    Returns:
        The active profile name stored in `.rig_active`, or None if unset.
    """

    marker = active_marker_path(datapath, harness_key)
    if not marker.exists() or not marker.is_file():
        return None

    content = marker.read_text(encoding="utf-8").strip()
    return content if content else None


def write_active_marker(datapath: Path, harness_key: HarnessKey, profile_name: str) -> None:
    """Write the active profile name to `.rig_active`.

    Args:
        datapath: The root data directory path.
        harness_key: The harness identifier.
        profile_name: The profile name that currently owns live files in `$HOME`.
    """

    marker = active_marker_path(datapath, harness_key)
    marker.parent.mkdir(parents=True, exist_ok=True)
    _ = marker.write_text(f"{profile_name}\n", encoding="utf-8")


def clear_active_marker(datapath: Path, harness_key: HarnessKey) -> None:
    """Remove the `.rig_active` marker file if it exists.

    Args:
        datapath: The root data directory path.
        harness_key: The harness identifier.
    """

    marker = active_marker_path(datapath, harness_key)
    if marker.exists() or marker.is_symlink():
        marker.unlink()


def _remove_path(path: Path) -> None:
    """Remove a file, symlink, or directory tree at ``path``.

    Args:
        path: Target path to remove.
    """

    if path.is_symlink() or path.is_file():
        path.unlink()

    elif path.is_dir():
        shutil.rmtree(path)


def migrate_home_to_profile(spec: HarnessSpec, datapath: Path, profile_name: str) -> bool:
    """Import existing `$HOME` items for ``spec`` into ``profile_name`` if any non-symlink item exists.

    Args:
        spec: The harness specification.
        datapath: The root data directory path.
        profile_name: Target profile name (usually `"default"`).

    Returns:
        True if at least one non-symlink `$HOME` item was found and migrated, False otherwise.
    """

    has_real_items = any(item.path.exists() and not item.path.is_symlink() for item in spec.items)
    if not has_real_items:
        return False

    profile_base = spec.profile_dir(datapath, profile_name)
    profile_base.mkdir(parents=True, exist_ok=True)

    for item in spec.items:
        home_target = item.path
        dest = profile_base / item.key
        dest.parent.mkdir(parents=True, exist_ok=True)

        if home_target.is_symlink():
            if home_target.exists():
                resolved_src = home_target.resolve()
                if resolved_src.is_dir():
                    _ = shutil.copytree(resolved_src, dest, dirs_exist_ok=True)

                else:
                    _ = shutil.copy2(resolved_src, dest)

            home_target.unlink()

        elif home_target.exists():
            _ = shutil.move(str(home_target), str(dest))

    _ = spec.init_profile_dir(datapath, profile_name)
    return True


def deactivate_harness(spec: HarnessSpec, datapath: Path) -> None:
    """Deactivate any active profile for ``spec`` and restore `$HOME` to an unlinked state.

    If `.rig_active` is present, moves live `$HOME` items back into the active
    profile directory in ``datapath`` and removes `.rig_active`. Removes any
    symlinks at the harness's target `$HOME` paths.

    Args:
        spec: The harness specification.
        datapath: The root data directory path.
    """

    active_profile = read_active_marker(datapath, spec.key)
    if active_profile is not None:
        dest_items = spec.profile_item_paths(datapath, active_profile)
        for item in spec.items:
            home_target = item.path
            dest = dest_items[item.key]
            if home_target.is_symlink():
                home_target.unlink()

            elif home_target.exists():
                if dest.exists() or dest.is_symlink():
                    _remove_path(dest)

                dest.parent.mkdir(parents=True, exist_ok=True)
                _ = shutil.move(str(home_target), str(dest))

        _ = spec.init_profile_dir(datapath, active_profile)
        clear_active_marker(datapath, spec.key)

    for item in spec.items:
        if item.path.is_symlink():
            item.path.unlink()


def _verify_no_home_conflicts(spec: HarnessSpec, datapath: Path) -> None:
    """Raise IsolationError if `$HOME` contains untracked non-symlink items."""

    active_profile = read_active_marker(datapath, spec.key)
    if active_profile is None:
        for item in spec.items:
            home_target = item.path
            if home_target.exists() and not home_target.is_symlink():
                raise IsolationError(
                    f"Conflicting untracked path exists at {home_target}. "
                    + "Move or remove it before activating a profile."
                )

        return

    active_items = spec.profile_item_paths(datapath, active_profile)
    for item in spec.items:
        home_target = item.path
        dest = active_items[item.key]
        if home_target.exists() and not home_target.is_symlink() and dest.exists():
            raise IsolationError(
                f"Conflicting path exists at {home_target} while {dest} also exists in profile '{active_profile}'."
            )


def activate_profile(
    spec: HarnessSpec,
    datapath: Path,
    profile_name: str,
    strategy: IsolationStrategy,
) -> None:
    """Activate ``profile_name`` for ``spec`` using the given isolation ``strategy``.

    Args:
        spec: The harness specification.
        datapath: The root data directory path.
        profile_name: The profile to activate.
        strategy: Either `"symlink"` or `"move"`.

    Raises:
        IsolationError: If an untracked non-symlink path exists in `$HOME` or
            if filesystem operations fail.
    """

    _verify_no_home_conflicts(spec, datapath)

    try:
        deactivate_harness(spec, datapath)
        _ = spec.init_profile_dir(datapath, profile_name)
        profile_items = spec.profile_item_paths(datapath, profile_name)

        if strategy == "symlink":
            for item in spec.items:
                home_target = item.path
                home_target.parent.mkdir(parents=True, exist_ok=True)
                home_target.symlink_to(profile_items[item.key])

        elif strategy == "move":
            for item in spec.items:
                home_target = item.path
                src_path = profile_items[item.key]
                home_target.parent.mkdir(parents=True, exist_ok=True)
                _ = shutil.move(str(src_path), str(home_target))

            write_active_marker(datapath, spec.key, profile_name)

    except OSError as exc:
        raise IsolationError(f"Failed to activate profile '{profile_name}' for '{spec.key}': {exc}") from exc


def _is_harness_synced(spec: HarnessSpec, datapath: Path, entry: HarnessEntryConfig) -> bool:
    """Return True if the harness's `$HOME` state matches its configured default profile."""

    marker = read_active_marker(datapath, spec.key)
    if entry.default_profile is None:
        return marker is None and not any(item.path.is_symlink() for item in spec.items)

    expected = spec.profile_item_paths(datapath, entry.default_profile)
    if entry.strategy == "symlink":
        return marker is None and all(
            item.path.is_symlink() and item.path.exists() and item.path.resolve() == expected[item.key].resolve()
            for item in spec.items
        )

    return marker == entry.default_profile and all(
        item.path.exists() and not item.path.is_symlink() for item in spec.items
    )


def check_harness_status(spec: HarnessSpec, config: RigConfig) -> HarnessStatus:
    """Inspect binary availability and profile sync status for ``spec``.

    Args:
        spec: The harness specification.
        config: The loaded RigConfig instance.

    Returns:
        A HarnessStatus report for ``spec``.
    """

    entry = config.harnesses.get(spec.key, HarnessEntryConfig())
    return HarnessStatus(
        spec=spec,
        strategy=entry.strategy,
        default_profile=entry.default_profile,
        profile_count=len(entry.profiles),
        synced=_is_harness_synced(spec, config.datapath, entry),
    )
