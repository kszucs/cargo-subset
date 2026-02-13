"""
Source code rewrite rules for cargo workspace subsetting.

This module provides rewrite rules for transforming Rust source code when packaging
workspace subsets. Each rule handles a specific transformation like rewriting imports,
pruning missing modules, or fixing path references.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Set


# Regex patterns used across multiple rules
# Module declarations: mod foo; or pub mod foo;
PATTERN_MOD_DECL = r"^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+([A-Za-z0-9_]+)\s*;\s*$"

# Pub use statements: pub use foo::bar;
PATTERN_PUB_USE = r"^\s*pub\s+use\s+([A-Za-z0-9_]+)::[^;]+;\s*$"

# Use statements with crate:: prefix
PATTERN_USE_CRATE = r"(^\s*(?:pub\s+)?use\s+)crate::([^;]+)"

# Dollar crate references in macros
PATTERN_DOLLAR_CRATE = r"\$crate::"


# Known external crates that should never be pruned
EXTERNAL_CRATES = {
    "std",
    "core",
    "alloc",
    "lazy_static",
    "tokio",
    "serde",
    "reqwest",
    "reqwest_middleware",
}


class TransformContext:
    """Context information for source code transformations."""

    def __init__(
        self,
        dest_file: Path,
        present_files: Set[Path],
        current_crate: str,
        current_sanitized: str,
        crate_name_map: Dict[str, str],
        macro_export_names: Set[str] | None = None,
    ):
        self.dest_file = dest_file
        self.present_files = present_files
        self.current_crate = current_crate
        self.current_sanitized = current_sanitized
        self.crate_name_map = crate_name_map
        self.macro_export_names = macro_export_names or set()

    @property
    def is_mod_file(self) -> bool:
        """Check if current file is mod.rs or lib.rs."""
        return self.dest_file.name in ("mod.rs", "lib.rs")

    @property
    def module_base_dir(self) -> Path:
        """Get the directory where this file's child modules would live."""
        if self.is_mod_file:
            # mod.rs and lib.rs: children are siblings
            return self.dest_file.parent
        else:
            # foo.rs: children are in foo/ subdirectory
            return self.dest_file.parent / self.dest_file.stem

    @property
    def available_modules(self) -> Set[str]:
        """Find all available module names that can be referenced from this file."""
        modules = set()
        base_dir = self.module_base_dir

        # Find child modules
        for p in self.present_files:
            # Direct .rs files in base_dir
            if (
                p.parent == base_dir
                and p.suffix == ".rs"
                and p.name not in ("mod.rs", "lib.rs")
            ):
                modules.add(p.stem)
            # Directories with mod.rs
            if p.name == "mod.rs" and p.parent.parent == base_dir:
                modules.add(p.parent.name)

        # For non-mod files, also include sibling modules
        if not self.is_mod_file:
            sibling_dir = self.dest_file.parent
            for p in self.present_files:
                if p == self.dest_file:
                    continue
                if (
                    p.parent == sibling_dir
                    and p.suffix == ".rs"
                    and p.name not in ("mod.rs", "lib.rs")
                ):
                    modules.add(p.stem)
                if (
                    p.name == "mod.rs"
                    and p.parent.parent == sibling_dir
                    and p.parent != base_dir
                ):
                    modules.add(p.parent.name)

        return modules


class RewriteRule:
    """Base class for source code rewrite rules."""

    def apply(self, text: str, context: TransformContext) -> str:
        """Apply this rewrite rule to the source text.

        Args:
            text: Source code to transform
            context: Transformation context with file paths and crate info

        Returns:
            Transformed source code
        """
        raise NotImplementedError

    def transform(self, text: str, context: TransformContext) -> str:
        """Backwards compatibility alias for apply()."""
        return self.apply(text, context)


