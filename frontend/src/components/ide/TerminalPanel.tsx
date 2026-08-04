'use client';

import React, { useRef, useState } from 'react';
import { ChevronDown, ChevronUp, GripHorizontal, Play, Scale, Gauge, Trash2 } from 'lucide-react';
import { RoboWeaverAPI } from '../../lib/api';
import { CompilationFailedError, RobotProfile } from '../../types';

type Severity = 'error' | 'warning' | 'info' | 'success';

interface TerminalLine {
  text: string;
  severity: Severity;
}

interface TerminalEntry {
  id: string;
  label: string;
  lines: TerminalLine[];
}

const SEVERITY_CLASS: Record<Severity, string> = {
  error: 'text-rose-400',
  warning: 'text-amber-300',
  info: 'text-slate-400',
  success: 'text-emerald-400',
};

const MIN_HEIGHT = 32;
const DEFAULT_HEIGHT = 240;
const MAX_HEIGHT = 560;

/**
 * A live structured-output viewer, NOT an interactive shell: there is no PTY,
 * no arbitrary command execution, no stdin. The three buttons below each
 * trigger one real backend call (`/api/compile?explain_passes=1`,
 * `/api/compare`, `/api/benchmark` -- dashboard API extensions, gap-fix item
 * 3) and render its real response as a monospace, severity-colored feed.
 * Nothing here is a simulated terminal session.
 */
interface TerminalPanelProps {
  robots: RobotProfile[];
  robot: string;
  onRobotChange: (robot: string) => void;
}

