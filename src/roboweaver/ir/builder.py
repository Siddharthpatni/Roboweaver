"""
RoboIR Generation — Stage 05. Assembles a RoboIR from the Task Understanding stage's
parsed SkillIntent and the target robot's RobotSpec.
"""

from __future__ import annotations

import uuid

from roboweaver.types import SkillIntent, Action, CompiledSkill, estimate_cycle_time
from roboweaver.hardware.robot_spec import RobotSpec
from roboweaver.ir.schema import (
    RoboIR,
    ObjectRef,
    CapabilityClaim,
    Constraints,
    RequiredCapabilities,
    ExecutionSpec,
    VerificationSpec,
    TaskSummary,
    MotionSummary,
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


def _build_capability_claims(
    manipulation: list[str], perception: list[str], sensing: list[str], robot_spec: RobotSpec,
) -> list[CapabilityClaim]:
    """Formalizes the RW102 (blocking, real declared field)/RW201 (warning, no
    perception system exists) distinction ir/diagnostics.py already draws into a
    structured, queryable list. `verified` means "backed by a real declared
    RobotSpec field", not "the robot happens to satisfy it" -- a robot that
    genuinely lacks a force/torque sensor still gets a *verified* claim (confidence
    0.0), because the check itself is grounded in real data either way.
    `confidence` is never an arbitrary number: it's either 1.0/0.0 from a real
    boolean RobotSpec field, or a stated 0.5 for a capability that is honestly
    unverifiable today (no perception system, no non-force-torque sensing model)."""
    claims: list[CapabilityClaim] = []

    for cap in manipulation:
        # Every RobotSpec has an IK solver by construction (hardware/kinematics_ndof.py
        # works generically off dof/joint limits) -- these are always real.
        claims.append(
            CapabilityClaim(name=f"manipulation.{cap}", confidence=1.0, verified=True, source="declared")
        )

    for cap in perception:
        claims.append(
            CapabilityClaim(name=f"perception.{cap}", confidence=0.5, verified=False, source="unimplemented")
        )

    for cap in sensing:
        if cap == "force_torque":
            has_sensor = bool(robot_spec.has_force_torque_sensor)
            claims.append(
                CapabilityClaim(
                    name=f"sensing.{cap}", confidence=1.0 if has_sensor else 0.0,
                    verified=True, source="declared",
                )
            )
        else:
            claims.append(
                CapabilityClaim(name=f"sensing.{cap}", confidence=0.5, verified=False, source="unimplemented")
            )

    return claims


def _infer_required_capabilities(intent: SkillIntent, robot_spec: RobotSpec) -> RequiredCapabilities:
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

    claims = _build_capability_claims(manipulation, perception, sensing, robot_spec)
    return RequiredCapabilities(perception=perception, manipulation=manipulation, sensing=sensing, claims=claims)


# Actions that need force-compliant (impedance) control rather than pure position
# control -- torque tightening, compliant peg insertion, and force-limited wiping all
# genuinely need this in real robotics, not just in this template's naming.
_COMPLIANT_CONTROL_ACTIONS = {Action.TIGHTEN, Action.PEG_INSERT, Action.CLEAN}


def _build_summaries(skill: CompiledSkill) -> tuple[TaskSummary, MotionSummary]:
    """Real summaries of a CompiledSkill's task graph and motion plan -- Stage 1
    toward RoboIR absorbing task/motion data (docs/COMPILER_ROADMAP.md v2 vision,
    item 1). The full task list/waypoints/behavior tree still live on CompiledSkill;
    this does not duplicate them, just summarizes real counts/types/timing."""
    task_summary = TaskSummary(
        task_count=len(skill.task_graph.tasks),
        task_types=[t.type.value for t in skill.task_graph.tasks],
    )
    total_waypoints = sum(len(seg.waypoints) for seg in skill.motion_plan.trajectories.values())
    motion_summary = MotionSummary(
        segment_count=len(skill.motion_plan.trajectories),
        total_waypoints=total_waypoints,
        estimated_cycle_time_s=round(estimate_cycle_time(skill), 4),
    )
    return task_summary, motion_summary


def build_ir(
    intent: SkillIntent,
    robot_spec: RobotSpec,
    raw_instruction: str,
    skill: CompiledSkill | None = None,
) -> RoboIR:
    """Stage 05: Task Understanding's SkillIntent + a target RobotSpec -> RoboIR.

    `skill` is optional and additive: every existing caller that omits it gets the
    exact same RoboIR as before (task_summary/motion_summary stay None). Passing the
    (possibly optimized) CompiledSkill populates real task/motion summaries --
    compiler.py::compile_with_diagnostics() does this; direct build_ir() callers in
    tests are unaffected.
    """
    controller = "impedance" if intent.action in _COMPLIANT_CONTROL_ACTIONS else "position"

    task_summary = None
    motion_summary = None
    if skill is not None:
        task_summary, motion_summary = _build_summaries(skill)

    return RoboIR(
        skill_id=f"skill_{intent.object_name}_{uuid.uuid4().hex[:8]}",
        skill_version="0.1.0",
        action=intent.action.value,
        raw_instruction=raw_instruction,
        objects=_build_objects(intent),
        constraints=Constraints(payload_kg=robot_spec.payload_capacity_kg, precision_mm=1.0),
        required_capabilities=_infer_required_capabilities(intent, robot_spec),
        execution=ExecutionSpec(robot_id=robot_spec.id, dof=robot_spec.dof, controller=controller),
        verification=VerificationSpec(),
        task_summary=task_summary,
        motion_summary=motion_summary,
    )
