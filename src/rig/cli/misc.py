import typer
from rich.console import Console

from rig.core.setup import check_if_setup_complete


def require_setup_complete() -> None:
    """Print out a string message indicating the setup is not complete."""

    if not check_if_setup_complete():
        c = Console()
        c.print(
            "[bold red]Error:[/bold red] Setup is not complete. Please run [bold green]rig setup[/bold green] to complete the setup process."
        )
        raise typer.Exit(code=1)
