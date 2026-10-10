from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from rig.cli.misc import require_setup_complete

app = typer.Typer(help="Manage profiles of an agent harness.")

console = Console()


@app.command("list")
def cmd_list(
    harness: Annotated[
        str | None,
        typer.Argument(help="Harness name"),
    ] = None,
) -> None:
    """List all profiles."""

    require_setup_complete()

    table = Table(title="Agent Harness Profiles", header_style="bold cyan")
    table.add_column("Harness", style="bold")
    table.add_column("Profile Name", style="green")
    table.add_column("Default", justify="center")
    table.add_column("Description")
    table.add_column("Last Updated", style="dim")

    console.print(table)


@app.command("create")
def cmd_create(
    harness: Annotated[str, typer.Argument(help="Harness name")],
    name: Annotated[str, typer.Argument(help="New profile name")],
    description: Annotated[str, typer.Option("--desc", "-d", help="Short description of the profile")] = "",
    set_default_flag: Annotated[bool, typer.Option("--default", help="Set as default")] = False,
) -> None:
    """Create a new profile."""

    require_setup_complete()


@app.command("use")
def cmd_use(
    harness: Annotated[str, typer.Argument(help="Harness name")],
    name: Annotated[str, typer.Argument(help="Profile name to set as default")],
) -> None:
    """Set a profile as the default."""

    require_setup_complete()


@app.command("delete")
def cmd_delete(
    harness: Annotated[str, typer.Argument(help="Harness name")],
    name: Annotated[str, typer.Argument(help="Profile name")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force delete even if active default"),
    ] = False,
) -> None:
    """Delete a profile."""

    require_setup_complete()


@app.command("export")
def cmd_export(
    harness: Annotated[str, typer.Argument(help="Harness name")],
    name: Annotated[str, typer.Argument(help="Profile name")],
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Path to output archive"),
    ] = None,
    non_interactive: Annotated[
        bool,
        typer.Option(
            "--non-interactive",
            help="Do not show prompts and use defaults",
        ),
    ] = False,
) -> None:
    """Export a profile as an archive."""

    require_setup_complete()


@app.command("import")
def cmd_import(
    archive: Annotated[Path, typer.Argument(help="Path to archive")],
    harness: Annotated[str | None, typer.Option("--harness", "-h", help="Override target harness")] = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Override target profile name")] = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Overwrite existing profile")] = False,
) -> None:
    """Import a profile from an archive."""

    require_setup_complete()
