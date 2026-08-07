'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Box,
  CheckCircle2,
  Clock3,
  Cloud,
  Copy,
  Database,
  Download,
  FlaskConical,
  HardDrive,
  Loader2,
  Network,
  Play,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { RoboWeaverAPI } from '../lib/api';
import type { ExperimentPlanResult, ObservabilityResult, ResearchEvaluationResult, ResearchStatusResult } from '../types';
import { ResearchMorphologyViewport } from './ResearchMorphologyViewport';

const EXAMPLES = [
  'Design a climbing monkey robot that learns stable hand-over-hand motion',
  'Create a compact inspection crawler for narrow industrial pipes',
  'Design a six-legged research robot for uneven warehouse terrain',
];

function downloadText(filename: string, value: string) {
  const url = URL.createObjectURL(new Blob([value], { type: 'text/plain;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.025] p-3.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-600">{label}</p>
      <p className="mt-1.5 font-data text-lg font-semibold text-white">{value}</p>
      <p className="mt-1 text-[10.5px] leading-4 text-slate-500">{detail}</p>
    </div>
  );
}

export function ResearchLabView() {
  const [objective, setObjective] = useState(EXAMPLES[0]);
  const [useAI, setUseAI] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<ResearchStatusResult | null>(null);
  const [observability, setObservability] = useState<ObservabilityResult | null>(null);
  const [result, setResult] = useState<ExperimentPlanResult | null>(null);
  const [artifact, setArtifact] = useState('experiment.json');
  const [evaluation, setEvaluation] = useState<ResearchEvaluationResult | null>(null);
  const [evaluationLoading, setEvaluationLoading] = useState(false);

  const refresh = async () => {
    const [nextStatus, nextObservability] = await Promise.allSettled([
      RoboWeaverAPI.researchStatus(), RoboWeaverAPI.observability(),
    ]);
    if (nextStatus.status === 'fulfilled') setStatus(nextStatus.value);
    if (nextObservability.status === 'fulfilled') setObservability(nextObservability.value);
  };

  useEffect(() => {
    let active = true;
    void Promise.allSettled([RoboWeaverAPI.researchStatus(), RoboWeaverAPI.observability()])
      .then(([nextStatus, nextObservability]) => {
        if (!active) return;
        if (nextStatus.status === 'fulfilled') setStatus(nextStatus.value);
        if (nextObservability.status === 'fulfilled') setObservability(nextObservability.value);
      });
    return () => { active = false; };
  }, []);

  const plan = async () => {
    if (!objective.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const next = await RoboWeaverAPI.planExperiment(objective.trim(), useAI);
      setResult(next);
      setArtifact('experiment.json');
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Experiment planning failed.');
    } finally {
      setLoading(false);
    }
  };

  const runEvaluation = async () => {
    setEvaluationLoading(true);
    setError(null);
    try {
      setEvaluation(await RoboWeaverAPI.researchEvaluation());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Research evaluation failed.');
    } finally {
      setEvaluationLoading(false);
    }
  };

  const providerRows = useMemo(() => status ? Object.entries(status.providers) : [], [status]);
  const totals = observability?.traces.totals;
  const currentArtifact = result?.artifacts[artifact] ?? '';

  return (
    <div className="h-full overflow-y-auto">
      <div className="w-full space-y-5 px-4 py-5 sm:px-6 sm:py-7 xl:px-8">
        <section className="app-card overflow-hidden">
          <div className="grid lg:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
            <div className="border-b border-white/[0.07] p-5 sm:p-7 lg:border-b-0 lg:border-r xl:p-8">
              <div className="flex flex-wrap items-center gap-2">
                <span className="kicker">Bounded embodiment research</span>
                <span className="rounded-full border border-emerald-300/20 bg-emerald-300/[0.06] px-2 py-1 text-[10px] font-semibold text-emerald-200">
                  no direct code execution
                </span>
              </div>
              <h2 className="mt-4 text-2xl font-semibold tracking-[-0.025em] text-white sm:text-[30px]">
                Design a new robot. Inspect exactly what AI proposed.
              </h2>
              <p className="mt-3 max-w-3xl text-[12.5px] leading-6 text-slate-400">
                The cascade tries local Ollama first, then configured cloud fallbacks. RoboWeaver accepts only a bounded morphology schema and deterministically emits the URDF and training scaffold.
              </p>
              <textarea
                value={objective}
                onChange={(event) => setObjective(event.target.value)}
                maxLength={1000}
                className="app-well mt-5 min-h-32 w-full resize-y rounded-xl px-4 py-3 text-[13px] leading-6 text-slate-100 outline-none focus:border-cyan-300/30"
                placeholder="Describe a research robot and the behavior it should learn…"
              />
              <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <label className="flex cursor-pointer items-center gap-2.5 text-[11.5px] text-slate-400">
                  <input type="checkbox" checked={useAI} onChange={(event) => setUseAI(event.target.checked)} className="h-4 w-4 accent-cyan-400" />
                  Use bounded AI cascade; deterministic fallback remains available
                </label>
                <button onClick={plan} disabled={loading || !objective.trim()} className="btn-neon flex items-center justify-center gap-2 px-4 py-2.5 text-[12px] disabled:opacity-50">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  {loading ? 'Designing and validating…' : 'Plan isolated experiment'}
                </button>
              </div>
              <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
                {EXAMPLES.map((example, index) => (
                  <button key={example} onClick={() => setObjective(example)} className="shrink-0 rounded-lg border border-white/[0.08] bg-white/[0.025] px-3 py-2 text-[10.5px] text-slate-400 hover:border-cyan-300/20 hover:text-cyan-200">
                    Example {index + 1}
                  </button>
                ))}
              </div>
              {error && <div className="mt-4 flex gap-2 rounded-xl border border-rose-300/20 bg-rose-300/[0.06] p-3 text-[11.5px] text-rose-200"><AlertTriangle className="h-4 w-4 shrink-0" />{error}</div>}
            </div>

            <div className="bg-[#0a121e]/70 p-5 sm:p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[12px] font-semibold text-slate-200">Provider cascade</p>
                  <p className="mt-0.5 text-[10.5px] text-slate-600">Maximum {status?.max_attempts ?? 3} attempts</p>
                </div>
                <button onClick={() => void refresh()} className="rounded-lg border border-white/[0.08] p-2 text-slate-500 hover:text-cyan-200" aria-label="Refresh provider status"><RefreshCw className="h-3.5 w-3.5" /></button>
              </div>
              <div className="mt-4 space-y-2.5">
                {providerRows.map(([name, provider], index) => {
                  const ready = name === 'ollama' ? provider.available : provider.configured;
                  const Icon = name === 'ollama' ? HardDrive : Cloud;
                  return (
                    <div key={name} className="flex items-center gap-3 rounded-xl border border-white/[0.07] bg-white/[0.02] p-3">
                      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/[0.04] text-cyan-300"><Icon className="h-4 w-4" /></span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2"><span className="text-[11.5px] font-semibold capitalize text-slate-200">{index + 1}. {name}</span><span className={ready ? 'status-dot-online' : 'status-dot-offline'} /></div>
                        <p className="truncate font-data text-[9.5px] text-slate-600">{provider.experiment_model ?? provider.model}</p>
                      </div>
                      <span className="text-[9.5px] font-semibold uppercase tracking-wider text-slate-600">{ready ? 'ready' : 'skip'}</span>
                    </div>
                  );
                })}
              </div>
              <div className="mt-4 rounded-xl border border-amber-300/15 bg-amber-300/[0.045] p-3">
                <div className="flex items-center gap-2 text-[11px] font-semibold text-amber-200"><ShieldCheck className="h-4 w-4" /> Safety boundary</div>
                <p className="mt-1.5 text-[10.5px] leading-5 text-slate-500">Prompts and responses are never written to traces. Cache hits re-run schema validation. API keys stay in the backend process.</p>
              </div>
            </div>
          </div>
        </section>

        <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Metric label="Requests" value={String(totals?.requests ?? 0)} detail="Unique cascade request IDs" />
          <Metric label="Failures" value={String(totals?.failed ?? 0)} detail="Provider or validation attempts" />
          <Metric label="Cache" value={`${Math.round((observability?.traces.cache_hit_rate ?? 0) * 100)}%`} detail={`${observability?.cache.entries ?? 0} exact entries in memory`} />
          <Metric label="P95 latency" value={observability?.traces.p95_latency_s == null ? '—' : `${observability.traces.p95_latency_s.toFixed(2)}s`} detail="Across recorded provider attempts" />
        </section>

        <section className="app-card overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-white/[0.07] p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <div>
              <h3 className="text-[13px] font-semibold text-white">Reproducible compiler evaluation</h3>
              <p className="mt-0.5 text-[10.5px] text-slate-600">Real compiles, an expected failure, three-run determinism, NativeTwin execution, and O0 vs O1.</p>
            </div>
            <button onClick={runEvaluation} disabled={evaluationLoading} className="flex items-center justify-center gap-2 rounded-lg border border-cyan-300/20 bg-cyan-300/[0.06] px-3.5 py-2 text-[11px] font-semibold text-cyan-200 hover:bg-cyan-300/[0.1] disabled:opacity-50">
              {evaluationLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              {evaluationLoading ? 'Running real cases…' : 'Run research benchmark'}
            </button>
          </div>
          {evaluation ? (
            <div className="p-4 sm:p-5">
              <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
                {evaluation.metrics.map((metric) => (
                  <div key={metric.name} className={`rounded-xl border p-3 ${metric.passed ? 'border-emerald-300/15 bg-emerald-300/[0.03]' : 'border-rose-300/20 bg-rose-300/[0.04]'}`}>
                    <div className="flex items-center justify-between gap-2"><span className="text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-600">{metric.name.replaceAll('_', ' ')}</span>{metric.passed ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-300" /> : <AlertTriangle className="h-3.5 w-3.5 text-rose-300" />}</div>
                    <p className="mt-2 font-data text-[15px] font-semibold text-white">{typeof metric.value === 'number' ? metric.value.toLocaleString() : String(metric.value)}</p>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex flex-col gap-2 text-[10px] text-slate-600 sm:flex-row sm:items-center sm:justify-between"><span>{evaluation.benchmark_version} · {evaluation.passed}/{evaluation.total} metrics passed · {evaluation.elapsed_s.toFixed(3)}s</span><span>Evidence is local to this commit and machine.</span></div>
            </div>
          ) : (
            <div className="p-5 text-[10.5px] leading-5 text-slate-600">This intentionally runs more than unit tests: it compiles mobile, hand, and arm targets; checks the exact RW102 refusal; executes the modeled PICK process; and compares optimization levels.</div>
          )}
        </section>

        {result ? (
          <>
            <section className="app-card overflow-hidden">
              <div className="flex flex-col gap-3 border-b border-white/[0.07] p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-[14px] font-semibold text-white">{result.spec.name}</h3>
                    <span className="rounded-full border border-cyan-300/20 bg-cyan-300/[0.06] px-2 py-0.5 text-[9.5px] font-semibold text-cyan-200">{result.spec.embodiment_class}</span>
                    {result.cache_hit && <span className="rounded-full border border-violet-300/20 bg-violet-300/[0.06] px-2 py-0.5 text-[9.5px] text-violet-200">cache hit + revalidated</span>}
                  </div>
                  <p className="mt-1 text-[10.5px] text-slate-500">{result.provider} · {result.model} · {result.attempts} provider attempt{result.attempts === 1 ? '' : 's'}</p>
                </div>
                <div className="flex flex-wrap gap-2 text-[10px]">
                  <span className="rounded-lg border border-white/[0.08] px-2.5 py-1.5 text-slate-400">{result.spec.links.length} links</span>
                  <span className="rounded-lg border border-white/[0.08] px-2.5 py-1.5 text-slate-400">{result.spec.joints.length} joints</span>
                  <span className="rounded-lg border border-white/[0.08] px-2.5 py-1.5 text-slate-400">{result.spec.training.algorithm}</span>
                </div>
              </div>
              <div className="grid gap-4 p-4 sm:p-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
                <ResearchMorphologyViewport links={result.spec.links} joints={result.spec.joints} />
                <div className="grid content-start gap-3 sm:grid-cols-2 xl:grid-cols-1">
                  <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-slate-600">Learning contract</p>
                    <p className="mt-2 text-[12px] font-semibold text-slate-200">{result.spec.training.algorithm} · {result.spec.training.max_steps.toLocaleString()} bounded steps</p>
                    <div className="mt-3 flex flex-wrap gap-1.5">{result.spec.training.reward_terms.map((item) => <span key={item} className="rounded-md bg-cyan-300/[0.06] px-2 py-1 text-[9.5px] text-cyan-200">{item}</span>)}</div>
                  </div>
                  <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-slate-600">Sensors requested</p>
                    <div className="mt-3 flex flex-wrap gap-1.5">{result.spec.sensors.map((item) => <span key={item} className="rounded-md bg-white/[0.045] px-2 py-1 text-[9.5px] text-slate-300">{item}</span>)}</div>
                  </div>
                  <div className="rounded-xl border border-emerald-300/15 bg-emerald-300/[0.035] p-4 sm:col-span-2 xl:col-span-1">
                    <p className="flex items-center gap-2 text-[11px] font-semibold text-emerald-200"><CheckCircle2 className="h-4 w-4" /> Deterministic gates passed</p>
                    <ul className="mt-2 space-y-1.5 text-[10.5px] text-slate-500">
                      <li>Schema and connected-tree morphology validated</li>
                      <li>Generated Python parsed and checked by AST policy</li>
                      <li>No network, devices, or physical hardware authorized</li>
                    </ul>
                  </div>
                </div>
              </div>
            </section>

            <section className="app-card overflow-hidden">
              <div className="flex flex-col gap-3 border-b border-white/[0.07] p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
                <div><h3 className="text-[13px] font-semibold text-white">Generated research package</h3><p className="mt-0.5 text-[10.5px] text-slate-600">Reviewable artifacts; nothing has been deployed or trained.</p></div>
                <div className="flex flex-wrap gap-2">
                  {Object.keys(result.artifacts).map((name) => <button key={name} onClick={() => setArtifact(name)} className={`rounded-lg px-2.5 py-1.5 font-data text-[9.5px] ${artifact === name ? 'bg-cyan-300/10 text-cyan-200' : 'border border-white/[0.07] text-slate-500'}`}>{name}</button>)}
                </div>
              </div>
              <div className="relative">
                <div className="absolute right-3 top-3 z-10 flex gap-2">
                  <button onClick={() => void navigator.clipboard.writeText(currentArtifact)} className="rounded-lg border border-white/[0.08] bg-[#0a121e]/90 p-2 text-slate-400 hover:text-cyan-200" aria-label="Copy artifact"><Copy className="h-3.5 w-3.5" /></button>
                  <button onClick={() => downloadText(artifact, currentArtifact)} className="rounded-lg border border-white/[0.08] bg-[#0a121e]/90 p-2 text-slate-400 hover:text-cyan-200" aria-label="Download artifact"><Download className="h-3.5 w-3.5" /></button>
                </div>
                <pre className="max-h-[440px] overflow-auto p-4 pr-24 font-data text-[10.5px] leading-5 text-slate-400 sm:p-5">{currentArtifact}</pre>
              </div>
            </section>
          </>
        ) : (
          <section className="app-card grid min-h-56 place-items-center p-8 text-center">
            <div><FlaskConical className="mx-auto h-7 w-7 text-slate-700" /><p className="mt-3 text-[12px] font-semibold text-slate-300">No experiment planned yet</p><p className="mt-1 text-[10.5px] text-slate-600">Start with the climbing-monkey example to inspect the full safe generation path.</p></div>
          </section>
        )}

        <section className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
          <div className="app-card overflow-hidden">
            <div className="flex items-center justify-between border-b border-white/[0.07] px-4 py-3.5 sm:px-5"><div><h3 className="text-[12px] font-semibold text-white">Recent model attempts</h3><p className="mt-0.5 text-[10px] text-slate-600">Metadata only — no prompt or response bodies</p></div><Database className="h-4 w-4 text-slate-600" /></div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[680px] text-left text-[10.5px]">
                <thead className="border-b border-white/[0.06] text-[9px] uppercase tracking-wider text-slate-700"><tr><th className="px-4 py-2.5">Provider</th><th className="px-4 py-2.5">Model</th><th className="px-4 py-2.5">Attempt</th><th className="px-4 py-2.5">Status</th><th className="px-4 py-2.5">Latency</th><th className="px-4 py-2.5">Error</th></tr></thead>
                <tbody>{(observability?.traces.recent ?? []).slice(0, 8).map((trace) => <tr key={trace.trace_id} className="border-b border-white/[0.04] text-slate-500"><td className="px-4 py-3 font-semibold capitalize text-slate-300">{trace.provider}</td><td className="max-w-52 truncate px-4 py-3 font-data">{trace.actual_model}</td><td className="px-4 py-3">{trace.attempt || 'cache'}</td><td className="px-4 py-3"><span className={trace.status === 'failed' ? 'text-rose-300' : trace.status === 'cache_hit' ? 'text-violet-300' : 'text-emerald-300'}>{trace.status}</span></td><td className="px-4 py-3">{trace.latency_s.toFixed(3)}s</td><td className="max-w-64 truncate px-4 py-3 text-rose-300/70">{trace.error_message ?? '—'}</td></tr>)}</tbody>
              </table>
              {!observability?.traces.recent.length && <div className="p-6 text-center text-[10.5px] text-slate-600">Run an AI-assisted experiment to record provider attempts.</div>}
            </div>
          </div>
          <div className="app-card p-4 sm:p-5">
            <div className="flex items-center gap-2"><Box className="h-4 w-4 text-cyan-300" /><h3 className="text-[12px] font-semibold text-white">Isolation contract</h3></div>
            <div className="mt-4 space-y-2.5 text-[10.5px]">
              <div className="flex items-center justify-between rounded-lg bg-white/[0.025] px-3 py-2.5"><span className="flex items-center gap-2 text-slate-500"><Network className="h-3.5 w-3.5" /> Network</span><span className="font-data text-emerald-300">none</span></div>
              <div className="flex items-center justify-between rounded-lg bg-white/[0.025] px-3 py-2.5"><span className="flex items-center gap-2 text-slate-500"><HardDrive className="h-3.5 w-3.5" /> Root filesystem</span><span className="font-data text-emerald-300">read-only</span></div>
              <div className="flex items-center justify-between rounded-lg bg-white/[0.025] px-3 py-2.5"><span className="flex items-center gap-2 text-slate-500"><ShieldCheck className="h-3.5 w-3.5" /> Devices</span><span className="font-data text-emerald-300">none</span></div>
              <div className="flex items-center justify-between rounded-lg bg-white/[0.025] px-3 py-2.5"><span className="flex items-center gap-2 text-slate-500"><Clock3 className="h-3.5 w-3.5" /> Physics</span><span className="font-data text-amber-300">adapter required</span></div>
            </div>
            <div className="mt-4 rounded-xl border border-white/[0.07] bg-[#070d16] p-3 font-data text-[9.5px] leading-5 text-slate-500">{status?.sandbox.command ?? 'docker compose --profile research run --rm experiment-sandbox'}</div>
            <p className="mt-3 flex gap-2 text-[10px] leading-4 text-amber-200/70"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />This validates generated artifacts in isolation. It does not claim Gazebo/MuJoCo physics or runtime correctness until that adapter reports evidence.</p>
          </div>
        </section>
      </div>
    </div>
  );
}
