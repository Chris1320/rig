from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from rig.cli.misc import (
    exit_with_error,
    print_app_banner,
    print_json,
    require_setup_complete,
)
from rig.cli.profile import app as profile_app
from rig.config import RigConfig, load_config, runtime_config
from rig.core.harnesses import HARNESSES
from rig.core.isolation import check_harness_status
from rig.core.setup import check_if_setup_complete, run_setup
from rig.exceptions import ConfigError, SetupError
from rig.info import DEFAULT_CONFIGPATH, DEFAULT_DATAPATH, DESCRIPTION, NAME, VERSION

app = typer.Typer(
    help=f"{NAME} - {DESCRIPTION}",
    rich_markup_mode="rich",
    no_args_is_help=True,
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
    """Run the initial setup and migrate existing home configurations."""

    try:
        result = run_setup(datadir)

    except SetupError as exc:
        exit_with_error(
            str(exc),
            exit_code=exc.exit_code,
            rich_prefix="[bold yellow]WARNING[/bold yellow]:",
            include_exit_code=True,
        )

    if runtime_config.json_mode:
        print_json(
            {
                "config_file": str(result.config_file),
                "datapath": str(result.datapath),
                "migrated_harnesses": list(result.migrated_harnesses),
            }
        )
        return

    c = Console()
    c.print(f"Created configuration file at [bold green]{result.config_file}[/bold green]")
    c.print(f"Created data directory at [bold green]{result.datapath}[/bold green]")
    if result.migrated_harnesses:
        migrated_str = ", ".join(result.migrated_harnesses)
        c.print(f"Migrated existing configurations into [bold cyan]default[/bold cyan] profile for: {migrated_str}")


@app.command("status")
def cmd_status() -> None:
    """Show status of harnesses and active profiles."""

    require_setup_complete()
    try:
        cfg = load_config()

    except ConfigError as exc:
        exit_with_error(str(exc))

    statuses = [check_harness_status(spec, cfg) for spec in HARNESSES.values()]

    if runtime_config.json_mode:
        print_json({"harnesses": [st.to_dict() for st in statuses]})
        return

    table = Table(title="Agent Harness Status", header_style="bold cyan")
    table.add_column("Harness", style="bold")
    table.add_column("Binary")
    table.add_column("Strategy")
    table.add_column("Default Profile", style="green")
    table.add_column("Synced", justify="center")
    table.add_column("Profiles", justify="right")

    for st in statuses:
        b_path = st.spec.binary_path()
        bin_display = f"[green]{st.spec.binary}[/green]" if b_path else f"[dim]{st.spec.binary} (missing)[/dim]"
        default_display = st.default_profile if st.default_profile else "-"
        synced_display = "[bold green]yes[/bold green]" if st.synced else "[bold red]no[/bold red]"
        table.add_row(
            st.spec.key,
            bin_display,
            st.strategy,
            default_display,
            synced_display,
            str(st.profile_count),
        )

    Console().print(table)


@app.command("config")
def cmd_config() -> None:
    """Show the current configuration of the application."""

    persisted: RigConfig | None = None
    if check_if_setup_complete():
        try:
            persisted = load_config()

        except ConfigError as exc:
            exit_with_error(str(exc))

    runtime_payload = {
        "configpath": str(runtime_config.configpath.expanduser().resolve()),
        "config_file": str(runtime_config.config_file),
        "json_mode": runtime_config.json_mode,
        "verbose": runtime_config.verbose,
    }

    if runtime_config.json_mode:
        print_json(
            {
                "name": NAME,
                "version": VERSION,
                "runtime": runtime_payload,
                "config": persisted.model_dump(mode="json") if persisted is not None else None,
            }
        )
        return

    c = Console()
    print_app_banner(c)
    c.print("[bold]Runtime Configuration:[/bold]")
    for key, value in runtime_payload.items():
        c.print(f"  [bold]{key}[/bold]: {value}")

    if persisted is not None:
        c.print("\n[bold]Persisted Configuration:[/bold]")
        c.print(f"  [bold]version[/bold]: {persisted.version}")
        c.print(f"  [bold]datapath[/bold]: {persisted.datapath}")
        for h_key, h_cfg in persisted.harnesses.items():
            default_prof = h_cfg.default_profile or "-"
            c.print(
                f"  [bold]{h_key}[/bold]: strategy={h_cfg.strategy}, "
                + f"default={default_prof}, profiles={len(h_cfg.profiles)}"
            )


@app.command("version")
def cmd_version() -> None:
    """Show the version of the application."""

    if runtime_config.json_mode:
        print_json(
            {
                "name": NAME,
                "version": VERSION,
                "description": DESCRIPTION,
            }
        )
        return

    c = Console()
    print_app_banner(c)
