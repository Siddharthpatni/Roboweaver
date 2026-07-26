"""
RoboWeaver Skill Repository Engine — indexes, searches, and version-manages skills.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from roboweaver.registry.package import SkillPackage, SkillPackageMetadata
from roboweaver.types import CompiledSkill


class SkillRepository:
    """Local and Remote Skill Package Registry."""

    def __init__(self, registry_dir: str | Path | None = None):
        if registry_dir is None:
            self.registry_dir = Path.cwd() / ".registry"
        else:
            self.registry_dir = Path(registry_dir)

        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.packages: dict[str, SkillPackage] = {}
        self._load_all()

    def register(self, skill_package: SkillPackage) -> None:
        """Register a new skill package in the repository."""
        self.packages[skill_package.metadata.id] = skill_package
        
        pkg_file = self.registry_dir / f"{skill_package.metadata.id}.json"
        pkg_file.write_text(json.dumps(skill_package.to_dict(), indent=2), encoding="utf-8")

    def list_packages(self) -> list[SkillPackageMetadata]:
        """List all registered skill package metadata."""
        return [pkg.metadata for pkg in self.packages.values()]

    def search(self, query: str) -> list[SkillPackageMetadata]:
        """Search skill packages by action, object name, or tags."""
        q = query.lower()
        results = []
        for pkg in self.packages.values():
            meta = pkg.metadata
            if (
                q in meta.name.lower()
                or q in meta.action.lower()
                or q in meta.target_object.lower()
                or any(q in tag.lower() for tag in meta.tags)
            ):
                results.append(meta)
        return results

    def get_package(self, package_id: str) -> SkillPackage | None:
        return self.packages.get(package_id)

    def _load_all(self) -> None:
        """Load registered packages from disk."""
        for f in self.registry_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                meta_dict = data.get("metadata", {})
                meta = SkillPackageMetadata(
                    id=meta_dict.get("id", f.stem),
                    name=meta_dict.get("name", f.stem),
                    version=meta_dict.get("version", "1.0.0"),
                    description=meta_dict.get("description", ""),
                    action=meta_dict.get("action", "PICK"),
                    target_object=meta_dict.get("target_object", "object"),
                    author=meta_dict.get("author", "RoboWeaver"),
                    license=meta_dict.get("license", "Apache-2.0"),
                    compatible_robots=meta_dict.get("compatible_robots", ["Generic 6-DOF Arm"]),
                    payload_capacity_kg=meta_dict.get("payload_capacity_kg", 2.0),
                    tags=meta_dict.get("tags", []),
                )
                self.packages[meta.id] = SkillPackage(meta, None)  # Metadata shell
            except Exception:
                pass
