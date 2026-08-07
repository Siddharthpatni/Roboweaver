"""
RoboIR Generation — Stage 05. Assembles a RoboIR from the Task Understanding stage's
parsed SkillIntent and the target robot's RobotSpec.
"""

from __future__ import annotations

import hashlib
import json

from roboweaver.identifiers import safe_identifier
from roboweaver.types import (
    BTNode,
    SkillIntent,
    Action,
    CompiledSkill,
    TaskType,
    estimate_cycle_time,
    supplied_pose_satisfies_perception,
)
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
    IRBehaviorNode,
    IRIKSolution,
    IRTask,
    IRTrajectory,
    LoweringSpec,
    ProgramSpec,
)

# Actions that need a measured or user-specified real-world pose. If no validated
# observation is supplied, these retain a disclosed perception requirement and emit
# an RW201 warning instead of silently treating an assumed pose as measured.
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
    Action.PALLETIZE,
    Action.POLISH,
    Action.DISASSEMBLE,
    Action.NAVIGATE,
}


def _guess_object_class(name: str) -> str:
    """Best-effort object class from a snake_case name, e.g. 'red_cube' -> 'cube'.

    This is a deterministic fallback, not an image classifier. An external
    observation provider can supply the measured class before IR construction.
    """
    parts = [p for p in name.split("_") if p]
    return parts[-1] if parts else name


