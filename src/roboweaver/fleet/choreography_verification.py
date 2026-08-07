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

`handover_target`'s real semantics, found by reading fleet/prompt_builder.py's own
construction logic (prompt_builder.py:137-141): it is the *robot_id* a step hands
off *to* -- set on the handing-off step, and (in every real construction site)
always a different robot than that step's own `robot_id`. Two real checks follow
from that (gap-fix batch, item 1d):
  - RW603 (error): `handover_target` doesn't match any `robot_id` actually used by
    any step in the schedule -- a real typo/bug, no such robot exists here at all.
  - RW604 (warning): `handover_target` names a real robot in the schedule, but no
    step assigned to that robot is reachable (transitively, via depends_on) from the
    handing-off step -- the handoff has no real downstream continuation, so nothing
    in the DAG actually guarantees the receiving robot runs after the handoff.
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


def _downstream_step_ids(schedule: WorkcellSchedule, from_step_id: str) -> set[str]:
    """Every step reachable from `from_step_id` by following depends_on edges
    forward -- i.e. steps that depend on `from_step_id`, directly or transitively.
    Real BFS over the DAG, same style as _find_cyclic_steps."""
    dependents: dict[str, list[str]] = {sid: [] for sid in schedule.steps}
    for step in schedule.steps.values():
        for dep in step.depends_on:
            if dep in dependents:
                dependents[dep].append(step.step_id)

    visited: set[str] = set()
    frontier = [from_step_id]
    while frontier:
        current = frontier.pop()
        for nxt in dependents.get(current, []):
            if nxt not in visited:
                visited.add(nxt)
                frontier.append(nxt)
    return visited


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

    diagnostics.extend(_check_resource_conflicts(schedule))
    diagnostics.extend(_check_handovers(schedule))
    return diagnostics


def _check_resource_conflicts(schedule: WorkcellSchedule) -> list[CompilerDiagnostic]:
    diagnostics: list[CompilerDiagnostic] = []
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


def _check_handovers(schedule: WorkcellSchedule) -> list[CompilerDiagnostic]:
    diagnostics: list[CompilerDiagnostic] = []
    robot_ids_in_schedule = {step.robot_id for step in schedule.steps.values()}
    for step in schedule.steps.values():
        if step.handover_target is None:
            continue
        if step.handover_target not in robot_ids_in_schedule:
            diagnostics.append(
                CompilerDiagnostic(
                    code="RW603",
                    severity="error",
                    message=f"Step '{step.step_id}' hands over to a robot that isn't in this workcell.",
                    reason=(
                        f"handover_target={step.handover_target!r} doesn't match any "
                        f"robot_id used by a step in workcell '{schedule.workcell_name}' "
                        f"(real robots here: {sorted(robot_ids_in_schedule)})."
                    ),
                    required_capability=None,
                    fixes=[
                        "Fix handover_target to reference a robot_id actually used in this workcell.",
                        "Add a step for the intended receiving robot.",
                    ],
                )
            )
            continue

        downstream = _downstream_step_ids(schedule, step.step_id)
        receiving_steps_downstream = [
            sid for sid in downstream if schedule.steps[sid].robot_id == step.handover_target
        ]
        if not receiving_steps_downstream:
            diagnostics.append(
                CompilerDiagnostic(
                    code="RW604",
                    severity="warning",
                    message=(
                        f"Step '{step.step_id}' hands over to '{step.handover_target}', but no "
                        f"step for that robot depends on it."
                    ),
                    reason=(
                        f"A handover implies ordering, but no step assigned to "
                        f"'{step.handover_target}' is reachable (via depends_on) from "
                        f"'{step.step_id}' -- nothing in the DAG guarantees the receiving "
                        f"robot actually runs after this handoff."
                    ),
                    required_capability=None,
                    fixes=[
                        f"Add a step for '{step.handover_target}' that depends_on "
                        f"(directly or transitively) '{step.step_id}'.",
                    ],
                )
            )

    return diagnostics
