"""
Tests for source code transforms.

This module tests the new transform system that initializes once with global
context and applies transforms per-module.
"""

import re
import textwrap
from pathlib import Path
from unittest.mock import Mock


from cargo_subset.modules import Module
from cargo_subset.transforms import Transform


def sanitize_crate_name(name: str) -> str:
    """Sanitize a crate name for use as a module identifier."""
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def make_modules_dict(
    crates: list[str] = None,
    present_files: list[Path] = None,
    current_crate: str = "",
    current_file: Path = None,
) -> tuple[dict, Module]:
    """Create a modules dict for testing.

    Returns:
        (modules_dict, current_module)
    """
    modules_dict = {}

    # Add crates to modules dict
    if crates:
        for crate_name in crates:
            mock_mod = Mock(spec=Module)
            mock_mod.file = Path()
            mock_mod.crate = crate_name
            mock_mod.id = (crate_name,)
            modules_dict[(crate_name,)] = mock_mod

    # Add present files as modules
    if present_files:
        for i, f in enumerate(present_files):
            mock_mod = Mock(spec=Module)
            mock_mod.file = f
            mock_mod.crate = current_crate
            mock_mod.id = (current_crate, str(i))
            modules_dict[(current_crate, str(i))] = mock_mod

    # Create current module
    current_module = Mock(spec=Module)
    current_module.file = current_file or Path()
    current_module.crate = current_crate
    current_module.id = (current_crate,) if current_crate else ()

    return modules_dict, current_module


class TestTransformBase:
    """Tests for Transform base class."""

    def test_initializes_with_modules_dict(self):
        """Test that Transform can be initialized with modules dict."""
        modules_dict, _ = make_modules_dict(crates=["core", "api"])

        class DummyTransform(Transform):
            def apply(self, module, text):
                return text

        transform = DummyTransform(modules_dict)

        assert transform.modules == modules_dict
        assert transform.crate_names == {"core", "api"}

    def test_precomputes_present_files(self):
        """Test that present_files are pre-computed from modules."""
        file1 = Path("/test/core/lib.rs")
        file2 = Path("/test/api/mod.rs")

        modules_dict, _ = make_modules_dict(present_files=[file1, file2])

        class DummyTransform(Transform):
            def apply(self, module, text):
                return text

        transform = DummyTransform(modules_dict)

        assert file1 in transform.present_files
        assert file2 in transform.present_files

    def test_helper_is_mod_file(self):
        """Test _is_mod_file helper method."""
        modules_dict, _ = make_modules_dict()

        class DummyTransform(Transform):
            def apply(self, module, text):
                return text

        transform = DummyTransform(modules_dict)

        # Test mod.rs
        mod_module = Mock(spec=Module)
        mod_module.file = Path("/test/mod.rs")
        assert transform._is_mod_file(mod_module)

        # Test lib.rs
        lib_module = Mock(spec=Module)
        lib_module.file = Path("/test/lib.rs")
        assert transform._is_mod_file(lib_module)

        # Test regular file
        regular_module = Mock(spec=Module)
        regular_module.file = Path("/test/utils.rs")
        assert not transform._is_mod_file(regular_module)

    def test_helper_get_module_base_dir(self):
        """Test _get_module_base_dir helper method."""
        modules_dict, _ = make_modules_dict()

        class DummyTransform(Transform):
            def apply(self, module, text):
                return text

        transform = DummyTransform(modules_dict)

        # Test mod.rs - children are siblings
        mod_module = Mock(spec=Module)
        mod_module.file = Path("/test/foo/mod.rs")
        assert transform._get_module_base_dir(mod_module) == Path("/test/foo")

        # Test regular file - children are in subdirectory
        regular_module = Mock(spec=Module)
        regular_module.file = Path("/test/utils.rs")
        assert transform._get_module_base_dir(regular_module) == Path("/test/utils")


# Placeholder test classes for each transform
# These will be populated as we port each transform


