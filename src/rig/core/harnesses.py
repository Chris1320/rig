import shutil
from dataclasses import dataclass
from pathlib import Path

from rig.exceptions import UnknownHarnessError
from rig.models import HarnessKey, ItemKind


@dataclass(frozen=True)
class TrackedItem:
    """Specification for a single filesystem path tracked for a harness."""

    key: str
    target: str
    kind: ItemKind = "dir"
    is_cache: bool = False

    @property
    def path(self) -> Path:
        """Absolute path to the tracked item inside the user's home directory."""
        return Path.home().resolve() / self.target


@dataclass(frozen=True)
class HarnessSpec:
    """Specification for a supported AI agent harness."""

    key: HarnessKey
    binary: str
    items: tuple[TrackedItem, ...]

    @property
    def paths(self) -> dict[str, Path]:
        """Map of tracked item keys to their absolute paths in $HOME."""
        return {item.key: item.path for item in self.items}

    @property
    def cache_keys(self) -> frozenset[str]:
        """Set of tracked item keys marked as cache directories."""
        return frozenset(item.key for item in self.items if item.is_cache)

    def profile_dir(self, datapath: Path, profile_name: str) -> Path:
        """Return the absolute directory path for a given profile."""
        return datapath.expanduser().resolve() / "profiles" / self.key / profile_name

    def profile_item_paths(self, datapath: Path, profile_name: str) -> dict[str, Path]:
        """Map of tracked item keys to their absolute paths inside the profile directory."""
        base = self.profile_dir(datapath, profile_name)
        return {item.key: base / item.key for item in self.items}

    def init_profile_dir(self, datapath: Path, profile_name: str) -> Path:
        """Create the profile directory and initialize all tracked items."""
        base = self.profile_dir(datapath, profile_name)
        base.mkdir(parents=True, exist_ok=True)
        for item in self.items:
            target_path = base / item.key
            if item.kind == "dir":
                target_path.mkdir(parents=True, exist_ok=True)
            elif item.kind == "json_file":
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if not target_path.exists():
                    _ = target_path.write_text("{}\n", encoding="utf-8")
        return base

    def binary_path(self) -> Path | None:
        """Return the resolved path to the harness executable if installed."""
        found = shutil.which(self.binary)
        return Path(found).resolve() if found is not None else None

    def is_installed(self) -> bool:
        """Return True if the harness executable is available on PATH."""
        return self.binary_path() is not None


HARNESSES: dict[str, HarnessSpec] = {
    "antigravity": HarnessSpec(
        key="antigravity",
        binary="agy",
        items=(
            TrackedItem(key="antigravity-cli", target=".gemini/antigravity-cli", kind="dir"),
            TrackedItem(key="config", target=".gemini/config", kind="dir"),
        ),
    ),
    "claude-code": HarnessSpec(
        key="claude-code",
        binary="claude",
        items=(
            TrackedItem(key="config", target=".claude", kind="dir"),
            TrackedItem(key="config.json", target=".claude.json", kind="json_file"),
            TrackedItem(key="data", target=".local/share/claude", kind="dir"),
        ),
    ),
    "opencode": HarnessSpec(
        key="opencode",
        binary="opencode",
        items=(
            TrackedItem(key="config", target=".config/opencode", kind="dir"),
            TrackedItem(key="data", target=".local/share/opencode", kind="dir"),
            TrackedItem(key="cache", target=".cache/opencode", kind="dir", is_cache=True),
        ),
    ),
}


def get_harness(key: str) -> HarnessSpec:
    """Return the HarnessSpec for ``key`` or raise UnknownHarnessError."""
    try:
        return HARNESSES[key]
    except KeyError as exc:
        raise UnknownHarnessError(key) from exc
