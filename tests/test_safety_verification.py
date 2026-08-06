"""
Verification Suite for the Safety Verification pass (src/roboweaver/ir/safety.py).

Verifies:
1. End-to-end: every industrial arm in the registry compiles clean (no false positives).
2. End-to-end: RW301 correctly refuses to compile the generic arm-reach pick-and-place
   skill for embodiments the generic single-target motion planner can't actually reach
   (mobile bases, hand-only specs) -- a real, previously-silent gap this pass closes.
3. RW302 catches a real out-of-range joint configuration.
4. RW303 catches a real payload violation.
5. RW304 catches a real trajectory that exceeds a declared joint velocity limit.
6. RW305 catches a real target beyond the declared workspace.
7. RW306 catches a real near-singular (fully extended) configuration.
8. The motion planner's home-seed clamp and velocity-aware duration scaling
   (compiler.py._plan_motion) actually prevent RW302/RW304 from firing on the
   standard pick-and-place compile for every registered arm -- regression coverage
   for the two real bugs this pass surfaced (Franka's zero-seed violating
   panda_joint4's range, and the fixed 1.0s/0.4s/0.5s durations exceeding real
   per-robot velocity limits).
"""

from __future__ import annotations

import dataclasses

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware.registry_robots import ROBOT_REGISTRY, get_robot_spec
from roboweaver.hardware.robot_spec import JointSpec, LinkSpec, RobotSpec
from roboweaver.ir import build_ir, check_safety
from roboweaver.ir.schema import Constraints
from roboweaver.types import (
    Action,
    BTNode,
    CompiledSkill,
    IKSolution,
    MotionPlan,
    MotionSegment,
    SkillIntent,
    TaskGraph,
)

REACHABLE_ROBOTS = ["franka_panda", "ur5e", "kuka_iiwa", "kinova_gen3", "abb_irb120", "pepper"]
UNREACHABLE_ROBOTS = ["temi", "shadow_hand", "robotiq_hand"]


def _tiny_robot_spec(dof: int = 2) -> RobotSpec:
    """A minimal synthetic 2-DOF arm with tight, known limits -- used to construct
    exact violations without depending on any particular registry robot's numbers."""
    joints = [
        JointSpec(f"j{i}", "revolute", (0, 0, 1), -1.0, 1.0, 1.0, 50.0) for i in range(dof)
    ]
    links = [LinkSpec(f"link{i}", 0.3, 2.0) for i in range(dof)]
    return RobotSpec(
        id="tiny_test_arm",
        name="Tiny Test Arm",
        manufacturer="Test",
        dof=dof,
        payload_capacity_kg=2.0,
        max_reach_m=0.6,
        base_height_m=0.1,
        joints=joints,
        links=links,
    )


def _empty_skill(dof: int, ik_results: dict, trajectories: dict | None = None) -> CompiledSkill:
    intent = SkillIntent(action=Action.PICK, object_name="test_object")
    task_graph = TaskGraph(tasks=[])
    motion_plan = MotionPlan(
        ik_results=ik_results,
        trajectories=trajectories or {},
        robot_model="tiny_test_arm",
    )
    bt = BTNode(type="Sequence", name="root")
    return CompiledSkill(intent=intent, task_graph=task_graph, motion_plan=motion_plan, behavior_tree=bt)


def test_all_reachable_arms_compile_clean():
    print("[TEST 1] Testing every reachable-embodiment arm compiles with no safety errors...")
    for robot_id in REACHABLE_ROBOTS:
        compiler = SkillCompiler(target_robot=robot_id)
        result = compiler.compile_with_diagnostics(
            "Pick the red cube and place it into the blue bin", verbose=False
        )
        errors = [d for d in result.diagnostics if d.severity == "error"]
        assert not errors, f"{robot_id} produced unexpected safety errors: {errors}"
    print(f"  -> {len(REACHABLE_ROBOTS)} arms compiled with zero safety errors [PASSED]")


