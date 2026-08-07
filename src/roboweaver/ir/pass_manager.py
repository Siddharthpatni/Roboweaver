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

`OptimizationLevel` is shared with the CompiledSkill pass manager. O0 disables the
registered waypoint-decimation and redundant-segment-elision passes; verification
passes remain mandatory at every level.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TYPE_CHECKING

from roboweaver.ir.diagnostics import CompilerDiagnostic
from roboweaver.ir.schema import RoboIR

if TYPE_CHECKING:
    from roboweaver.hardware.robot_spec import RobotSpec
    from roboweaver.types import CompiledSkill


class OptimizationLevel(Enum):
    """GCC/LLVM-style optimization modes shared by both pass managers."""

    O0 = "O0"
    O1 = "O1"
    O2 = "O2"
    O3 = "O3"
    OS = "Os"
    OENERGY = "Oenergy"
    OSAFE = "Osafe"


@dataclass(frozen=True)
class PreservedAnalyses:
    """LLVM-style declaration of analyses that survive an IR-changing pass."""

    names: frozenset[str] = frozenset()
    preserve_all: bool = False

    @classmethod
    def all(cls) -> "PreservedAnalyses":
        return cls(preserve_all=True)

    @classmethod
    def none(cls) -> "PreservedAnalyses":
        return cls()

    @classmethod
    def only(cls, *names: str) -> "PreservedAnalyses":
        return cls(frozenset(names))

    def preserves(self, name: str) -> bool:
        return self.preserve_all or name in self.names


AnalysisProvider = Callable[["PassContext"], Any]


class AnalysisManager:
    """Lazy per-IR analysis cache with explicit preservation/invalidation."""

    def __init__(self):
        self._providers: dict[str, AnalysisProvider] = {}
        self._cache: dict[tuple[int, str], Any] = {}
        self.hits = 0
        self.misses = 0
        self.invalidations = 0

    def register(self, name: str, provider: AnalysisProvider) -> None:
        if not name or name in self._providers:
            raise ValueError(f"analysis {name!r} is empty or already registered")
        self._providers[name] = provider

    def get(self, name: str, ctx: "PassContext") -> Any:
        try:
            provider = self._providers[name]
        except KeyError as exc:
            raise LookupError(f"analysis {name!r} is not registered") from exc
        key = (id(ctx.ir), name)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1
        value = provider(ctx)
        self._cache[key] = value
        return value

    def invalidate(self, ir: RoboIR, preserved: PreservedAnalyses) -> None:
        doomed = [
            key for key in self._cache
            if key[0] == id(ir) and not preserved.preserves(key[1])
        ]
        for key in doomed:
            del self._cache[key]
        self.invalidations += len(doomed)

    def snapshot(self) -> tuple[int, int, int]:
        return self.hits, self.misses, self.invalidations


def _ir_structure_analysis(ctx: "PassContext") -> dict[str, int]:
    program = ctx.ir.program
    lowering = ctx.ir.lowering
    return {
        "object_count": len(ctx.ir.objects),
        "task_count": len(program.tasks) if program is not None else 0,
        "move_task_count": (
            sum(task.type == "MOVE_TO" for task in program.tasks) if program is not None else 0
        ),
        "trajectory_count": len(lowering.trajectories) if lowering is not None else 0,
    }


def _default_analysis_manager() -> AnalysisManager:
    manager = AnalysisManager()
    manager.register("roboir.structure", _ir_structure_analysis)
    return manager


@dataclass
class PassContext:
    """Everything a CompilerPass needs to run.

    ``skill`` remains for compatibility with third-party passes during the RoboIR
    transition. Built-in verification passes use complete ``ir`` as their semantic
    source of truth.
    """

    ir: RoboIR
    skill: "CompiledSkill"
    robot_spec: "RobotSpec"
    optimization_level: OptimizationLevel = OptimizationLevel.O1
    analyses: AnalysisManager = field(default_factory=_default_analysis_manager)


@dataclass
class PassResult:
    """What a single CompilerPass.run() call produces."""

    ir: RoboIR
    diagnostics: list[CompilerDiagnostic] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    modified: bool = False
    preserved_analyses: PreservedAnalyses | None = None


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
        analyses = _default_analysis_manager()

        for generation, compiler_pass in enumerate(self.passes, start=1):
            ctx = PassContext(
                ir=current_ir, skill=skill, robot_spec=robot_spec,
                optimization_level=optimization_level,
                analyses=analyses,
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
            stats_before = analyses.snapshot()
            result = compiler_pass.run(ctx)
            elapsed = time.perf_counter() - start
            preserved = result.preserved_analyses
            if preserved is None:
                preserved = PreservedAnalyses.none() if result.modified else PreservedAnalyses.all()
            if result.modified:
                analyses.invalidate(current_ir, preserved)
            stats_after = analyses.snapshot()
            metrics = dict(result.metrics)
            metrics.update({
                "analysis_cache_hits": float(stats_after[0] - stats_before[0]),
                "analysis_cache_misses": float(stats_after[1] - stats_before[1]),
                "analysis_invalidations": float(stats_after[2] - stats_before[2]),
            })

            records.append(
                PassRecord(
                    pass_name=compiler_pass.name, generation=generation,
                    ir_before=current_ir, ir_after=result.ir,
                    diagnostics=result.diagnostics, metrics=metrics,
                    modified=result.modified, timing_s=elapsed,
                )
            )
            current_ir = result.ir

        return PipelineTrace(records=records, initial_ir=initial_ir, final_ir=current_ir)
