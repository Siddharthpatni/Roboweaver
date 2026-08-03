"""
IR Diff -- compares two RoboIR snapshots at the schema level that exists today:
objects, capabilities, constraints, execution/verification config.

This deliberately does NOT produce a task/motion-level diff ("Removed MOVE MOVE,
Merged GRASP, Inserted WAIT") -- RoboIR has no field for tasks, trajectories, or the
behavior tree (those still live separately on CompiledSkill), so a diff at that level
would have to be fabricated. docs/COMPILER_ROADMAP.md Phase 2 tracks that as deferred
work: RoboIR needs to absorb task/motion data before that diff can be real. What this
module *can* diff honestly today: e.g. "compiling the same instruction for panda vs
ur5e changes execution.dof and constraints.payload_kg", or "pass N in a PipelineTrace
changed field X" -- both real comparisons over data RoboIR actually carries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from roboweaver.ir.pass_manager import PipelineTrace
from roboweaver.ir.schema import ObjectRef, RoboIR


def _flatten_fields(ir: RoboIR) -> dict[str, Any]:
    """Every scalar (non-`objects`) field worth comparing, as a flat dot-path dict."""
    return {
        "skill_id": ir.skill_id,
        "skill_version": ir.skill_version,
        "ir_version": ir.ir_version,
        "action": ir.action,
        "raw_instruction": ir.raw_instruction,
        "parser": ir.parser,
        "constraints.payload_kg": ir.constraints.payload_kg,
        "constraints.precision_mm": ir.constraints.precision_mm,
        "required_capabilities.perception": tuple(ir.required_capabilities.perception),
        "required_capabilities.manipulation": tuple(ir.required_capabilities.manipulation),
        "required_capabilities.sensing": tuple(ir.required_capabilities.sensing),
        "execution.robot_id": ir.execution.robot_id,
        "execution.dof": ir.execution.dof,
        "execution.planner": ir.execution.planner,
        "execution.controller": ir.execution.controller,
        "verification.collision_check": ir.verification.collision_check,
        "verification.simulation_required": ir.verification.simulation_required,
        "verification.safety_checks": tuple(ir.verification.safety_checks),
    }


@dataclass
class IRDiff:
    objects_added: list[ObjectRef] = field(default_factory=list)
    objects_removed: list[ObjectRef] = field(default_factory=list)
    objects_changed: list[tuple[ObjectRef, ObjectRef]] = field(default_factory=list)
    field_changes: dict[str, tuple[Any, Any]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (
            self.objects_added or self.objects_removed
            or self.objects_changed or self.field_changes
        )

    def pretty(self) -> str:
        if self.is_empty():
            return "No differences."
        lines: list[str] = []
        if self.objects_removed:
            lines.append("Removed objects:")
            lines += [f"  - [{o.role}] {o.name} ({o.id})" for o in self.objects_removed]
        if self.objects_added:
            lines.append("Inserted objects:")
            lines += [f"  + [{o.role}] {o.name} ({o.id})" for o in self.objects_added]
        if self.objects_changed:
            lines.append("Changed objects:")
            for old, new in self.objects_changed:
                lines.append(f"  ~ {old.id}: {old.to_dict()} -> {new.to_dict()}")
        if self.field_changes:
            lines.append("Changed fields:")
            for k, (old_v, new_v) in sorted(self.field_changes.items()):
                lines.append(f"  ~ {k}: {old_v!r} -> {new_v!r}")
        return "\n".join(lines)


def diff_ir(
    old: RoboIR, new: RoboIR, *, ignore_fields: frozenset[str] = frozenset({"skill_id"})
) -> IRDiff:
    old_objs = {o.id: o for o in old.objects}
    new_objs = {o.id: o for o in new.objects}

    added = sorted((new_objs[i] for i in new_objs.keys() - old_objs.keys()), key=lambda o: o.id)
    removed = sorted((old_objs[i] for i in old_objs.keys() - new_objs.keys()), key=lambda o: o.id)
    changed = sorted(
        (
            (old_objs[i], new_objs[i])
            for i in old_objs.keys() & new_objs.keys()
            if old_objs[i] != new_objs[i]
        ),
        key=lambda pair: pair[0].id,
    )

    old_fields = _flatten_fields(old)
    new_fields = _flatten_fields(new)
    field_changes = {
        k: (old_fields[k], new_fields[k])
        for k in old_fields
        if k not in ignore_fields and old_fields[k] != new_fields[k]
    }

    return IRDiff(
        objects_added=added, objects_removed=removed,
        objects_changed=changed, field_changes=field_changes,
    )


def diff_trace(trace: PipelineTrace) -> list[tuple[str, IRDiff]]:
    """Per-pass diff across a whole PipelineTrace, using each PassRecord's
    ir_before/ir_after. Skipped passes (applies() returned False) are excluded --
    there's nothing to diff for a pass that didn't run."""
    return [
        (rec.pass_name, diff_ir(rec.ir_before, rec.ir_after))
        for rec in trace.records
        if not rec.skipped
    ]
