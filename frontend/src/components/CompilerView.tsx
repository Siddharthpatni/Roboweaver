'use client';

import React, { useEffect, useState } from 'react';
import {
  Wand2,
  Loader2,
  AlertTriangle,
  AlertOctagon,
  CheckCircle2,
  Copy,
  Check,
  Download,
  Code2,
  Layers,
  Box,
} from 'lucide-react';
import { RoboWeaverAPI } from '../lib/api';
import { RobotProfile, CompiledSkillResult, CompilerDiagnostic } from '../types';
import { CompilationFailedError } from '../types';

const EXAMPLES = [
  'Pick the red cube and place it into the blue bin',
  'Tighten the M8 bolt',
  'Pick up the heavy gear assembly',
];

function DiagnosticCard({ d }: { d: CompilerDiagnostic }) {
  const isError = d.severity === 'error';
  return (
    <div
      className={`rounded-lg border p-3.5 space-y-2 ${
        isError ? 'bg-rose-500/[0.06] border-rose-500/25' : 'bg-amber-500/[0.06] border-amber-500/20'
      }`}
    >
      <div className="flex items-center gap-2">
        {isError ? (
          <AlertOctagon className="w-4 h-4 text-rose-400 shrink-0" />
        ) : (
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
        )}
        <span className={`font-data text-[11px] font-semibold ${isError ? 'text-rose-300' : 'text-amber-300'}`}>
          {d.code}
        </span>
        <span className="text-[12.5px] text-slate-200">{d.message}</span>
      </div>
      <p className="text-[12px] text-slate-400 leading-relaxed pl-6">{d.reason}</p>
      {d.required_capability && (
        <div className="pl-6 text-[11px] font-data text-slate-500">
          required: <span className="text-slate-300">{d.required_capability}</span>
        </div>
      )}
      {d.fixes.length > 0 && (
        <ul className="pl-6 space-y-0.5">
          {d.fixes.map((fix, i) => (
            <li key={i} className="text-[11.5px] text-slate-400">
              {i + 1}. {fix}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export const CompilerView: React.FC = () => {
  const [robots, setRobots] = useState<RobotProfile[]>([]);
  const [instruction, setInstruction] = useState(EXAMPLES[0]);
  const [robotId, setRobotId] = useState('franka_panda');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CompiledSkillResult | null>(null);
  const [blockingDiagnostics, setBlockingDiagnostics] = useState<CompilerDiagnostic[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    RoboWeaverAPI.robots()
      .then(setRobots)
      .catch(() => {});
  }, []);

  const handleCompile = async () => {
    if (!instruction.trim()) return;
    setLoading(true);
    setError(null);
    setBlockingDiagnostics(null);
    setResult(null);
    try {
      const data = await RoboWeaverAPI.compile(instruction, robotId);
      setResult(data);
    } catch (e) {
      if (e instanceof CompilationFailedError) {
        setBlockingDiagnostics(e.diagnostics);
      } else {
        setError('Could not reach the RoboWeaver backend. Start it with: roboweaver dashboard --port 8080');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (!result) return;
    navigator.clipboard.writeText(result.behavior_tree_xml);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleDownload = () => {
    if (!result) return;
    const blob = new Blob([result.behavior_tree_xml], { type: 'application/xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${result.ir.skill.id}.xml`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto p-8 space-y-6">
        <div>
          <span className="kicker">Compiler</span>
          <h1 className="text-[19px] font-semibold text-white mt-1">
            Human Intent → RoboIR → Behavior Tree
          </h1>
          <p className="text-[13px] text-slate-400 mt-1.5 leading-relaxed max-w-2xl">
            Every instruction compiles through RoboIR (Stage 05) before any motion planning happens. The
            Compiler Debugger checks RoboIR&apos;s required capabilities against the target robot and fails
            loudly — never a silently wrong skill.
          </p>
        </div>

        <div className="app-card p-5 space-y-4">
          <textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            rows={2}
            placeholder='e.g. "Pick the red cube and place it into the blue bin"'
            className="w-full app-well rounded-lg px-3.5 py-3 text-[13px] text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/40 resize-none transition-colors"
          />

          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => setInstruction(ex)}
                className="px-2.5 py-1 rounded-md bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.06] hover:border-white/10 text-[11.5px] text-slate-400 hover:text-slate-200 transition-colors"
              >
                {ex}
              </button>
            ))}
          </div>

          <div className="flex items-center justify-between gap-3 flex-wrap">
            <select
              value={robotId}
              onChange={(e) => setRobotId(e.target.value)}
              className="app-well rounded-lg px-3 py-2 text-[12.5px] text-slate-200 focus:outline-none focus:border-emerald-500/40"
            >
              {robots.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} ({r.dof}-DOF)
                </option>
              ))}
            </select>
            <button
              onClick={handleCompile}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-[#0a0c11] text-[13px] font-semibold transition-colors"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
              {loading ? 'Compiling…' : 'Compile'}
            </button>
          </div>

          {error && (
            <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg bg-rose-500/[0.07] border border-rose-500/20 text-rose-300 text-[12.5px]">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>

        {blockingDiagnostics && (
          <div className="app-card p-5 space-y-3 animate-fade-in">
            <div className="flex items-center gap-2">
              <AlertOctagon className="w-4 h-4 text-rose-400" />
              <h3 className="text-[13px] font-semibold text-slate-200">Compilation failed</h3>
            </div>
            {blockingDiagnostics.map((d, i) => (
              <DiagnosticCard key={i} d={d} />
            ))}
          </div>
        )}

        {result && (
          <div className="space-y-5 animate-fade-in">
            <div className="app-card p-5 flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-1.5 text-emerald-400">
                <CheckCircle2 className="w-4 h-4" />
                <span className="text-[12.5px] font-medium">Compiled successfully</span>
              </div>
              <span className="font-data text-[11.5px] text-slate-500">{result.ir.skill.id}</span>
            </div>

            {result.diagnostics.length > 0 && (
              <div className="app-card p-5 space-y-3">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  <h3 className="text-[13px] font-semibold text-slate-200">Compiler diagnostics</h3>
                </div>
                {result.diagnostics.map((d, i) => (
                  <DiagnosticCard key={i} d={d} />
                ))}
              </div>
            )}

            {/* RoboIR */}
            <div className="app-card p-5 space-y-4">
              <div className="flex items-center gap-2">
                <Box className="w-4 h-4 text-slate-500" />
                <h3 className="text-[13px] font-semibold text-slate-200">RoboIR</h3>
                <span className="font-data text-[10.5px] text-slate-600">v{result.ir.ir_version}</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="app-well rounded-lg p-3.5 space-y-2">
                  <div className="text-[10.5px] font-medium text-slate-500">Objects</div>
                  {result.ir.objects.map((o) => (
                    <div key={o.id} className="flex items-center justify-between text-[12px]">
                      <span className="text-slate-200">{o.name}</span>
                      <span className="flex items-center gap-1.5">
                        <span className="px-1.5 py-0.5 rounded bg-white/[0.06] text-slate-300 text-[10px]">{o.role}</span>
                        {o.pose_source === 'assumed_default' && (
                          <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 text-[10px]">assumed pose</span>
                        )}
                      </span>
                    </div>
                  ))}
                </div>

                <div className="app-well rounded-lg p-3.5 space-y-2">
                  <div className="text-[10.5px] font-medium text-slate-500">Execution</div>
                  <div className="text-[12px] text-slate-300 space-y-1 font-data">
                    <div>robot: {result.ir.execution.robot_id}</div>
                    <div>dof: {result.ir.execution.dof}</div>
                    <div>planner: {result.ir.execution.planner}</div>
                    <div>controller: {result.ir.execution.controller}</div>
                  </div>
                </div>

                <div className="app-well rounded-lg p-3.5 space-y-2">
                  <div className="text-[10.5px] font-medium text-slate-500">Required capabilities</div>
                  <div className="flex flex-wrap gap-1">
                    {[...result.ir.required_capabilities.manipulation, ...result.ir.required_capabilities.perception, ...result.ir.required_capabilities.sensing].map(
                      (cap, i) => (
                        <span key={i} className="px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-300 font-data text-[10.5px]">
                          {cap}
                        </span>
                      )
                    )}
                    {result.ir.required_capabilities.manipulation.length +
                      result.ir.required_capabilities.perception.length +
                      result.ir.required_capabilities.sensing.length === 0 && (
                      <span className="text-[11px] text-slate-600">none</span>
                    )}
                  </div>
                </div>

                <div className="app-well rounded-lg p-3.5 space-y-2">
                  <div className="text-[10.5px] font-medium text-slate-500">Verification</div>
                  <div className="flex flex-wrap gap-1">
                    {result.ir.verification.safety_checks.map((c, i) => (
                      <span key={i} className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 font-data text-[10.5px]">
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Task graph */}
            <div className="app-card p-5 space-y-3">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-slate-500" />
                <h3 className="text-[13px] font-semibold text-slate-200">Task graph</h3>
              </div>
              <div className="space-y-1.5">
                {result.tasks.map((t, i) => (
                  <div key={i} className="app-well rounded-lg px-3.5 py-2 flex items-center gap-3">
                    <span className="font-data text-[10.5px] text-slate-600 shrink-0">{i + 1}</span>
                    <span className="font-data text-[11px] text-emerald-400 shrink-0">{t.type}</span>
                    <span className="text-[12px] text-slate-300 truncate">{t.description}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* BT XML */}
            <div className="app-card overflow-hidden">
              <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/[0.06]">
                <div className="flex items-center gap-2">
                  <Code2 className="w-4 h-4 text-slate-500" />
                  <h3 className="text-[13px] font-semibold text-slate-200">BehaviorTree XML</h3>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleCopy}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.06] text-[11.5px] text-slate-300 transition-colors"
                  >
                    {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    {copied ? 'Copied' : 'Copy'}
                  </button>
                  <button
                    onClick={handleDownload}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-emerald-500/10 hover:bg-emerald-500/15 border border-emerald-500/20 text-[11.5px] text-emerald-300 transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Export
                  </button>
                </div>
              </div>
              <pre className="p-5 text-[11.5px] leading-relaxed font-data text-slate-300 overflow-x-auto max-h-80 overflow-y-auto bg-black/20">
{result.behavior_tree_xml}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
