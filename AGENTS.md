# Agent instructions

rig is a Python CLI and TUI for managing profiles across AI agent harnesses, including OpenCode, Claude Code, and Google Antigravity CLI.

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
- `src/rig/__main__.py`: Direct module execution entrypoint for Nuitka.
- `src/rig/info.py`: Metadata constants `NAME`, `VERSION`, `DESCRIPTION`, and `DEFAULT_DATAPATH`.
- `src/rig/config.py`: Runtime configuration dataclass `RigConfig` and active `config` instance.
- `src/rig/cli/`: Typer command handlers. `src/rig/cli/__init__.py` handles global options `--datadir`, `--json`, and `--verbose`, registers top-level commands `run`, `setup`, `status`, `config`, and `version`, then mounts the `profile` subcommand group defined in `src/rig/cli/profile.py`.
- `src/rig/core/`: Profile management logic, setup validation, and harness integrations.
- `src/rig/tui/`: Textual user interface.

## Conventions and gotchas

- Keep version numbers synchronized. `version` in `pyproject.toml` and `VERSION` in `src/rig/info.py` must match. GitHub Actions release detection compares the `pyproject.toml` version against the previous commit.
- Use conventional commits, such as `feat:`, `fix:`, `chore:`, or `build:`.
