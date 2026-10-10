from pathlib import Path

NAME = "rig"
VERSION = "0.1.0"
DESCRIPTION = "Manage multiple profiles for agent harnesses."

CURRENT_CONFIG_VERSION = 1.0
MIN_SUPPORTED_CONFIG_VERSION = 1.0
DEFAULT_DATAPATH = Path(Path.home() / ".config") / NAME
