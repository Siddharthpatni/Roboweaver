"""
Pass Manager — the compiler infrastructure layer on top of RoboIR (ir/schema.py).

Before this module, `compiler.py::compile_with_diagnostics()` called
`check_required_capabilities()` and `check_safety()` as two sequential function calls
with no shared structure, no timing, and no record of what each stage actually did to
the IR. That's already pass-shaped (each function takes a RoboIR, returns
`list[CompilerDiagnostic]`) -- it just wasn't a Pass Manager: nothing recorded
per-stage timing, nothing could see "which pass produced this diagnostic" as
structured data, and there was no way to ask "what did the IR look like before/after
stage N" (see ir/diff.py). This module adds that structure without changing what any
existing pass computes.

`OptimizationLevel` is plumbing only in this phase: no pass registered anywhere in
RoboWeaver today reads `optimization_level` to change its behavior, because no real
optimization pass exists yet (that's docs/COMPILER_ROADMAP.md Phase 4 -- waypoint
merge, trajectory smoothing, etc.). The enum exists now so `CompilerPass.applies()`
has something real to key off once those passes are written, instead of retrofitting
this plumbing later.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

from roboweaver.ir.diagnostics import CompilerDiagnostic
from roboweaver.ir.schema import RoboIR

if TYPE_CHECKING:
    from roboweaver.hardware.robot_spec import RobotSpec
    from roboweaver.types import CompiledSkill


class OptimizationLevel(Enum):
    """Mirrors GCC/LLVM-style optimization flags. See this module's docstring --
    currently gates zero registered passes."""

    O0 = "O0"
    O1 = "O1"
    O2 = "O2"
    O3 = "O3"
    OS = "Os"
    OENERGY = "Oenergy"
    OSAFE = "Osafe"


@dataclass
class PassContext:
    """Everything a CompilerPass needs to run. `skill` (motion plan, IK results,
    trajectories) is threaded through alongside `ir` because SafetyPass genuinely
    needs data RoboIR doesn't carry yet -- RoboIR has no task/motion/behavior-tree
    fields today (docs/COMPILER_ROADMAP.md Phase 2's deferred list). This is a known
    seam, not an oversight: it closes once RoboIR absorbs that data."""

    ir: RoboIR
    skill: "CompiledSkill"
    robot_spec: "RobotSpec"
    optimization_level: OptimizationLevel = OptimizationLevel.O1


@dataclass
class PassResult:
    """What a single CompilerPass.run() call produces."""

    ir: RoboIR
    diagnostics: list[CompilerDiagnostic] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    modified: bool = False


class CompilerPass(ABC):
    """Base class for every compiler pass. Subclasses implement `run()`; `applies()`
    defaults to always-on and exists so a future pass can opt out based on
    `ctx.optimization_level` (e.g. an aggressive-only optimization skipping at O0/O1)."""

    name: str = "unnamed_pass"

    def applies(self, ctx: PassContext) -> bool:
        return True

    @abstractmethod
    def run(self, ctx: PassContext) -> PassResult:
        raise NotImplementedError


@dataclass(frozen=True)
class PassRecord:
    """One row of a PipelineTrace -- what happened when one pass ran. `timing_s` is
    measured by PassManager itself around the `run()` call, not self-reported by the
    pass, so a pass can't under- or over-state its own cost."""

    pass_name: str
    generation: int
    ir_before: RoboIR
    ir_after: RoboIR
    diagnostics: list[CompilerDiagnostic]
    metrics: dict[str, float]
    modified: bool
    timing_s: float
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass_name": self.pass_name,
            "generation": self.generation,
            "modified": self.modified,
            "skipped": self.skipped,
            "timing_s": round(self.timing_s, 6),
            "diagnostic_count": len(self.diagnostics),
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "metrics": self.metrics,
        }


@dataclass
class PipelineTrace:
    """The full record of one PassManager.run() -- an IR v0 -> v1 -> ... -> vN chain
    plus, for each step, what diagnostics/metrics/timing that step produced. Generation
    0 is always `initial_ir` (the RoboIR build_ir() produced, before any pass ran)."""

    records: list[PassRecord]
    initial_ir: RoboIR
    final_ir: RoboIR

    def diagnostics(self) -> list[CompilerDiagnostic]:
        out: list[CompilerDiagnostic] = []
        for rec in self.records:
            out.extend(rec.diagnostics)
        return out

    def total_timing_s(self) -> float:
        return sum(rec.timing_s for rec in self.records)

    def snapshot_at(self, generation: int) -> RoboIR:
        """The RoboIR as it stood after `generation` passes ran (0 = initial_ir,
        before any pass). Enables rollback/debugging to any point in the trace."""
        if generation <= 0:
            return self.initial_ir
        if generation > len(self.records):
            raise IndexError(
                f"generation {generation} exceeds pipeline length ({len(self.records)} passes)"
            )
        return self.records[generation - 1].ir_after

    def to_dict(self) -> dict[str, Any]:
        return {
            "generations": len(self.records) + 1,
            "total_timing_s": round(self.total_timing_s(), 6),
            "diagnostic_count": len(self.diagnostics()),
            "passes": [rec.to_dict() for rec in self.records],
        }


class PassManager:
    """Runs a fixed, ordered sequence of CompilerPass instances over one RoboIR,
    threading the (possibly new) IR from one pass to the next and recording a
    PassRecord per pass. Doesn't decide compile success/failure -- same as before this
    module existed, that's the caller's job (compiler.py raises SkillCompilationError
    on any `severity == "error"` diagnostic in the aggregated trace)."""

    def __init__(self, passes: "list[CompilerPass]"):
        self.passes = list(passes)

    def run(
        self,
        initial_ir: RoboIR,
        skill: "CompiledSkill",
        robot_spec: "RobotSpec",
        optimization_level: OptimizationLevel = OptimizationLevel.O1,
    ) -> PipelineTrace:
        current_ir = initial_ir
        records: list[PassRecord] = []

        for generation, compiler_pass in enumerate(self.passes, start=1):
            ctx = PassContext(
                ir=current_ir, skill=skill, robot_spec=robot_spec,
                optimization_level=optimization_level,
            )

            if not compiler_pass.applies(ctx):
                records.append(
                    PassRecord(
                        pass_name=compiler_pass.name, generation=generation,
                        ir_before=current_ir, ir_after=current_ir,
                        diagnostics=[], metrics={}, modified=False,
                        timing_s=0.0, skipped=True,
                    )
                )
                continue

            start = time.perf_counter()
            result = compiler_pass.run(ctx)
            elapsed = time.perf_counter() - start

            records.append(
                PassRecord(
                    pass_name=compiler_pass.name, generation=generation,
                    ir_before=current_ir, ir_after=result.ir,
                    diagnostics=result.diagnostics, metrics=result.metrics,
                    modified=result.modified, timing_s=elapsed,
                )
            )
            current_ir = result.ir

        return PipelineTrace(records=records, initial_ir=initial_ir, final_ir=current_ir)