def _build_objects(intent: SkillIntent) -> list[ObjectRef]:
    destination = intent.parameters.get("destination_object")
    pose_source = (
        str(intent.parameters.get("_pose_source", "user_specified"))
        if all(key in intent.parameters for key in ("x_m", "y_m", "z_m"))
        else "assumed_default"
    )
    observation = None
    if pose_source == "perception":
        observation = {
            "frame_id": intent.parameters.get("_observation_frame"),
            "observed_at": intent.parameters.get("_observation_timestamp"),
            "confidence": intent.parameters.get("_observation_confidence"),
            "provider_id": intent.parameters.get("_observation_provider"),
            "calibration_id": intent.parameters.get("_calibration_id"),
        }
    source = ObjectRef(
        id="obj_1",
        name=intent.object_name.replace("_", " "),
        object_class=_guess_object_class(intent.object_name),
        role="source",
        pose_source=pose_source,
        observation=observation,
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
    observation satisfies it) distinction ir/diagnostics.py draws into a
    structured, queryable list. `verified` means "backed by a real declared
    RobotSpec field", not "the robot happens to satisfy it" -- a robot that
    genuinely lacks a force/torque sensor still gets a *verified* claim (confidence
    0.0), because the check itself is grounded in real data either way.
    `confidence` is never an arbitrary number: it is 1.0/0.0 from a declared
    RobotSpec field, or 0.5 for a requirement not satisfied by the current input."""
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


def _infer_required_capabilities(
    intent: SkillIntent, robot_spec: RobotSpec, skill: CompiledSkill | None = None,
) -> RequiredCapabilities:
    manipulation = ["grasp_planning", "inverse_kinematics"]
    perception: list[str] = []
    sensing: list[str] = []

    template_requires_perception = (
        any(task.type is TaskType.PERCEIVE for task in skill.task_graph.tasks)
        if skill is not None
        else intent.action in _PERCEPTION_REQUIRING_ACTIONS
    )
    if template_requires_perception and not supplied_pose_satisfies_perception(intent):
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
    elif intent.action == Action.POLISH:
        # skills/taxonomy.py's POLISHING template requires ["ft_sensor", "profilometer"]
        # for its compliant impedance polishing raster -- a real declared need, same
        # class as TIGHTEN/PEG_INSERT/CLEAN.
        sensing = ["force_torque"]
        manipulation.append("compliant_force_control")
    elif intent.action == Action.DISASSEMBLE:
        # skills/taxonomy.py's DISASSEMBLY template requires ["camera", "ft_sensor"]
        # for force-monitored fastener extraction.
        sensing = ["force_torque"]

    claims = _build_capability_claims(manipulation, perception, sensing, robot_spec)
    return RequiredCapabilities(perception=perception, manipulation=manipulation, sensing=sensing, claims=claims)


# Actions that need force-compliant (impedance) control rather than pure position
# control -- torque tightening, compliant peg insertion, and force-limited wiping all
# genuinely need this in real robotics, not just in this template's naming.
_COMPLIANT_CONTROL_ACTIONS = {Action.TIGHTEN, Action.PEG_INSERT, Action.CLEAN, Action.POLISH}


def _build_summaries(skill: CompiledSkill) -> tuple[TaskSummary, MotionSummary]:
    """Build compact indexes over RoboIR's complete ProgramSpec/LoweringSpec data.

    The summaries are convenience fields, not substitutes for the task list,
    behavior tree, IK evidence, or trajectories that ``build_ir()`` stores below.
    Verification checks that the indexes and complete data agree.
    """
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


def _build_behavior(node: BTNode) -> IRBehaviorNode:
    return IRBehaviorNode(
        type=node.type,
        name=node.name,
        children=tuple(_build_behavior(child) for child in node.children),
    )


def _build_program(skill: CompiledSkill) -> ProgramSpec:
    return ProgramSpec(
        object_name=skill.intent.object_name,
        parameters=dict(skill.intent.parameters),
        confidence=float(skill.intent.confidence),
        parse_warnings=tuple(skill.intent.parse_warnings),
        tasks=tuple(
            IRTask(task.type.value, task.description, dict(task.params))
            for task in skill.task_graph.tasks
        ),
        behavior_tree=_build_behavior(skill.behavior_tree),
    )


def _build_lowering(skill: CompiledSkill, robot_spec: RobotSpec) -> LoweringSpec:
    return LoweringSpec(
        robot_id=robot_spec.id,
        joint_names=tuple(joint.name for joint in robot_spec.joints[: robot_spec.dof]),
        ik_solutions=tuple(
            IRIKSolution(
                task_description=description,
                joint_angles=tuple(float(value) for value in solution.joint_angles),
                target_position=tuple(float(value) for value in solution.target_pos),
                residual_m=float(solution.residual),
                iterations=int(solution.iterations),
                success=bool(solution.success),
                solver=solution.solver,
            )
            for description, solution in skill.motion_plan.ik_results.items()
        ),
        trajectories=tuple(
            IRTrajectory(
                task_description=description,
                start_pose=tuple(float(value) for value in segment.start_pose),
                end_pose=tuple(float(value) for value in segment.end_pose),
                waypoints=tuple(
                    tuple(float(value) for value in waypoint)
                    for waypoint in segment.waypoints
                ),
                duration_s=float(segment.duration),
            )
            for description, segment in skill.motion_plan.trajectories.items()
        ),
        motion_model=skill.motion_plan.lowerer,
        scene_digest=skill.motion_plan.scene_digest,
        legalization_trace=skill.motion_plan.legalization_trace,
    )


def build_ir(
    intent: SkillIntent,
    robot_spec: RobotSpec,
    raw_instruction: str,
    skill: CompiledSkill | None = None,
) -> RoboIR:
    """Stage 05: Task Understanding's SkillIntent + a target RobotSpec -> RoboIR.

    ``skill`` remains optional for direct front-end-only callers. Production compile
    paths pass the final optimized CompiledSkill and therefore populate complete
    ProgramSpec/LoweringSpec data plus their checked summary indexes.
    """
    controller = "impedance" if intent.action in _COMPLIANT_CONTROL_ACTIONS else "position"

    task_summary = None
    motion_summary = None
    program = None
    lowering = None
    if skill is not None:
        task_summary, motion_summary = _build_summaries(skill)
        program = _build_program(skill)
        lowering = _build_lowering(skill, robot_spec)

    identity_payload = json.dumps(
        {
            "action": intent.action.value,
            "object_name": intent.object_name,
            "parameters": intent.parameters,
            "raw_instruction": " ".join(raw_instruction.split()),
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    source_id = hashlib.sha256(identity_payload).hexdigest()[:12]

    return RoboIR(
        skill_id=f"skill_{safe_identifier(intent.object_name)}_{source_id}",
        skill_version="0.1.0",
        action=intent.action.value,
        raw_instruction=raw_instruction,
        objects=_build_objects(intent),
        constraints=Constraints(payload_kg=robot_spec.payload_capacity_kg, precision_mm=1.0),
        required_capabilities=_infer_required_capabilities(intent, robot_spec, skill),
        execution=ExecutionSpec(
            robot_id=robot_spec.id,
            dof=robot_spec.dof,
            planner=skill.motion_plan.lowerer if skill is not None else robot_spec.motion_model,
            controller=controller,
        ),
        verification=VerificationSpec(
            collision_check=bool(skill and skill.motion_plan.collision_checked),
            safety_checks=(
                "reach", "floor", "payload", "joint_limits", "environment_collision"
            ) if skill and skill.motion_plan.collision_checked else (
                "reach", "floor", "payload", "joint_limits"
            ),
        ),
        task_summary=task_summary,
        motion_summary=motion_summary,
        program=program,
        lowering=lowering,
        ir_version="0.2.0",
    )
