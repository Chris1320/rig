import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from rig.cli.misc import require_setup_complete
from rig.cli.profile import app as profile_app
from rig.config import (
    AntigravityHarnessConfig,
    ClaudeCodeHarnessConfig,
    HarnessConfig,
    OpencodeHarnessConfig,
    RigConfig,
    runtime_config,
)
from rig.info import (
    CURRENT_CONFIG_VERSION,
    DEFAULT_CONFIGPATH,
    DEFAULT_DATAPATH,
    DESCRIPTION,
    NAME,
    VERSION,
)

app = typer.Typer(
    help=f"{NAME} - {DESCRIPTION}",
    rich_markup_mode="rich",
    no_args_is_help=False,
)
app.add_typer(profile_app, name="profile")


@app.callback()
def global_options(
    configdir: Annotated[
        Path,
        typer.Option("--config-dir", "-c", help="The configuration path"),
    ] = DEFAULT_CONFIGPATH,
    json_mode: Annotated[bool, typer.Option("--json", "-j", help="Output in JSON format")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
) -> None:
    """Supply global options."""

    runtime_config.configpath = configdir
    runtime_config.json_mode = json_mode
    runtime_config.verbose = verbose


@app.command("run", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def cmd_run(
    ctx: typer.Context,
    harness: Annotated[str, typer.Argument(help="Harness name")],
    name: Annotated[str, typer.Argument(help="Profile to run")],
) -> None:
    """Run an agent harness under a specific profile."""

    require_setup_complete()


@app.command("setup")
def cmd_setup(
    datadir: Annotated[Path, typer.Option("--data-dir", "-d", help="Directory for data files")] = DEFAULT_DATAPATH,
) -> None:
    """Run the interactive setup wizard."""

    c = Console()
    if runtime_config.configpath.exists() and any(runtime_config.configpath.iterdir()):
        c.print(
            f"[bold yellow]WARNING[/bold yellow]: Configuration file already exists at [bold green]{runtime_config.config_file.absolute()}[/bold green]."
        )
        raise typer.Exit(code=2)

    if datadir.exists() and any(datadir.iterdir()):
        c.print(
            f"[bold yellow]WARNING[/bold yellow]: Data directory already exists at [bold green]{datadir.absolute()}[/bold green]."
        )
        raise typer.Exit(code=3)

    c.print(f"Creating configuration directory at [bold green]{runtime_config.configpath.absolute()}[/bold green]")
    claude_code_config = ClaudeCodeHarnessConfig()
    opencode_config = OpencodeHarnessConfig()
    antigravity_config = AntigravityHarnessConfig()
    harness_config = HarnessConfig(
        claude_code=claude_code_config,
        opencode=opencode_config,
        antigravity=antigravity_config,
    )
    rig_config = RigConfig(harness=harness_config, datapath=datadir, version=CURRENT_CONFIG_VERSION)

    new_config = asdict(rig_config)
    runtime_config.configpath.mkdir(parents=True, exist_ok=True)
    _ = runtime_config.config_file.write_text(json.dumps(new_config, default=str, indent=2))

    c.print(f"Creating data directory at [bold green]{datadir.absolute()}[/bold green]")
    datadir.mkdir(parents=True, exist_ok=True)


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
