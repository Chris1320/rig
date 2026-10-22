from typing import final


@final
class ConfigError(Exception):
    """Raised when configuration cannot be loaded, validated, or saved."""


@final
class UnknownHarnessError(ValueError):
    """Raised when an unsupported harness key is requested."""

    def __init__(self, key: str) -> None:
        super().__init__(f"Unknown harness '{key}'.")
        self.key: str = key
