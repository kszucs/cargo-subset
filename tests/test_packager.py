"""
Integration tests using a realistic workspace fixture.

These tests validate the entire packaging pipeline using a gold-standard
fixture containing multiple crates with various problematic patterns.
"""

import subprocess


from cargo_subset import metadata, packager
from conftest import compare_directories


class TestEndToEndTransformations:
    """Test end-to-end transformations via build_single_crate."""

    def test_extract_storage_client(self, fixtures_dir, tmp_path):
        """Test extracting storage_client module with proper transformations."""
        workspace = metadata.Workspace.from_cargo(fixtures_dir / "workspace")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Extract storage_client
        extracted = packager.build_single_crate(
            workspace,
            entry_crate="core",
            entry_module="storage_client",
            output_dir=output_dir,
            new_crate_name="extracted_storage_client",
        )

        # Compare against expected output
        expected_dir = fixtures_dir / "extracted_storage_client"
        differences = compare_directories(extracted, expected_dir)

        assert not differences, "Output differs from expected:\n" + "\n".join(
            differences
        )

    def test_extract_client_crate(self, fixtures_dir, tmp_path):
        """Test extracting full client crate with cross-crate transformations."""
        workspace = metadata.Workspace.from_cargo(fixtures_dir / "workspace")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Extract client crate
        extracted = packager.build_single_crate(
            workspace,
            entry_crate="client",
            entry_module="crate",
            output_dir=output_dir,
            new_crate_name="extracted_client",
        )

        # Compare against expected output
        expected_dir = fixtures_dir / "extracted_client"
        differences = compare_directories(extracted, expected_dir)

        assert not differences, "Output differs from expected:\n" + "\n".join(
            differences
        )


class TestEndToEndProperties:
    """Test end-to-end properties of the transformation."""

    def test_all_lazy_static_blocks_have_imports(self, fixture_workspace):
        """Test that all files with lazy_static! either have the import or use configuration_utils."""
        # Find all files with lazy_static!
        rust_files = list(fixture_workspace.rglob("*.rs"))

        for rust_file in rust_files:
            content = rust_file.read_text()
            if "lazy_static!" in content:
                # Check if file has lazy_static import or imports configuration_utils (which re-exports it)
                has_lazy_static_import = "use lazy_static::lazy_static" in content
                has_config_utils_import = (
                    "use crate::utils::configuration_utils" in content
                    or "pub use lazy_static::lazy_static" in content
                )

                # File should have one of these ways to access lazy_static!
                assert has_lazy_static_import or has_config_utils_import, (
                    f"File {rust_file} uses lazy_static! but doesn't import it"
                )

    def test_no_unqualified_crate_refs_after_rewrite(self, fixture_workspace, tmp_path):
        """Test that workspace crate refs are qualified after rewriting."""
        workspace = metadata.Workspace.from_cargo(fixture_workspace)

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Extract client which imports from core and utils
        extracted = packager.build_single_crate(
            workspace,
            entry_crate="client",
            entry_module="crate",
            output_dir=output_dir,
            new_crate_name="extracted_client",
        )

        # Read the extracted client lib.rs
        client_lib = (extracted / "src" / "client" / "lib.rs").read_text()

        # After rewriting, bare workspace crate names in use statements
        # should be prefixed with crate::
        lines = client_lib.split("\n")
        use_lines = [line for line in lines if line.strip().startswith("use ")]

        for line in use_lines:
            # Workspace crate uses should start with crate::
            if "use core::" in line or "use utils::" in line:
                assert "use crate::core::" in line or "use crate::utils::" in line

    def test_fixture_has_all_test_patterns(self, fixture_workspace):
        """Verify fixture contains all the patterns we're testing for."""
        all_content = ""
        for rust_file in fixture_workspace.rglob("*.rs"):
            all_content += rust_file.read_text() + "\n"

        # Check for various patterns
        assert "pub use crate::" in all_content, "Missing self-referential pub use"
        assert "lazy_static!" in all_content, "Missing lazy_static usage"
        assert "pub mod" in all_content, "Missing pub mod declarations"
        assert "#[macro_export]" in all_content, "Missing macro exports"
        assert "use super::" in all_content or "pub use" in all_content, (
            "Missing relative imports"
        )


class TestCargoCompatibility:
    """Test that the fixture workspace is valid Rust code that compiles and tests."""

    def test_cargo_check_succeeds(self, fixture_workspace):
        """Test that `cargo check` passes on the fixture workspace."""
        result = subprocess.run(
            ["cargo", "check", "--workspace"],
            cwd=fixture_workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.returncode == 0, (
            f"cargo check failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_cargo_test_succeeds(self, fixture_workspace):
        """Test that `cargo test` passes on the fixture workspace."""
        result = subprocess.run(
            ["cargo", "test", "--workspace"],
            cwd=fixture_workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        assert result.returncode == 0, (
            f"cargo test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_cargo_check_individual_crates(self, fixture_workspace):
        """Test that each crate can be checked individually."""
        crates = ["core", "utils", "client"]

        for crate_name in crates:
            result = subprocess.run(
                ["cargo", "check", "-p", crate_name],
                cwd=fixture_workspace,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                print(f"STDOUT ({crate_name}):", result.stdout)
                print(f"STDERR ({crate_name}):", result.stderr)

            assert result.returncode == 0, (
                f"cargo check failed for crate {crate_name}:\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )
