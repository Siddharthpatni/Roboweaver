"""
RoboWeaver Skill Repository Engine — indexes, searches, and version-manages skills.
"""

from __future__ import annotations

from pathlib import Path

from roboweaver.identifiers import require_safe_identifier
from roboweaver.json_utils import loads_strict
from roboweaver.registry.package import SkillPackage, SkillPackageMetadata


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
        package_id = require_safe_identifier(
            skill_package.metadata.id,
            field_name="skill package id",
        )
        self.packages[package_id] = skill_package
        
        pkg_file = self.registry_dir / f"{package_id}.json"
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
        """Load registered packages from disk.

        Reconstructs the full compiled skill via SkillPackage.from_dict(), not just
        metadata -- a package registered before a process restart used to come back
        as an empty metadata shell (skill=None) because to_dict()/reload didn't
        round-trip the compiled body. See docs/REDESIGN.md's audit of this bug.
        """
        for f in self.registry_dir.glob("*.json"):
            try:
                data = loads_strict(f.read_text(encoding="utf-8"))
                pkg = SkillPackage.from_dict(data)
                if not pkg.metadata.id:
                    pkg.metadata.id = f.stem
                require_safe_identifier(pkg.metadata.id, field_name="skill package id")
                self.packages[pkg.metadata.id] = pkg
            except Exception:
                pass
