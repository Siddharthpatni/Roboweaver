"""
RoboWeaver Skill Package (.rwsp) Engine — packages, serializes, and archives skills.
"""

from __future__ import annotations

import json
import tarfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from roboweaver.codegen.groot2 import export_groot2_xml
from roboweaver.types import CompiledSkill


@dataclass
class SkillPackageMetadata:
    """Metadata specification for a versioned Skill Package."""
    id: str
    name: str
    version: str
    description: str
    action: str
    target_object: str
    author: str = "RoboWeaver Skill Compiler"
    license: str = "Apache-2.0"
    compatible_robots: list[str] = field(
        default_factory=lambda: ["Franka Panda", "UR5e", "Generic 6-DOF Arm"]
    )
    payload_capacity_kg: float = 2.0
    tags: list[str] = field(default_factory=lambda: ["manipulation", "pick-and-place"])


class SkillPackage:
    """A versioned, self-contained RoboWeaver Skill Package."""

    def __init__(self, metadata: SkillPackageMetadata, skill: CompiledSkill):
        self.metadata = metadata
        self.skill = skill

    def to_dict(self) -> dict[str, Any]:
        """Convert skill package to structured dictionary."""
        return {
            "metadata": asdict(self.metadata),
            "intent": {
                "action": self.skill.intent.action.value,
                "object_name": self.skill.intent.object_name,
                "parameters": self.skill.intent.parameters,
            },
            "task_graph": [
                {
                    "type": t.type.value,
                    "description": t.description,
                    "params": t.params,
                }
                for t in self.skill.task_graph.tasks
            ],
            "trajectories": {
                name: {
                    "waypoints": seg.waypoints,
                    "duration": seg.duration,
                }
                for name, seg in self.skill.motion_plan.trajectories.items()
            },
        }

    def export_archive(self, output_path: str | Path) -> Path:
        """Export skill package to a `.rwsp` tarball archive."""
        out = Path(output_path)
        pkg_dir = out.parent / f"tmp_{self.metadata.id}"
        pkg_dir.mkdir(parents=True, exist_ok=True)

        # Write metadata.json
        (pkg_dir / "metadata.json").write_text(
            json.dump_str if hasattr(json, "dump_str") else json.dumps(asdict(self.metadata), indent=2),
            encoding="utf-8",
        )

        # Write package_data.json
        (pkg_dir / "package_data.json").write_text(
            json.dumps(self.to_dict(), indent=2), encoding="utf-8"
        )

        # Write behavior_tree.xml
        bt_xml = export_groot2_xml(self.skill)
        (pkg_dir / "behavior_tree.xml").write_text(bt_xml, encoding="utf-8")

        # Create tar.gz archive with extension .rwsp
        archive_path = out if str(out).endswith(".rwsp") else out.with_suffix(".rwsp")
        with tarfile.open(archive_path, "w:gz") as tar:
            for item in pkg_dir.iterdir():
                tar.add(item, arcname=item.name)

        # Clean up temp dir
        for item in pkg_dir.iterdir():
            item.unlink()
        pkg_dir.rmdir()

        return archive_path