class PruneMods(RewriteRule):
    """Comments out mod declarations whose backing files are missing."""

    def apply(self, text: str, context: TransformContext) -> str:
        """Comment out `mod foo;` declarations if backing file is missing."""

        def should_keep_mod(name: str) -> bool:
            # Check both foo.rs and foo/mod.rs
            file_candidate = context.module_base_dir / f"{name}.rs"
            dir_candidate = context.module_base_dir / name / "mod.rs"
            return (
                file_candidate in context.present_files
                or dir_candidate in context.present_files
            )

        def replace(match):
            module_name = match.group(1)
            if should_keep_mod(module_name):
                return match.group(0)
            return f"// pruned missing mod {match.group(0).strip()}"

        return re.sub(PATTERN_MOD_DECL, replace, text, flags=re.MULTILINE)


class PrunePubUses(RewriteRule):
    """Comments out pub use statements whose modules are missing."""

    def apply(self, text: str, context: TransformContext) -> str:
        """Comment out pub use lines whose leading module is not present."""

        def should_keep_pub_use(module: str) -> bool:
            # Always keep fully qualified paths
            if module in ("crate", "super", "self"):
                return True
            # Always keep external crates
            if module in EXTERNAL_CRATES:
                return True
            # Keep if module is available
            return module in context.available_modules

        def replace(match):
            full_line = match.group(0)
            module = match.group(1)
            if should_keep_pub_use(module):
                return full_line
            return f"// pruned missing pub use {full_line.strip()}"

        return re.sub(PATTERN_PUB_USE, replace, text, flags=re.MULTILINE)


class RewriteUses(RewriteRule):
    """Rewrites use statements to work with nested crate modules."""

    def apply(self, text: str, context: TransformContext) -> str:
        """Rewrite use statements to inject crate module names."""
        # Step 1: Rewrite crate:: imports
        text = self._rewrite_crate_imports(text, context)

        # Step 2: Rewrite cross-crate imports
        text = self._rewrite_cross_crate_imports(text, context)

        # Step 3: Rewrite path references in code
        text = self._rewrite_path_references(text, context)

        # Step 4: Fix bare crate:: references
        text = self._fix_bare_crate_refs(text, context)

        return text

    def _rewrite_crate_imports(self, text: str, context: TransformContext) -> str:
        """Rewrite use crate::foo to use crate::<current>::foo."""

        def replace(match):
            prefix = match.group(1)
            path = match.group(2)
            # Skip if already qualified
            if path.startswith(f"{context.current_sanitized}::"):
                return match.group(0)
            return f"{prefix}crate::{context.current_sanitized}::{path}"

        return re.sub(PATTERN_USE_CRATE, replace, text, flags=re.MULTILINE)

    def _rewrite_cross_crate_imports(self, text: str, context: TransformContext) -> str:
        """Rewrite use other_crate::foo to use crate::other_crate::foo."""
        for crate_name in sorted(context.crate_name_map):
            if crate_name == context.current_crate:
                continue

            sanitized = context.crate_name_map[crate_name]
            pattern = rf"(^\s*(?:pub\s+)?use\s+){re.escape(crate_name)}::([^;]+)"

            def replace(match):
                prefix = match.group(1)
                items = match.group(2)

                # Handle macro_export macros - they live at crate root
                if context.macro_export_names:
                    rewritten = self._split_macro_imports(
                        prefix, items, sanitized, context.macro_export_names
                    )
                    if rewritten:
                        return rewritten

                return f"{prefix}crate::{sanitized}::{items}"

            text = re.sub(pattern, replace, text, flags=re.MULTILINE)

        return text

    def _split_macro_imports(
        self, prefix: str, items: str, sanitized: str, macro_names: Set[str]
    ) -> str | None:
        """Split imports to handle macro_export macros at crate root."""
        # Check if any macro names appear in the import
        has_macros = any(macro in items for macro in macro_names)
        if not has_macros:
            return None

        # Handle grouped imports: use foo::{Bar, my_macro, Baz};
        if "{" in items:
            match = re.match(r"(.*)\{([^}]+)\}(.*)", items)
            if not match:
                return None

            path_prefix = match.group(1)
            items_str = match.group(2)
            suffix = match.group(3)

            # Split items into macros vs regular
            all_items = [item.strip() for item in items_str.split(",")]
            macro_items = [
                item for item in all_items if any(m in item for m in macro_names)
            ]
            regular_items = [item for item in all_items if item not in macro_items]

            # Build separate import statements
            result = []
            if regular_items:
                regular = f"{prefix}crate::{sanitized}::{path_prefix}{{{', '.join(regular_items)}}}{suffix}"
                result.append(regular.rstrip(";"))
            if macro_items:
                macro = f"{prefix}crate::{{{', '.join(macro_items)}}}{suffix}"
                result.append(macro.rstrip(";"))

            return ";\n".join(result) + (";" if suffix.strip() == ";" else "")

        # Simple case: use foo::my_macro;
        if any(macro in items for macro in macro_names):
            return f"{prefix}crate::{items}"

        return None

    def _rewrite_path_references(self, text: str, context: TransformContext) -> str:
        """Rewrite bare crate paths in expressions and types."""
        for crate_name, sanitized in context.crate_name_map.items():
            if crate_name == context.current_crate:
                continue

            # Build pattern that excludes macro_export macro invocations
            if context.macro_export_names:
                macro_pattern = "|".join(
                    re.escape(name) for name in context.macro_export_names
                )
                pattern = rf"(?<![A-Za-z0-9_:]){re.escape(crate_name)}::(?!(?:{macro_pattern})!)"
            else:
                pattern = rf"(?<![A-Za-z0-9_:]){re.escape(crate_name)}::"

            text = re.sub(pattern, f"crate::{sanitized}::", text)

        # Rewrite macro invocations: other_crate::my_macro! -> crate::my_macro!
        if context.macro_export_names:
            for macro_name in context.macro_export_names:
                pattern = rf"(?:[A-Za-z0-9_]+::)+({re.escape(macro_name)}!)"
                text = re.sub(pattern, r"crate::\1", text)

        return text

    def _fix_bare_crate_refs(self, text: str, context: TransformContext) -> str:
        """Fix bare crate:: references (not in use statements)."""
        # Pattern to match known module names
        known_modules = "|".join(re.escape(s) for s in context.crate_name_map.values())

        lines = []
        for line in text.split("\n"):
            # Skip use statements
            if re.match(r"^\s*(?:pub\s+)?use\s+", line):
                lines.append(line)
                continue

            # Temporarily protect macro invocations
            macro_pattern = rf"(crate::(?!(?:{known_modules})::)[A-Za-z0-9_:]+!)"
            macros = re.findall(macro_pattern, line)
            placeholders = {}
            for i, macro in enumerate(macros):
                placeholder = f"__MACRO_{i}__"
                placeholders[placeholder] = macro
                line = line.replace(macro, placeholder, 1)

            # Rewrite bare crate:: to crate::<current>::
            pattern = rf"(?<!\$)crate::(?!(?:{known_modules})::)"
            line = re.sub(pattern, f"crate::{context.current_sanitized}::", line)

            # Restore macros
            for placeholder, macro in placeholders.items():
                line = line.replace(placeholder, macro)

            lines.append(line)

        return "\n".join(lines)


class RewriteMacroRefs(RewriteRule):
    """Rewrites $crate:: references in macro definitions."""

    def apply(self, text: str, context: TransformContext) -> str:
        """Replace $crate:: with crate::<current_module>::."""
        return re.sub(
            PATTERN_DOLLAR_CRATE, f"crate::{context.current_sanitized}::", text
        )


class FixSelfPubUses(RewriteRule):
    """Fixes self-referential pub use statements.

    Transforms: pub use crate::my_module::Item; -> pub use Item;
    when current module is my_module.
    """

    def apply(self, text: str, context: TransformContext) -> str:
        """Simplify pub use statements that reference the current module."""
        pattern = rf"(^\s*pub\s+use\s+)crate::{re.escape(context.current_sanitized)}::([^;]+);(\s*)$"

        def replace(match):
            prefix = match.group(1)
            relative_path = match.group(2)
            suffix = match.group(3)
            return f"{prefix}{relative_path};{suffix}"

        return re.sub(pattern, replace, text, flags=re.MULTILINE)


