import typer
from rich.console import Console

from rig.config import runtime_config
from rig.core.setup import check_if_setup_complete


def vprint(
    *args: object,
    sep: str = " ",
    end: str = "\n",
    use_rich: bool = True,
    prefix: str = "[black][VERBOSE][/black]",
    force_enable: bool = False,
) -> None:
    """Print a message if verbose mode is enabled.

    Args:
        args: Positional arguments to pass to the print function.
        sep: Separator between arguments.
        end: String appended after the last value.
        use_rich: Whether to use rich for printing.
        prefix: Prefix to prepend to the message.
        force_enable: Whether to force enable printing regardless of verbose mode.
    """

    if runtime_config.verbose or force_enable:
        if use_rich:
            Console().print(*((prefix,) + args), sep=sep, end=end)

        else:
            print(*((prefix,) + args), sep=sep, end=end)


def require_setup_complete() -> None:
    """Print out a string message indicating the setup is not complete."""

    if not check_if_setup_complete():
        c = Console()
        c.print(
            "[bold red]Error:[/bold red] Setup is not complete. Please run [bold green]rig setup[/bold green] to complete the setup process."
        )
        raise typer.Exit(code=1)
