"""
Tests for the module dependency resolution.
"""

from pathlib import Path

import pytest

from cargo_subset.modules import Module, modules
from cargo_subset.metadata import Workspace


def test_modules_exact_output_for_core(fixture_workspace):
    """Test exact output of modules() for core crate."""
    workspace = Workspace.from_cargo(fixture_workspace)
    result = modules(workspace, ("core",))

    # Check exact set of module IDs
    expected_ids = {
        ("core",),
        ("core", "config"),
        ("core", "internal"),
        ("core", "storage"),
        ("core", "storage", "error"),
        ("core", "storage", "format"),
        ("core", "storage", "serializer"),
        ("core", "storage_client"),
        ("core", "types"),
        ("core", "types", "nested"),
        ("core", "unused"),
        ("utils",),
        ("utils", "constants"),
        ("utils", "helpers"),
    }
    assert set(result.keys()) == expected_ids

    # Spot check key modules
    core = result[("core",)]
    assert core.file.name == "lib.rs"
    assert core.crate == "core"
    assert core.destination_path == Path("src/core/lib.rs")
    assert str(core) == "core"

    config = result[("core", "config")]
    assert config.file.name == "config.rs"
    assert config.destination_path == Path("src/core/config.rs")
    assert str(config) == "core::config"

    storage = result[("core", "storage")]
    assert storage.file.name == "mod.rs"
    assert storage.destination_path == Path("src/core/storage/mod.rs")

    nested = result[("core", "types", "nested")]
    assert nested.file.name == "nested.rs"
    assert nested.destination_path == Path("src/core/types/nested.rs")
    assert str(nested) == "core::types::nested"


def test_modules_exact_output_for_utils(fixture_workspace):
    """Test exact output of modules() for utils crate."""
    workspace = Workspace.from_cargo(fixture_workspace)
    result = modules(workspace, ("utils",))

    # Check exact set of module IDs
    expected_ids = {
        ("utils",),
        ("utils", "constants"),
        ("utils", "helpers"),
    }
    assert set(result.keys()) == expected_ids
    assert len(result) == 3

    # Check all modules
    for module in result.values():
        assert module.file.exists()
        assert module.file.name in ("lib.rs", "constants.rs", "helpers.rs")
        assert module.crate == "utils"


def test_modules_exact_output_for_client(fixture_workspace):
    """Test exact output of modules() for client crate with cross-crate deps."""
    workspace = Workspace.from_cargo(fixture_workspace)
    result = modules(workspace, ("client",))

    # Check that we have client, core, and utils modules
    crates = {module.crate for module in result.values()}
    assert crates == {"client", "core", "utils"}

    # Check client-specific modules
    client_ids = {
        ("client",),
        ("client", "http_client"),
        ("client", "interface"),
    }
    assert client_ids.issubset(result.keys())

    # Check cross-crate dependencies are included
    assert ("core",) in result
    assert ("utils",) in result


def test_module_from_id_caching(fixture_workspace):
    """Test that Module.from_id properly caches modules."""
    workspace = Workspace.from_cargo(fixture_workspace)
    cache = {}

    module1 = Module.from_id(workspace, ("core", "config"), cache)
    module2 = Module.from_id(workspace, ("core", "config"), cache)

    # Should be the exact same object
    assert module1 is module2
    assert ("core", "config") in cache


def test_dependencies_are_valid_module_objects(fixture_workspace):
    """Test that all dependencies are proper Module objects in the cache."""
    workspace = Workspace.from_cargo(fixture_workspace)
    result = modules(workspace, ("client",))

    for module in result.values():
        # Check depends_on is a list of Module instances
        assert isinstance(module.depends_on, list)
        for dep in module.depends_on:
            assert isinstance(dep, Module)
            assert dep.id in result
            assert dep.file.exists()


def test_modules_with_submodule_entry(fixture_workspace):
    """Test modules() with a specific submodule as entry point."""
    workspace = Workspace.from_cargo(fixture_workspace)
    result = modules(workspace, ("core", "config"))

    # Should include the config module and its dependencies
    assert ("core", "config") in result
    assert result[("core", "config")].file.name == "config.rs"


def test_error_handling(fixture_workspace):
    """Test error handling for invalid inputs."""
    workspace = Workspace.from_cargo(fixture_workspace)

    # Nonexistent crate
    with pytest.raises(KeyError):
        modules(workspace, ("nonexistent_crate",))

    # Empty tuple
    with pytest.raises((KeyError, IndexError, ValueError)):
        modules(workspace, ())


@pytest.fixture
def fixture_workspace():
    """Fixture providing the test workspace path."""
    return Path(__file__).parent / "fixtures" / "workspace"
