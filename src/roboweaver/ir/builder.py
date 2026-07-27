"""
RoboIR Generation — Stage 05. Assembles a RoboIR from the Task Understanding stage's
parsed SkillIntent and the target robot's RobotSpec.
"""

from __future__ import annotations

import uuid

from roboweaver.types import SkillIntent, Action
from roboweaver.hardware.robot_spec import RobotSpec
from roboweaver.ir.schema import (
    RoboIR,
    ObjectRef,
    Constraints,
    RequiredCapabilities,
    ExecutionSpec,
    VerificationSpec,
)

# Actions that need to know where a real-world object actually is. RoboWeaver has no
# perception system today, so every action in this set always gets a perception
# requirement -- an honest, always-on Compiler Debugger warning (ir/diagnostics.py)
# instead of a silently assumed pose.
_PERCEPTION_REQUIRING_ACTIONS = {
    Action.PICK,
    Action.PLACE,
    Action.PUSH,
    Action.PEG_INSERT,
    Action.POUR,
    Action.PACKAGE,
    Action.CNC_LOAD,
    Action.SURGERY_ASSIST,
    Action.SORT,
    Action.CLEAN,
}


def _guess_object_class(name: str) -> str:
    """Best-effort object class from a snake_case name, e.g. 'red_cube' -> 'cube'.

    This is a heuristic, not a real classifier -- there is no perception system to
    ask, so the last token of the parsed name is the only signal available.
    """
    parts = [p for p in name.split("_") if p]
    return parts[-1] if parts else name


def _build_objects(intent: SkillIntent) -> list[ObjectRef]:
    destination = intent.parameters.get("destination_object")
    source = ObjectRef(
        id="obj_1",
        name=intent.object_name.replace("_", " "),
        object_class=_guess_object_class(intent.object_name),
        role="source",
    )
    if not destination:
        return [source]

    dest_name = str(destination)
    destination_ref = ObjectRef(
        id="obj_2",
        name=dest_name.replace("_", " "),
        object_class=_guess_object_class(dest_name),
        role="destination",
    )
    return [source, destination_ref]


def _infer_required_capabilities(intent: SkillIntent) -> RequiredCapabilities:
    manipulation = ["grasp_planning", "inverse_kinematics"]
    perception: list[str] = []
    sensing: list[str] = []

    if intent.action in _PERCEPTION_REQUIRING_ACTIONS:
        perception = ["object_detection", "pose_estimation"]

    if intent.action == Action.TIGHTEN:
        sensing = ["force_torque"]
        manipulation.append("torque_control")
    elif intent.action == Action.PEG_INSERT:
        sensing = ["force_torque"]
        manipulation.append("compliant_insertion")
    elif intent.action == Action.CNC_LOAD:
        sensing = ["machine_interface"]
    elif intent.action == Action.SURGERY_ASSIST:
        manipulation.append("tremor_filtering")
    elif intent.action == Action.CLEAN:
        manipulation.append("compliant_force_control")

    return RequiredCapabilities(perception=perception, manipulation=manipulation, sensing=sensing)


# Actions that need force-compliant (impedance) control rather than pure position
# control -- torque tightening, compliant peg insertion, and force-limited wiping all
# genuinely need this in real robotics, not just in this template's naming.
_COMPLIANT_CONTROL_ACTIONS = {Action.TIGHTEN, Action.PEG_INSERT, Action.CLEAN}


def build_ir(intent: SkillIntent, robot_spec: RobotSpec, raw_instruction: str) -> RoboIR:
    """Stage 05: Task Understanding's SkillIntent + a target RobotSpec -> RoboIR."""
    controller = "impedance" if intent.action in _COMPLIANT_CONTROL_ACTIONS else "position"

    return RoboIR(
        skill_id=f"skill_{intent.object_name}_{uuid.uuid4().hex[:8]}",
        skill_version="0.1.0",
        action=intent.action.value,
        raw_instruction=raw_instruction,
        objects=_build_objects(intent),
        constraints=Constraints(payload_kg=robot_spec.payload_capacity_kg, precision_mm=1.0),
        required_capabilities=_infer_required_capabilities(intent),
        execution=ExecutionSpec(robot_id=robot_spec.id, dof=robot_spec.dof, controller=controller),
        verification=VerificationSpec(),
    )
