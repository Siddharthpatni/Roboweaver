"""
Compiler optimization + static-analysis infrastructure for CompiledSkill.

RoboIR (ir/pass_manager.py) has no task/motion/behavior-tree fields yet -- those
still live only on CompiledSkill (docs/COMPILER_ROADMAP.md Phase 2's deferred list).
This package is a second, symmetric Pass Manager for CompiledSkill: same shape as
ir/pass_manager.py (manager-measured timing, generation threading, a real trace),
kept as its own small module rather than a generic refactor of the RoboIR one --
see docs/COMPILER_ROADMAP.md Phase 3/4 for why.
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
    WaypointDecimationPass,
    RedundantSegmentElisionPass,
)

__all__ = [
    "SkillPass",
    "SkillPassContext",
    "SkillPassResult",
    "SkillPassRecord",
    "SkillPipelineTrace",
    "SkillPassManager",
    "CompiledSkillVerificationPass",
    "WaypointDecimationPass",
    "RedundantSegmentElisionPass",
]
