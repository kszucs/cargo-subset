"""Tests for AST dependency extraction."""

from pathlib import Path
from textwrap import dedent

import pytest

from cargo_subset.ast import extract_dependencies, extract_macro_exports


class TestExtractDependencies:
    """Tests for extract_dependencies function."""

    def test_simple_mod_declaration(self, tmp_path: Path):
        """Test extracting simple mod declaration."""
        test_file = tmp_path / "test.rs"
        test_file.write_text("mod foo;")

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate"})
        assert ("my_crate", ("foo",)) in deps

    def test_multiple_mod_declarations(self, tmp_path: Path):
        """Test extracting multiple mod declarations."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(dedent("""
            mod foo;
            pub mod bar;
            mod baz;
        """))

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate"})
        assert ("my_crate", ("foo",)) in deps
        assert ("my_crate", ("bar",)) in deps
        assert ("my_crate", ("baz",)) in deps

    def test_inline_mod_ignored(self, tmp_path: Path):
        """Test that inline mod with body is ignored."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(dedent("""
            mod foo;
            mod bar { fn test() {} }
        """))

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate"})
        # Only foo should be included, not bar (has body)
        assert ("my_crate", ("foo",)) in deps
        bar_deps = [d for d in deps if d == ("my_crate", ("bar",))]
        assert len(bar_deps) == 0

    def test_simple_use_statement(self, tmp_path: Path):
        """Test extracting simple use statement."""
        test_file = tmp_path / "test.rs"
        test_file.write_text("use foo::bar;")

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate"})
        # In Rust 2018, bare path 'foo' is resolved as local module
        assert ("my_crate", ("foo", "bar")) in deps

    def test_grouped_use_statements(self, tmp_path: Path):
        """Test extracting grouped use statements."""
        test_file = tmp_path / "test.rs"
        test_file.write_text("use foo::{bar, baz};")

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate"})
        assert ("my_crate", ("foo", "bar")) in deps
        assert ("my_crate", ("foo", "baz")) in deps

    def test_wildcard_use(self, tmp_path: Path):
        """Test extracting wildcard use statement."""
        test_file = tmp_path / "test.rs"
        test_file.write_text("use foo::bar::*;")

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate"})
        assert ("my_crate", ("foo", "bar")) in deps

    def test_crate_relative_use(self, tmp_path: Path):
        """Test extracting crate-relative use."""
        test_file = tmp_path / "test.rs"
        test_file.write_text("use crate::foo::bar;")

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate"})
        assert ("my_crate", ("foo", "bar")) in deps

    def test_self_and_super_use(self, tmp_path: Path):
        """Test extracting self and super use statements."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(dedent("""
            use self::foo;
            use super::bar;
        """))

        # Test from a nested module context
        deps = extract_dependencies(("my_crate", "submod"), test_file, {"my_crate"})
        # self::foo from my_crate::submod -> my_crate::submod::foo
        assert ("my_crate", ("submod", "foo")) in deps
        # super::bar from my_crate::submod -> my_crate::bar
        assert ("my_crate", ("bar",)) in deps

    def test_aliased_use(self, tmp_path: Path):
        """Test extracting aliased use statement."""
        test_file = tmp_path / "test.rs"
        test_file.write_text("use foo::bar as baz;")

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate"})
        # Should extract original path, not the alias
        assert ("my_crate", ("foo", "bar")) in deps

    def test_nested_grouped_use(self, tmp_path: Path):
        """Test extracting nested grouped use statements."""
        test_file = tmp_path / "test.rs"
        test_file.write_text("use foo::{bar::{a, b}, baz};")

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate"})
        assert ("my_crate", ("foo", "bar", "a")) in deps
        assert ("my_crate", ("foo", "bar", "b")) in deps
        assert ("my_crate", ("foo", "baz")) in deps

    def test_mixed_declarations(self, tmp_path: Path):
        """Test extracting mixed mod and use declarations."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(dedent("""
            mod internal;
            pub mod public;
            use crate::foo::Bar;
            use external::Baz;
        """))

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate", "external"})
        assert ("my_crate", ("internal",)) in deps
        assert ("my_crate", ("public",)) in deps
        assert ("my_crate", ("foo", "Bar")) in deps
        # external is a workspace crate
        assert ("external", ("Baz",)) in deps


class TestWorkspaceFixtures:
    """Tests using actual workspace fixture files."""

    def test_core_lib_dependencies(self):
        """Test extracting dependencies from core/src/lib.rs."""
        fixture_path = Path("tests/fixtures/workspace/core/src/lib.rs")
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")

        workspace_crates = {"core", "utils", "client"}
        deps = extract_dependencies(("core",), fixture_path, workspace_crates)

        # Check mod declarations
        assert ("core", ("config",)) in deps
        assert ("core", ("types",)) in deps
        assert ("core", ("storage",)) in deps
        assert ("core", ("storage_client",)) in deps
        assert ("core", ("internal",)) in deps
        assert ("core", ("unused",)) in deps

        # Check normalized use declarations
        assert ("core", ("config", "Config")) in deps
        # utils is a workspace crate
        assert any("utils" in str(d) for d in deps)

    def test_utils_lib_dependencies(self):
        """Test extracting dependencies from utils/src/lib.rs."""
        fixture_path = Path("tests/fixtures/workspace/utils/src/lib.rs")
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")

        workspace_crates = {"utils"}
        deps = extract_dependencies(("utils",), fixture_path, workspace_crates)

        # Check mod declarations
        assert ("utils", ("helpers",)) in deps
        assert ("utils", ("constants",)) in deps

    def test_client_lib_dependencies(self):
        """Test extracting dependencies from client/src/lib.rs."""
        fixture_path = Path("tests/fixtures/workspace/client/src/lib.rs")
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")

        workspace_crates = {"client", "core", "utils"}
        deps = extract_dependencies(("client",), fixture_path, workspace_crates)

        # Check mod declarations
        assert ("client", ("http_client",)) in deps
        assert ("client", ("interface",)) in deps

        # Check use declarations (workspace crate imports are normalized)
        assert ("core", ("types", "Item")) in deps
        assert ("core", ("Config",)) in deps
        assert ("utils", ("helpers",)) in deps

    def test_storage_mod_dependencies(self):
        """Test extracting dependencies from core/src/storage/mod.rs."""
        fixture_path = Path("tests/fixtures/workspace/core/src/storage/mod.rs")
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")

        workspace_crates = {"core"}
        deps = extract_dependencies(("core", "storage"), fixture_path, workspace_crates)

        # Storage module likely has submodule declarations
        # Just verify we can extract dependencies without errors
        assert isinstance(deps, list)
        assert all(isinstance(d, tuple) and len(d) == 2 for d in deps)


class TestExtractMacroExports:
    """Tests for extract_macro_exports function."""

    def test_macro_with_export_attribute(self, tmp_path: Path):
        """Test detecting macro with #[macro_export]."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(dedent("""
            #[macro_export]
            macro_rules! my_macro {
                ($x:expr) => { println!("{}", $x) };
            }
        """))

        macros = extract_macro_exports(test_file)
        assert "my_macro" in macros

    def test_macro_without_export_attribute(self, tmp_path: Path):
        """Test that macro without #[macro_export] is not detected."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(dedent("""
            macro_rules! local_macro {
                ($x:expr) => { println!("{}", $x) };
            }
        """))

        macros = extract_macro_exports(test_file)
        assert len(macros) == 0

    def test_multiple_macros(self, tmp_path: Path):
        """Test detecting multiple exported macros."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(dedent("""
            #[macro_export]
            macro_rules! macro_one {
                () => { };
            }

            macro_rules! local_macro {
                () => { };
            }

            #[macro_export]
            macro_rules! macro_two {
                () => { };
            }
        """))

        macros = extract_macro_exports(test_file)
        assert "macro_one" in macros
        assert "macro_two" in macros
        assert "local_macro" not in macros
        assert len(macros) == 2

    def test_utils_lib_macro(self):
        """Test detecting macro from utils/lib.rs fixture."""
        fixture_path = Path("tests/fixtures/workspace/utils/src/lib.rs")
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")

        macros = extract_macro_exports(fixture_path)
        assert "log_info" in macros

    def test_core_lib_macro(self):
        """Test detecting macro from core/lib.rs fixture."""
        fixture_path = Path("tests/fixtures/workspace/core/src/lib.rs")
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")

        macros = extract_macro_exports(fixture_path)
        assert "debug_log" in macros


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_file(self, tmp_path: Path):
        """Test extracting from empty file."""
        test_file = tmp_path / "test.rs"
        test_file.write_text("")

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate"})
        assert deps == []

    def test_file_with_only_comments(self, tmp_path: Path):
        """Test extracting from file with only comments."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(dedent("""
            // This is a comment
            /* This is a block comment */
        """))

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate"})
        assert deps == []

    def test_file_with_attributes(self, tmp_path: Path):
        """Test extracting with attributes on declarations."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(dedent("""
            #[cfg(test)]
            mod tests;

            #[path = "custom.rs"]
            mod custom;
        """))

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate"})
        assert ("my_crate", ("tests",)) in deps
        assert ("my_crate", ("custom",)) in deps

    def test_pub_use_statements(self, tmp_path: Path):
        """Test extracting pub use statements."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(dedent("""
            pub use foo::bar;
            pub(crate) use baz::qux;
        """))

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate"})
        assert ("my_crate", ("foo", "bar")) in deps
        assert ("my_crate", ("baz", "qux")) in deps

    def test_complex_nested_structure(self, tmp_path: Path):
        """Test extracting from complex nested structure."""
        test_file = tmp_path / "test.rs"
        test_file.write_text(dedent("""
            pub mod outer {
                mod inner;
                use super::foo;
            }
            use crate::bar::{baz::{a, b}, c};
        """))

        deps = extract_dependencies(("my_crate",), test_file, {"my_crate"})
        # Should find inner mod and all use statements
        assert ("my_crate", ("inner",)) in deps
        # super::foo from root context would try to go up from root
        # crate::bar::... paths
        assert ("my_crate", ("bar", "baz", "a")) in deps
        assert ("my_crate", ("bar", "baz", "b")) in deps
        assert ("my_crate", ("bar", "c")) in deps
