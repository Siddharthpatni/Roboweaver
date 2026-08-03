"""
Static analysis for WorkcellSchedule (fleet/choreographer.py) -- the real DAG with
depends_on edges across multiple robots, which is where the roadmap's cycle
detection / deadlock / resource-conflict bullets (docs/COMPILER_ROADMAP.md Phase 3)
become honest: a single skill's TaskGraph is a flat list with no dependency edges,
so those checks don't structurally apply there.

Reuses the existing CompilerDiagnostic type (ir/diagnostics.py) -- no new diagnostic
type needed. Additive: WorkcellSchedule.get_execution_tiers() keeps its own bare
`raise ValueError` on a cycle, unchanged; this module is a second, non-raising way to
get the same finding as structured data, plus resource-conflict detection tiers()
never did at all.

NOT checked here, and why: `handover_target` (WorkcellTaskStep) turns out, on
inspection, to be write-only everywhere it's touched (dashboard/server.py,
fleet/prompt_builder.py) -- set but never read or acted on by any real logic. Its one
concrete usage (tests/test_multi_robot_choreography.py) sets it to a *robot_id*
("pepper"), not a step_id, which isn't what a "target step" check would have assumed.
Validating a field whose semantics no consuming code has pinned down would be
guessing, not checking -- deferred until handover_target is actually consumed by
something (e.g. real inter-robot DDS sync), not before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from roboweaver.ir.diagnostics import CompilerDiagnostic

if TYPE_CHECKING:
    # Type-hint only -- choreographer.py imports this module, so importing
    # WorkcellSchedule back at runtime would be circular. Duck-typed access
    # (schedule.steps, step.step_id, step.depends_on, step.robot_id) is all this
    # module actually needs.
    from roboweaver.fleet.choreographer import WorkcellSchedule


def _find_cyclic_steps(schedule: WorkcellSchedule) -> set[str]:
    """Kahn's algorithm; whatever remains un-removable (once dangling depends_on
    references are ruled out separately) is exactly the set of steps in a cycle.
    Mirrors WorkcellSchedule.get_execution_tiers()'s own topological sort but
    returns the stuck set instead of raising."""
    remaining = dict(schedule.steps)
    completed: set[str] = set()

    progressed = True
    while remaining and progressed:
        progressed = False
        for s_id, step in list(remaining.items()):
            if all(dep in completed for dep in step.depends_on):
                completed.add(s_id)
                del remaining[s_id]
                progressed = True

    return set(remaining.keys())


def check_choreography(schedule: WorkcellSchedule) -> list[CompilerDiagnostic]:
    """Real static analysis over a WorkcellSchedule's DAG. Order: dangling
    depends_on references first (RW605) -- a schedule with one of these isn't a
    well-formed DAG at all, so cycle/tier analysis on it would be meaningless; cycle
    detection (RW601) next; resource conflicts (RW602) only computed once the DAG is
    confirmed acyclic, since get_execution_tiers() would raise otherwise."""
    diagnostics: list[CompilerDiagnostic] = []
    all_ids = set(schedule.steps.keys())

    dangling = {
        step.step_id: sorted(d for d in step.depends_on if d not in all_ids)
        for step in schedule.steps.values()
    }
    dangling = {k: v for k, v in dangling.items() if v}
    for step_id, missing in dangling.items():
        diagnostics.append(
            CompilerDiagnostic(
                code="RW605",
                severity="error",
                message=f"Step '{step_id}' depends_on unknown step(s).",
                reason=(
                    f"depends_on references {missing}, which are not step_ids in "
                    f"workcell '{schedule.workcell_name}'."
                ),
                required_capability=None,
                fixes=["Fix depends_on to reference real step_ids.", "Add the missing step(s)."],
            )
        )

    if dangling:
        return diagnostics

    cyclic_ids = _find_cyclic_steps(schedule)
    if cyclic_ids:
        diagnostics.append(
            CompilerDiagnostic(
                code="RW601",
                severity="error",
                message=f"Workcell '{schedule.workcell_name}' has a cyclic dependency among {len(cyclic_ids)} step(s).",
                reason=(
                    f"Step(s) {sorted(cyclic_ids)} form a dependency cycle -- "
                    "get_execution_tiers() cannot topologically sort them."
                ),
                required_capability=None,
                fixes=["Remove or reorder depends_on edges among: " + ", ".join(sorted(cyclic_ids))],
            )
        )
        return diagnostics

    tiers = schedule.get_execution_tiers()
    for tier_idx, tier in enumerate(tiers):
        seen: dict[str, str] = {}
        for step in tier:
            if step.robot_id in seen:
                diagnostics.append(
                    CompilerDiagnostic(
                        code="RW602",
                        severity="error",
                        message=f"Robot '{step.robot_id}' is assigned to two steps that can run concurrently.",
                        reason=(
                            f"Steps '{seen[step.robot_id]}' and '{step.step_id}' are both in "
                            f"execution tier {tier_idx} (neither depends on the other) but both "
                            f"target robot '{step.robot_id}', which cannot execute two steps at once."
                        ),
                        required_capability=None,
                        fixes=[
                            f"Add a depends_on edge between '{seen[step.robot_id]}' and '{step.step_id}'.",
                            "Assign one of the two steps to a different robot.",
                        ],
                    )
                )
            else:
                seen[step.robot_id] = step.step_id

    return diagnostics
