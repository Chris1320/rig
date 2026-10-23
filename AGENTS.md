# Agent instructions

rig is a Python CLI for managing profiles across AI agent harnesses, including OpenCode, Claude Code, and Google Antigravity CLI.

## Requirements and setup

Python 3.14 or newer is required. uv manages dependencies and virtual environments.

- Sync dependencies: `uv sync --group dev`
- Run CLI locally: `uv run rig --help`

## Verification commands

Run checks in this order before submitting changes:

1. Code style and lint: `./scripts/lint.sh`
    - Pylint requires a score of 9.0 or higher: `uv run pylint --fail-under=9 src tests`
    - Format check: `uv run black --check --verbose src tests`
    - Import order check: `uv run isort --check-only --diff --profile black src tests`
    - Format code: `uv run black src tests && uv run isort --profile black src tests`
2. Test suite with coverage: `./scripts/test.sh`
    - Run a single test file: `uv run pytest tests/test_info.py`
    - Run a specific test function: `uv run pytest tests/test_info.py -k test_info`
    - Test without coverage, or when the workspace root is read-only: `uv run pytest -o cache_dir=/tmp/pytest_cache`

## Building and packaging

Build outputs are saved to `dist/`:

- Build wheel: `./scripts/build.sh wheel` or `uv build --wheel --out-dir dist`
- Build standalone executable: `./scripts/build.sh nuitka`
    - Linux builds require `patchelf`. Install it via `sudo dnf install patchelf` or `sudo apt install patchelf`.
- Build both targets: `./scripts/build.sh all`

## Codebase architecture

Source files live in `src/rig/`:

- `src/rig/__init__.py`: Package root and console entrypoint `main`.
- `src/rig/__main__.py`: Direct module execution entrypoint (`python -m rig` and Nuitka).
- `src/rig/info.py`: `Final` package metadata, version bounds, marker/lock/manifest filenames, and `PROFILE_NAME_PATTERN`.
- `src/rig/exceptions.py`: All `@final` domain exceptions (`ConfigError`, `UnknownHarnessError`, `IsolationError`, `SetupError`, `ProfileError`, `RunnerError`, `ArchiveError`).
- `src/rig/models.py`: Shared `Literal` type aliases (`HarnessKey`, `IsolationStrategy`, `ItemKind`). Keep domain dataclasses in their owning `core/` modules.
- `src/rig/misc.py`: Shared UTC ISO-8601 timestamp helpers and `atomic_temp_path`.
- `src/rig/config.py`: `RuntimeConfig` dataclass (`runtime_config` singleton) plus Pydantic `RigConfig`, `HarnessEntryConfig`, `ProfileEntry`, `load_config`, and atomic `save_config`.
- `src/rig/cli/`: Typer command handlers. `src/rig/cli/__init__.py` handles global options `--config-dir` (`-c`), `--json` (`-j`), and `--verbose` (`-v`), registers top-level commands `run`, `setup` (`--data-dir` / `-d`), `status`, `config`, and `version`, and mounts `src/rig/cli/profile.py` (`list`, `create`, `use`, `delete`, `export`, `import`).
- `src/rig/core/`: `harnesses.py` (built-in harness specs), `isolation.py` (`symlink`/`move` strategies and `.rig_active`), `setup.py` (initial setup and `$HOME` migration), `profiles.py` (profile CRUD), `runner.py` (`.rig.lock` and temporary `rig run` execution), and `archive.py` (`.tar.gz` export and import).

## Conventions and gotchas

- Keep version numbers synchronized. `version` in `pyproject.toml` and `VERSION` in `src/rig/info.py` must match. GitHub Actions release detection compares the `pyproject.toml` version against the previous commit.
- Write Google-style docstrings (`Args:`, `Returns:`/`Yields:`, `Raises:`) on public functions and helpers, `@final` on exception classes in `src/rig/exceptions.py`, and `Final[...]` annotations on constants in `src/rig/info.py`.
- `TrackedItem.path` and `RigConfig` resolve `Path.home()` dynamically at call time, whereas `DEFAULT_CONFIGPATH` and `DEFAULT_DATAPATH` in `src/rig/info.py` bind at import time. Isolate `$HOME` in CLI tests with `monkeypatch.setenv("HOME", ...)` alongside `-c <config_dir>` and `setup -d <data_dir>` (see `isolated_env` in `tests/conftest.py`).
- Use conventional commits, such as `feat:`, `fix:`, `chore:`, or `build:`.
