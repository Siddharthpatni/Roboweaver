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
import { PipelineTraceView } from './PipelineTraceView';

const EXAMPLES = [
  'Pick the red cube and place it into the blue bin',
  'Tighten the M8 bolt',
  'Pick up the heavy gear assembly',
];

/** The four real pipeline stages a compile request runs through server-side. */
const PIPELINE_STAGES = ['Parse intent', 'RoboIR + checks', 'N-DOF motion plan', 'BehaviorTree'];

/**
 * Pipeline indicator. A compile is a single round-trip with no intermediate
 * progress events, so while it is in flight every stage is shown as "in
 * flight" (shimmer) rather than inventing per-stage completion. Stages only
 * resolve to complete once a result comes back and actually proves they ran.
 */
function PipelineSteps({ state }: { state: 'idle' | 'running' | 'done' }) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {PIPELINE_STAGES.map((stage, i) => (
        <React.Fragment key={stage}>
          {i > 0 && <span className="text-slate-700 text-[10px]">→</span>}
          <span
            className={`px-2 py-1 rounded-md text-[10.5px] font-data border transition-colors ${
              state === 'done'
                ? 'border-cyan-400/25 bg-cyan-500/[0.08] text-cyan-300'
                : state === 'running'
                ? 'border-cyan-400/20 text-cyan-200/80 animate-shimmer'
                : 'border-white/[0.06] text-slate-600'
            }`}
          >
            {state === 'done' ? '✓ ' : ''}
            {stage}
          </span>
        </React.Fragment>
      ))}
    </div>
  );
}

/**
 * Minimal XML syntax colouring. Tokenises into tags/attributes/values and
 * renders real React nodes — never dangerouslySetInnerHTML, since this string
 * comes back over the wire from the compiler.
 */
function renderAttrs(attrs: string, keyBase: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const re = /([\w:.-]+)(=)("[^"]*"|'[^']*')|(\s+)|(\S+)/g;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(attrs)) !== null) {
    if (m[1]) {
      nodes.push(
        <span key={`${keyBase}-n${i}`} className="text-cyan-300">
          {m[1]}
        </span>,
        <span key={`${keyBase}-e${i}`} className="text-slate-500">
          {m[2]}
        </span>,
        <span key={`${keyBase}-v${i}`} className="text-amber-200/90">
          {m[3]}
        </span>
      );
    } else if (m[4]) {
      nodes.push(<span key={`${keyBase}-w${i}`}>{m[4]}</span>);
    } else if (m[5]) {
      nodes.push(
        <span key={`${keyBase}-o${i}`} className="text-slate-400">
          {m[5]}
        </span>
      );
    }
    i += 1;
  }
  return nodes;
}

function XmlHighlight({ xml }: { xml: string }) {
  const parts = xml.split(/(<[^>]*>)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (!part) return null;
        if (!part.startsWith('<')) {
          return (
            <span key={i} className="text-slate-400">
              {part}
            </span>
          );
        }
        if (part.startsWith('<!--')) {
          return (
            <span key={i} className="text-slate-600 italic">
              {part}
            </span>
          );
        }
        if (part.startsWith('<?')) {
          return (
            <span key={i} className="text-violet-400">
              {part}
            </span>
          );
        }
        const m = /^(<\/?)([\w:.-]+)([\s\S]*?)(\/?>)$/.exec(part);
        if (!m) {
          return (
            <span key={i} className="text-slate-400">
              {part}
            </span>
          );
        }
        return (
          <span key={i}>
            <span className="text-slate-600">{m[1]}</span>
            <span className="text-violet-300 font-medium">{m[2]}</span>
            {renderAttrs(m[3], String(i))}
            <span className="text-slate-600">{m[4]}</span>
          </span>
        );
      })}
    </>
  );
}

function DiagnosticCard({ d }: { d: CompilerDiagnostic }) {
  const isError = d.severity === 'error';
  return (
    <div
      className={`rounded-lg border p-3.5 space-y-2 animate-fade-in-up ${
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

  const handleCompile = async () => {
    if (!instruction.trim()) return;
    setLoading(true);
    setError(null);
    setBlockingDiagnostics(null);
    setResult(null);
    try {
      const data = await RoboWeaverAPI.compile(instruction, robotId, true);
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

  useEffect(() => {
    RoboWeaverAPI.robots()
      .then(setRobots)
      .catch(() => {});
    // Compiles the default example immediately so the tab opens on a real,
    // populated result instead of an empty console -- the same compile a
    // user would trigger manually, just run once up front.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    handleCompile();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
          {/* Terminal-style instruction editor */}
          <div className="app-well rounded-lg overflow-hidden transition-all duration-300 focus-within:shadow-[0_0_0_3px_rgba(34,211,238,0.07),0_0_22px_-6px_rgba(34,211,238,0.45)]">
            <div className="flex items-center gap-2 px-3 py-1.5 border-b border-cyan-400/[0.07] bg-black/20">
              <span className="w-2 h-2 rounded-full bg-rose-500/50" />
              <span className="w-2 h-2 rounded-full bg-amber-400/50" />
              <span className="w-2 h-2 rounded-full bg-cyan-400/50" />
              <span className="ml-1 text-[10.5px] font-data text-slate-600">instruction</span>
            </div>
            <div className="flex items-start gap-2 px-3.5 py-3">
              <span className="font-data text-[13px] text-cyan-400 select-none shrink-0 leading-relaxed">
                ›
              </span>
              <textarea
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                rows={2}
                placeholder='e.g. "Pick the red cube and place it into the blue bin"'
                className="flex-1 bg-transparent font-data text-[13px] text-slate-200 placeholder-slate-600 focus:outline-none resize-none leading-relaxed"
              />
            </div>
          </div>

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
              className="flex items-center gap-2 px-4 py-2 btn-neon disabled:opacity-50 text-[13px]"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
              {loading ? 'Compiling…' : 'Compile'}
            </button>
          </div>

          <div className="pt-1 border-t border-cyan-400/[0.07]">
            <div className="pt-3">
              <PipelineSteps state={loading ? 'running' : result ? 'done' : 'idle'} />
            </div>
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
            <div
              className="app-card p-5 flex items-center justify-between gap-3 flex-wrap"
              style={{
                borderColor: 'rgba(34,211,238,0.3)',
                boxShadow: '0 0 22px -8px rgba(34,211,238,0.5)',
              }}
            >
              <div className="flex items-center gap-1.5 text-cyan-400">
                <CheckCircle2 className="w-4 h-4" />
                <span className="text-[12.5px] font-medium">Compiled successfully</span>
              </div>
              <span className="font-data text-[11.5px] text-slate-500">{result.ir.skill.id}</span>
            </div>

            <PipelineTraceView pipeline={result.pipeline} skillPipeline={result.skill_pipeline} />

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
                    <span className="font-data text-[11px] text-cyan-400 shrink-0">{t.type}</span>
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
              <pre className="p-5 text-[11.5px] leading-relaxed font-data overflow-x-auto max-h-80 overflow-y-auto bg-black/30">
<XmlHighlight xml={result.behavior_tree_xml} />
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
