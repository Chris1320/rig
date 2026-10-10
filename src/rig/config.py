from dataclasses import dataclass
from pathlib import Path

from rig.info import CURRENT_CONFIG_VERSION, DEFAULT_DATAPATH


@dataclass()
class RuntimeConfig:
    datapath: Path = DEFAULT_DATAPATH
    json_mode: bool = False
    verbose: bool = False

    @property
    def configpath(self) -> Path:
        """The path to the configuration file."""
        return self.datapath / "config.json"


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
    claude_code: ClaudeCodeHarnessConfig
    opencode: OpencodeHarnessConfig
    antigravity: AntigravityHarnessConfig


@dataclass()
class RigConfig:
    harness: HarnessConfig
    version: float = CURRENT_CONFIG_VERSION


# Global configuration object for the application
runtime_config = RuntimeConfig()