def test_unreachable_embodiments_are_refused_not_silently_accepted():
    print("\n[TEST 2] Testing RW301 refuses embodiments the generic motion planner can't reach...")
    for robot_id in UNREACHABLE_ROBOTS:
        compiler = SkillCompiler(target_robot=robot_id)
        raised = False
        try:
            compiler.compile_with_diagnostics(
                "Pick the red cube and place it into the blue bin", verbose=False
            )
        except Exception as exc:
            raised = True
            assert "RW301" in str(exc) or "did not converge" in str(exc)
        assert raised, f"{robot_id} should have been refused (IK never converges for this target) but wasn't"
    print(f"  -> {len(UNREACHABLE_ROBOTS)} embodiments correctly refused instead of silently accepted [PASSED]")


def test_joint_limit_violation_detected():
    print("\n[TEST 3] Testing RW302 catches a real out-of-range joint configuration...")
    spec = _tiny_robot_spec(dof=2)
    ik_results = {
        "grasp": IKSolution(joint_angles=[0.5, 0.5], residual=0.0001, iterations=5, success=True),
        "approach": IKSolution(joint_angles=[1.5, 0.0], residual=0.0001, iterations=5, success=True),  # out of [-1, 1]
        "lift": IKSolution(joint_angles=[0.5, 0.5], residual=0.0001, iterations=5, success=True),
    }
    skill = _empty_skill(spec.dof, ik_results)
    ir = build_ir(skill.intent, spec, raw_instruction="test")
    diagnostics = check_safety(skill, ir, spec)
    codes = [d.code for d in diagnostics]
    assert "RW302" in codes, f"expected RW302 for a 1.5rad joint on a [-1,1] limit, got {codes}"
    print("  -> Out-of-range joint configuration correctly flagged [PASSED]")


def test_payload_violation_detected():
    print("\n[TEST 4] Testing RW303 catches a real payload violation...")
    spec = _tiny_robot_spec(dof=2)
    ik_results = {"grasp": IKSolution(joint_angles=[0.0, 0.0], residual=0.0, iterations=1, success=True)}
    skill = _empty_skill(spec.dof, ik_results)
    intent = skill.intent
    ir = build_ir(intent, spec, raw_instruction="test")
    # RoboIR is frozen (ir/schema.py) -- dataclasses.replace() produces a new instance
    # with this one field overridden, rather than mutating `ir` in place.
    ir = dataclasses.replace(ir, constraints=Constraints(payload_kg=5.0, precision_mm=1.0))  # spec caps at 2.0kg
    diagnostics = check_safety(skill, ir, spec)
    codes = [d.code for d in diagnostics]
    assert "RW303" in codes, f"expected RW303 for a 5.0kg payload on a 2.0kg-rated arm, got {codes}"
    print("  -> Payload exceeding rated capacity correctly flagged [PASSED]")


def test_velocity_limit_violation_detected():
    print("\n[TEST 5] Testing RW304 catches a trajectory that exceeds a declared joint velocity limit...")
    spec = _tiny_robot_spec(dof=2)  # max_velocity = 1.0 rad/s per joint
    ik_results = {"grasp": IKSolution(joint_angles=[0.0, 0.0], residual=0.0, iterations=1, success=True)}
    # 1.0 rad in 0.01s == 100 rad/s, far past the 1.0 rad/s limit.
    trajectories = {
        "too fast": MotionSegment(
            start_pose=[0.0, 0.0], end_pose=[1.0, 0.0], waypoints=[[0.0, 0.0], [1.0, 0.0]], duration=0.01
        )
    }
    skill = _empty_skill(spec.dof, ik_results, trajectories)
    ir = build_ir(skill.intent, spec, raw_instruction="test")
    diagnostics = check_safety(skill, ir, spec)
    codes = [d.code for d in diagnostics]
    assert "RW304" in codes, f"expected RW304 for a 100rad/s move on a 1.0rad/s-rated joint, got {codes}"
    print("  -> Trajectory exceeding declared max_velocity correctly flagged [PASSED]")


