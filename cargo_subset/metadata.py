from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from toolz import groupby, join


@dataclass
class Target:
    name: str
    kind: List[str]
    src_path: Path
    doctest: bool = True

    @property
    def is_lib(self) -> bool:
        return "lib" in self.kind

    @property
    def is_bin(self) -> bool:
        return "bin" in self.kind


@dataclass
class Crate:
    id: str
    name: str
    manifest_path: Path
    targets: List[Target]
    dependencies: List["Dependency"]
    edition: Optional[str] = None
    features: Optional[Dict[str, List[str]]] = None

    @property
    def root(self) -> Target:
        """Root target for this crate (library or binary)."""
        # Prefer library target, otherwise first binary, else first target.
        for target in self.targets:
            if target.is_lib:
                return target
        for target in self.targets:
            if target.is_bin:
                return target
        if not self.targets:
            raise ValueError(f"Crate {self.name} has no targets")
        return self.targets[0]

    def module(self, segments: Tuple[str, ...]) -> Tuple[Tuple[str, ...], Path]:
        """Resolve module segments to file, handling type/symbol imports.

        Tries progressively shorter paths to find the actual module file.

        Args:
            segments: Module path segments within this crate

        Returns:
            Tuple of (actual_segments, file_path) where actual_segments is the resolved
            module path (may be shorter than input if it contained non-module symbols)

        Raises:
            FileNotFoundError: If no module file can be found
        """
        current_segments = segments

        # Try from longest to shortest path
        while True:
            # If no segments, resolve to the root target (lib.rs or main.rs)
            if not current_segments:
                return ((), self.root.src_path)

            # Build path from segments
            # Try both patterns: foo/bar.rs and foo/bar/mod.rs
            manifest_dir = self.manifest_path.parent
            src_dir = manifest_dir / "src"

            # Build the path from segments
            path_parts = list(current_segments[:-1])
            last_segment = current_segments[-1]

            # Try pattern: path/to/file.rs
            candidate1 = src_dir / Path(*path_parts) / f"{last_segment}.rs"
            if candidate1.exists():
                return (current_segments, candidate1.resolve())

            # Try pattern: path/to/file/mod.rs
            candidate2 = src_dir / Path(*path_parts) / last_segment / "mod.rs"
            if candidate2.exists():
                return (current_segments, candidate2.resolve())

            # Neither pattern worked, try parent path
            if len(current_segments) > 0:
                current_segments = current_segments[:-1]
            else:
                raise FileNotFoundError(
                    f"Could not find module file for {self.name}::{'::'.join(segments)}. "
                    f"Tried various patterns starting from the full path."
                )

    def merge(self, other: "Crate") -> "Crate":
        """Merge another package's dependencies into this one.

        Args:
            other: Another package whose dependencies to merge

        Returns:
            New Crate with merged dependencies and features

        Raises:
            DependencyMergeError: If version requirements cannot be merged
        """
        # Join dependencies on (name, kind) and merge them
        merged_deps = []

        for self_dep, other_dep in join(
            lambda d: (d.name, d.kind),
            self.dependencies,
            lambda d: (d.name, d.kind),
            other.dependencies,
            left_default=None,
            right_default=None,
        ):
            if self_dep is None:
                # Only in other
                merged_deps.append(other_dep)
            elif other_dep is None:
                # Only in self
                merged_deps.append(self_dep)
            else:
                # In both, merge them
                merged_deps.append(self_dep.merge(other_dep))

        # Merge features
        merged_features = {}
        if self.features:
            merged_features.update(self.features)
        if other.features:
            for feature_name, feature_deps in other.features.items():
                if feature_name in merged_features:
                    # Combine feature dependencies, preserving order and removing duplicates
                    existing = merged_features[feature_name]
                    merged_features[feature_name] = existing + [
                        d for d in feature_deps if d not in existing
                    ]
                else:
                    merged_features[feature_name] = feature_deps

        return Crate(
            id=self.id,
            name=self.name,
            manifest_path=self.manifest_path,
            targets=self.targets,
            dependencies=merged_deps,
            edition=self.edition,
            features=merged_features if merged_features else None,
        )

    def render(self) -> str:
        """Render this package as a Cargo.toml file.

        Returns:
            Complete Cargo.toml file content as a string
        """
        # Group dependencies by kind
        deps_by_kind = groupby(lambda d: d.kind or "normal", self.dependencies)
        normal = {d.name: d for d in deps_by_kind.get("normal", [])}
        build = {d.name: d for d in deps_by_kind.get("build", [])}
        dev = {d.name: d for d in deps_by_kind.get("dev", [])}

        lines: List[str] = []

        # Crate metadata
        lines.append("[package]")
        lines.append(f'name = "{self.name}"')
        lines.append('version = "0.1.0"')
        lines.append(f'edition = "{self.edition or "2021"}"')
        lines.append("")

        # [lib] section for doctest flag if needed
        lib_targets = [t for t in self.targets if t.is_lib]
        if lib_targets and not lib_targets[0].doctest:
            lines.append("[lib]")
            lines.append("doctest = false")
            lines.append("")

        # Dependencies
        if normal:
            lines.append("[dependencies]")
            for key in sorted(normal):
                lines.append(f"{key} = {normal[key].render()}")
            lines.append("")

        # Build dependencies
        if build:
            lines.append("[build-dependencies]")
            for key in sorted(build):
                lines.append(f"{key} = {build[key].render()}")
            lines.append("")

        # Dev dependencies
        if dev:
            lines.append("[dev-dependencies]")
            for key in sorted(dev):
                lines.append(f"{key} = {dev[key].render()}")
            lines.append("")

        # Features
        if self.features:
            lines.append("[features]")
            for feature_name in sorted(self.features.keys()):
                feature_deps = self.features[feature_name]
                if feature_deps:
                    deps_str = ", ".join(f'"{dep}"' for dep in feature_deps)
                    lines.append(f"{feature_name} = [{deps_str}]")
                else:
                    lines.append(f"{feature_name} = []")
            lines.append("")

        return "\n".join(lines)


