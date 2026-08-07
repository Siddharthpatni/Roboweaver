"""
Real Compile -> Digital Twin -> Test -> Deploy gate (docs/COMPILER_ROADMAP.md v2
vision, item 5). Wires simulation_backends/twin.py's DigitalTwin interface into a
single validation call that plugins/backend.py::RobotBackend.deploy() uses before
touching real hardware.
"""

from __future__ import annotations

from roboweaver.hardware.robot_spec import RobotSpec
from roboweaver.ir.adapters import compiled_skill_from_ir
from roboweaver.ir.schema import RoboIR
from roboweaver.simulation_backends.twin import DigitalTwin, NativeTwin
from roboweaver.types import CompiledSkill, ExecutionResult


def validate_in_simulation(
    skill: CompiledSkill | RoboIR, robot_spec: RobotSpec, twin: DigitalTwin | None = None,
) -> ExecutionResult:
    """Defaults to NativeTwin -- the only twin that genuinely executes today (see
    simulation_backends/twin.py's module docstring for why RemoteTwin can't)."""
    if twin is None:
        twin = NativeTwin()
    twin.load_robot(robot_spec)
    runtime_skill = compiled_skill_from_ir(skill) if isinstance(skill, RoboIR) else skill
    return twin.execute(runtime_skill)
