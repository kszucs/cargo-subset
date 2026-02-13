"""
Tests for dependency management and Cargo.toml generation.
"""

from pathlib import Path
from textwrap import dedent

import pytest

from toolz import groupby

from cargo_subset.metadata import (
    Dependency,
    DependencyMergeError,
    Crate,
    VersionRequirement,
    Workspace,
)


class TestCargoDeps:
    """Tests for Crate external dependency collection."""

    def test_collect_from_fixture_workspace(self, fixture_workspace):
        """Test collecting external dependencies from fixture workspace."""
        workspace = Workspace.from_cargo(fixture_workspace)

       # Collect from all crates
        crate_names = {"core", "utils", "client"}
        merged_pkg = None
        for crate in crate_names:
            pkg = workspace.crate(crate)
            if merged_pkg is None:
                merged_pkg = pkg
            else:
                merged_pkg = merged_pkg.merge(pkg)

        # Filter external dependencies
        external_deps = [
            dep for dep in merged_pkg.dependencies
            if not dep.optional
            and dep.name not in crate_names
            and not workspace.is_workspace_member(dep.name)
        ]

        deps_by_kind = groupby(lambda d: d.kind or "normal", external_deps)
        normal = {d.name: d for d in deps_by_kind.get("normal", [])}
        build = {d.name: d for d in deps_by_kind.get("build", [])}
        dev = {d.name: d for d in deps_by_kind.get("dev", [])}
        assert isinstance(normal, dict)
        assert isinstance(build, dict)
        assert isinstance(dev, dict)

    def test_collect_empty_crate_list(self, fixture_workspace):
        """Test collecting with empty crate list."""
        workspace = Workspace.from_cargo(fixture_workspace)
        external_deps = []  # Empty crate list means no dependencies

        deps_by_kind = groupby(lambda d: d.kind or "normal", external_deps)
        normal = {d.name: d for d in deps_by_kind.get("normal", [])}
        build = {d.name: d for d in deps_by_kind.get("build", [])}
        dev = {d.name: d for d in deps_by_kind.get("dev", [])}
        assert normal == {}
        assert build == {}
        assert dev == {}

    def test_collect_excludes_workspace_members(self, fixture_workspace):
        """Test that workspace members are excluded from dependencies."""
        workspace = Workspace.from_cargo(fixture_workspace)

        crate_names = {"client"}
        merged_pkg = None
        for crate in crate_names:
            pkg = workspace.crate(crate)
            if merged_pkg is None:
                merged_pkg = pkg
            else:
                merged_pkg = merged_pkg.merge(pkg)

        # Filter external dependencies
        external_deps = [
            dep for dep in merged_pkg.dependencies
            if not dep.optional
            and dep.name not in crate_names
            and not workspace.is_workspace_member(dep.name)
        ]

        # Workspace crates should not appear in dependencies
        deps_by_kind = groupby(lambda d: d.kind or "normal", external_deps)
        normal = {d.name: d for d in deps_by_kind.get("normal", [])}
        build = {d.name: d for d in deps_by_kind.get("build", [])}
        dev = {d.name: d for d in deps_by_kind.get("dev", [])}
        all_deps = set(normal.keys()) | set(build.keys()) | set(dev.keys())

        for member in workspace.crates.keys():
            assert member not in all_deps


