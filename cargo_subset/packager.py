from __future__ import annotations

from pathlib import Path

from .ast import extract_macro_exports
from .metadata import Workspace, Crate, Target
from .modules import modules
from .rewrites import TransformContext, apply_rewrites


class PackagingError(RuntimeError):
    pass


def write_modules(
    module_dict: dict,
    dest_root: Path,
) -> None:
    """Transform and write all modules to destination.

    Args:
        module_dict: Dictionary of modules to write
        dest_root: Root directory of the output crate
    """
    # Auto-detect macro_export names
    macro_export_names = set()
    for module in module_dict.values():
        macro_export_names.update(extract_macro_exports(module.file))

    # Build crate name map (identity mapping since we use crate names directly)
    included_crates = {m.crate for m in module_dict.values()}
    crate_name_map = {crate: crate for crate in included_crates}

    # Collect all present files for context
    present_files = {dest_root / m.destination_path for m in module_dict.values()}

    # Apply transforms to each module
    for module in module_dict.values():
        dest_file = dest_root / module.destination_path
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        # Create context for this module
        context = TransformContext(
            dest_file=dest_file,
            present_files=present_files,
            current_crate=module.crate,
            current_sanitized=module.crate,  # Use crate name as-is
            crate_name_map=crate_name_map,
            macro_export_names=macro_export_names,
        )

        # Read source and apply all rewrites
        source_text = module.file.read_text()
        transformed = apply_rewrites(source_text, context)

        dest_file.write_text(transformed)


def write_lib_rs(module_dict: dict, dest_root: Path) -> set[str]:
    """Write root lib.rs with pub mod declarations for all included crates.

    Args:
        module_dict: Dictionary of modules
        dest_root: Root directory of the output crate

    Returns:
        Set of included crate names
    """
    included_crates = {m.crate for m in module_dict.values()}
    lib_lines = [f"pub mod {crate};" for crate in sorted(included_crates)]
    (dest_root / "src" / "lib.rs").write_text("\n".join(lib_lines) + "\n")
    return included_crates


def write_cargo_toml(
    workspace: Workspace,
    included_crates: set[str],
    entry_crate: str,
    new_crate_name: str,
    dest_root: Path,
) -> None:
    """Generate and write Cargo.toml for the output crate.

    Args:
        workspace: Workspace metadata
        included_crates: Set of included crate names
        entry_crate: Name of the entry crate (for edition)
        new_crate_name: Name for the generated crate
        dest_root: Root directory of the output crate
    """
    edition = workspace.crate(entry_crate).edition or "2021"

    # Merge all included crates' packages to collect dependencies
    merged_pkg = None
    for crate in included_crates:
        pkg = workspace.crate(crate)
        if merged_pkg is None:
            merged_pkg = pkg
        else:
            merged_pkg = merged_pkg.merge(pkg)

    # Filter dependencies: keep only external, non-optional dependencies
    if merged_pkg:
        external_deps = [
            dep
            for dep in merged_pkg.dependencies
            if not dep.optional
            and dep.name not in included_crates
            and not workspace.is_workspace_member(dep.name)
        ]
        merged_features = merged_pkg.features
    else:
        external_deps = []
        merged_features = None

    # Check if any included crate has doctest=false on lib target
    doctest = True
    for crate_name in included_crates:
        crate = workspace.crate(crate_name)
        for target in crate.targets:
            if target.is_lib and not target.doctest:
                doctest = False
                break
        if not doctest:
            break

    # Create lib target with appropriate doctest flag
    lib_target = Target(
        name=new_crate_name,
        kind=["lib"],
        src_path=dest_root / "src" / "lib.rs",
        doctest=doctest,
    )

    # Create synthetic package for rendering
    pkg = Crate(
        id=f"{new_crate_name}#0.1.0",
        name=new_crate_name,
        manifest_path=Path(new_crate_name) / "Cargo.toml",
        targets=[lib_target],
        dependencies=external_deps,
        edition=edition,
        features=merged_features,
    )
    cargo_toml = pkg.render()
    (dest_root / "Cargo.toml").write_text(cargo_toml)


def build_single_crate(
    workspace: Workspace,
    entry_crate: str,
    entry_module: str,
    output_dir: Path,
    new_crate_name: str,
) -> Path:
    """Build a single crate subset from workspace.

    Args:
        workspace: Workspace metadata
        entry_crate: Name of the entry crate
        entry_module: Module path within the entry crate
        output_dir: Directory to write the output crate
        new_crate_name: Name for the generated crate

    Returns:
        Path to the generated crate root directory
    """
    # Step 1: Collect reachable modules
    symbol = (
        f"{entry_crate}::{entry_module}" if entry_module != "crate" else entry_crate
    )
    parts = symbol.split("::")
    module_id = tuple(parts[1:]) if len(parts) > 1 else ()
    id = (entry_crate,) + module_id
    module_dict = modules(workspace, id)

    # Step 2: Prepare output directory
    dest_root = output_dir / new_crate_name
    if dest_root.exists() and any(dest_root.iterdir()):
        raise PackagingError(f"Destination {dest_root} already exists and is not empty")

    # Step 3: Copy and transform files
    write_modules(module_dict, dest_root)

    # Step 4: Write root lib.rs
    included_crates = write_lib_rs(module_dict, dest_root)

    # Step 5: Generate Cargo.toml
    write_cargo_toml(workspace, included_crates, entry_crate, new_crate_name, dest_root)

    return dest_root