export const TerminalPanel: React.FC<TerminalPanelProps> = ({ robots, robot, onRobotChange }) => {
  const [collapsed, setCollapsed] = useState(true);
  const [height, setHeight] = useState(DEFAULT_HEIGHT);
  const [entries, setEntries] = useState<TerminalEntry[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [instruction, setInstruction] = useState('Pick up the red cube');
  const dragState = useRef<{ startY: number; startHeight: number } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const pushEntry = (entry: TerminalEntry) => {
    setEntries((prev) => [...prev, entry].slice(-30));
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    });
  };

  const runCompileTrace = async () => {
    setBusy('compile');
    try {
      const res = await RoboWeaverAPI.compile(instruction, robot, true);
      const lines: TerminalLine[] = [];
      for (const trace of [res.pipeline, res.skill_pipeline]) {
        if (!trace) continue;
        for (const pass of trace.passes) {
          lines.push({
            text: `[gen ${pass.generation}] ${pass.pass_name} — modified=${pass.modified} skipped=${pass.skipped} ${pass.timing_s.toFixed(6)}s`,
            severity: 'info',
          });
          for (const d of pass.diagnostics) {
            lines.push({ text: `  ${d.code} ${d.message}`, severity: d.severity === 'error' ? 'error' : 'warning' });
          }
        }
      }
      for (const d of res.diagnostics) {
        lines.push({ text: `${d.code} ${d.message}`, severity: d.severity === 'error' ? 'error' : 'warning' });
      }
      if (lines.length === 0) lines.push({ text: 'No pass records — backend did not return a trace.', severity: 'warning' });
      lines.push({ text: `compiled clean for ${robot}.`, severity: 'success' });
      pushEntry({ id: crypto.randomUUID(), label: `compile --explain-passes "${instruction}" --robot ${robot}`, lines });
    } catch (e) {
      const lines: TerminalLine[] =
        e instanceof CompilationFailedError
          ? e.diagnostics.map((d) => ({ text: `${d.code} ${d.message}`, severity: 'error' as Severity }))
          : [{ text: String(e instanceof Error ? e.message : e), severity: 'error' }];
      pushEntry({ id: crypto.randomUUID(), label: `compile --explain-passes "${instruction}" --robot ${robot}`, lines });
    } finally {
      setBusy(null);
    }
  };

  const runCompare = async () => {
    const ids = robots.slice(0, 6).map((r) => r.id);
    if (ids.length < 2) return;
    setBusy('compare');
    try {
      const res = await RoboWeaverAPI.compare(instruction, ids);
      const lines: TerminalLine[] = res.ranked.map((entry, i) => ({
        text: `#${i + 1} ${entry.robot} — score=${entry.score.toFixed(4)} cycle=${entry.cost.estimated_cycle_time_s}s manip_margin=${entry.cost.manipulability_margin}${res.pareto_optimal.includes(entry.robot) ? ' [pareto-optimal]' : ''}`,
        severity: res.pareto_optimal.includes(entry.robot) ? 'success' : 'info',
      }));
      for (const [id, reason] of Object.entries(res.skipped)) {
        lines.push({ text: `${id}: skipped — ${reason}`, severity: 'warning' });
      }
      pushEntry({ id: crypto.randomUUID(), label: `compare --instruction "${instruction}" --robots ${ids.join(',')}`, lines });
    } catch (e) {
      pushEntry({
        id: crypto.randomUUID(),
        label: `compare --instruction "${instruction}"`,
        lines: [{ text: String(e instanceof Error ? e.message : e), severity: 'error' }],
      });
    } finally {
      setBusy(null);
    }
  };

  const runBenchmark = async () => {
    setBusy('benchmark');
    try {
      const res = await RoboWeaverAPI.benchmark();
      const lines: TerminalLine[] = [
        { text: res.scope, severity: 'info' },
        { text: `${res.success_count}/${res.total_cells} cells compiled clean in ${res.total_compile_time_s}s`, severity: 'success' },
      ];
      for (const cell of res.cells) {
        if (!cell.success) {
          lines.push({ text: `FAIL ${cell.category} x ${cell.robot_id} — ${cell.failure_reason}`, severity: 'error' });
        }
      }
      pushEntry({ id: crypto.randomUUID(), label: 'benchmark', lines });
    } catch (e) {
      pushEntry({
        id: crypto.randomUUID(),
        label: 'benchmark',
        lines: [{ text: String(e instanceof Error ? e.message : e), severity: 'error' }],
      });
    } finally {
      setBusy(null);
    }
  };

  const onDragStart = (e: React.MouseEvent) => {
    dragState.current = { startY: e.clientY, startHeight: height };
    const onMove = (ev: MouseEvent) => {
      if (!dragState.current) return;
      const delta = dragState.current.startY - ev.clientY;
      setHeight(Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, dragState.current.startHeight + delta)));
    };
    const onUp = () => {
      dragState.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  return (
    <div
      className="shrink-0 border-t border-cyan-400/[0.08] bg-[#050810]/90 backdrop-blur-xl flex flex-col"
      style={{ height: collapsed ? MIN_HEIGHT : height }}
    >
      <div
        onMouseDown={collapsed ? undefined : onDragStart}
        className={`h-2 shrink-0 flex items-center justify-center ${collapsed ? '' : 'cursor-row-resize'}`}
      >
        {!collapsed && <GripHorizontal className="w-3.5 h-3.5 text-slate-700" />}
      </div>

      <div className="h-8 shrink-0 flex items-center gap-2 px-3 border-b border-white/[0.05]">
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="flex items-center gap-1.5 text-[11px] font-bold tracking-[0.14em] text-slate-400 hover:text-slate-200 uppercase"
        >
          {collapsed ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          Terminal
        </button>

        {!collapsed && (
          <>
            <div className="flex-1" />
            <input
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="instruction"
              className="app-well rounded px-2 py-1 text-[11.5px] font-data text-slate-300 placeholder-slate-600 w-56 focus:outline-none focus:border-cyan-400/40"
            />
            <select
              value={robot}
              onChange={(e) => onRobotChange(e.target.value)}
              className="app-well rounded px-2 py-1 text-[11.5px] font-data text-slate-300 focus:outline-none"
            >
              {(robots.length ? robots.map((r) => r.id) : [robot]).map((id) => (
                <option key={id} value={id}>{id}</option>
              ))}
            </select>
            <button
              onClick={runCompileTrace}
              disabled={busy !== null}
              title="Real /api/compile?explain_passes=1 pass trace"
              className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium text-cyan-300 hover:bg-cyan-500/[0.10] disabled:opacity-40"
            >
              <Play className="w-3 h-3" /> compile
            </button>
            <button
              onClick={runCompare}
              disabled={busy !== null || robots.length < 2}
              title="Real /api/compare across registered robots"
              className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium text-violet-300 hover:bg-violet-500/[0.10] disabled:opacity-40"
            >
              <Scale className="w-3 h-3" /> compare
            </button>
            <button
              onClick={runBenchmark}
              disabled={busy !== null}
              title="Real /api/benchmark compile-time report"
              className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium text-emerald-300 hover:bg-emerald-500/[0.10] disabled:opacity-40"
            >
              <Gauge className="w-3 h-3" /> benchmark
            </button>
            <button
              onClick={() => setEntries([])}
              title="Clear"
              className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium text-slate-500 hover:text-slate-300 hover:bg-white/[0.05]"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </>
        )}
      </div>

      {!collapsed && (
        <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto px-3 py-2 font-data text-[12px] leading-relaxed">
          {entries.length === 0 && (
            <p className="text-slate-600">
              No output yet — run compile / compare / benchmark above for a real, structured feed from the
              compiler. This panel shows backend results, not a shell; there is no command input here.
            </p>
          )}
          {entries.map((entry) => (
            <div key={entry.id} className="mb-3">
              <div className="text-slate-500">$ roboweaver {entry.label}</div>
              {entry.lines.map((line, i) => (
                <div key={i} className={SEVERITY_CLASS[line.severity]}>{line.text}</div>
              ))}
            </div>
          ))}
          {busy && <div className="text-cyan-400 animate-pulse">running {busy}…</div>}
        </div>
      )}
    </div>
  );
};
