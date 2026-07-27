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
from roboweaver.types import (
    Action,
    BTNode,
    CompiledSkill,
    IKResult,
    MotionPlan,
    SkillIntent,
    Task,
    TaskGraph,
    TaskType,
    TrajectorySegment,
)


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

    def __init__(self, metadata: SkillPackageMetadata, skill: CompiledSkill | None):
        self.metadata = metadata
        self.skill = skill

    def to_dict(self) -> dict[str, Any]:
        """Convert skill package to structured dictionary.

        Includes the full compiled skill (intent, task graph, motion plan, behavior
        tree) so a reload from disk can reconstruct the actual skill, not just its
        metadata -- see SkillRepository._load_all(), which used to discard the
        compiled body on every process restart.
        """
        data: dict[str, Any] = {"metadata": asdict(self.metadata)}
        if self.skill is None:
            return data

        data["intent"] = {
            "action": self.skill.intent.action.value,
            "object_name": self.skill.intent.object_name,
            "parameters": self.skill.intent.parameters,
        }
        data["task_graph"] = [
            {"type": t.type.value, "description": t.description, "params": t.params}
            for t in self.skill.task_graph.tasks
        ]
        data["motion_plan"] = {
            "robot_model": self.skill.motion_plan.robot_model,
            "ik_results": {
                name: {
                    "joint_angles": list(r.joint_angles),
                    "residual": r.residual,
                    "iterations": r.iterations,
                    "success": r.success,
                    "target_pos": list(r.target_pos),
                }
                for name, r in self.skill.motion_plan.ik_results.items()
            },
            "trajectories": {
                name: {
                    "start_pose": list(seg.start_pose),
                    "end_pose": list(seg.end_pose),
                    "waypoints": [list(wp) for wp in seg.waypoints],
                    "duration": seg.duration,
                }
                for name, seg in self.skill.motion_plan.trajectories.items()
            },
        }
        data["behavior_tree"] = self._bt_to_dict(self.skill.behavior_tree)
        return data

    @staticmethod
    def _bt_to_dict(node: BTNode) -> dict[str, Any]:
        return {
            "type": node.type,
            "name": node.name,
            "children": [SkillPackage._bt_to_dict(c) for c in node.children],
        }

    @staticmethod
    def _bt_from_dict(d: dict[str, Any]) -> BTNode:
        return BTNode(
            type=d["type"],
            name=d["name"],
            children=[SkillPackage._bt_from_dict(c) for c in d.get("children", [])],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillPackage":
        """Reconstruct a SkillPackage -- including the compiled skill body, not just
        metadata -- from what to_dict() produced."""
        meta_dict = data.get("metadata", {})
        meta = SkillPackageMetadata(
            id=meta_dict.get("id", ""),
            name=meta_dict.get("name", ""),
            version=meta_dict.get("version", "1.0.0"),
            description=meta_dict.get("description", ""),
            action=meta_dict.get("action", "PICK"),
            target_object=meta_dict.get("target_object", "object"),
            author=meta_dict.get("author", "RoboWeaver Skill Compiler"),
            license=meta_dict.get("license", "Apache-2.0"),
            compatible_robots=meta_dict.get("compatible_robots", ["Generic 6-DOF Arm"]),
            payload_capacity_kg=meta_dict.get("payload_capacity_kg", 2.0),
            tags=meta_dict.get("tags", []),
        )

        skill: CompiledSkill | None = None
        if "intent" in data and "task_graph" in data and "motion_plan" in data and "behavior_tree" in data:
            intent_d = data["intent"]
            intent = SkillIntent(
                action=Action(intent_d["action"]),
                object_name=intent_d["object_name"],
                parameters=intent_d.get("parameters", {}),
            )
            tasks = [
                Task(type=TaskType(t["type"]), description=t["description"], params=t.get("params", {}))
                for t in data["task_graph"]
            ]
            task_graph = TaskGraph(tasks=tasks)

            mp_d = data["motion_plan"]
            ik_results = {
                name: IKResult(
                    joint_angles=r["joint_angles"],
                    residual=r["residual"],
                    iterations=r["iterations"],
                    success=r.get("success", True),
                    target_pos=r.get("target_pos", [0.0, 0.0, 0.0]),
                )
                for name, r in mp_d.get("ik_results", {}).items()
            }
            trajectories = {
                name: TrajectorySegment(
                    start_pose=t["start_pose"],
                    end_pose=t["end_pose"],
                    waypoints=t["waypoints"],
                    duration=t["duration"],
                )
                for name, t in mp_d.get("trajectories", {}).items()
            }
            motion_plan = MotionPlan(
                ik_results=ik_results, trajectories=trajectories, robot_model=mp_d.get("robot_model", "panda")
            )

            behavior_tree = cls._bt_from_dict(data["behavior_tree"])

            skill = CompiledSkill(
                intent=intent, task_graph=task_graph, motion_plan=motion_plan, behavior_tree=behavior_tree
            )

        return cls(meta, skill)

    def export_archive(self, output_path: str | Path) -> Path:
        """Export skill package to a `.rwsp` tarball archive."""
        out = Path(output_path)
        pkg_dir = out.parent / f"tmp_{self.metadata.id}"
        pkg_dir.mkdir(parents=True, exist_ok=True)

        # Write metadata.json
        (pkg_dir / "metadata.json").write_text(
            json.dumps(asdict(self.metadata), indent=2),
            encoding="utf-8",
        )

        # Write package_data.json
        (pkg_dir / "package_data.json").write_text(
            json.dumps(self.to_dict(), indent=2), encoding="utf-8"
        )

        # Write behavior_tree.xml
        if self.skill is not None:
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
