from dataclasses import dataclass
from pathlib import Path

from rig.info import CURRENT_CONFIG_VERSION, DEFAULT_CONFIGPATH, DEFAULT_DATAPATH


@dataclass()
class RuntimeConfig:
    """Runtime configuration for the application."""

    configpath: Path = DEFAULT_CONFIGPATH
    json_mode: bool = False
    verbose: bool = False

    @property
    def config_file(self) -> Path:
        """The path to the configuration file."""
        return self.configpath / "config.json"


@dataclass()
class ClaudeCodeHarnessConfig:
    """Configuration for the Claude Code harness."""

    # TODO: To be implemented


@dataclass()
class OpencodeHarnessConfig:
    """Configuration for the OpenCode harness."""

    # TODO: To be implemented


@dataclass()
class AntigravityHarnessConfig:
    """Configuration for the Antigravity harness."""

    # TODO: To be implemented


@dataclass()
class HarnessConfig:
    """This dataclass acts as the container for the configs of supported
    agent harnesses.
    """

    claude_code: ClaudeCodeHarnessConfig
    opencode: OpencodeHarnessConfig
    antigravity: AntigravityHarnessConfig


@dataclass()
class RigConfig:
    """Configuration for rig saved in the configuration file."""

    harness: HarnessConfig
    datapath: Path = DEFAULT_DATAPATH
    version: float = CURRENT_CONFIG_VERSION


# Global configuration object for the application
runtime_config = RuntimeConfig()
