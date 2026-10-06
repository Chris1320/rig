from typing import Annotated

import typer
from rich.console import Console

from rig.cli.profile import app as profile_app
from rig.info import DESCRIPTION, NAME, VERSION

app = typer.Typer(
    help=f"{NAME} - {DESCRIPTION}",
    rich_markup_mode="rich",
    no_args_is_help=False,
)
app.add_typer(profile_app, name="profile")


@app.command(
    "run", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def run_profile(
    ctx: typer.Context,
    harness: Annotated[str, typer.Argument(help="Harness name")],
    name: Annotated[str, typer.Argument(help="Profile to run")],
) -> None:
    """Run an agent harness under a specific profile."""


@app.command("setup")
def setup() -> None:
    """Run the interactive setup wizard."""


@app.command("status")
def status() -> None:
    """Show status of harnesses and active profiles."""


@app.command("version")
def version() -> None:
    """Show the version of the application."""

    c = Console()
    c.print(f"[bold cyan]{NAME}[/bold cyan] - [dim]{DESCRIPTION}[/dim]")
    c.print(f"Version: [bold green]{VERSION}[/bold green]")
