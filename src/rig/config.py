import json
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from rig.core.harnesses import HARNESSES
from rig.exceptions import ConfigError
from rig.info import (
    CURRENT_CONFIG_VERSION,
    DEFAULT_CONFIGPATH,
    MIN_SUPPORTED_CONFIG_VERSION,
    NAME,
)
from rig.misc import atomic_temp_path, utc_now_iso, validate_iso_timestamp
from rig.models import IsolationStrategy


def _default_datapath() -> Path:
    """Return the default data path for the application."""
    return (Path.home() / ".local" / "share" / NAME).resolve()


@dataclass()
class RuntimeConfig:
    """Runtime configuration for the application."""

    configpath: Path = DEFAULT_CONFIGPATH
    json_mode: bool = False
    verbose: bool = False

    @property
    def config_file(self) -> Path:
        """The absolute path to the configuration file."""
        return self.configpath.expanduser().resolve() / "config.json"


class ProfileEntry(BaseModel):
    """Metadata for a single profile registered under a harness."""

    name: str
    description: str = ""
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    @field_validator("created_at", "updated_at", mode="after")
    @classmethod
    def _validate_iso_timestamp(cls, value: str) -> str:
        return validate_iso_timestamp(value)


class HarnessEntryConfig(BaseModel):
    """Configuration for a single agent harness."""

    strategy: IsolationStrategy = "move"
    default_profile: str | None = None
    profiles: list[ProfileEntry] = Field(default_factory=list)

    def _find_index(self, name: str) -> int | None:
        """Find the index of the profile matching ``name`` or None if not found.

        Args:
            name: The name of the profile to search for.

        Returns:
            The index of the profile in the profiles list, or None if not found.
        """

        for idx, existing in enumerate(self.profiles):
            if existing.name == name:
                return idx

        return None

    def get_profile(self, name: str) -> ProfileEntry | None:
        """Return the profile matching ``name`` or None.

        Args:
            name: The name of the profile to search for.

        Returns:
            The profile entry if found, or None if not found.
        """

        idx = self._find_index(name)
        return self.profiles[idx] if idx is not None else None

    def upsert_profile(self, entry: ProfileEntry) -> None:
        """Insert a new profile or update an existing profile while preserving `created_at`.

        Args:
            entry: The profile entry to insert or update.
        """

        idx = self._find_index(entry.name)
        if idx is not None:
            existing = self.profiles[idx]
            self.profiles[idx] = entry.model_copy(update={"created_at": existing.created_at})
            return

        self.profiles.append(entry)

    def remove_profile(self, name: str) -> bool:
        """Remove the profile matching `name`. Returns True if removed.

        Args:
            name: The name of the profile to remove.

        Returns:
            True if the profile was found and removed, False otherwise.
        """

        idx = self._find_index(name)
        if idx is None:
            return False

        del self.profiles[idx]
        if self.default_profile == name:
            self.default_profile = None

        return True


def _default_harnesses() -> dict[str, HarnessEntryConfig]:
    return {key: HarnessEntryConfig() for key in HARNESSES}


class RigConfig(BaseModel):
    """Configuration for rig saved in the configuration file."""

    version: float = CURRENT_CONFIG_VERSION
    datapath: Path = Field(default_factory=_default_datapath, validate_default=True)
    harnesses: dict[str, HarnessEntryConfig] = Field(default_factory=_default_harnesses)

    @field_validator("datapath", mode="after")
    @classmethod
    def _normalize_datapath(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @model_validator(mode="after")
    def _validate_version_and_harnesses(self) -> Self:
        if not MIN_SUPPORTED_CONFIG_VERSION <= self.version <= CURRENT_CONFIG_VERSION:
            msg = (
                f"Unsupported config version {self.version} "
                + f"(supported: {MIN_SUPPORTED_CONFIG_VERSION}..{CURRENT_CONFIG_VERSION})"
            )
            raise ValueError(msg)

        unknown = set(self.harnesses.keys()) - set(HARNESSES.keys())
        if unknown:
            unknown_list = ", ".join(sorted(unknown))
            raise ValueError(f"Unknown harness keys in config: {unknown_list}")

        for key in HARNESSES:
            if key not in self.harnesses:
                self.harnesses[key] = HarnessEntryConfig()

        return self


# Global configuration object for the application
runtime_config = RuntimeConfig()


def _resolve_config_path(path: Path | None) -> Path:
    """Resolve the configuration file path, using the provided path or the default from runtime_config.

    Args:
        path: Optional path to the configuration file. If None, the default from runtime_config is used.

    Returns:
        The resolved absolute path to the configuration file.
    """

    return (path or runtime_config.config_file).expanduser().resolve()


def load_config(path: Path | None = None) -> RigConfig:
    """Load and validate RigConfig from disk.

    Args:
        path: Optional path to the configuration file. If None, the default from runtime_config is used.

    Returns:
        The loaded and validated RigConfig object.

    Raises:
        ConfigError: If the configuration file is missing, unreadable, or fails schema validation.
    """

    target = _resolve_config_path(path)
    if not target.exists() or not target.is_file():
        raise ConfigError(f"Configuration file not found at {target}")

    try:
        raw_text = target.read_text(encoding="utf-8")
        data: object = json.loads(raw_text)  # pyright: ignore[reportAny]

    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Failed to read configuration file at {target}: {exc}") from exc

    try:
        return RigConfig.model_validate(data)

    except ValidationError as exc:
        raise ConfigError(f"Invalid configuration in {target}: {exc}") from exc


def save_config(config: RigConfig, path: Path | None = None) -> None:
    """Atomically serialize and write RigConfig to disk.

    Args:
        config: The RigConfig object to serialize and save.
        path: Optional path to the configuration file. If None, the default from runtime_config is used.

    Raises:
        ConfigError: If writing or atomically replacing the configuration file fails.
    """

    target = _resolve_config_path(path)
    payload = json.dumps(config.model_dump(mode="json"), indent=2) + "\n"
    try:
        with atomic_temp_path(target, prefix=".config.", suffix=".tmp") as tmp_path:
            _ = tmp_path.write_text(payload, encoding="utf-8")

    except OSError as exc:
        raise ConfigError(f"Failed to write configuration file at {target}: {exc}") from exc
