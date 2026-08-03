"""RoboIR — the intermediate representation. See docs/REDESIGN.md §2."""

from roboweaver.ir.schema import (
    RoboIR,
    ObjectRef,
    Constraints,
    RequiredCapabilities,
    ExecutionSpec,
    VerificationSpec,
)
from roboweaver.ir.builder import build_ir
from roboweaver.ir.diagnostics import CompilerDiagnostic, SkillCompilationError, check_required_capabilities
from roboweaver.ir.safety import check_safety
from roboweaver.ir.pass_manager import (
    OptimizationLevel,
    PassContext,
    PassResult,
    CompilerPass,
    PassRecord,
    PipelineTrace,
    PassManager,
)
from roboweaver.ir.passes import RoboIRVerificationPass, CapabilityPass, SafetyPass
from roboweaver.ir.diff import IRDiff, diff_ir, diff_trace

__all__ = [
    "RoboIR",
    "ObjectRef",
    "Constraints",
    "RequiredCapabilities",
    "ExecutionSpec",
    "VerificationSpec",
    "build_ir",
    "CompilerDiagnostic",
    "SkillCompilationError",
    "check_required_capabilities",
    "check_safety",
    "OptimizationLevel",
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
]
