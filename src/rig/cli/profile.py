from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from rig.cli.misc import exit_with_error, print_json, require_setup_complete
from rig.config import ProfileEntry, RigConfig, load_config, runtime_config
from rig.core.archive import export_profile, import_profile
from rig.core.profiles import (
    create_profile,
    delete_profile,
    list_profiles,
    resolve_existing_profile,
    use_profile,
)
from rig.exceptions import (
    ArchiveError,
    ConfigError,
    IsolationError,
    ProfileError,
    UnknownHarnessError,
)
from rig.models import IsolationStrategy

app = typer.Typer(help="Manage profiles of an agent harness.", no_args_is_help=True)

console = Console()


def _print_profile_result_json(cfg: RigConfig, harness: str, profile: ProfileEntry) -> None:
    """Print profile result in JSON format.

    Args:
        cfg: The RigConfig object.
        harness: The name of the harness.
        profile: The ProfileEntry object.
    """

    print_json(
        {
            "harness": harness,
            "profile": profile.model_dump(mode="json"),
            "is_default": cfg.harnesses[harness].default_profile == profile.name,
            "strategy": cfg.harnesses[harness].strategy,
        }
    )


@app.command("list")
def cmd_list(
    harness: Annotated[
        str | None,
        typer.Argument(help="Harness name"),
    ] = None,
) -> None:
    """List all profiles."""

    require_setup_complete()
    try:
        cfg = load_config()
        items = list_profiles(cfg, harness=harness)

    except (ConfigError, UnknownHarnessError) as exc:
        exit_with_error(str(exc))

    if runtime_config.json_mode:
        print_json({"profiles": [item.to_dict() for item in items]})
        return

    table = Table(title="Agent Harness Profiles", header_style="bold cyan")
    table.add_column("Harness", style="bold")
    table.add_column("Profile Name", style="green")
    table.add_column("Default", justify="center")
    table.add_column("Description")
    table.add_column("Last Updated", style="dim")

    for item in items:
        default_mark = "[bold green]*[/bold green]" if item.is_default else ""
        table.add_row(
            item.harness,
            item.name,
            default_mark,
            item.description,
            item.updated_at,
        )

    console.print(table)


@app.command("create")
def cmd_create(
    harness: Annotated[str, typer.Argument(help="Harness name")],
    name: Annotated[str, typer.Argument(help="New profile name")],
    description: Annotated[str, typer.Option("--desc", "-d", help="Short description of the profile")] = "",
    set_default_flag: Annotated[bool, typer.Option("--default", help="Set as default")] = False,
    strategy: Annotated[
        IsolationStrategy | None,
        typer.Option("--strategy", help="Isolation strategy (symlink or move)"),
    ] = None,
) -> None:
    """Create a new profile."""

    require_setup_complete()
    try:
        cfg = load_config()
        created = create_profile(
            cfg,
            harness=harness,
            name=name,
            description=description,
            set_default=set_default_flag,
            strategy=strategy,
        )

    except (ConfigError, UnknownHarnessError, ProfileError, IsolationError) as exc:
        exit_with_error(str(exc))

    if runtime_config.json_mode:
        _print_profile_result_json(cfg, harness, created)
        return

    console.print(f"Created profile [bold green]{created.name}[/bold green] for [bold cyan]{harness}[/bold cyan].")
    if set_default_flag:
        console.print(f"Activated [bold green]{created.name}[/bold green] as default profile.")


@app.command("use")
def cmd_use(
    harness: Annotated[str, typer.Argument(help="Harness name")],
    name: Annotated[str, typer.Argument(help="Profile name to set as default")],
    strategy: Annotated[
        IsolationStrategy | None,
        typer.Option("--strategy", help="Isolation strategy (symlink or move)"),
    ] = None,
) -> None:
    """Set a profile as the default."""

    require_setup_complete()
    try:
        cfg = load_config()
        updated = use_profile(cfg, harness=harness, name=name, strategy=strategy)

    except (ConfigError, UnknownHarnessError, ProfileError, IsolationError) as exc:
        exit_with_error(str(exc))

    if runtime_config.json_mode:
        _print_profile_result_json(cfg, harness, updated)
        return

    console.print(
        f"Using profile [bold green]{updated.name}[/bold green] for [bold cyan]{harness}[/bold cyan] "
        + f"(strategy: [bold]{cfg.harnesses[harness].strategy}[/bold])."
    )


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
    try:
        cfg = load_config()
        delete_profile(cfg, harness=harness, name=name, force=force)

    except (ConfigError, UnknownHarnessError, ProfileError) as exc:
        exit_with_error(str(exc))

    if runtime_config.json_mode:
        print_json({"harness": harness, "deleted": name})
        return

    console.print(f"Deleted profile [bold green]{name}[/bold green] from [bold cyan]{harness}[/bold cyan].")


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
    try:
        cfg = load_config()
        spec, _, _ = resolve_existing_profile(cfg, harness, name)

    except (ConfigError, UnknownHarnessError, ProfileError) as exc:
        exit_with_error(str(exc))

    exclude_caches = True
    if spec.cache_keys and not non_interactive and not runtime_config.json_mode:
        exclude_caches = typer.confirm("Exclude cache directories from archive?", default=True)

    try:
        archive_path = export_profile(
            cfg,
            harness=spec.key,
            name=name,
            output_path=output,
            exclude_caches=exclude_caches,
        )

    except (UnknownHarnessError, ProfileError, ArchiveError) as exc:
        exit_with_error(str(exc))

    caches_excluded = exclude_caches and bool(spec.cache_keys)
    if runtime_config.json_mode:
        print_json(
            {
                "harness": spec.key,
                "profile": name,
                "archive": str(archive_path),
                "caches_excluded": caches_excluded,
            }
        )
        return

    console.print(
        f"Exported profile [bold green]{name}[/bold green] from [bold cyan]{spec.key}[/bold cyan] "
        + f"to [bold]{archive_path}[/bold]."
    )


@app.command("import")
def cmd_import(
    archive: Annotated[Path, typer.Argument(help="Path to archive")],
    harness: Annotated[str | None, typer.Option("--harness", "-h", help="Override target harness")] = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Override target profile name")] = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Overwrite existing profile")] = False,
) -> None:
    """Import a profile from an archive."""

    require_setup_complete()
    try:
        cfg = load_config()
        target_harness, imported = import_profile(
            cfg,
            archive_path=archive,
            harness=harness,
            name=name,
            overwrite=overwrite,
        )

    except (ConfigError, UnknownHarnessError, ProfileError, IsolationError, ArchiveError) as exc:
        exit_with_error(str(exc))

    if runtime_config.json_mode:
        _print_profile_result_json(cfg, target_harness, imported)
        return

    console.print(
        f"Imported profile [bold green]{imported.name}[/bold green] into [bold cyan]{target_harness}[/bold cyan]."
    )
