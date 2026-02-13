from __future__ import annotations

import sys
from pathlib import Path

import click

from .modules import modules
from .metadata import CargoMetadataError, Workspace
from .packager import PackagingError, build_single_crate


@click.group()
def cli() -> None:
    """Cargo workspace subsetting tools."""
    pass


@cli.command()
@click.option(
    "--workspace-path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Root path of the cargo workspace",
)
@click.option("--crate", "crate_name", required=True, help="Workspace crate name")
@click.option(
    "--module",
    "module_path",
    default="crate",
    show_default=True,
    help="Starting module path (e.g. crate::foo::bar)",
)
@click.option(
    "--show-files/--hide-files",
    default=True,
    show_default=True,
    help="Whether to print source file paths alongside modules",
)
def tree(workspace_path: Path, crate_name: str, module_path: str, show_files: bool) -> None:
    """Display dependency tree for a module."""
    try:
        workspace = Workspace.from_cargo(workspace_path)
    except CargoMetadataError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)

    # Parse module path and build module ID
    if module_path == "crate":
        module_id = (crate_name,)
    else:
        parts = module_path.split("::")
        if parts[0] == "crate":
            parts = parts[1:]
        module_id = (crate_name,) + tuple(parts)

    try:
        module_dict = modules(workspace, module_id)
    except FileNotFoundError as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)
    except KeyError as exc:
        click.echo(str(exc), err=True)
        sys.exit(3)

    # Print modules as a flat list (tree structure not preserved in new API)
    click.echo(f"Modules reachable from {crate_name}::{module_path}:")
    click.echo()
    for mod_id, mod in sorted(module_dict.items()):
        module_name = "::".join(mod_id)
        if show_files:
            click.echo(f"  {module_name}")
            click.echo(f"    -> {mod.file}")
        else:
            click.echo(f"  {module_name}")


@cli.command()
@click.option(
    "--workspace-path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Root path of the cargo workspace",
)
@click.option("--crate", "crate_name", required=True, help="Entry workspace crate name")
@click.option(
    "--module",
    "module_path",
    default="crate",
    show_default=True,
    help="Starting module path (e.g. crate::foo::bar)",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("dist"),
    show_default=True,
    help="Directory where the new crate will be written",
)
@click.option("--name", "new_crate_name", required=True, help="Name for the generated crate")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Allow writing into an existing empty directory",
)
def pack(
    workspace_path: Path,
    crate_name: str,
    module_path: str,
    output_dir: Path,
    new_crate_name: str,
    force: bool,
) -> None:
    """Build a single crate from workspace subset."""
    try:
        workspace = Workspace.from_cargo(workspace_path)
    except CargoMetadataError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)

    dest = output_dir / new_crate_name
    if dest.exists() and any(dest.iterdir()) and not force:
        click.echo(f"Destination {dest} exists and is not empty. Use --force to override.", err=True)
        sys.exit(2)
    dest.mkdir(parents=True, exist_ok=True)

    try:
        out_path = build_single_crate(
            workspace,
            entry_crate=crate_name,
            entry_module=module_path,
            output_dir=output_dir,
            new_crate_name=new_crate_name,
        )
    except (PackagingError, FileNotFoundError, KeyError) as exc:
        click.echo(str(exc), err=True)
        sys.exit(3)

    click.echo(f"Generated crate at {out_path}")




if __name__ == "__main__":
    cli()
