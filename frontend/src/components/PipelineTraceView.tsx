'use client';

import React from 'react';
import { ArrowRight, CheckCircle2, MinusCircle, AlertTriangle, AlertOctagon } from 'lucide-react';
import { PipelineTraceResult, PassRecordResult } from '../types';

function PassCard({ pass, maxTimingS }: { pass: PassRecordResult; maxTimingS: number }) {
  const errorCount = pass.diagnostics.filter((d) => d.severity === 'error').length;
  const warningCount = pass.diagnostics.filter((d) => d.severity === 'warning').length;
  const barPct = maxTimingS > 0 ? Math.max(4, (pass.timing_s / maxTimingS) * 100) : 4;

  return (
    <div
      className={`shrink-0 w-52 rounded-lg border p-3 space-y-2 ${
        pass.skipped
          ? 'border-white/[0.06] bg-white/[0.01] opacity-60'
          : pass.modified
          ? 'border-cyan-400/25 bg-cyan-500/[0.05]'
          : 'border-white/[0.08] bg-white/[0.02]'
      }`}
    >
      <div className="flex items-center justify-between gap-1.5">
        <span className="font-data text-[11px] text-slate-200 truncate" title={pass.pass_name}>
          {pass.pass_name}
        </span>
        {pass.skipped ? (
          <MinusCircle className="w-3.5 h-3.5 text-slate-600 shrink-0" />
        ) : pass.modified ? (
          <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
        ) : (
          <CheckCircle2 className="w-3.5 h-3.5 text-slate-600 shrink-0" />
        )}
      </div>

      <div className="space-y-1">
        <div className="h-1 w-full bg-black/30 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-cyan-500 to-violet-500 rounded-full"
            style={{ width: `${barPct}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-[10px] font-data text-slate-500">
          <span>{(pass.timing_s * 1000).toFixed(3)}ms</span>
          <span>{pass.skipped ? 'skipped' : pass.modified ? 'modified' : 'unchanged'}</span>
        </div>
      </div>

      {(errorCount > 0 || warningCount > 0) && (
        <div className="flex items-center gap-2 text-[10.5px]">
          {errorCount > 0 && (
            <span className="flex items-center gap-1 text-rose-400">
              <AlertOctagon className="w-3 h-3" /> {errorCount}
            </span>
          )}
          {warningCount > 0 && (
            <span className="flex items-center gap-1 text-amber-400">
              <AlertTriangle className="w-3 h-3" /> {warningCount}
            </span>
          )}
        </div>
      )}

      {Object.keys(pass.metrics).length > 0 && (
        <div className="flex flex-wrap gap-1 pt-1 border-t border-white/[0.06]">
          {Object.entries(pass.metrics).map(([k, v]) => (
            <span
              key={k}
              className="px-1.5 py-0.5 rounded bg-white/[0.04] text-slate-400 text-[9.5px] font-data"
              title={k}
            >
              {k}={typeof v === 'number' ? Math.round(v * 1000) / 1000 : String(v)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function PipelineFlow({ label, trace }: { label: string; trace: PipelineTraceResult }) {
  const maxTimingS = Math.max(...trace.passes.map((p) => p.timing_s), 0.000001);
  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between">
        <h4 className="text-[11.5px] font-semibold text-slate-300">{label}</h4>
        <span className="text-[10.5px] font-data text-slate-500">
          {trace.passes.length} passes · {(trace.total_timing_s * 1000).toFixed(3)}ms total ·{' '}
          {trace.diagnostic_count} diagnostic{trace.diagnostic_count === 1 ? '' : 's'}
        </span>
      </div>
      <div className="flex items-stretch gap-2 overflow-x-auto pb-1">
        {trace.passes.map((pass, i) => (
          <React.Fragment key={`${pass.pass_name}-${pass.generation}`}>
            <PassCard pass={pass} maxTimingS={maxTimingS} />
            {i < trace.passes.length - 1 && (
              <div className="flex items-center shrink-0">
                <ArrowRight className="w-4 h-4 text-slate-700" />
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

/**
 * The compile pipeline made visible: real per-pass timing/modification/diagnostic
 * data from `/api/compile?explain_passes=1` (`ir/pass_manager.py`,
 * `optimize/pass_manager.py`), rendered as a real flow instead of a text feed.
 * Nothing here is estimated -- every bar width, badge, and metric chip is the
 * exact value the PassManager itself measured.
 */
export const PipelineTraceView: React.FC<{
  pipeline?: PipelineTraceResult;
  skillPipeline?: PipelineTraceResult;
}> = ({ pipeline, skillPipeline }) => {
  if (!pipeline && !skillPipeline) return null;
  return (
    <div className="app-card p-5 space-y-5">
      {skillPipeline && skillPipeline.passes.length > 0 && (
        <PipelineFlow label="Optimization Pipeline (CompiledSkill)" trace={skillPipeline} />
      )}
      {pipeline && pipeline.passes.length > 0 && (
        <PipelineFlow label="RoboIR Pipeline" trace={pipeline} />
      )}
    </div>
  );
};
