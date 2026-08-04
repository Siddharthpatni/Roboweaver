"""
RoboBench (docs/COMPILER_ROADMAP.md v2 vision, item 11): a real, in-repo,
compile-time benchmark -- not simulator-execution benchmarking (no 5 simulators
exist in this environment). Scoped down from the original "100 skills x 20 robots x
5 simulators" to what's real and measurable today: every distinct registered robot x
every skill category the compiler's NL pipeline can actually reach.

Originally, only 13 of the 17 IndustrialSkillCategory templates with real,
hand-authored task graphs (skills/taxonomy.py) were reachable through
SkillCompiler.compile() -- PALLETIZING, POLISHING, DISASSEMBLY, and MOBILE_NAV had
no entry in compiler.py::ACTION_CATEGORY_MAP. The gap-fix batch that followed the v2
vision added the missing Action values/keywords/category-map entries (item 1b) and
generalized compiler.py::_plan_motion to plan real per-task trajectories for any
category (item 1a) -- all 17 are reachable now, exercised below.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware.registry_robots import ROBOT_REGISTRY
from roboweaver.ir import SkillCompilationError

# One real instruction per reachable Action -> IndustrialSkillCategory mapping
# (compiler.py::ACTION_CATEGORY_MAP), each verified to route through the real
# deterministic keyword parser (compiler.py::_ACTION_KEYWORDS) -- not fabricated.
_CANONICAL_INSTRUCTIONS: dict[str, str] = {
    "PICK_AND_PLACE": "Pick up the red cube",
    "TIGHTEN_BOLT": "Tighten the M8 bolt",
    "OPEN_DOOR": "Open the door",
    "TOOL_EXCHANGE": "Exchange the tool",
    "INSPECT_SURFACE": "Inspect the surface of the panel",
    "WELD_SEAM": "Weld the seam",
    "PEGGING": "Insert the peg into the alignment hole",
    "POURING_LIQUID": "Pour the liquid into the beaker",
    "PACKAGING": "Pack the item into the carton",
    "CNC_LOADING": "Load the workpiece into the CNC chuck",
    "SURGERY_ASSIST": "Assist with the surgical instrument",
    "SORTING": "Sort the item into the correct bin",
    "CLEANING": "Clean the work surface",
    "PALLETIZING": "Stack the box on the pallet",
    "POLISHING": "Polish the metal panel",
    "DISASSEMBLY": "Disassemble the fastener from the panel",
    "MOBILE_NAV": "Navigate to the loading dock",
}


@dataclass
class BenchmarkCell:
    category: str
    robot_id: str
    instruction: str
    success: bool
    compile_time_s: float
    error_count: int
    warning_count: int
    waypoint_pct_reduction: float | None
    failure_reason: str | None = None


@dataclass
class BenchmarkReport:
    cells: list[BenchmarkCell] = field(default_factory=list)

    def success_count(self) -> int:
        return sum(1 for c in self.cells if c.success)

    def total_compile_time_s(self) -> float:
        return sum(c.compile_time_s for c in self.cells)

    def to_dict(self) -> dict[str, Any]:
        robot_ids = sorted({c.robot_id for c in self.cells})
        return {
            "scope": (
                f"{len({c.category for c in self.cells})} skill categories x "
                f"{len(robot_ids)} distinct registered robots -- real compile-time "
                f"measurement, not simulator-execution benchmarking (scoped down "
                f"from the original 100 skills x 20 robots x 5 simulators)."
            ),
            "total_cells": len(self.cells),
            "success_count": self.success_count(),
            "total_compile_time_s": round(self.total_compile_time_s(), 4),
            "cells": [
                {
                    "category": c.category, "robot_id": c.robot_id, "instruction": c.instruction,
                    "success": c.success, "compile_time_s": round(c.compile_time_s, 6),
                    "error_count": c.error_count, "warning_count": c.warning_count,
                    "waypoint_pct_reduction": c.waypoint_pct_reduction,
                    "failure_reason": c.failure_reason,
                }
                for c in self.cells
            ],
        }


def _distinct_registered_robot_ids() -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for spec in ROBOT_REGISTRY.values():
        if spec.id not in seen:
            seen.add(spec.id)
            ids.append(spec.id)
    return ids


def run_benchmark(robot_ids: list[str] | None = None) -> BenchmarkReport:
    """Real compile-pipeline measurement over every (category, robot) cell. A
    robot that genuinely can't compile a given category (e.g. missing a declared
    capability) is recorded as a real failure cell with the real blocking reason,
    not skipped silently."""
    if robot_ids is None:
        robot_ids = _distinct_registered_robot_ids()

    report = BenchmarkReport()
    for category, instruction in _CANONICAL_INSTRUCTIONS.items():
        for robot_id in robot_ids:
            compiler = SkillCompiler(target_robot=robot_id)
            start = time.perf_counter()
            try:
                result = compiler.compile_with_diagnostics(instruction, verbose=False)
                elapsed = time.perf_counter() - start
                errors = [d for d in result.diagnostics if d.severity == "error"]
                warnings = [d for d in result.diagnostics if d.severity == "warning"]

                pct_reduction = None
                if result.skill_pipeline is not None:
                    for rec in result.skill_pipeline.records:
                        if rec.pass_name == "WaypointDecimationPass" and "pct_reduction" in rec.metrics:
                            pct_reduction = rec.metrics["pct_reduction"]

                report.cells.append(BenchmarkCell(
                    category=category, robot_id=robot_id, instruction=instruction,
                    success=True, compile_time_s=elapsed,
                    error_count=len(errors), warning_count=len(warnings),
                    waypoint_pct_reduction=pct_reduction,
                ))
            except SkillCompilationError as exc:
                elapsed = time.perf_counter() - start
                report.cells.append(BenchmarkCell(
                    category=category, robot_id=robot_id, instruction=instruction,
                    success=False, compile_time_s=elapsed,
                    error_count=len(exc.diagnostics), warning_count=0,
                    waypoint_pct_reduction=None,
                    failure_reason="; ".join(d.message for d in exc.diagnostics),
                ))

    return report