def test_workspace_violation_detected():
    print("\n[TEST 6] Testing RW305 catches a target beyond the declared workspace...")
    spec = _tiny_robot_spec(dof=2)  # max_reach_m = 0.6
    ik_results = {
        "grasp": IKSolution(
            joint_angles=[0.0, 0.0], residual=0.0, iterations=1, success=True, target_pos=[5.0, 0.0, 0.1]
        )
    }
    skill = _empty_skill(spec.dof, ik_results)
    ir = build_ir(skill.intent, spec, raw_instruction="test")
    diagnostics = check_safety(skill, ir, spec)
    codes = [d.code for d in diagnostics]
    assert "RW305" in codes, f"expected RW305 for a 5m target on a 0.6m-reach arm, got {codes}"
    violation = next(d for d in diagnostics if d.code == "RW305")
    assert violation.severity == "error", "workspace violations must block deployment"
    print("  -> Target beyond declared max_reach_m correctly flagged [PASSED]")


def test_singularity_warning_detected():
    print("\n[TEST 7] Testing RW306 catches a fully-extended, near-singular configuration...")
    spec = get_robot_spec("franka_panda")
    # Fully extended (all joints at zero) is a classic near-singular pose for a
    # serial arm -- the wrist axes align and Cartesian manipulability collapses.
    q = [0.0] * spec.dof
    from roboweaver.hardware.kinematics_ndof import forward_kinematics_ndof

    pos = forward_kinematics_ndof(spec, q).pos
    ik_results = {
        "grasp": IKSolution(
            joint_angles=q, residual=0.0001, iterations=1, success=True, target_pos=[pos.x, pos.y, pos.z]
        )
    }
    skill = _empty_skill(spec.dof, ik_results)
    ir = build_ir(skill.intent, spec, raw_instruction="test")
    diagnostics = check_safety(skill, ir, spec)
    codes = [d.code for d in diagnostics]
    assert "RW306" in codes, f"expected RW306 for a fully-extended configuration, got {codes}"
    print("  -> Near-singular configuration correctly flagged [PASSED]")


def test_home_seed_and_duration_fixes_prevent_false_positives():
    print("\n[TEST 8] Testing the motion planner's home-seed clamp and velocity-aware durations...")
    # Regression test for the two real bugs RW302/RW304 surfaced the first time this
    # pass ran: Franka's zero-seed home configuration violates panda_joint4's real
    # range, and the fixed 1.0s/0.4s/0.5s trajectory durations exceeded real per-robot
    # joint velocity limits. Both are now fixed in compiler.py._plan_motion.
    spec = get_robot_spec("franka_panda")
    assert not (spec.joints[3].lower_limit <= 0.0 <= spec.joints[3].upper_limit), (
        "this test's premise (panda_joint4's range excludes zero) no longer holds -- "
        "if the registry changed, the home-seed clamp is no longer exercised by this case"
    )
    compiler = SkillCompiler(target_robot="franka_panda")
    result = compiler.compile_with_diagnostics(
        "Pick the red cube and place it into the blue bin", verbose=False
    )
    codes = [d.code for d in result.diagnostics]
    assert "RW302" not in codes, "home-seed clamp regression: RW302 fired again"
    assert "RW304" not in codes, "velocity-aware duration regression: RW304 fired again"
    print("  -> Home-seed clamp and velocity-aware durations hold on the real Franka compile [PASSED]")


if __name__ == "__main__":
    print("=== STARTING SAFETY VERIFICATION PASS TESTS ===")
    test_all_reachable_arms_compile_clean()
    test_unreachable_embodiments_are_refused_not_silently_accepted()
    test_joint_limit_violation_detected()
    test_payload_violation_detected()
    test_velocity_limit_violation_detected()
    test_workspace_violation_detected()
    test_singularity_warning_detected()
    test_home_seed_and_duration_fixes_prevent_false_positives()
    print("\n=== ALL SAFETY VERIFICATION PASS TESTS PASSED SUCCESSFULLY ===")
