'use client';

import React, { useEffect, useState } from 'react';
import { GitCompare, Wand2, Loader2, AlertTriangle, Share2, Trophy, Brain } from 'lucide-react';
import { RoboWeaverAPI } from '../lib/api';
import { RobotProfile, RobotComparisonResult, IRDiffResult, CompilationFailedError } from '../types';
import { RoboIRDiffView } from './RoboIRDiffView';

const EXAMPLES = ['Tighten the M8 bolt', 'Pick up the red cube', 'Weld the seam'];

/**
 * The godbolt.org-style "compare targets" page: one instruction, real
 * cost-ranked comparison across robots (optimize/cost_model.py::compare_robots(),
 * with the real knowledge graph supplying candidates when none are picked), plus
 * a real RoboIR diff between any two of them.
 */
export const CompareView: React.FC = () => {
  const [robots, setRobots] = useState<RobotProfile[]>([]);
  const [instruction, setInstruction] = useState(EXAMPLES[0]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RobotComparisonResult | null>(null);

  const [diffFrom, setDiffFrom] = useState('');
  const [diffTo, setDiffTo] = useState('');
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);
  const [diff, setDiff] = useState<IRDiffResult | null>(null);
  const [explainDiff, setExplainDiff] = useState(false);

  useEffect(() => {
    RoboWeaverAPI.robots()
      .then(setRobots)
      .catch(() => {});
  }, []);

  const runCompare = React.useCallback(async () => {
    if (!instruction.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const robotIds = Array.from(selected);
      const data = await RoboWeaverAPI.compare(instruction, robotIds.length ? robotIds : undefined);
      setResult(data);
      const ids = [...data.ranked.map((r) => r.robot), ...Object.keys(data.skipped)];
      if (ids.length >= 2) {
        setDiffFrom(ids[0]);
        setDiffTo(ids[1]);
      }
    } catch {
      setError('Could not reach the RoboWeaver backend. Start it with: roboweaver dashboard --port 8080');
    } finally {
      setLoading(false);
    }
  }, [instruction, selected]);

  useEffect(() => {
    // Same reasoning as CompilerView: open on a real, populated result.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    runCompare();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runDiff = async () => {
    if (!diffFrom || !diffTo || diffFrom === diffTo) return;
    setDiffLoading(true);
    setDiffError(null);
    setDiff(null);
    try {
      const data = await RoboWeaverAPI.diff(instruction, diffFrom, diffTo, explainDiff);
      setDiff(data);
    } catch (e) {
      if (e instanceof CompilationFailedError) {
        setDiffError(e.diagnostics.map((d) => `${d.code} ${d.message}`).join('; '));
      } else {
        setDiffError('Could not reach the RoboWeaver backend.');
      }
    } finally {
      setDiffLoading(false);
    }
  };

  const toggleRobot = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="w-full space-y-6 px-4 py-5 sm:px-6 sm:py-7 xl:px-8">
        <div>
          <span className="kicker">Choose a robot</span>
          <h1 className="text-[19px] font-semibold text-white mt-1">Find the best robot for this job</h1>
          <p className="text-[13px] text-slate-400 mt-1.5 leading-relaxed max-w-2xl">
            Describe the job and RoboWeaver will compile it for each candidate, reject robots that
            cannot meet the requirements, and rank the accepted options by estimated cost.
          </p>
        </div>

        <div className="app-card p-5 space-y-4">
          <textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            rows={2}
            className="w-full app-well rounded-lg px-3.5 py-3 text-[13px] text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/40 resize-none"
          />
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => setInstruction(ex)}
                className="px-2.5 py-1 rounded-md bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.06] text-[11.5px] text-slate-400 hover:text-slate-200 transition-colors"
              >
                {ex}
              </button>
            ))}
          </div>

          <div className="space-y-1.5">
            <span className="text-[11px] text-slate-500 font-medium">
              Robots to compare (leave all unchecked to use every suitable candidate)
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
            onClick={runCompare}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 btn-neon disabled:opacity-50 text-[13px]"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitCompare className="w-4 h-4" />}
            {loading ? 'Comparing…' : 'Compare'}
          </button>

          {error && (
            <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg bg-rose-500/[0.07] border border-rose-500/20 text-rose-300 text-[12.5px]">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>

        {result && (
          <div className="app-card p-5 space-y-3 animate-fade-in">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Trophy className="w-4 h-4 text-slate-500" />
                <h3 className="text-[13px] font-semibold text-slate-200">Ranking</h3>
              </div>
              <span
                className={`text-[10.5px] font-data px-2 py-0.5 rounded-full ${
                  result.candidate_source === 'knowledge_graph'
                    ? 'bg-violet-500/10 text-violet-300 border border-violet-400/20'
                    : 'bg-white/[0.04] text-slate-500'
                }`}
                title={
                  result.candidate_source === 'knowledge_graph'
                    ? 'Candidates came from the real knowledge graph, not an explicit choice'
                    : 'Explicit robot selection'
                }
              >
                {result.candidate_source === 'knowledge_graph' ? (
                  <span className="flex items-center gap-1">
                    <Share2 className="w-3 h-3" /> graph-derived
                  </span>
                ) : (
                  'explicit'
                )}
              </span>
            </div>
            <div className="space-y-1.5">
              {result.ranked.map((entry, i) => (
                <div key={entry.robot} className="app-well rounded-lg px-3.5 py-2.5 flex items-center gap-3">
                  <span className="font-data text-[10.5px] text-slate-600 w-4">{i + 1}</span>
                  <span className="font-data text-[12.5px] text-slate-200 flex-1">{entry.robot}</span>
                  {result.pareto_optimal.includes(entry.robot) && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300">pareto</span>
                  )}
                  <span className="font-data text-[11px] text-slate-500">score {entry.score.toFixed(3)}</span>
                  <span className="font-data text-[11px] text-slate-500">
                    {entry.cost.estimated_cycle_time_s.toFixed(2)}s
                  </span>
                </div>
              ))}
              {Object.entries(result.skipped).map(([rid, reason]) => (
                <div key={rid} className="app-well rounded-lg px-3.5 py-2.5 flex items-center gap-3 opacity-60">
                  <span className="font-data text-[12.5px] text-slate-400 flex-1">{rid}</span>
                  <span className="text-[11px] text-amber-400 truncate max-w-xs" title={reason}>
                    skipped — {reason}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {result && (result.ranked.length + Object.keys(result.skipped).length) >= 2 && (
          <div className="app-card p-5 space-y-3">
            <div className="flex items-center gap-2">
              <Wand2 className="w-4 h-4 text-slate-500" />
              <h3 className="text-[13px] font-semibold text-slate-200">Diff two of them</h3>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <select
                value={diffFrom}
                onChange={(e) => setDiffFrom(e.target.value)}
                className="app-well rounded-lg px-3 py-1.5 text-[12px] text-slate-200 focus:outline-none"
              >
                {[...result.ranked.map((r) => r.robot), ...Object.keys(result.skipped)].map((id) => (
                  <option key={id} value={id}>{id}</option>
                ))}
              </select>
              <span className="text-slate-600">→</span>
              <select
                value={diffTo}
                onChange={(e) => setDiffTo(e.target.value)}
                className="app-well rounded-lg px-3 py-1.5 text-[12px] text-slate-200 focus:outline-none"
              >
                {[...result.ranked.map((r) => r.robot), ...Object.keys(result.skipped)].map((id) => (
                  <option key={id} value={id}>{id}</option>
                ))}
              </select>
              <button
                onClick={runDiff}
                disabled={diffLoading || diffFrom === diffTo}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-500/10 hover:bg-violet-500/15 border border-violet-500/20 text-violet-300 text-[12px] font-medium disabled:opacity-40"
              >
                {diffLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <GitCompare className="w-3.5 h-3.5" />}
                Diff
              </button>
              <button
                type="button"
                onClick={() => setExplainDiff((v) => !v)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[12px] ${
                  explainDiff
                    ? 'border-violet-400/30 bg-violet-500/10 text-violet-300'
                    : 'border-white/[0.08] bg-white/[0.03] text-slate-500'
                }`}
              >
                <Brain className="w-3.5 h-3.5" /> AI summary {explainDiff ? 'on' : 'off'}
              </button>
            </div>
            {diffError && <p className="text-[12px] text-rose-300">{diffError}</p>}
          </div>
        )}

        {diff && <RoboIRDiffView diff={diff} />}
        {diff && (diff.explanation !== undefined || diff.explanation_error) && (
          <div className="app-card p-5 border-violet-400/20 space-y-2">
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-violet-300" />
              <h3 className="text-[13px] font-semibold text-slate-200">AI cross-robot summary</h3>
              {diff.explanation_model && <span className="font-data text-[10px] text-slate-600">{diff.explanation_model}</span>}
            </div>
            {diff.explanation ? (
              <p className="text-[12.5px] text-slate-300 whitespace-pre-wrap leading-relaxed">{diff.explanation}</p>
            ) : (
              <p className="text-[12px] text-amber-300">{diff.explanation_error ?? 'No AI summary returned.'}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