class TestDependencyMerge:
    """Tests for Dependency.merge() method."""

    def test_merge_same_version(self):
        """Test merging dependencies with same version."""
        dep1 = Dependency(
            name="serde",
            version=VersionRequirement.parse("^1.0.0"),
            kind="normal",
            optional=False,
            uses_default_features=True,
            features=[],
            target=None,
        )
        dep2 = Dependency(
            name="serde",
            version=VersionRequirement.parse("^1.0.0"),
            kind="normal",
            optional=False,
            uses_default_features=True,
            features=[],
            target=None,
        )

        result = dep1.merge(dep2)
        assert result.name == "serde"
        assert result.version.format() == "^1"

    def test_merge_combines_features(self):
        """Test that merging combines features."""
        dep1 = Dependency(
            name="serde",
            version=VersionRequirement.parse("^1.0.0"),
            kind="normal",
            optional=False,
            uses_default_features=True,
            features=["derive"],
            target=None,
        )
        dep2 = Dependency(
            name="serde",
            version=VersionRequirement.parse("^1.0.0"),
            kind="normal",
            optional=False,
            uses_default_features=True,
            features=["serde_json"],
            target=None,
        )

        result = dep1.merge(dep2)
        assert set(result.features) == {"derive", "serde_json"}

    def test_merge_higher_version(self):
        """Test merging takes higher compatible version."""
        dep1 = Dependency(
            name="tokio",
            version=VersionRequirement.parse("^1.0.0"),
            kind="normal",
            optional=False,
            uses_default_features=True,
            features=[],
            target=None,
        )
        dep2 = Dependency(
            name="tokio",
            version=VersionRequirement.parse("^1.5.0"),
            kind="normal",
            optional=False,
            uses_default_features=True,
            features=[],
            target=None,
        )

        result = dep1.merge(dep2)
        # Should merge to higher compatible version
        assert result.name == "tokio"
        assert "1." in result.version.format()


class TestDependencyRender:
    """Tests for Dependency.render() method."""

    def test_render_simple_dependency(self):
        """Test rendering simple dependency."""
        dep = Dependency(
            name="serde",
            version=VersionRequirement.parse("^1.0.0"),
            kind="normal",
            optional=False,
            uses_default_features=True,
            features=[],
            target=None,
        )

        result = dep.render()
        # Simple dependencies are rendered as just version strings
        assert result == '"1.0"'

    def test_render_with_features(self):
        """Test rendering dependency with features."""
        dep = Dependency(
            name="serde",
            version=VersionRequirement.parse("^1.0.0"),
            kind="normal",
            optional=False,
            uses_default_features=True,
            features=["derive", "alloc"],
            target=None,
        )

        result = dep.render()
        assert "features = [" in result
        assert '"derive"' in result
        assert '"alloc"' in result

    def test_render_with_optional(self):
        """Test rendering optional dependency."""
        dep = Dependency(
            name="foo",
            version=VersionRequirement.parse("^1.0.0"),
            kind="normal",
            optional=True,
            uses_default_features=True,
            features=[],
            target=None,
        )

        result = dep.render()
        assert "optional = true" in result

    def test_render_with_no_default_features(self):
        """Test rendering dependency without default features."""
        dep = Dependency(
            name="bar",
            version=VersionRequirement.parse("^1.0.0"),
            kind="normal",
            optional=False,
            uses_default_features=False,
            features=[],
            target=None,
        )

        result = dep.render()
        assert "default-features = false" in result