class FixBareImports(RewriteRule):
    """Fixes bare module names in pub use statements by adding super::.

    For non-mod files, transforms: pub use sibling::Item; -> pub use super::sibling::Item;
    """

    def apply(self, text: str, context: TransformContext) -> str:
        """Add super:: prefix to bare sibling module imports."""
        # Skip for mod.rs and lib.rs - they import children, not siblings
        if context.is_mod_file:
            return text

        # Find sibling modules (files in same directory)
        siblings = set()
        base_dir = context.dest_file.parent
        for p in context.present_files:
            if p == context.dest_file:
                continue
            if (
                p.parent == base_dir
                and p.suffix == ".rs"
                and p.name not in ("mod.rs", "lib.rs")
            ):
                siblings.add(p.stem)
            if p.name == "mod.rs" and p.parent.parent == base_dir:
                siblings.add(p.parent.name)

        lines = []
        for line in text.split("\n"):
            # Skip comments
            if line.strip().startswith("//"):
                lines.append(line)
                continue

            # Match pub use module_name::something;
            match = re.match(
                r"^(\s*pub\s+use\s+)([A-Za-z0-9_]+)(::(?:[^;]+);)(\s*)$", line
            )
            if match and match.group(2) in siblings:
                prefix = match.group(1)
                module = match.group(2)
                rest = match.group(3)
                suffix = match.group(4)
                line = f"{prefix}super::{module}{rest}{suffix}"

            lines.append(line)

        return "\n".join(lines)


class PruneTypeAliases(RewriteRule):
    """Comments out type aliases that reference pruned or missing modules.

    For example, if `groups::data` was pruned, this will comment out:
    pub type DataConfig = groups::data::ConfigValues;
    """

    def apply(self, text: str, context: TransformContext) -> str:
        """Comment out type aliases that reference missing modules."""
        lines = []
        for line in text.split("\n"):
            # Match type alias patterns: pub type Foo = module::path::Type;
            # Look for patterns like: groups::data::ConfigValues
            type_match = re.match(
                r"^\s*pub\s+type\s+\w+\s*=\s*([A-Za-z0-9_]+)::([A-Za-z0-9_]+)::", line
            )
            if type_match:
                first_module = type_match.group(1)
                second_module = type_match.group(2)

                # Build the expected path for this module
                # For groups::data, we expect groups/data/mod.rs or groups/data.rs
                module_dir = context.module_base_dir / first_module

                # Check both possible locations
                mod_rs_path = module_dir / second_module / "mod.rs"
                direct_rs_path = module_dir / f"{second_module}.rs"

                # If neither path exists in present_files, comment out the type alias
                if (
                    mod_rs_path not in context.present_files
                    and direct_rs_path not in context.present_files
                ):
                    lines.append(
                        f"// pruned type alias referencing missing module: {line.strip()}"
                    )
                    continue

            lines.append(line)

        return "\n".join(lines)


# Default rewrite rules applied in order
DEFAULT_RULES = [
    RewriteUses(),
    RewriteMacroRefs(),
    FixSelfPubUses(),
    FixBareImports(),
    PruneMods(),
    PrunePubUses(),
    PruneTypeAliases(),
]


def apply_rewrites(
    text: str, context: TransformContext, rules: list[RewriteRule] | None = None
) -> str:
    """Apply rewrite rules to source code in order.

    Args:
        text: Source code to transform
        context: Transformation context with file paths and crate info
        rules: List of rewrite rules to apply (uses DEFAULT_RULES if None)

    Returns:
        Transformed source code
    """
    rules_to_apply = rules if rules is not None else DEFAULT_RULES
    for rule in rules_to_apply:
        text = rule.apply(text, context)
    return text
