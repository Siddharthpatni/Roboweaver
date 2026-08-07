'use client';

import React, { useEffect, useState } from 'react';
import { Gauge, Loader2, AlertTriangle, CheckCircle2, XCircle, ArrowUpDown } from 'lucide-react';
import { RoboWeaverAPI } from '../lib/api';
import { RobotProfile, BenchmarkReportResult, BenchmarkCellResult } from '../types';

type SortKey = 'category' | 'robot_id' | 'compile_time_s' | 'success';

function SortableHeader({ label, k, onSort }: { label: string; k: SortKey; onSort: (k: SortKey) => void }) {
  return (
    <th
      onClick={() => onSort(k)}
      className="px-3 py-2 text-left text-[10.5px] font-semibold text-slate-500 uppercase tracking-wide cursor-pointer select-none hover:text-slate-300"
    >
      <span className="flex items-center gap-1">
        {label}
        <ArrowUpDown className="w-3 h-3" />
      </span>
    </th>
  );
}

/**
 * RoboBench (benchmark/robobench.py) as a real sortable table -- every distinct
 * registered robot x every NL-reachable skill category, real compile-time
 * measurement. Explicitly not simulator-execution benchmarking; the report's own
 * `scope` string says so and is rendered verbatim, not paraphrased.
 */
export const BenchmarkView: React.FC = () => {
  const [robots, setRobots] = useState<RobotProfile[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<BenchmarkReportResult | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('robot_id');
  const [sortAsc, setSortAsc] = useState(true);

  useEffect(() => {
    RoboWeaverAPI.robots()
      .then(setRobots)
      .catch(() => {});
  }, []);

  const run = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const robotIds = Array.from(selected);
      const data = await RoboWeaverAPI.benchmark(robotIds.length ? robotIds : undefined);
      setReport(data);
    } catch {
      setError('Could not reach the RoboWeaver backend. Start it with: roboweaver dashboard --port 8080');
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleRobot = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const sortBy = (key: SortKey) => {
    if (sortKey === key) setSortAsc((a) => !a);
    else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const sortedCells: BenchmarkCellResult[] = report
    ? [...report.cells].sort((a, b) => {
        let cmp = 0;
        if (sortKey === 'category') cmp = a.category.localeCompare(b.category);
        else if (sortKey === 'robot_id') cmp = a.robot_id.localeCompare(b.robot_id);
        else if (sortKey === 'compile_time_s') cmp = a.compile_time_s - b.compile_time_s;
        else if (sortKey === 'success') cmp = Number(a.success) - Number(b.success);
        return sortAsc ? cmp : -cmp;
      })
    : [];


  return (
    <div className="h-full overflow-y-auto">
      <div className="w-full space-y-6 px-4 py-5 sm:px-6 sm:py-7 xl:px-8">
        <div>
          <span className="kicker">Test the compiler</span>
          <h1 className="text-[19px] font-semibold text-white mt-1">Measure compile speed and success</h1>
          <p className="text-[13px] text-slate-400 mt-1.5 leading-relaxed max-w-2xl">
            Run every supported task category against the selected robots. This measures compiler
            latency and compatibility only; it does not measure physical execution or simulator speed.
          </p>
        </div>

        <div className="app-card p-5 space-y-4">
          <div className="space-y-1.5">
            <span className="text-[11px] text-slate-500 font-medium">
              Robots (default: franka_panda, ur5e, kuka_iiwa)
            </span>
            <div className="flex flex-wrap gap-1.5">
              {robots.map((r) => (
                <button
                  key={r.id}
                  onClick={() => toggleRobot(r.id)}
                  className={`px-2.5 py-1 rounded-md text-[11.5px] font-medium transition-colors ${
                    selected.has(r.id)
                      ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-400/25'
                      : 'bg-white/[0.03] text-slate-400 border border-white/[0.06] hover:text-slate-200'
                  }`}
                >
                  {r.id}
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={run}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 btn-neon disabled:opacity-50 text-[13px]"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Gauge className="w-4 h-4" />}
            {loading ? 'Running…' : 'Run benchmark'}
          </button>
          {error && (
            <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg bg-rose-500/[0.07] border border-rose-500/20 text-rose-300 text-[12.5px]">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>

        {report && (
          <div className="app-card overflow-hidden animate-fade-in">
            <div className="px-5 py-3.5 border-b border-white/[0.06] space-y-1">
              <p className="text-[11.5px] text-slate-500">{report.scope}</p>
              <p className="text-[13px] text-slate-200 font-medium">
                {report.success_count}/{report.total_cells} cells compiled clean in {report.total_compile_time_s}s
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-white/[0.06]">
                    <th className="px-3 py-2 text-left text-[10.5px] font-semibold text-slate-500 uppercase tracking-wide">
                      Status
                    </th>
                    <SortableHeader label="Category" k="category" onSort={sortBy} />
                    <SortableHeader label="Robot" k="robot_id" onSort={sortBy} />
                    <SortableHeader label="Compile time" k="compile_time_s" onSort={sortBy} />
                    <th className="px-3 py-2 text-left text-[10.5px] font-semibold text-slate-500 uppercase tracking-wide">
                      Diagnostics
                    </th>
                    <th className="px-3 py-2 text-left text-[10.5px] font-semibold text-slate-500 uppercase tracking-wide">
                      Waypoint reduction
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedCells.map((cell, i) => (
                    <tr key={i} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                      <td className="px-3 py-2">
                        {cell.success ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <XCircle className="w-3.5 h-3.5 text-rose-400" />
                        )}
                      </td>
                      <td className="px-3 py-2 font-data text-cyan-300">{cell.category}</td>
                      <td className="px-3 py-2 font-data text-slate-300">{cell.robot_id}</td>
                      <td className="px-3 py-2 font-data text-slate-400">{(cell.compile_time_s * 1000).toFixed(3)}ms</td>
                      <td className="px-3 py-2 text-slate-400">
                        {cell.error_count > 0 && <span className="text-rose-400">{cell.error_count} err </span>}
                        {cell.warning_count > 0 && <span className="text-amber-400">{cell.warning_count} warn</span>}
                        {cell.error_count === 0 && cell.warning_count === 0 && '—'}
                        {!cell.success && cell.failure_reason && (
                          <div className="text-[10.5px] text-rose-400/80 truncate max-w-xs" title={cell.failure_reason}>
                            {cell.failure_reason}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2 font-data text-slate-400">
                        {cell.waypoint_pct_reduction !== null ? `${cell.waypoint_pct_reduction.toFixed(1)}%` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
