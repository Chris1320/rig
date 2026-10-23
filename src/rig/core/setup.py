from dataclasses import dataclass
from pathlib import Path

from rig.config import ProfileEntry, RigConfig, runtime_config, save_config
from rig.core.harnesses import HARNESSES
from rig.core.isolation import activate_profile, migrate_home_to_profile
from rig.exceptions import SetupError
from rig.info import CURRENT_CONFIG_VERSION
from rig.models import HarnessKey


@dataclass(frozen=True)
class SetupResult:
    """Result summary returned by `run_setup`."""

    config_file: Path
    datapath: Path
    migrated_harnesses: tuple[HarnessKey, ...]


def check_if_setup_complete() -> bool:
    """Return True if the configuration directory and file exist.

    Returns:
        True if setup has been completed, False otherwise.
    """

    config_dir = runtime_config.configpath.expanduser().resolve()
    if not config_dir.exists() or not config_dir.is_dir():
        return False

    return runtime_config.config_file.exists() and runtime_config.config_file.is_file()


def run_setup(datadir: Path) -> SetupResult:
    """Initialize configuration and data directories, auto-migrating existing files.

    Detects non-symlink harness files/directories in `$HOME`, moves them into a
    `default` profile under `<datadir>/profiles/<harness>/default/`, and activates
    `default` under the harness's configured default strategy so existing user data is preserved.

    Args:
        datadir: Target data directory path.

    Returns:
        A SetupResult containing created paths and migrated harness keys.

    Raises:
        SetupError: If the configuration directory (exit_code=2) or data directory
            (exit_code=3) already exists and is non-empty.
    """

    config_dir = runtime_config.configpath.expanduser().resolve()
    data_dir = datadir.expanduser().resolve()

    if config_dir.exists() and any(config_dir.iterdir()):
        raise SetupError(
            f"Configuration file already exists at {runtime_config.config_file.absolute()}.",
            exit_code=2,
        )

    if data_dir.exists() and any(data_dir.iterdir()):
        raise SetupError(
            f"Data directory already exists at {data_dir.absolute()}.",
            exit_code=3,
        )

    config_dir.mkdir(parents=True, exist_ok=True)
    profiles_root = data_dir / "profiles"
    profiles_root.mkdir(parents=True, exist_ok=True)

    rig_config = RigConfig(datapath=data_dir, version=CURRENT_CONFIG_VERSION)
    migrated: list[HarnessKey] = []

    for spec in HARNESSES.values():
        if not migrate_home_to_profile(spec, data_dir, "default"):
            continue

        entry = rig_config.harnesses[spec.key]
        activate_profile(spec, data_dir, "default", entry.strategy)
        entry.default_profile = "default"
        entry.upsert_profile(
            ProfileEntry(
                name="default",
                description="Migrated from existing home configuration",
            )
        )
        migrated.append(spec.key)

    save_config(rig_config)
    return SetupResult(
        config_file=runtime_config.config_file,
        datapath=data_dir,
        migrated_harnesses=tuple(migrated),
    )
