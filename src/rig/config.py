from dataclasses import dataclass
from pathlib import Path

from rig.info import DEFAULT_DATAPATH


@dataclass()
class RigConfig:
    datapath: Path = DEFAULT_DATAPATH
    json_mode: bool = False
    verbose: bool = False


# Global configuration object for the application
config = RigConfig()
