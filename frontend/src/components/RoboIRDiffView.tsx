'use client';

import React from 'react';
import { GitCompare, Plus, Minus, Pencil } from 'lucide-react';
import { IRDiffResult } from '../types';

/** Real field label -> value formatter. Tuples/arrays render as comma-joined so
 * `required_capabilities.manipulation` reads as a real list, not `[object Object]`. */
function fmt(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (Array.isArray(v)) return v.length ? v.join(', ') : '(none)';
  return String(v);
}

/**
 * Renders a real `ir/diff.py::IRDiff` (via `GET /api/diff`) -- the godbolt.org-style
 * "compare targets" moment: the same instruction, compiled for two real robots,
 * diffed field-by-field. Deliberately not a per-pass diff (see `types/index.ts`'s
 * `IRDiffResult` doc comment for why that would be empty for almost every real
 * compile today) -- this is the honest, substantive comparison.
 */
export const RoboIRDiffView: React.FC<{ diff: IRDiffResult }> = ({ diff }) => {
  const fieldEntries = Object.entries(diff.field_changes).sort(([a], [b]) => a.localeCompare(b));
  const isEmpty =
    fieldEntries.length === 0 &&
    diff.objects_added.length === 0 &&
    diff.objects_removed.length === 0 &&
    diff.objects_changed.length === 0;

  return (
    <div className="app-card p-5 space-y-4">
      <div className="flex items-center gap-2">
        <GitCompare className="w-4 h-4 text-slate-500" />
        <h3 className="text-[13px] font-semibold text-slate-200">RoboIR Diff</h3>
        <span className="font-data text-[11.5px] text-slate-500">
          {diff.from_robot} <span className="text-cyan-400">→</span> {diff.to_robot}
        </span>
      </div>

      {isEmpty && (
        <p className="text-[12.5px] text-slate-500">
          No differences — both robots produce identical RoboIR for this instruction. A real
          result, not a placeholder: it means neither DOF, payload, capabilities, nor
          verification config actually diverged between these two targets.
        </p>
      )}

      {fieldEntries.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10.5px] font-medium text-slate-500 uppercase tracking-wide">
            Changed fields
          </div>
          {fieldEntries.map(([field, [before, after]]) => (
            <div
              key={field}
              className="app-well rounded-lg px-3.5 py-2.5 flex items-center gap-3 flex-wrap"
            >
              <Pencil className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              <span className="font-data text-[11.5px] text-slate-300 shrink-0">{field}</span>
              <span className="flex-1" />
              <span className="font-data text-[12px] text-rose-300">{fmt(before)}</span>
              <span className="text-slate-600">→</span>
              <span className="font-data text-[12px] text-emerald-300">{fmt(after)}</span>
            </div>
          ))}
        </div>
      )}

      {diff.objects_added.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10.5px] font-medium text-slate-500 uppercase tracking-wide">
            Objects only in {diff.to_robot}
          </div>
          {diff.objects_added.map((o) => (
            <div key={o.id} className="app-well rounded-lg px-3.5 py-2 flex items-center gap-2">
              <Plus className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <span className="text-[12px] text-slate-200">{o.name}</span>
              <span className="text-[10.5px] text-slate-500 font-data">{o.role}</span>
            </div>
          ))}
        </div>
      )}

      {diff.objects_removed.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10.5px] font-medium text-slate-500 uppercase tracking-wide">
            Objects only in {diff.from_robot}
          </div>
          {diff.objects_removed.map((o) => (
            <div key={o.id} className="app-well rounded-lg px-3.5 py-2 flex items-center gap-2">
              <Minus className="w-3.5 h-3.5 text-rose-400 shrink-0" />
              <span className="text-[12px] text-slate-200">{o.name}</span>
              <span className="text-[10.5px] text-slate-500 font-data">{o.role}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
