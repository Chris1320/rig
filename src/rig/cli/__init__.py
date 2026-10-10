import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from rig.cli.misc import require_setup_complete, vprint
from rig.cli.profile import app as profile_app
from rig.config import (
    AntigravityHarnessConfig,
    ClaudeCodeHarnessConfig,
    HarnessConfig,
    OpencodeHarnessConfig,
    RigConfig,
    runtime_config,
)
from rig.info import DEFAULT_DATAPATH, DESCRIPTION, NAME, VERSION

app = typer.Typer(
    help=f"{NAME} - {DESCRIPTION}",
    rich_markup_mode="rich",
    no_args_is_help=False,
)
app.add_typer(profile_app, name="profile")


@app.callback()
def global_options(
    datadir: Annotated[
        Path,
        typer.Option(
            "--datadir", "-d", help="Directory for configuration and data files"
        ),
    ] = DEFAULT_DATAPATH,
    json_mode: Annotated[
        bool, typer.Option("--json", "-j", help="Output in JSON format")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose output")
    ] = False,
) -> None:
    """Supply global options."""

    runtime_config.datapath = datadir
    runtime_config.json_mode = json_mode
    runtime_config.verbose = verbose


@app.command(
    "run", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def cmd_run(
    ctx: typer.Context,
    harness: Annotated[str, typer.Argument(help="Harness name")],
    name: Annotated[str, typer.Argument(help="Profile to run")],
) -> None:
    """Run an agent harness under a specific profile."""

    require_setup_complete()


@app.command("setup")
def cmd_setup(
    clean: Annotated[
        bool,
        typer.Option("--clean", "-c", help="Remove existing configuration directory"),
    ] = False,
) -> None:
    """Run the interactive setup wizard."""

    c = Console()
    if clean and runtime_config.datapath.exists():
        vprint("Removing existing configuration and data files...")
        shutil.rmtree(runtime_config.datapath)

    c.print(
        f"Creating configuration and data directory at [bold green]{runtime_config.datapath}[/bold green]"
    )
    runtime_config.datapath.mkdir(parents=True, exist_ok=True)
    claude_code_config = ClaudeCodeHarnessConfig()
    opencode_config = OpencodeHarnessConfig()
    antigravity_config = AntigravityHarnessConfig()
    harness_config = HarnessConfig(
        claude_code=claude_code_config,
        opencode=opencode_config,
        antigravity=antigravity_config,
    )
    rig_config = RigConfig(harness_config)

    new_config = asdict(rig_config)

    _ = runtime_config.configpath.write_text(json.dumps(new_config, indent=2))


@app.command("status")
def cmd_status() -> None:
    """Show status of harnesses and active profiles."""

    require_setup_complete()


@app.command("config")
def cmd_config() -> None:
    """Show the current configuration of the application."""

    c = Console()
    c.print(f"[bold cyan]{NAME}[/bold cyan] - [dim]{DESCRIPTION}[/dim]")
    c.print(f"Version: [bold green]{VERSION}[/bold green]\n")
    c.print("[bold]Runtime Configuration:[/bold]")
    for key, value in runtime_config.__dict__.items():  # pyright: ignore[reportAny]
        c.print(f"  [bold]{key}[/bold]: {value}")


@app.command("version")
def cmd_version() -> None:
    """Show the version of the application."""

    c = Console()
    c.print(f"[bold cyan]{NAME}[/bold cyan] - [dim]{DESCRIPTION}[/dim]")
    c.print(f"Version: [bold green]{VERSION}[/bold green]\n")
