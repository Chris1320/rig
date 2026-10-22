import json
from typing import Never

import typer
from rich.console import Console

from rig.config import runtime_config
from rig.core.setup import check_if_setup_complete
from rig.info import DESCRIPTION, NAME, VERSION


def print_json(payload: object) -> None:
    """Print structured JSON output to stdout without Rich line wrapping.

    Args:
        payload: A JSON-serializable object.
    """

    print(json.dumps(payload, indent=2, default=str))


def print_app_banner(console: Console) -> None:
    """Print the application name, description, and version header.

    Args:
        console: The Rich Console instance to print to.
    """

    console.print(f"[bold cyan]{NAME}[/bold cyan] - [dim]{DESCRIPTION}[/dim]")
    console.print(f"Version: [bold green]{VERSION}[/bold green]\n")


def exit_with_error(
    message: str,
    exit_code: int = 1,
    rich_prefix: str = "[bold red]Error:[/bold red]",
    include_exit_code: bool = False,
) -> Never:
    """Render an error in JSON or Rich format and exit with ``exit_code``.

    Args:
        message: Error message to display.
        exit_code: Process exit code.
        rich_prefix: Prefix markup for Rich output.
        include_exit_code: Whether to include `exit_code` in JSON payload.
    """

    if runtime_config.json_mode:
        payload: dict[str, object] = {"error": message}
        if include_exit_code:
            payload["exit_code"] = exit_code

        print_json(payload)

    else:
        Console().print(f"{rich_prefix} {message}")

    raise typer.Exit(code=exit_code)


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
    """Ensure setup is complete or exit with code 1."""

    if not check_if_setup_complete():
        if runtime_config.json_mode:
            exit_with_error("Setup is not complete. Please run `rig setup` to complete the setup process.")

        exit_with_error(
            "Setup is not complete. Please run [bold green]rig setup[/bold green] to complete the setup process."
        )
