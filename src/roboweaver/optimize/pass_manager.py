"""
Pass Manager for CompiledSkill -- the optimization/static-analysis counterpart to
ir/pass_manager.py's PassManager for RoboIR. Same shape (manager-measured timing,
generation threading via dataclasses.replace, a real PipelineTrace-like record) —
deliberately a separate, small class hierarchy rather than a generic refactor of
ir/pass_manager.py. See this package's __init__.py docstring for why.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from roboweaver.ir.diagnostics import CompilerDiagnostic
from roboweaver.ir.pass_manager import OptimizationLevel

if TYPE_CHECKING:
    from roboweaver.hardware.robot_spec import RobotSpec
    from roboweaver.types import CompiledSkill


@dataclass
class SkillPassContext:
    skill: "CompiledSkill"
    robot_spec: "RobotSpec"
    optimization_level: OptimizationLevel = OptimizationLevel.O1


@dataclass
class SkillPassResult:
    skill: "CompiledSkill"
    diagnostics: list[CompilerDiagnostic] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    modified: bool = False


class SkillPass(ABC):
    """Base class for every CompiledSkill pass. `applies()` defaults to always-on;
    optimization passes override it to skip at O0, matching GCC/LLVM convention."""

    name: str = "unnamed_skill_pass"

    def applies(self, ctx: SkillPassContext) -> bool:
        return True

    @abstractmethod
    def run(self, ctx: SkillPassContext) -> SkillPassResult:
        raise NotImplementedError


@dataclass(frozen=True)
class SkillPassRecord:
    pass_name: str
    generation: int
    skill_before: "CompiledSkill"
    skill_after: "CompiledSkill"
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
class SkillPipelineTrace:
    records: list[SkillPassRecord]
    initial_skill: "CompiledSkill"
    final_skill: "CompiledSkill"

    def diagnostics(self) -> list[CompilerDiagnostic]:
        out: list[CompilerDiagnostic] = []
        for rec in self.records:
            out.extend(rec.diagnostics)
        return out

    def total_timing_s(self) -> float:
        return sum(rec.timing_s for rec in self.records)

    def snapshot_at(self, generation: int) -> "CompiledSkill":
        if generation <= 0:
            return self.initial_skill
        if generation > len(self.records):
            raise IndexError(
                f"generation {generation} exceeds pipeline length ({len(self.records)} passes)"
            )
        return self.records[generation - 1].skill_after

    def to_dict(self) -> dict[str, Any]:
        return {
            "generations": len(self.records) + 1,
            "total_timing_s": round(self.total_timing_s(), 6),
            "diagnostic_count": len(self.diagnostics()),
            "passes": [rec.to_dict() for rec in self.records],
        }


class SkillPassManager:
    """Runs a fixed, ordered sequence of SkillPass instances over one CompiledSkill,
    threading the (possibly new) skill from one pass to the next. Same non-deciding
    contract as ir/pass_manager.py::PassManager -- the caller (compiler.py) decides
    what to do with the aggregated diagnostics."""

    def __init__(self, passes: "list[SkillPass]"):
        self.passes = list(passes)

    def run(
        self,
        initial_skill: "CompiledSkill",
        robot_spec: "RobotSpec",
        optimization_level: OptimizationLevel = OptimizationLevel.O1,
    ) -> SkillPipelineTrace:
        current_skill = initial_skill
        records: list[SkillPassRecord] = []

        for generation, skill_pass in enumerate(self.passes, start=1):
            ctx = SkillPassContext(
                skill=current_skill, robot_spec=robot_spec, optimization_level=optimization_level,
            )

            if not skill_pass.applies(ctx):
                records.append(
                    SkillPassRecord(
                        pass_name=skill_pass.name, generation=generation,
                        skill_before=current_skill, skill_after=current_skill,
                        diagnostics=[], metrics={}, modified=False,
                        timing_s=0.0, skipped=True,
                    )
                )
                continue

            start = time.perf_counter()
            result = skill_pass.run(ctx)
            elapsed = time.perf_counter() - start

            records.append(
                SkillPassRecord(
                    pass_name=skill_pass.name, generation=generation,
                    skill_before=current_skill, skill_after=result.skill,
                    diagnostics=result.diagnostics, metrics=result.metrics,
                    modified=result.modified, timing_s=elapsed,
                )
            )
            current_skill = result.skill

        return SkillPipelineTrace(records=records, initial_skill=initial_skill, final_skill=current_skill)
