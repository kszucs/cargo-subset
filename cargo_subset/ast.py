"""
Tree-sitter based dependency extraction for Rust source code.

This module provides a simple function to extract module and use dependencies
from Rust source files that need further investigation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Set, Tuple


# Lazily initialize the parser to avoid upfront cost
_parser = None


def _normalize(
    segments: List[str],
    context_crate: str,
    context_id: Tuple[str, ...],
    workspace_crates: Set[str],
) -> Tuple[str, Tuple[str, ...]]:
    """Normalize a use path to an absolute module identity.

    Handles 'crate::', 'self::', 'super::', and external crate references.
    """
    if not segments:
        raise ValueError("Cannot normalize empty module path segments")

    first = segments[0]
    base: List[str]
    target_crate: str = context_crate

    if first == "crate":
        base = []
        remainder = segments[1:]
    elif first == "self":
        base = list(context_id)
        remainder = segments[1:]
    elif first == "super":
        base = list(context_id)
        idx = 0
        while idx < len(segments) and segments[idx] == "super":
            if base:
                base.pop()
            idx += 1
        remainder = segments[idx:]
    else:
        # Rust 2018: bare paths - check if it's a workspace crate
        if first == context_crate:
            target_crate = context_crate
            base = []
            remainder = segments[1:]
        elif first in workspace_crates:
            target_crate = first
            base = []
            remainder = segments[1:]
        else:
            # Treat as a relative module path from current context
            # This handles cases like `pub use nested::Foo` in a module file
            # which should resolve to current_module::nested::Foo
            base = list(context_id)
            remainder = segments

    absolute = base + remainder
    if not absolute:
        raise ValueError(f"Invalid module path: cannot normalize {segments}")
    return (target_crate, tuple(absolute))


def _get_parser():
    """Get or initialize the tree-sitter Rust parser."""
    global _parser
    if _parser is None:
        from tree_sitter_languages import get_parser

        _parser = get_parser("rust")
    return _parser


def extract_macro_exports(file_path: Path) -> Set[str]:
    """Extract names of macros marked with #[macro_export].

    Args:
        file_path: Path to the Rust source file

    Returns:
        Set of macro names that have #[macro_export]
    """
    source_bytes = file_path.read_bytes()
    tree = _get_parser().parse(source_bytes)
    root = tree.root_node

    macro_names = set()

    # Iterate through top-level items looking for attribute + macro_definition pairs
    children = root.children
    for i, node in enumerate(children):
        # Look for macro_definition preceded by attribute_item
        if node.type == "macro_definition":
            # Check if previous sibling is #[macro_export] attribute
            has_macro_export = False
            if i > 0 and children[i - 1].type == "attribute_item":
                attr_text = source_bytes[
                    children[i - 1].start_byte : children[i - 1].end_byte
                ].decode("utf-8")
                if "macro_export" in attr_text:
                    has_macro_export = True

            # Extract macro name
            if has_macro_export:
                for child in node.children:
                    if child.type == "identifier":
                        macro_name = source_bytes[
                            child.start_byte : child.end_byte
                        ].decode("utf-8")
                        macro_names.add(macro_name)
                        break

    return macro_names


def extract_dependencies(
    id: Tuple[str, ...],
    file_path: Path,
    workspace_crates: Set[str],
) -> List[Tuple[str, Tuple[str, ...]]]:
    """Extract and normalize module and use dependencies from a Rust source file.

    This function extracts dependencies and resolves crate::, self::, super:: references.

    Args:
        id: Current module's full identity (crate, *path_segments)
        file_path: Path to the Rust source file
        workspace_crates: Set of all workspace crate names

    Returns:
        List of (crate, module_id) tuples representing normalized dependencies.
        Examples:
        - `use crate::foo::bar;` returns `('current_crate', ('foo', 'bar'))`
        - `mod foo;` returns `('current_crate', ('current', 'module', 'foo'))`
        - `use super::sibling;` returns `('current_crate', ('parent', 'sibling'))`
    """
    crate = id[0]
    module_id = id[1:]

    source_bytes = file_path.read_bytes()
    tree = _get_parser().parse(source_bytes)
    root = tree.root_node

    raw_dependencies = []

    def walk(node: Any) -> None:
        # Extract mod declarations (e.g., mod foo;)
        # Note: Only extract mod declarations without a body (external modules)
        # Inline modules (with body) are not separate files
        if node.type == "mod_item":
            has_body = any(child.type == "declaration_list" for child in node.children)
            if not has_body:
                # Extract the module name
                for child in node.children:
                    if child.type == "identifier":
                        mod_name = source_bytes[
                            child.start_byte : child.end_byte
                        ].decode("utf-8")
                        # Add as a submodule of current context
                        raw_dependencies.append((mod_name,))
                        break

        # Extract use declarations
        if node.type == "use_declaration":
            for child in node.children:
                if child.type in (
                    "scoped_identifier",
                    "identifier",
                    "scoped_use_list",
                    "use_list",
                    "use_wildcard",
                    "use_as_clause",
                ):
                    _extract_use_paths(child, [], raw_dependencies, source_bytes)
                    break

        # Extract macro invocations (e.g., utils::log_info!(...))
        # Macros with #[macro_export] are available at the crate root
        if node.type == "macro_invocation":
            for child in node.children:
                if child.type == "scoped_identifier":
                    path_parts = _extract_scoped_path(child, source_bytes)
                    if path_parts:  # Only add if we have a path
                        raw_dependencies.append(tuple(path_parts))
                    break

        # Recurse into children
        for child in node.children:
            walk(child)

    walk(root)

    # Normalize all dependencies (from mod declarations, use statements, and macro invocations)
    normalized = []
    for dep_tuple in raw_dependencies:
        try:
            # Single-element tuples are from 'mod foo;' declarations (child modules)
            # These should always be appended to the current module path, not normalized
            if len(dep_tuple) == 1:
                dep_crate, dep_id = crate, module_id + dep_tuple
            else:
                # Multi-element tuples are from 'use' statements and macro invocations
                dep_crate, dep_id = _normalize(
                    list(dep_tuple),
                    crate,
                    module_id,
                    workspace_crates,
                )
            normalized.append((dep_crate, dep_id))
        except ValueError:
            # Skip invalid paths
            pass

    return normalized


def _extract_use_paths(
    node: Any,
    prefix: List[str],
    dependencies: List[Tuple[str, ...]],
    source_bytes: bytes,
) -> None:
    """Recursively extract use paths from a use tree node."""

    if node.type == "identifier":
        name = source_bytes[node.start_byte : node.end_byte].decode("utf-8")
        dependencies.append(tuple(prefix + [name]))

    elif node.type == "scoped_identifier":
        path_parts = _extract_scoped_path(node, source_bytes)
        dependencies.append(tuple(prefix + path_parts))

    elif node.type == "use_wildcard":
        # For `use foo::*`, extract the path before the wildcard
        for child in node.children:
            if child.type == "scoped_identifier":
                path_parts = _extract_scoped_path(child, source_bytes)
                dependencies.append(tuple(prefix + path_parts))
                return
        # Just `use *` (rare case)
        if prefix:
            dependencies.append(tuple(prefix))

    elif node.type == "use_as_clause":
        # For `use foo as bar`, extract the original path (not the alias)
        for child in node.children:
            if child.type in ("identifier", "scoped_identifier"):
                if child.type == "identifier":
                    name = source_bytes[child.start_byte : child.end_byte].decode(
                        "utf-8"
                    )
                    dependencies.append(tuple(prefix + [name]))
                else:
                    path_parts = _extract_scoped_path(child, source_bytes)
                    dependencies.append(tuple(prefix + path_parts))
                break

    elif node.type == "scoped_use_list":
        # For `foo::{bar, baz}`, extract the prefix first
        new_prefix = prefix[:]
        use_list_node = None

        for child in node.children:
            if child.type == "scoped_identifier" or child.type == "identifier":
                if child.type == "identifier":
                    name = source_bytes[child.start_byte : child.end_byte].decode(
                        "utf-8"
                    )
                    new_prefix.append(name)
                else:
                    new_prefix.extend(_extract_scoped_path(child, source_bytes))
            elif child.type == "use_list":
                use_list_node = child

        if use_list_node:
            _extract_use_paths(use_list_node, new_prefix, dependencies, source_bytes)

    elif node.type == "use_list":
        # For `{a, b, c}`, extract each item
        for child in node.children:
            if child.type not in ("{", "}", ","):
                _extract_use_paths(child, prefix, dependencies, source_bytes)


def _extract_scoped_path(node: Any, source_bytes: bytes) -> List[str]:
    """Extract path segments from a scoped_identifier node.

    Handles special path prefixes like crate::, self::, super::
    """
    segments = []

    def walk_path(n: Any) -> None:
        if n.type == "identifier":
            name = source_bytes[n.start_byte : n.end_byte].decode("utf-8")
            segments.append(name)
        elif n.type in ("self", "super", "crate"):
            name = source_bytes[n.start_byte : n.end_byte].decode("utf-8")
            segments.append(name)
        elif n.type == "scoped_identifier":
            for child in n.children:
                if child.type != "::":
                    walk_path(child)

    walk_path(node)
    return segments