class TestCargoTomlRendering:
    """Tests for Crate.render() method."""

    def test_render_minimal_toml(self):
        """Test rendering minimal Cargo.toml."""
        pkg = Crate(
            id="my_crate#0.1.0",
            name="my_crate",
            manifest_path=Path("my_crate/Cargo.toml"),
            targets=[],
            dependencies=[],
            edition="2021",
        )
        result = pkg.render()

        assert "[package]" in result
        assert 'name = "my_crate"' in result
        assert 'version = "0.1.0"' in result
        assert 'edition = "2021"' in result

    def test_render_with_dependencies(self):
        """Test rendering with dependencies."""
        dep = Dependency(
            name="serde",
            version=VersionRequirement.parse("^1.0.0"),
            kind=None,
            optional=False,
            uses_default_features=True,
            features=[],
            target=None,
        )

        pkg = Crate(
            id="my_crate#0.1.0",
            name="my_crate",
            manifest_path=Path("my_crate/Cargo.toml"),
            targets=[],
            dependencies=[dep],
            edition="2021",
        )
        result = pkg.render()

        assert "[dependencies]" in result
        assert "serde" in result

    def test_render_sorted_dependencies(self):
        """Test that dependencies are sorted alphabetically."""
        deps = [
            Dependency("zebra", VersionRequirement.parse("^1.0.0"), None, False, True, [], None),
            Dependency("alpha", VersionRequirement.parse("^1.0.0"), None, False, True, [], None),
            Dependency("beta", VersionRequirement.parse("^1.0.0"), None, False, True, [], None),
        ]

        pkg = Crate(
            id="my_crate#0.1.0",
            name="my_crate",
            manifest_path=Path("my_crate/Cargo.toml"),
            targets=[],
            dependencies=deps,
            edition="2021",
        )
        result = pkg.render()

        # Find positions
        alpha_pos = result.find("alpha")
        beta_pos = result.find("beta")
        zebra_pos = result.find("zebra")

        assert alpha_pos < beta_pos < zebra_pos

    def test_render_build_dependencies(self):
        """Test rendering with build dependencies."""
        build_dep = Dependency(
            name="cc",
            version=VersionRequirement.parse("^1.0.0"),
            kind="build",
            optional=False,
            uses_default_features=True,
            features=[],
            target=None,
        )

        pkg = Crate(
            id="my_crate#0.1.0",
            name="my_crate",
            manifest_path=Path("my_crate/Cargo.toml"),
            targets=[],
            dependencies=[build_dep],
            edition="2021",
        )
        result = pkg.render()

        assert "[build-dependencies]" in result
        assert "cc" in result

    def test_render_dev_dependencies(self):
        """Test rendering with dev dependencies."""
        dev_dep = Dependency(
            name="proptest",
            version=VersionRequirement.parse("^1.0.0"),
            kind="dev",
            optional=False,
            uses_default_features=True,
            features=[],
            target=None,
        )

        pkg = Crate(
            id="my_crate#0.1.0",
            name="my_crate",
            manifest_path=Path("my_crate/Cargo.toml"),
            targets=[],
            dependencies=[dev_dep],
            edition="2021",
        )
        result = pkg.render()

        assert "[dev-dependencies]" in result
        assert "proptest" in result


class TestDependencyMergeError:
    """Tests for DependencyMergeError exception."""

    def test_exception_creation(self):
        """Test creating exception."""
        error = DependencyMergeError("test message")
        assert str(error) == "test message"


class TestIntegrationScenarios:
    """Integration tests for complete dependency workflows."""

    def test_full_dependency_workflow(self, fixture_workspace):
        """Test complete workflow from collection to rendering."""
        workspace = Workspace.from_cargo(fixture_workspace)

        # Step 1: Collect external dependencies
        crate_names = {"core"}
        merged_pkg = workspace.crate("core")

        # Filter external dependencies
        external_deps = [
            dep for dep in merged_pkg.dependencies
            if not dep.optional
            and dep.name not in crate_names
            and not workspace.is_workspace_member(dep.name)
        ]

        # Create synthetic package
        pkg = Crate(
            id="extracted_subset#0.1.0",
            name="extracted_subset",
            manifest_path=Path("extracted_subset") / "Cargo.toml",
            targets=[],
            dependencies=external_deps,
            edition="2021",
        )

        # Step 2: Render to Cargo.toml
        toml_content = pkg.render()

        # Verify structure
        assert "[package]" in toml_content
        assert 'name = "extracted_subset"' in toml_content
        assert 'edition = "2021"' in toml_content


@pytest.fixture
def fixture_workspace():
    """Fixture providing the test workspace path."""
    return Path(__file__).parent / "fixtures" / "workspace"