@dataclass
class Workspace:
    root: Path
    crates: Dict[str, Crate]

    def crate(self, name: str) -> Crate:
        try:
            return self.crates[name]
        except KeyError as exc:
            raise KeyError(f"Crate '{name}' not found in workspace") from exc

    def is_workspace_member(self, name: str) -> bool:
        return name in self.crates

    @classmethod
    def from_metadata(cls, metadata: dict, workspace_path: Path) -> Workspace:
        """Create Workspace from cargo metadata dictionary.

        Args:
            metadata: Parsed JSON metadata from cargo metadata command
            workspace_path: Path to the workspace root

        Returns:
            Workspace instance with all packages and dependencies loaded
        """
        root = Path(metadata.get("workspace_root", workspace_path)).resolve()

        # Get workspace members (actual workspace crates, not dependencies)
        workspace_member_ids = set(metadata.get("workspace_members", []))

        crates: Dict[str, Crate] = {}
        for pkg in metadata.get("packages", []):
            # Only include workspace members, not dependencies
            if pkg["id"] not in workspace_member_ids:
                continue
            targets: List[Target] = []
            for target in pkg.get("targets", []):
                targets.append(
                    Target(
                        name=target["name"],
                        kind=list(target.get("kind", [])),
                        src_path=Path(target["src_path"]).resolve(),
                        doctest=bool(target.get("doctest", True)),
                    )
                )
            deps: List[Dependency] = []
            for dep in pkg.get("dependencies", []):
                if not dep.get("name"):
                    continue
                req_str = dep.get("req", "*")
                version_req = VersionRequirement.parse(req_str)
                if version_req is None:
                    # Fallback for unparseable versions - treat as caret with 0.0.0
                    version_req = VersionRequirement("caret", (0, 0, 0))
                deps.append(
                    Dependency(
                        name=dep["name"],
                        version=version_req,
                        kind=dep.get("kind"),
                        optional=bool(dep.get("optional", False)),
                        uses_default_features=bool(
                            dep.get("uses_default_features", True)
                        ),
                        features=list(dep.get("features", [])),
                        target=dep.get("target"),
                    )
                )
            # Parse features
            features_dict = pkg.get("features")
            features = None
            if features_dict:
                features = {k: list(v) for k, v in features_dict.items()}

            crate = Crate(
                id=pkg["id"],
                name=pkg["name"],
                manifest_path=Path(pkg["manifest_path"]).resolve(),
                targets=targets,
                dependencies=deps,
                edition=pkg.get("edition"),
                features=features,
            )
            crates[crate.name] = crate

        return cls(
            root=root,
            crates=crates,
        )

    @classmethod
    def from_cargo(cls, workspace_path: Path) -> Workspace:
        """Load workspace metadata by running cargo metadata.

        Args:
            workspace_path: Path to the workspace root

        Returns:
            Workspace instance with all packages and dependencies loaded

        Raises:
            CargoMetadataError: If cargo metadata fails or returns invalid JSON
        """
        cmd = [
            "cargo",
            "metadata",
            "--format-version",
            "1",
        ]
        try:
            completed = subprocess.run(
                cmd,
                cwd=workspace_path,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            stderr = (
                exc.stderr if isinstance(exc, subprocess.CalledProcessError) else ""
            )
            raise CargoMetadataError(
                f"Failed to run cargo metadata: {exc}\n{stderr}"
            ) from exc

        try:
            metadata = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise CargoMetadataError("cargo metadata returned invalid JSON") from exc

        return cls.from_metadata(metadata, workspace_path)


class CargoMetadataError(RuntimeError):
    pass


class DependencyMergeError(Exception):
    """Raised when dependency version requirements cannot be merged."""

    pass


@dataclass
class VersionRequirement:
    """Represents a Cargo version requirement."""

    requirement_type: str  # 'caret', 'exact', 'ge'
    version: Tuple[int, int, int]  # (major, minor, patch)

    @classmethod
    def parse(cls, req: str) -> Optional[VersionRequirement]:
        """Parse a version requirement string.

        Args:
            req: Version requirement string like "^1.2.3", "=1.0.0", ">=2.0.0"

        Returns:
            VersionRequirement instance or None if invalid
        """
        if req.startswith("^"):
            ver = req[1:]
            parts = ver.split(".")
            try:
                nums = [int(p) for p in parts]
            except ValueError:
                return None
            while len(nums) < 3:
                nums.append(0)
            return cls("caret", tuple(nums[:3]))

        if req.startswith("="):
            ver = req[1:]
            parts = ver.split(".")
            try:
                nums = [int(p) for p in parts]
            except ValueError:
                return None
            while len(nums) < 3:
                nums.append(0)
            return cls("exact", tuple(nums[:3]))

        if req.startswith(">="):
            ver = req[2:]
            parts = ver.split(".")
            try:
                nums = [int(p) for p in parts]
            except ValueError:
                return None
            while len(nums) < 3:
                nums.append(0)
            return cls("ge", tuple(nums[:3]))

        return None

    def merge(self, other: VersionRequirement) -> Optional[VersionRequirement]:
        """Merge this version requirement with another.

        Args:
            other: Other version requirement to merge

        Returns:
            Merged version requirement or None if incompatible
        """
        # Both exact: must match
        if self.requirement_type == "exact" and other.requirement_type == "exact":
            if self.version == other.version:
                return self
            return None

        # Both caret: take higher lower bound
        if self.requirement_type == "caret" and other.requirement_type == "caret":
            return VersionRequirement("caret", max(self.version, other.version))

        # Exact vs caret
        if self.requirement_type == "exact" and other.requirement_type == "caret":
            exact, caret = self.version, other.version
            if exact >= caret:
                return VersionRequirement("exact", exact)
            return None
        elif self.requirement_type == "caret" and other.requirement_type == "exact":
            exact, caret = other.version, self.version
            if exact >= caret:
                return VersionRequirement("exact", exact)
            return None

        # >= vs caret
        elif self.requirement_type == "ge" and other.requirement_type == "caret":
            lower = max(self.version, other.version)
            return VersionRequirement("caret", lower)
        elif self.requirement_type == "caret" and other.requirement_type == "ge":
            lower = max(self.version, other.version)
            return VersionRequirement("caret", lower)

        # Both >=
        elif self.requirement_type == "ge" and other.requirement_type == "ge":
            if self.version[0] != other.version[0]:  # Different major versions
                return None
            return VersionRequirement("ge", max(self.version, other.version))

        # Exact vs >=
        elif self.requirement_type == "exact" and other.requirement_type == "ge":
            exact, ge = self.version, other.version
            if exact >= ge and exact[0] == ge[0]:
                return VersionRequirement("exact", exact)
            return None
        elif self.requirement_type == "ge" and other.requirement_type == "exact":
            exact, ge = other.version, self.version
            if exact >= ge and exact[0] == ge[0]:
                return VersionRequirement("exact", exact)
            return None

        return None

    def format(self) -> str:
        """Format version tuple as a string, omitting trailing zeros."""
        major, minor, patch = self.version
        if patch != 0:
            ver_str = f"{major}.{minor}.{patch}"
        elif minor != 0:
            ver_str = f"{major}.{minor}"
        else:
            ver_str = str(major)

        if self.requirement_type == "caret":
            return f"^{ver_str}"
        elif self.requirement_type == "exact":
            return f"={ver_str}"
        elif self.requirement_type == "ge":
            return f">={ver_str}"
        return ver_str


@dataclass
class Dependency:
    name: str
    version: VersionRequirement
    kind: Optional[str]
    optional: bool
    uses_default_features: bool
    features: List[str]
    target: Optional[str]

    def merge(self, other: Dependency) -> Dependency:
        """Merge this dependency with another.

        Attempts to merge version requirements, features, and other attributes.
        Raises DependencyMergeError if versions are incompatible.

        Args:
            other: Other dependency to merge in

        Returns:
            Merged dependency specification

        Raises:
            DependencyMergeError: If version requirements cannot be merged
        """
        version = self.version
        if self.version != other.version:
            merged = self.version.merge(other.version)
            if merged is None:
                raise DependencyMergeError(
                    f"Dependency version mismatch for {self.name}: "
                    f"{self.version.format()} vs {other.version.format()}. "
                    f"Consider manually resolving this conflict."
                )
            version = merged

        optional = self.optional and other.optional
        uses_default_features = (
            self.uses_default_features and other.uses_default_features
        )
        features = sorted(set(self.features) | set(other.features))

        return Dependency(
            name=self.name,
            version=version,
            kind=self.kind,
            optional=optional,
            uses_default_features=uses_default_features,
            features=features,
            target=self.target,
        )

    def render(self) -> str:
        """Render this dependency as a Cargo.toml value string.

        Returns:
            TOML value string like '"1.0"' or '{ version = "1.0", features = ["foo"] }'
        """
        # Format version without requirement prefix for simplicity
        major, minor, patch = self.version.version
        if patch != 0:
            version_str = f"{major}.{minor}.{patch}"
        else:
            # Keep minor version even if 0 (e.g., "1.0" not "1")
            version_str = f"{major}.{minor}"

        # Use simple string format if no other attributes
        if not self.optional and self.uses_default_features and not self.features:
            return f'"{version_str}"'

        # Otherwise use inline table format
        parts = [f'version = "{version_str}"']

        if self.optional:
            parts.append("optional = true")
        if not self.uses_default_features:
            parts.append("default-features = false")
        if self.features:
            features = ", ".join(f'"{f}"' for f in self.features)
            parts.append(f"features = [{features}]")

        return "{ " + ", ".join(parts) + " }"
