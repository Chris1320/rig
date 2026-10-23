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


@final
class IsolationError(Exception):
    """Raised when profile isolation or activation fails."""


@final
class SetupError(Exception):
    """Raised when initial setup validation or migration fails."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code: int = exit_code


@final
class ProfileError(Exception):
    """Raised when a profile operation fails validation or preconditions."""


@final
class RunnerError(Exception):
    """Raised when running a harness under a temporary profile fails."""