class TestFeaturesAndDoctest:
    """Tests for features and doctest preservation in generated Cargo.toml."""

    def test_render_with_features(self):
        """Test that features are included in rendered Cargo.toml."""
        pkg = Crate(
            id="my_crate#0.1.0",
            name="my_crate",
            manifest_path=Path("my_crate/Cargo.toml"),
            targets=[],
            dependencies=[],
            edition="2021",
            features={
                "default": ["feature1"],
                "feature1": [],
                "feature2": ["dep:optional_dep"],
            },
        )
        result = pkg.render()

        assert "[features]" in result
        assert 'default = ["feature1"]' in result
        assert "feature1 = []" in result
        assert 'feature2 = ["dep:optional_dep"]' in result

    def test_render_with_doctest_false(self):
        """Test that doctest = false is included when lib target has doctest=false."""
        from cargo_subset.metadata import Target

        lib_target = Target(
            name="my_crate",
            kind=["lib"],
            src_path=Path("src/lib.rs"),
            doctest=False,
        )

        pkg = Crate(
            id="my_crate#0.1.0",
            name="my_crate",
            manifest_path=Path("my_crate/Cargo.toml"),
            targets=[lib_target],
            dependencies=[],
            edition="2021",
        )
        result = pkg.render()

        assert "[lib]" in result
        assert "doctest = false" in result

    def test_render_with_doctest_true(self):
        """Test that [lib] section is omitted when doctest=true (default)."""
        from cargo_subset.metadata import Target

        lib_target = Target(
            name="my_crate",
            kind=["lib"],
            src_path=Path("src/lib.rs"),
            doctest=True,
        )

        pkg = Crate(
            id="my_crate#0.1.0",
            name="my_crate",
            manifest_path=Path("my_crate/Cargo.toml"),
            targets=[lib_target],
            dependencies=[],
            edition="2021",
        )
        result = pkg.render()

        # [lib] section should not be present when doctest is true (default)
        assert "[lib]" not in result

    def test_merge_features(self):
        """Test that merging crates combines features."""
        crate1 = Crate(
            id="crate1#0.1.0",
            name="crate1",
            manifest_path=Path("crate1/Cargo.toml"),
            targets=[],
            dependencies=[],
            edition="2021",
            features={
                "default": ["feature1"],
                "feature1": [],
            },
        )

        crate2 = Crate(
            id="crate2#0.1.0",
            name="crate2",
            manifest_path=Path("crate2/Cargo.toml"),
            targets=[],
            dependencies=[],
            edition="2021",
            features={
                "default": ["feature2"],
                "feature2": [],
                "feature3": ["dep:something"],
            },
        )

        merged = crate1.merge(crate2)

        assert merged.features is not None
        assert "feature1" in merged.features
        assert "feature2" in merged.features
        assert "feature3" in merged.features
        # default should combine both feature1 and feature2
        assert "feature1" in merged.features["default"]
        assert "feature2" in merged.features["default"]

    def test_render_full_cargo_toml_with_features_and_doctest(self):
        """Test rendering a complete Cargo.toml with features and doctest."""
        from cargo_subset.metadata import Target

        lib_target = Target(
            name="complete_crate",
            kind=["lib"],
            src_path=Path("src/lib.rs"),
            doctest=False,
        )

        dep = Dependency(
            name="serde",
            version=VersionRequirement.parse("^1.0.0"),
            kind=None,
            optional=False,
            uses_default_features=True,
            features=["derive"],
            target=None,
        )

        pkg = Crate(
            id="complete_crate#0.1.0",
            name="complete_crate",
            manifest_path=Path("complete_crate/Cargo.toml"),
            targets=[lib_target],
            dependencies=[dep],
            edition="2021",
            features={
                "default": [],
                "strict": [],
                "extra": ["dep:optional_crate"],
            },
        )

        result = pkg.render()

        # Check all sections are present
        assert "[package]" in result
        assert 'name = "complete_crate"' in result
        assert 'edition = "2021"' in result

        assert "[lib]" in result
        assert "doctest = false" in result

        assert "[dependencies]" in result
        assert "serde" in result

        assert "[features]" in result
        assert "default = []" in result
        assert "strict = []" in result
        assert 'extra = ["dep:optional_crate"]' in result

