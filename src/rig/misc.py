import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Returns:
        An ISO-8601 formatted UTC timestamp string.
    """

    return datetime.now(UTC).isoformat()


def validate_iso_timestamp(value: str) -> str:
    """Validate that `value` parses as an ISO-8601 UTC timestamp string.

    Args:
        value: Timestamp string to validate.

    Returns:
        The validated timestamp string.

    Raises:
        ValueError: If `value` is not a valid ISO-8601 UTC timestamp.
    """

    try:
        parsed = datetime.fromisoformat(value)

    except ValueError as exc:
        raise ValueError(f"Invalid timestamp: '{value}'") from exc

    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"Invalid timestamp (must be UTC): '{value}'")

    return value


@contextmanager
def atomic_temp_path(
    target: Path,
    *,
    prefix: str = ".tmp-",
    suffix: str = ".tmp",
    overwrite: bool = True,
) -> Generator[Path]:
    """Yield a temporary sibling path and atomically commit it to `target` on clean exit.

    Args:
        target: Final destination file path.
        prefix: Filename prefix for the temporary sibling file.
        suffix: Filename suffix for the temporary sibling file.
        overwrite: When True, atomically replaces `target` via `os.replace`. When False,
            uses `os.link` so an existing file at `target` raises `FileExistsError` without overwriting.

    Yields:
        Path to the temporary sibling file ready to be written.

    Raises:
        FileExistsError: If `overwrite` is False and `target` already exists.
        OSError: If directory creation, temporary file creation, or atomic commit fails.
    """

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(dir=target.parent, prefix=prefix, suffix=suffix)
    os.close(fd)
    tmp_path = Path(raw_tmp)
    try:
        yield tmp_path
        if overwrite:
            os.replace(tmp_path, target)

        else:
            os.link(tmp_path, target)
            tmp_path.unlink()

    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()

        raise