class TestRewriteMacroRefs:
    """Tests for RewriteMacroRefs transform."""

    def test_rewrites_dollar_crate_refs(self):
        """Test that $crate:: is replaced with crate::<current>::."""
        from cargo_subset.transforms import RewriteMacroRefs

        text = textwrap.dedent(
            """
            macro_rules! my_macro {
                () => {
                    $crate::utils::foo()
                };
            }
            use $crate::bar::Baz;
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["my_module"], current_crate="my_module"
        )

        transform = RewriteMacroRefs(modules_dict)
        rewritten = transform.apply(current_module, text)

        assert "crate::my_module::utils::foo()" in rewritten
        assert "use crate::my_module::bar::Baz;" in rewritten
        assert "$crate::" not in rewritten

    def test_preserves_already_qualified_paths(self):
        """Test that $crate:: replacement works even with already qualified paths."""
        from cargo_subset.transforms import RewriteMacroRefs

        text = textwrap.dedent(
            """
            #[macro_export]
            macro_rules! config_group {
                () => {
                    for item in $crate::xet_config::ENVIRONMENT_NAME_ALIASES {
                        println!("{:?}", item);
                    }
                    use $crate::xet_config::ParsableConfigValue;
                };
            }
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["xet_config"], current_crate="xet_config"
        )

        transform = RewriteMacroRefs(modules_dict)
        rewritten = transform.apply(current_module, text)

        # $crate:: is replaced with crate::xet_config::
        # This may result in paths like crate::xet_config::xet_config:: if already qualified
        # That's expected - other transforms handle avoiding double-nesting
        assert "$crate::" not in rewritten
        assert "crate::xet_config::" in rewritten


class TestRewriteCrateImports:
    """Tests for RewriteCrateImports transform."""

    def test_rewrites_crate_relative_imports(self):
        """Test that use crate:: is rewritten to use crate::<current>::."""
        from cargo_subset.transforms import RewriteCrateImports

        text = textwrap.dedent(
            """
            use crate::utils::foo;
            use crate::nested::bar;
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["my_crate"], current_crate="my_crate"
        )

        transform = RewriteCrateImports(modules_dict)
        rewritten = transform.apply(current_module, text)

        assert "use crate::my_crate::utils::foo;" in rewritten
        assert "use crate::my_crate::nested::bar;" in rewritten

    def test_handles_pub_use(self):
        """Test that pub use statements are also rewritten."""
        from cargo_subset.transforms import RewriteCrateImports

        text = textwrap.dedent(
            """
            pub use crate::types::Item;
            use crate::utils::helper;
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["core"], current_crate="core"
        )

        transform = RewriteCrateImports(modules_dict)
        rewritten = transform.apply(current_module, text)

        assert "pub use crate::core::types::Item;" in rewritten
        assert "use crate::core::utils::helper;" in rewritten


