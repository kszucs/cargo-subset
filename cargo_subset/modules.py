"""
Dependency graph construction for Rust workspace modules.

This module provides a clean, object-oriented API for building and traversing
dependency graphs of Rust modules within a cargo workspace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from .ast import extract_dependencies
from .metadata import Workspace


@dataclass
class Module:
    """Represents a Rust module with its file, dependencies, and identity.

    A module is identified by its id tuple:
    - id[0]: crate name
    - id[1:]: module path segments within the crate

    Example: ('core', 'utils', 'helpers') represents core::utils::helpers
    """
    id: Tuple[str, ...]
    file: Path
    depends_on: List["Module"] = field(default_factory=list)

    @property
    def crate(self) -> str:
        """The crate name (first element of id)."""
        return self.id[0] if self.id else ""

    @property
    def destination_path(self) -> Path:
        """The relative path where this module should be placed in the new crate.

        Returns:
            Relative path from the new crate root, including crate name
            (e.g., src/core/mod.rs, src/core/utils.rs, src/core/utils/mod.rs)
        """
        # Crate root: use mod.rs since the parent lib.rs references it as a module
        if len(self.id) == 1:
            return Path("src") / self.id[0] / "mod.rs"

        # Check if this is a mod.rs or lib.rs file
        if self.file.name in ("mod.rs", "lib.rs"):
            # For mod.rs/lib.rs files, keep the directory structure with full id
            return Path("src") / Path(*self.id) / "mod.rs"
        else:
            # For standalone module files, use the last segment as filename
            # All segments except the last become the directory path
            return Path("src") / Path(*self.id[:-1]) / f"{self.id[-1]}.rs"

    def __str__(self) -> str:
        if len(self.id) <= 1:
            return self.crate
        return f"{self.crate}::{('::'.join(self.id[1:]))}"

    @classmethod
    def from_id(
        cls,
        workspace: Workspace,
        id: Tuple[str, ...],
        cache: Dict[Tuple[str, ...], "Module"],
    ) -> "Module":
        """Build a Module from its identity, recursively resolving dependencies.

        Args:
            workspace: Workspace metadata
            id: Module identity as (crate, *module_segments) tuple
            cache: Cache to avoid infinite recursion and duplicate work

        Returns:
            Module with dependencies populated
        """
        # Check cache first
        if id in cache:
            return cache[id]

        # Resolve file
        _, file_path = workspace.crate(id[0]).module(id[1:])

        # Create module
        mod = cls(id=id, file=file_path)

        # Store in cache immediately to handle circular dependencies
        cache[id] = mod

        # Extract and normalize all dependencies
        dependencies = extract_dependencies(
            id,
            file_path,
            set(workspace.crates.keys()),
        )

        for dep_crate, dep_id in dependencies:
            # Skip external crates (not workspace members)
            if not workspace.is_workspace_member(dep_crate):
                continue

            try:
                # Resolve to actual module file (handles type/symbol imports)
                actual_segments, _ = workspace.crate(dep_crate).module(dep_id)
                actual_dep_id = (dep_crate,) + actual_segments

                # Build the dependency module recursively
                dep_module = cls.from_id(workspace, actual_dep_id, cache)
                mod.depends_on.append(dep_module)
            except (FileNotFoundError, KeyError, ValueError):
                # Not a valid workspace module, skip (3rd party or unknown)
                pass

        return mod


def modules(
    workspace: Workspace,
    id: Tuple[str, ...],
) -> Dict[Tuple[str, ...], Module]:
    """Build a module dependency graph from an entry module.

    Args:
        workspace: Workspace metadata
        id: Entry module identity as (crate, *module_segments) tuple

    Returns:
        Dictionary mapping module identities to Module objects, containing
        all reachable modules from the entry point

    Raises:
        FileNotFoundError: If entry module cannot be resolved
        KeyError: If crate is not a workspace member
    """
    cache: Dict[Tuple[str, ...], Module] = {}
    Module.from_id(workspace, id, cache)
    return cache

