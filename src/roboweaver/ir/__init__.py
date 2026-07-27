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
]