class TestRewriteCrossCreateImports:
    """Tests for RewriteCrossCreateImports transform."""

    def test_rewrites_cross_crate_imports(self):
        """Test that use other_crate:: is rewritten to use crate::other_crate::."""
        from cargo_subset.transforms import RewriteCrossCreateImports

        text = textwrap.dedent(
            """
            use cas_client::adapter;
            use cas_object::CompressionScheme;
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["my_crate", "cas_client", "cas_object"], current_crate="my_crate"
        )

        transform = RewriteCrossCreateImports(modules_dict)
        rewritten = transform.apply(current_module, text)

        assert "use crate::cas_client::adapter;" in rewritten
        assert "use crate::cas_object::CompressionScheme;" in rewritten

    def test_handles_macro_export_in_simple_import(self):
        """Test that macro_export macros are imported from crate root."""
        from cargo_subset.transforms import RewriteCrossCreateImports

        text = textwrap.dedent(
            """
            use xet_runtime::global_semaphore_handle;
            use xet_runtime::GlobalSemaphoreHandle;
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["data", "xet_runtime"], current_crate="data"
        )

        transform = RewriteCrossCreateImports(
            modules_dict, macro_export_names={"global_semaphore_handle"}
        )
        rewritten = transform.apply(current_module, text)

        # Macro should be at crate root
        assert "use crate::global_semaphore_handle;" in rewritten
        # Regular item should be in module
        assert "use crate::xet_runtime::GlobalSemaphoreHandle;" in rewritten

    def test_handles_pub_use(self):
        """Test that pub use statements are also rewritten."""
        from cargo_subset.transforms import RewriteCrossCreateImports

        text = textwrap.dedent(
            """
            pub use other_crate::Item;
            use another_crate::helper;
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["my_crate", "other_crate", "another_crate"],
            current_crate="my_crate",
        )

        transform = RewriteCrossCreateImports(modules_dict)
        rewritten = transform.apply(current_module, text)

        assert "pub use crate::other_crate::Item;" in rewritten
        assert "use crate::another_crate::helper;" in rewritten


class TestRewritePathReferences:
    """Tests for RewritePathReferences transform."""

    def test_rewrites_type_references_in_code(self):
        """Test that bare crate references in code are rewritten."""
        from cargo_subset.transforms import RewritePathReferences

        text = textwrap.dedent(
            """
            let err: cas_client::CasClientError = todo!();
            let scheme = cas_object::CompressionScheme::default();
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["my_crate", "cas_client", "cas_object"], current_crate="my_crate"
        )

        transform = RewritePathReferences(modules_dict)
        rewritten = transform.apply(current_module, text)

        assert "crate::cas_client::CasClientError" in rewritten
        assert "crate::cas_object::CompressionScheme" in rewritten

    def test_excludes_macro_invocations_from_path_rewrite(self):
        """Test that macro_export macros are excluded from path rewriting."""
        from cargo_subset.transforms import RewritePathReferences

        text = textwrap.dedent(
            """
            let x = other_crate::some_type();
            other_crate::config_group!({ ref FOO: i32 = 1; });
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["my_crate", "other_crate"], current_crate="my_crate"
        )

        transform = RewritePathReferences(
            modules_dict, macro_export_names={"config_group"}
        )
        rewritten = transform.apply(current_module, text)

        # Regular paths should be rewritten with crate prefix
        assert "crate::other_crate::some_type()" in rewritten

        # Macro invocations should be rewritten to crate root (not nested)
        assert "crate::config_group!" in rewritten
        assert "crate::other_crate::config_group!" not in rewritten
        assert "other_crate::config_group!" not in rewritten

    def test_strips_module_prefix_from_macro_invocations(self):
        """Test that module prefixes are stripped from macro_export macro invocations."""
        from cargo_subset.transforms import RewritePathReferences

        text = textwrap.dedent(
            """
            utils::test_configurable_constants! {
                ref FOO: usize = 42;
            }

            crate::utils::test_configurable_constants! {
                ref BAR: usize = 24;
            }
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["my_crate", "utils"], current_crate="my_crate"
        )

        transform = RewritePathReferences(
            modules_dict, macro_export_names={"test_configurable_constants"}
        )
        rewritten = transform.apply(current_module, text)

        # Module prefixes should be rewritten to crate:: for macro invocations
        assert "crate::test_configurable_constants! {" in rewritten
        assert "utils::test_configurable_constants!" not in rewritten
        assert "crate::utils::test_configurable_constants!" not in rewritten


class TestFixBareCrateRefs:
    """Tests for FixBareCrateRefs transform."""

    def test_avoids_double_nesting_already_qualified_paths(self):
        """Test that already qualified paths are not double-nested."""
        from cargo_subset.transforms import FixBareCrateRefs

        text = textwrap.dedent(
            """
            for item in crate::xet_config::ENVIRONMENT_NAME_ALIASES {
                println!("{:?}", item);
            }
            use crate::xet_config::XetConfig;
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["xet_config"], current_crate="xet_config"
        )

        transform = FixBareCrateRefs(modules_dict)
        rewritten = transform.apply(current_module, text)

        # Should preserve paths, NOT double up to crate::xet_config::xet_config::
        assert "crate::xet_config::ENVIRONMENT_NAME_ALIASES" in rewritten
        assert (
            "crate::xet_config::xet_config::ENVIRONMENT_NAME_ALIASES" not in rewritten
        )

    def test_rewrites_bare_crate_refs(self):
        """Test that bare crate:: is rewritten to crate::{current}::."""
        from cargo_subset.transforms import FixBareCrateRefs

        text = textwrap.dedent(
            """
            let x = crate::utils::helper();
            let y = crate::types::MyType::new();
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["my_crate"], current_crate="my_crate"
        )

        transform = FixBareCrateRefs(modules_dict)
        rewritten = transform.apply(current_module, text)

        assert "crate::my_crate::utils::helper()" in rewritten
        assert "crate::my_crate::types::MyType::new()" in rewritten

    def test_skips_use_statements(self):
        """Test that use statements are not modified."""
        from cargo_subset.transforms import FixBareCrateRefs

        text = textwrap.dedent(
            """
            use crate::foo;
            pub use crate::bar;
            let x = crate::baz();
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["my_crate"], current_crate="my_crate"
        )

        transform = FixBareCrateRefs(modules_dict)
        rewritten = transform.apply(current_module, text)

        # Use statements should be unchanged
        assert "use crate::foo;" in rewritten
        assert "pub use crate::bar;" in rewritten
        # But code should be rewritten
        assert "crate::my_crate::baz()" in rewritten


class TestFixSelfPubUses:
    """Tests for FixSelfPubUses transform."""

    def test_simplifies_self_referential_imports(self):
        """Test that self-referential pub uses are simplified."""
        from cargo_subset.transforms import FixSelfPubUses

        text = textwrap.dedent(
            """
            pub use crate::xet_config::XetConfig;
            pub use crate::xet_config::nested::Config;
            pub use crate::other_module::Thing;
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["xet_config", "other_module"], current_crate="xet_config"
        )

        transform = FixSelfPubUses(modules_dict)
        rewritten = transform.apply(current_module, text)

        # Self-referential imports should be rewritten to relative paths
        assert "pub use XetConfig;" in rewritten
        assert "pub use nested::Config;" in rewritten

        # Other module imports should remain unchanged
        assert "pub use crate::other_module::Thing;" in rewritten

    def test_preserves_whitespace_and_formatting(self):
        """Test that whitespace and formatting are preserved."""
        from cargo_subset.transforms import FixSelfPubUses

        text = "pub use crate::my_module::Item;  \n"

        modules_dict, current_module = make_modules_dict(
            crates=["my_module"], current_crate="my_module"
        )

        transform = FixSelfPubUses(modules_dict)
        rewritten = transform.apply(current_module, text)

        assert "pub use Item;  \n" in rewritten


