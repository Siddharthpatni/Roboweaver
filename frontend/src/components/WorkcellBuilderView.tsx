'use client';

import React, { useState } from 'react';
import {
  Wand2,
  ArrowDown,
  ArrowRightLeft,
  Copy,
  Check,
  Download,
  CheckCircle2,
  Loader2,
  AlertTriangle,
  Layers,
  Code2,
} from 'lucide-react';
import { RoboWeaverAPI } from '../lib/api';
import { EXAMPLE_BUILD_PROMPTS } from '../data/examplePrompts';
import { WorkcellBuildResult } from '../types';

export const WorkcellBuilderView: React.FC = () => {
  const [prompt, setPrompt] = useState(EXAMPLE_BUILD_PROMPTS[0]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<WorkcellBuildResult | null>(null);
  const [copied, setCopied] = useState(false);

  const handleBuild = async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await RoboWeaverAPI.build(prompt);
      setResult(data);
    } catch {
      setError('Could not reach the RoboWeaver backend. Start it with: roboweaver dashboard --port 8080');
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
    a.download = `composite_workcell_${result.workcell_name.toLowerCase()}.xml`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto p-8 space-y-6">
        <div>
          <span className="kicker">Workcell Builder</span>
          <h1 className="text-[19px] font-semibold text-white mt-1">Prompt-to-system compiler</h1>
          <p className="text-[13px] text-slate-400 mt-1.5 leading-relaxed max-w-2xl">
            Describe a multi-robot job in plain English. RoboWeaver parses the fleet, schedules a DAG of
            execution tiers, compiles a skill per robot embodiment, and synthesizes a Groot2 BehaviorTree —
            live, from the compiler running on the backend.
          </p>
        </div>

        {/* Prompt console */}
        <div className="app-card p-5 space-y-4">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            placeholder='e.g. "Build ShopMate-R retail assistant with Temi for navigation, Pepper for customer interaction, and Franka arm for restocking"'
            className="w-full app-well rounded-lg px-3.5 py-3 text-[13px] text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/40 resize-none transition-colors"
          />

          <div className="flex flex-wrap gap-2">
            {EXAMPLE_BUILD_PROMPTS.map((ex) => (
              <button
                key={ex}
                onClick={() => setPrompt(ex)}
                className="px-2.5 py-1 rounded-md bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.06] hover:border-white/10 text-[11.5px] text-slate-400 hover:text-slate-200 transition-colors truncate max-w-xs"
                title={ex}
              >
                {ex.length > 46 ? `${ex.slice(0, 46)}…` : ex}
              </button>
            ))}
          </div>

          <div className="flex items-center justify-between pt-1 gap-3">
            <span className="text-[11.5px] text-slate-500 truncate">
              Compiles via <code className="font-data text-slate-400">PromptToWorkcellBuilder</code>
            </span>
            <button
              onClick={handleBuild}
              disabled={loading}
              className="shrink-0 flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-[#0a0c11] text-[13px] font-semibold transition-colors"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
              {loading ? 'Compiling…' : 'Compile workcell'}
            </button>
          </div>

          {error && (
            <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg bg-rose-500/[0.07] border border-rose-500/20 text-rose-300 text-[12.5px] animate-fade-in">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>

        {/* Results */}
        {result && (
          <div className="space-y-5 animate-fade-in">
            <div className="app-card p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-1.5 text-emerald-400">
                  <CheckCircle2 className="w-4 h-4" />
                  <span className="text-[12px] font-medium">Built successfully</span>
                </div>
                <h2 className="text-[17px] font-semibold text-white mt-1">{result.workcell_name}</h2>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {result.robots.map((r) => (
                  <span
                    key={r}
                    className="px-2.5 py-1 rounded-md bg-white/[0.05] border border-white/[0.1] text-slate-300 text-[11.5px] font-medium"
                  >
                    {r}
                  </span>
                ))}
              </div>
            </div>

            {/* DAG tiers */}
            <div className="app-card p-5 space-y-4">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-slate-500" />
                <h3 className="text-[13px] font-semibold text-slate-200">
                  DAG execution schedule <span className="text-slate-500 font-normal">· {result.tiers.length} tiers</span>
                </h3>
              </div>

              <div className="space-y-2.5">
                {result.tiers.map((tier, tierIdx) => (
                  <div key={tierIdx}>
                    <div className={`grid gap-2.5 ${tier.length > 1 ? 'md:grid-cols-2 lg:grid-cols-3' : 'grid-cols-1'}`}>
                      {tier.map((step) => (
                        <div key={step.step_id} className="app-well rounded-lg p-3.5 space-y-1.5">
                          <div className="flex items-center justify-between">
                            <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 text-[10.5px] font-data">
                              {step.robot_id}
                            </span>
                            <span className="text-[10.5px] text-slate-600">Tier {tierIdx + 1}</span>
                          </div>
                          <p className="text-[12.5px] text-slate-200 leading-snug">{step.instruction}</p>
                          <div className="flex items-center justify-between text-[10.5px] text-slate-500">
                            <span>{step.action ?? '—'}</span>
                            {step.handover_target && (
                              <span className="flex items-center gap-1 text-violet-400">
                                <ArrowRightLeft className="w-3 h-3" />
                                {step.handover_target}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                    {tierIdx < result.tiers.length - 1 && (
                      <div className="flex justify-center py-1">
                        <ArrowDown className="w-3.5 h-3.5 text-slate-700" />
                      </div>
                    )}
                  </div>
                ))}
              </div>
              {result.tiers.some((t) => t.length > 1) && (
                <p className="text-[11px] text-violet-400/80 pt-2 border-t border-white/[0.06]">
                  Steps sharing a tier execute in parallel across robot namespaces.
                </p>
              )}
            </div>

            {/* BT XML */}
            <div className="app-card overflow-hidden">
              <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/[0.06]">
                <div className="flex items-center gap-2">
                  <Code2 className="w-4 h-4 text-slate-500" />
                  <h3 className="text-[13px] font-semibold text-slate-200">Composite BehaviorTree XML</h3>
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
              <pre className="p-5 text-[11.5px] leading-relaxed font-data text-slate-300 overflow-x-auto max-h-96 overflow-y-auto bg-black/20">
{result.behavior_tree_xml}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
