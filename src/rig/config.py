from dataclasses import dataclass
from pathlib import Path

from rig.info import DEFAULT_DATAPATH


@dataclass()
class RuntimeConfig:
    datapath: Path = DEFAULT_DATAPATH
    json_mode: bool = False
    verbose: bool = False

    @property
    def configpath(self) -> Path:
        """The path to the configuration file."""
        return self.datapath / "config.json"


# Global configuration object for the application
runtime_config = RuntimeConfig()
