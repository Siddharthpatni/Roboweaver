"""RoboIR — the intermediate representation. See docs/REDESIGN.md §2."""

from roboweaver.ir.schema import (
    RoboIR,
    ObjectRef,
    Constraints,
    RequiredCapabilities,
    ExecutionSpec,
    VerificationSpec,
    IRTask,
    IRBehaviorNode,
    ProgramSpec,
    IRIKSolution,
    IRTrajectory,
    LoweringSpec,
)
from roboweaver.ir.builder import build_ir
from roboweaver.ir.diagnostics import CompilerDiagnostic, SkillCompilationError, check_required_capabilities
from roboweaver.ir.safety import check_safety
from roboweaver.ir.pass_manager import (
    OptimizationLevel,
    AnalysisManager,
    PreservedAnalyses,
    PassContext,
    PassResult,
    CompilerPass,
    PassRecord,
    PipelineTrace,
    PassManager,
)
from roboweaver.ir.passes import RoboIRVerificationPass, CapabilityPass, SafetyPass
from roboweaver.ir.diff import IRDiff, diff_ir, diff_trace
from roboweaver.ir.adapters import compiled_skill_from_ir

__all__ = [
    "RoboIR",
    "ObjectRef",
    "Constraints",
    "RequiredCapabilities",
    "ExecutionSpec",
    "VerificationSpec",
    "IRTask",
    "IRBehaviorNode",
    "ProgramSpec",
    "IRIKSolution",
    "IRTrajectory",
    "LoweringSpec",
    "build_ir",
    "CompilerDiagnostic",
    "SkillCompilationError",
    "check_required_capabilities",
    "check_safety",
    "OptimizationLevel",
    "AnalysisManager",
    "PreservedAnalyses",
    "PassContext",
    "PassResult",
    "CompilerPass",
    "PassRecord",
    "PipelineTrace",
    "PassManager",
    "RoboIRVerificationPass",
    "CapabilityPass",
    "SafetyPass",
    "IRDiff",
    "diff_ir",
    "diff_trace",
    "compiled_skill_from_ir",
]
