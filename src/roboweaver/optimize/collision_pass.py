"""Final trajectory collision planning pass."""

from __future__ import annotations

import dataclasses

from roboweaver.optimize.pass_manager import SkillPass, SkillPassContext, SkillPassResult
from roboweaver.planning import CollisionAwarePlanner, Scene


class CollisionPlanningPass(SkillPass):
    """Recheck/replan after optimizers so the verified path is the emitted path."""

    name = "environment_collision_planning"

    def __init__(self, scene: Scene):
        self.scene = scene

    def run(self, ctx: SkillPassContext) -> SkillPassResult:
        old_plan = ctx.skill.motion_plan
        new_plan = CollisionAwarePlanner(ctx.robot_spec, self.scene).replan(old_plan)
        changed_waypoints = sum(
            old_plan.trajectories[name].waypoints != segment.waypoints
            for name, segment in new_plan.trajectories.items()
            if name in old_plan.trajectories
        )
        return SkillPassResult(
            skill=dataclasses.replace(ctx.skill, motion_plan=new_plan),
            metrics={
                "scene_obstacles": float(len(self.scene.obstacles)),
                "replanned_segments": float(changed_waypoints),
            },
            modified=(new_plan != old_plan),
        )
