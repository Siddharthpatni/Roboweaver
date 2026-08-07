import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.ir import SkillCompilationError
from roboweaver.math3d import Vec3
from roboweaver.planning import Scene, Sphere


def test_mobile_astar_routes_around_inflated_obstacle_and_records_scene_digest():
    scene = Scene(
        "robot_base",
        (Sphere("safety_post", Vec3(0.60, 0.28, 0.10), 0.03),),
        resolution_m=0.04,
    )
    result = SkillCompiler("temi", scene=scene).compile_with_diagnostics(
        "Navigate to dock x=0.8 y=0 z=0.1", verbose=False,
    )
    assert result.ir.verification.collision_check is True
    assert result.ir.lowering.scene_digest == scene.digest()
    assert "environment_collision" in result.ir.verification.safety_checks
    assert any(
        abs(waypoint[1]) > 0.01
        for segment in result.skill.motion_plan.trajectories.values()
        for waypoint in segment.waypoints
    )
    collision_records = [
        item for item in result.skill_pipeline.records
        if item.pass_name == "environment_collision_planning"
    ]
    assert len(collision_records) == 1


def test_invalid_scene_frame_fails_as_structured_compiler_diagnostic():
    scene = Scene("camera_optical", (), resolution_m=0.04)
    with pytest.raises(SkillCompilationError) as caught:
        SkillCompiler("temi", scene=scene).compile_with_diagnostics(
            "Navigate to dock x=0.8 y=0 z=0.1", verbose=False,
        )
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "RW307"
    assert diagnostic.required_capability == "planning.environment_collision"
