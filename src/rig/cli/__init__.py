from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from rig.cli.profile import app as profile_app
from rig.config import config
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

    config.datapath = datadir
    config.json_mode = json_mode
    config.verbose = verbose


@app.command(
    "run", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def cmd_run(
    ctx: typer.Context,
    harness: Annotated[str, typer.Argument(help="Harness name")],
    name: Annotated[str, typer.Argument(help="Profile to run")],
) -> None:
    """Run an agent harness under a specific profile."""


@app.command("setup")
def cmd_setup() -> None:
    """Run the interactive setup wizard."""


@app.command("status")
def cmd_status() -> None:
    """Show status of harnesses and active profiles."""


@app.command("config")
def cmd_config() -> None:
    """Show the current configuration of the application."""

    c = Console()
    c.print(f"[bold cyan]{NAME}[/bold cyan] - [dim]{DESCRIPTION}[/dim]")
    c.print(f"Version: [bold green]{VERSION}[/bold green]\n")
    c.print("[bold]Configuration:[/bold]")
    for key, value in config.__dict__.items():  # pyright: ignore[reportAny]
        c.print(f"  [bold]{key}[/bold]: {value}")


@app.command("version")
def cmd_version() -> None:
    """Show the version of the application."""

    c = Console()
    c.print(f"[bold cyan]{NAME}[/bold cyan] - [dim]{DESCRIPTION}[/dim]")
    c.print(f"Version: [bold green]{VERSION}[/bold green]\n")
