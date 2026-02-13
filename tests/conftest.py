import difflib
from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir():
    """Return the path to the fixture workspace directory."""
    return Path(__file__).parent / "fixtures"


def compare_directories(actual_dir: Path, expected_dir: Path) -> list[str]:
    """Compare two directory trees and return list of differences.

    Returns:
        List of difference messages. Empty list if directories match.
    """
    differences = []

    # Get all files in both directories
    actual_files = {
        f.relative_to(actual_dir) for f in actual_dir.rglob("*") if f.is_file()
    }
    expected_files = {
        f.relative_to(expected_dir) for f in expected_dir.rglob("*") if f.is_file()
    }

    # Check for missing/extra files
    missing_files = expected_files - actual_files
    extra_files = actual_files - expected_files

    for f in sorted(missing_files):
        differences.append(f"Missing file: {f}")

    for f in sorted(extra_files):
        differences.append(f"Extra file: {f}")

    # Compare content of common files
    common_files = actual_files & expected_files
    for rel_path in sorted(common_files):
        actual_file = actual_dir / rel_path
        expected_file = expected_dir / rel_path

        actual_content = actual_file.read_text()
        expected_content = expected_file.read_text()

        if actual_content != expected_content:
            differences.append(f"\nContent mismatch in {rel_path}:")
            diff = difflib.unified_diff(
                expected_content.splitlines(keepends=True),
                actual_content.splitlines(keepends=True),
                fromfile=f"expected/{rel_path}",
                tofile=f"actual/{rel_path}",
                lineterm="",
            )
            differences.append("".join(diff))

    return differences
