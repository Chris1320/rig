import shutil
from dataclasses import dataclass

from rig.config import HarnessEntryConfig, ProfileEntry, RigConfig, save_config
from rig.core.harnesses import HARNESSES, HarnessSpec, get_harness
from rig.core.isolation import activate_profile, deactivate_harness
from rig.exceptions import IsolationError, ProfileError
from rig.info import PROFILE_NAME_PATTERN
from rig.misc import utc_now_iso
from rig.models import HarnessKey, IsolationStrategy


@dataclass(frozen=True)
class ProfileListItem:
    """Summary entry for a single profile returned by `list_profiles`."""

    harness: HarnessKey
    name: str
    is_default: bool
    description: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        """Serialize the profile list item into a JSON-compatible dictionary."""

        return {
            "harness": self.harness,
            "name": self.name,
            "is_default": self.is_default,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def validate_profile_name(name: str) -> str:
    """Validate that `name` is a safe profile identifier.

    Args:
        name: Candidate profile name.

    Returns:
        The validated profile name.

    Raises:
        ProfileError: If `name` is empty, starts with `.`, or contains disallowed characters.
    """

    if not PROFILE_NAME_PATTERN.match(name):
        raise ProfileError(
            f"Invalid profile name '{name}'. Profile names must start with an alphanumeric character "
            + "and contain only letters, digits, '.', '_', or '-'."
        )

    return name


def resolve_existing_profile(
    config: RigConfig,
    harness: str,
    name: str,
) -> tuple[HarnessSpec, HarnessEntryConfig, ProfileEntry]:
    """Validate `harness` and `name` and return the spec, harness config, and existing profile.

    Args:
        config: Loaded RigConfig instance.
        harness: Target harness key.
        name: Profile name to look up.

    Returns:
        Tuple of `(HarnessSpec, HarnessEntryConfig, ProfileEntry)`.

    Raises:
        UnknownHarnessError: If `harness` is not supported.
        ProfileError: If `name` is invalid or does not exist.
    """

    spec = get_harness(harness)
    _ = validate_profile_name(name)
    entry_cfg = config.harnesses[spec.key]
    existing = entry_cfg.get_profile(name)
    if existing is None:
        raise ProfileError(f"Profile '{name}' does not exist for harness '{spec.key}'.")

    return spec, entry_cfg, existing


def list_profiles(config: RigConfig, harness: str | None = None) -> list[ProfileListItem]:
    """List profiles across all harnesses or for a single `harness`.

    Args:
        config: Loaded RigConfig instance.
        harness: Optional harness key filter.

    Returns:
        A list of ProfileListItem entries.
    """

    specs: list[HarnessSpec]
    if harness is not None:
        specs = [get_harness(harness)]

    else:
        specs = list(HARNESSES.values())

    items: list[ProfileListItem] = []
    for spec in specs:
        entry_cfg = config.harnesses[spec.key]
        for prof in entry_cfg.profiles:
            items.append(
                ProfileListItem(
                    harness=spec.key,
                    name=prof.name,
                    is_default=entry_cfg.default_profile == prof.name,
                    description=prof.description,
                    created_at=prof.created_at,
                    updated_at=prof.updated_at,
                )
            )

    return items


def create_profile(  # pylint: disable=too-many-arguments
    config: RigConfig,
    harness: str,
    name: str,
    *,
    description: str = "",
    set_default: bool = False,
    strategy: IsolationStrategy | None = None,
) -> ProfileEntry:
    """Create a new profile for `harness` and optionally activate it as default.

    Args:
        config: Loaded RigConfig instance.
        harness: Target harness key.
        name: New profile name.
        description: Optional human-readable description.
        set_default: Whether to activate the profile and mark it as default.
        strategy: Optional isolation strategy override for the harness.

    Returns:
        The created ProfileEntry.

    Raises:
        ProfileError: If the profile name is invalid or already exists.
        IsolationError: If activating the profile fails.
    """

    spec = get_harness(harness)
    _ = validate_profile_name(name)
    entry_cfg = config.harnesses[spec.key]
    prof_dir = spec.profile_dir(config.datapath, name)

    if entry_cfg.get_profile(name) is not None or prof_dir.exists():
        raise ProfileError(f"Profile '{name}' already exists for harness '{spec.key}'.")

    target_strategy: IsolationStrategy = strategy if strategy is not None else entry_cfg.strategy
    _ = spec.init_profile_dir(config.datapath, name)
    try:
        if set_default:
            activate_profile(spec, config.datapath, name, target_strategy)
            entry_cfg.default_profile = name

    except IsolationError:
        if prof_dir.exists():
            shutil.rmtree(prof_dir)

        raise

    entry_cfg.strategy = target_strategy
    profile = ProfileEntry(name=name, description=description)
    entry_cfg.upsert_profile(profile)
    save_config(config)
    return profile


def use_profile(
    config: RigConfig,
    harness: str,
    name: str,
    strategy: IsolationStrategy | None = None,
) -> ProfileEntry:
    """Activate `name` for `harness` and set it as the default profile.

    Args:
        config: Loaded RigConfig instance.
        harness: Target harness key.
        name: Profile name to activate.
        strategy: Optional isolation strategy override for the harness.

    Returns:
        The updated ProfileEntry.

    Raises:
        ProfileError: If the profile does not exist.
        IsolationError: If activating the profile fails.
    """

    spec, entry_cfg, existing = resolve_existing_profile(config, harness, name)
    target_strategy: IsolationStrategy = strategy if strategy is not None else entry_cfg.strategy
    activate_profile(spec, config.datapath, name, target_strategy)

    entry_cfg.strategy = target_strategy
    entry_cfg.default_profile = name
    updated = existing.model_copy(update={"updated_at": utc_now_iso()})
    entry_cfg.upsert_profile(updated)
    save_config(config)
    return updated


def delete_profile(
    config: RigConfig,
    harness: str,
    name: str,
    force: bool = False,
) -> None:
    """Delete `name` from `harness` and remove its directory from disk.

    Args:
        config: Loaded RigConfig instance.
        harness: Target harness key.
        name: Profile name to delete.
        force: Allow deleting the currently active default profile.

    Raises:
        ProfileError: If the profile does not exist or is the active default without `force`.
    """

    spec, entry_cfg, _ = resolve_existing_profile(config, harness, name)
    if entry_cfg.default_profile == name:
        if not force:
            raise ProfileError(f"Profile '{name}' is the active default for '{spec.key}'. Pass --force to delete it.")

        deactivate_harness(spec, config.datapath)

    prof_dir = spec.profile_dir(config.datapath, name)
    if prof_dir.exists():
        shutil.rmtree(prof_dir)

    _ = entry_cfg.remove_profile(name)
    save_config(config)
