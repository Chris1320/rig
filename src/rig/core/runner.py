import fcntl
import subprocess
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path

from rig.config import RigConfig
from rig.core.harnesses import get_harness
from rig.core.isolation import activate_profile, deactivate_harness
from rig.core.profiles import resolve_existing_profile
from rig.exceptions import IsolationError, RunnerError
from rig.info import LOCK_FILENAME
from rig.models import HarnessKey


def lockfile_path(datapath: Path, harness_key: HarnessKey) -> Path:
    """Return the path to the per-harness lockfile `<datapath>/profiles/<harness>/.rig.lock`.

    Args:
        datapath: Root data directory path.
        harness_key: Harness identifier.

    Returns:
        Resolved path to the lockfile.
    """

    return get_harness(harness_key).harness_profiles_dir(datapath) / LOCK_FILENAME


@contextmanager
def harness_lock(datapath: Path, harness_key: HarnessKey) -> Generator[None]:
    """Acquire an exclusive non-blocking lock on the harness's `.rig.lock` file.

    Args:
        datapath: Root data directory path.
        harness_key: Harness identifier.

    Raises:
        RunnerError: If another `rig` process already holds the harness lock.
    """

    lock_path = lockfile_path(datapath, harness_key)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    except OSError as exc:
        lock_file.close()
        raise RunnerError(
            f"Harness '{harness_key}' is already locked by another running 'rig' process ({lock_path})."
        ) from exc

    try:
        yield

    finally:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        finally:
            lock_file.close()


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
