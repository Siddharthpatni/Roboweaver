"""
Compiler optimization + static-analysis infrastructure for CompiledSkill.

RoboIR now carries complete program and lowering data. This package remains a second,
small Pass Manager for the pre-RoboIR ``CompiledSkill`` optimization boundary so
trajectory transformations can be verified before ``build_ir()`` freezes their
result into the target lowering.
"""

from roboweaver.optimize.pass_manager import (
    SkillPass,
    SkillPassContext,
    SkillPassResult,
    SkillPassRecord,
    SkillPipelineTrace,
    SkillPassManager,
)
from roboweaver.optimize.passes import (
    CompiledSkillVerificationPass,
    BoundedFormalVerificationPass,
    WaypointDecimationPass,
    RedundantSegmentElisionPass,
)
from roboweaver.optimize.collision_pass import CollisionPlanningPass

__all__ = [
    "SkillPass",
    "SkillPassContext",
    "SkillPassResult",
    "SkillPassRecord",
    "SkillPipelineTrace",
    "SkillPassManager",
    "CompiledSkillVerificationPass",
    "BoundedFormalVerificationPass",
    "WaypointDecimationPass",
    "RedundantSegmentElisionPass",
    "CollisionPlanningPass",
]
