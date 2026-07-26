"""
Fleet Deployment Orchestrator — manages multi-robot workcells and skill distribution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from roboweaver.hardware import RobotSpec, get_robot_spec
from roboweaver.registry import SkillPackage
from roboweaver.fleet.retargeter import SkillRetargeter


@dataclass
class FleetRobotNode:
    node_id: str
    robot_spec: RobotSpec
    workcell_id: str
    status: str = "IDLE"  # IDLE, EXECUTING, ERROR, OFFLINE
    active_skill_id: str | None = None


@dataclass
class Workcell:
    workcell_id: str
    name: str
    nodes: list[FleetRobotNode] = field(default_factory=list)


class FleetOrchestrator:
    """Orchestrates multi-robot workcells and skill deployment."""

    def __init__(self):
        self.workcells: dict[str, Workcell] = {}

    def register_workcell(self, workcell_id: str, name: str) -> Workcell:
        wc = Workcell(workcell_id, name)
        self.workcells[workcell_id] = wc
        return wc

    def add_robot_to_workcell(self, workcell_id: str, node_id: str, robot_type: str) -> FleetRobotNode:
        spec = get_robot_spec(robot_type)
        node = FleetRobotNode(node_id, spec, workcell_id)
        if workcell_id not in self.workcells:
            self.register_workcell(workcell_id, f"Workcell {workcell_id}")
        self.workcells[workcell_id].nodes.append(node)
        return node

    def deploy_skill_to_fleet(self, skill_package: SkillPackage | None, workcell_id: str) -> dict[str, bool]:
        """Deploy a skill package across all compatible robots in a workcell."""
        wc = self.workcells.get(workcell_id)
        if not wc:
            return {}

        results = {}
        retargeter = SkillRetargeter()

        for node in wc.nodes:
            if skill_package is not None and skill_package.skill is not None:
                retarget_res = retargeter.retarget(skill_package.skill, node.robot_spec)
                node.status = "EXECUTING" if retarget_res.success else "ERROR"
                node.active_skill_id = skill_package.metadata.id
                results[node.node_id] = retarget_res.success
            else:
                node.status = "EXECUTING"
                results[node.node_id] = True

        return results

    def get_fleet_status(self) -> list[dict[str, Any]]:
        status_list = []
        for wc in self.workcells.values():
            for node in wc.nodes:
                status_list.append({
                    "workcell_id": wc.workcell_id,
                    "node_id": node.node_id,
                    "robot": node.robot_spec.name,
                    "dof": node.robot_spec.dof,
                    "status": node.status,
                    "active_skill": node.active_skill_id,
                })
        return status_list