class TestFixBareImports:
    """Tests for FixBareImports transform."""

    def test_adds_super_to_sibling_imports(self):
        """Test that bare sibling imports get super:: prefix."""
        from cargo_subset.transforms import FixBareImports

        text = textwrap.dedent(
            """
            pub use shard_format::*;
            pub use crate::other::Thing;
            use std::collections::HashMap;
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["my_crate"],
            current_crate="my_crate",
            current_file=Path("/test/shard_file.rs"),
        )

        transform = FixBareImports(modules_dict)
        rewritten = transform.apply(current_module, text)

        # Bare sibling import should get super:: prefix
        assert "pub use super::shard_format::*;" in rewritten

        # Already qualified paths should not be modified
        assert "pub use crate::other::Thing;" in rewritten

    def test_preserves_mod_file_imports(self):
        """Test that mod.rs files don't get super:: added."""
        from cargo_subset.transforms import FixBareImports

        text = textwrap.dedent(
            """
            pub use sibling::Item;
            pub use other::Thing;
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["my_crate"],
            current_crate="my_crate",
            current_file=Path("/test/mod.rs"),
        )

        transform = FixBareImports(modules_dict)
        rewritten = transform.apply(current_module, text)

        # mod.rs should not add super::
        assert "pub use sibling::Item;" in rewritten
        assert "pub use other::Thing;" in rewritten
        assert "super::" not in rewritten

    def test_skips_already_qualified_imports(self):
        """Test that already qualified imports are not modified."""
        from cargo_subset.transforms import FixBareImports

        text = textwrap.dedent(
            """
            pub use crate::foo::Bar;
            pub use super::baz::Qux;
            pub use self::local::Item;
            pub use std::collections::HashMap;
            pub use core::fmt::Debug;
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["my_crate"],
            current_crate="my_crate",
            current_file=Path("/test/regular.rs"),
        )

        transform = FixBareImports(modules_dict)
        rewritten = transform.apply(current_module, text)

        # All should remain unchanged
        assert "pub use crate::foo::Bar;" in rewritten
        assert "pub use super::baz::Qux;" in rewritten
        assert "pub use self::local::Item;" in rewritten
        assert "pub use std::collections::HashMap;" in rewritten
        assert "pub use core::fmt::Debug;" in rewritten


class TestPruneMods:
    """Tests for PruneMods transform."""

    def test_prunes_missing_mods_and_keeps_present(self):
        """Test that missing mods are commented out, present ones kept."""
        from cargo_subset.transforms import PruneMods

        text = textwrap.dedent(
            """
            mod present_child;
            pub mod missing_child;
            """
        )

        present_child = Path("/test/mycrate/present_child.rs")
        modules_dict, current_module = make_modules_dict(
            crates=["my_crate"],
            present_files=[present_child],
            current_crate="my_crate",
            current_file=Path("/test/mycrate/mod.rs"),
        )

        transform = PruneMods(modules_dict)
        rewritten = transform.apply(current_module, text)

        assert "mod present_child;" in rewritten
        assert "// pruned missing mod" in rewritten
        assert "pub mod missing_child;" in rewritten

    def test_handles_various_visibility_modifiers(self):
        """Test that various visibility modifiers are handled correctly."""
        from cargo_subset.transforms import PruneMods

        text = textwrap.dedent(
            """
            mod plain;
            pub mod public;
            pub(crate) mod crate_visible;
            pub(in crate::foo) mod scoped;
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["my_crate"],
            present_files=[],
            current_crate="my_crate",
            current_file=Path("/tmp/test/lib.rs"),
        )

        transform = PruneMods(modules_dict)
        result = transform.apply(current_module, text)

        # All should be commented out since none of the files exist
        assert result.count("// pruned missing mod") == 4

    def test_handles_mod_rs_vs_regular_file_resolution(self):
        """Test that modules are resolved differently for mod.rs vs regular files."""
        from cargo_subset.transforms import PruneMods

        text = "mod child;"

        # For mod.rs, child modules are siblings
        child_of_mod = Path("/test/parent/child.rs")
        modules_dict_mod, mod_module = make_modules_dict(
            crates=["my_crate"],
            present_files=[child_of_mod],
            current_crate="my_crate",
            current_file=Path("/test/parent/mod.rs"),
        )

        transform = PruneMods(modules_dict_mod)
        result_mod = transform.apply(mod_module, text)
        assert "mod child;" in result_mod
        assert "pruned" not in result_mod

        # For foo.rs, child modules are in foo/ subdirectory
        child_of_foo = Path("/test/parent/foo/child.rs")
        modules_dict_foo, foo_module = make_modules_dict(
            crates=["my_crate"],
            present_files=[child_of_foo],
            current_crate="my_crate",
            current_file=Path("/test/parent/foo.rs"),
        )

        transform_foo = PruneMods(modules_dict_foo)
        result_foo = transform_foo.apply(foo_module, text)
        assert "mod child;" in result_foo
        assert "pruned" not in result_foo


class TestPrunePubUses:
    """Tests for PrunePubUses transform."""

    def test_preserves_external_crates(self):
        """Test that external crates are preserved."""
        from cargo_subset.transforms import PrunePubUses

        text = textwrap.dedent(
            """
            pub use std::collections::HashMap;
            pub use reqwest_middleware::ClientWithMiddleware;
            pub use missing_module::Thing;
            pub use available_module::Item;
            """
        )

        available = Path("/test/src/available_module.rs")
        modules_dict, current_module = make_modules_dict(
            crates=["my_crate"],
            present_files=[available],
            current_crate="my_crate",
            current_file=Path("/test/src/lib.rs"),
        )

        transform = PrunePubUses(modules_dict)
        rewritten = transform.apply(current_module, text)

        # External crates should be preserved
        assert "pub use std::collections::HashMap;" in rewritten
        assert "pub use reqwest_middleware::ClientWithMiddleware;" in rewritten

        # Available module should be preserved
        assert "pub use available_module::Item;" in rewritten

        # Missing module should be commented out
        assert "// pruned missing pub use" in rewritten

    def test_preserves_fully_qualified_paths(self):
        """Test that fully qualified paths are preserved."""
        from cargo_subset.transforms import PrunePubUses

        text = textwrap.dedent(
            """
            pub use crate::my_module::Thing;
            pub use super::sibling::Item;
            pub use self::local::Foo;
            pub use bare_missing::Bar;
            """
        )

        modules_dict, current_module = make_modules_dict(
            crates=["my_crate"],
            present_files=[],
            current_crate="my_crate",
            current_file=Path("/test/src/lib.rs"),
        )

        transform = PrunePubUses(modules_dict)
        rewritten = transform.apply(current_module, text)

        # Qualified paths should be preserved
        assert "pub use crate::my_module::Thing;" in rewritten
        assert "pub use super::sibling::Item;" in rewritten
        assert "pub use self::local::Foo;" in rewritten

        # Bare missing should be commented out
        assert "// pruned missing pub use pub use bare_missing::Bar;" in rewritten
