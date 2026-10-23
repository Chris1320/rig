import re
from pathlib import Path
from typing import Final

NAME: Final[str] = "rig"
VERSION: Final[str] = "0.1.0"
DESCRIPTION: Final[str] = "Manage multiple profiles for agent harnesses."

CURRENT_CONFIG_VERSION: Final[float] = 1.0
MIN_SUPPORTED_CONFIG_VERSION: Final[float] = 1.0
DEFAULT_CONFIGPATH: Final[Path] = Path(Path.home() / ".config" / NAME)
DEFAULT_DATAPATH: Final[Path] = Path(Path.home() / ".local" / "share" / NAME)

ACTIVE_MARKER_FILENAME: Final[str] = ".rig_active"
LOCK_FILENAME: Final[str] = ".rig.lock"

PROFILE_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
