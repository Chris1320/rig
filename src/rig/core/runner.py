import subprocess
from collections.abc import Sequence

from rig.config import RigConfig
from rig.core.isolation import (
    activate_profile,
    deactivate_harness,
    harness_lock,
    lockfile_path,
)
from rig.core.profiles import resolve_existing_profile
from rig.exceptions import IsolationError, RunnerError

__all__ = ["harness_lock", "lockfile_path", "run_harness_profile"]


def run_harness_profile(
    config: RigConfig,
    harness: str,
    profile_name: str,
    args: Sequence[str],
) -> int:
    """Temporarily activate `profile_name`, run the harness binary, and restore prior state.

    Args:
        config: Loaded RigConfig instance.
        harness: Target harness key.
        profile_name: Profile to activate for the duration of the run.
        args: Extra CLI arguments forwarded to the harness binary.

    Returns:
        The exit code returned by the harness subprocess.

    Raises:
        ProfileError: If `profile_name` is invalid or does not exist.
        RunnerError: If the binary is missing, the lockfile is held, or profile swap fails.
    """

    spec, entry_cfg, _ = resolve_existing_profile(config, harness, profile_name)
    bin_path = spec.binary_path()
    if bin_path is None:
        raise RunnerError(f"Executable '{spec.binary}' for harness '{spec.key}' was not found on PATH.")

    previous_default = entry_cfg.default_profile
    strategy = entry_cfg.strategy

    with harness_lock(config.datapath, spec.key):
        try:
            activate_profile(spec, config.datapath, profile_name, strategy)

        except IsolationError as exc:
            raise RunnerError(str(exc)) from exc

        try:
            try:
                completed = subprocess.run([str(bin_path), *args], check=False)

            except OSError as exc:
                raise RunnerError(f"Failed to execute '{bin_path}': {exc}") from exc

            return completed.returncode

        finally:
            try:
                if previous_default is not None:
                    activate_profile(spec, config.datapath, previous_default, strategy)

                else:
                    deactivate_harness(spec, config.datapath)

            except IsolationError as exc:
                raise RunnerError(f"Failed to restore previous profile state for '{spec.key}': {exc}") from exc
