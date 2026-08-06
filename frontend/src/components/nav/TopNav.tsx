'use client';

import React, { useState, useEffect } from 'react';
import { Bot, ArrowRight, Brain, Loader2, Download } from 'lucide-react';
import { ViewType } from '../../types';
import { VIEW_META } from './viewMeta';
import { RoboWeaverAPI } from '../../lib/api';
import type { AIStatusResult } from '../../types';

interface TopNavProps {
  active: ViewType;
  onNavigate: (view: ViewType) => void;
  apiOnline: boolean;
}

/**
 * Pipeline-shaped primary navigation -- replaces the old Activity Bar + Explorer
 * file-tree + multi-tab strip. One active destination at a time (a stepper, not an
 * editor): Compile/Compare/Workcell/Benchmark render as a connected sequence
 * (real pipeline-adjacent stages), everything else (robots, digital twin,
 * knowledge graph, packages, connect, settings) as a plain destination list --
 * real supporting data, not a second-class "explorer" tree.
 */
export const TopNav: React.FC<TopNavProps> = ({ active, onNavigate, apiOnline }) => {
  const pipelineViews = VIEW_META.filter((v) => v.group === 'pipeline');
  const supportViews = VIEW_META.filter((v) => v.group === 'support' && v.id !== 'overview');
  const overview = VIEW_META.find((v) => v.id === 'overview')!;

  const [aiStatus, setAiStatus] = useState<AIStatusResult | null>(null);
  const [showAiDropdown, setShowAiDropdown] = useState(false);
  const [selectedFeature, setSelectedFeature] = useState('chat');
  const [pullModel, setPullModel] = useState('llama3.1:8b');
  const [aiMutationLoading, setAiMutationLoading] = useState(false);
  const [aiMutationMessage, setAiMutationMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const probe = async () => {
      try {
        const status = await RoboWeaverAPI.aiStatus();
        if (!cancelled) {
          setAiStatus(status);
          setPullModel((current) => current || status.recommendations.chat || status.default_model);
        }
      } catch {
        if (!cancelled) setAiStatus(null);
      }
    };
    probe();
    const interval = setInterval(probe, 30_000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  const ollamaAvailable = aiStatus?.available ?? false;

  const refreshAIStatus = async () => {
    setAiStatus(await RoboWeaverAPI.aiStatus());
  };

  const handleModelSelection = async (model: string) => {
    setAiMutationLoading(true);
    setAiMutationMessage(null);
    try {
      await RoboWeaverAPI.aiConfigureModel(selectedFeature, model);
      await refreshAIStatus();
      setAiMutationMessage(`${selectedFeature} now uses ${model}`);
    } catch (e) {
      setAiMutationMessage(e instanceof Error ? e.message : 'Could not change model.');
    } finally {
      setAiMutationLoading(false);
    }
  };

  const handlePullModel = async () => {
    if (!pullModel.trim()) return;
    setAiMutationLoading(true);
    setAiMutationMessage(`Pulling ${pullModel.trim()}…`);
    try {
      const result = await RoboWeaverAPI.aiPullModel(pullModel.trim());
      await refreshAIStatus();
      setAiMutationMessage(result.message ?? `Pulled ${result.model}`);
    } catch (e) {
      setAiMutationMessage(e instanceof Error ? e.message : 'Could not pull model.');
    } finally {
      setAiMutationLoading(false);
    }
  };

  return (
    <header className="shrink-0 border-b border-cyan-400/[0.08] bg-[#070b16]/85 backdrop-blur-xl">
      <div className="h-14 flex items-center gap-4 px-4">
        <button
          onClick={() => onNavigate('overview')}
          className="flex items-center gap-2.5 shrink-0"
          title="RoboWeaver Overview"
        >
          <div className="relative w-8 h-8 shrink-0 flex items-center justify-center">
            <span
              className="absolute inset-0 rounded-full animate-spin-slow"
              style={{
                background:
                  'conic-gradient(from 0deg, transparent 0deg, rgba(34,211,238,0.7) 90deg, rgba(139,92,246,0.7) 180deg, transparent 300deg)',
                WebkitMask: 'radial-gradient(circle, transparent 11px, black 12px)',
                mask: 'radial-gradient(circle, transparent 11px, black 12px)',
              }}
            />
            <span
              className="absolute inset-[3px] rounded-full bg-[#0a0f1e] border border-cyan-400/20"
              style={{ boxShadow: 'inset 0 0 8px rgba(34,211,238,0.15)' }}
            />
            <Bot className="relative w-3.5 h-3.5 text-cyan-300" />
          </div>
          <div className="hidden sm:block text-left leading-tight">
            <div className="text-[9.5px] font-bold tracking-[0.16em] kicker">SID LABS</div>
            <div className="text-[12.5px] font-semibold text-slate-100">RoboWeaver</div>
          </div>
        </button>

        <div className="w-px h-6 bg-white/[0.08] shrink-0" />

        {/* Pipeline-shaped sequence: Compile -> Compare -> Workcell -> Benchmark */}
        <nav className="flex items-center gap-1 overflow-x-auto">
          {pipelineViews.map((v, i) => {
            const Icon = v.icon;
            const isActive = active === v.id;
            return (
              <React.Fragment key={v.id}>
                <button
                  onClick={() => onNavigate(v.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12.5px] font-medium whitespace-nowrap transition-colors ${
                    isActive
                      ? 'bg-cyan-500/[0.12] text-cyan-300'
                      : 'text-slate-400 hover:text-slate-100 hover:bg-white/[0.05]'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {v.label}
                </button>
                {i < pipelineViews.length - 1 && (
                  <ArrowRight className="w-3.5 h-3.5 text-slate-700 shrink-0" />
                )}
              </React.Fragment>
            );
          })}
        </nav>

        <div className="w-px h-6 bg-white/[0.08] shrink-0" />

        <nav className="flex items-center gap-0.5 overflow-x-auto">
          <button
            onClick={() => onNavigate('overview')}
            title={overview.label}
            className={`p-2 rounded-lg transition-colors ${
              active === 'overview'
                ? 'bg-cyan-500/[0.12] text-cyan-300'
                : 'text-slate-500 hover:text-slate-200 hover:bg-white/[0.05]'
            }`}
          >
            <overview.icon className="w-4 h-4" />
          </button>
          {supportViews.map((v) => {
            const Icon = v.icon;
            const isActive = active === v.id;
            return (
              <button
                key={v.id}
                onClick={() => onNavigate(v.id)}
                title={v.label}
                className={`p-2 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-cyan-500/[0.12] text-cyan-300'
                    : 'text-slate-500 hover:text-slate-200 hover:bg-white/[0.05]'
                }`}
              >
                <Icon className="w-4 h-4" />
              </button>
            );
          })}
        </nav>

        <div className="flex-1" />

        {/* AI Status Indicator */}
        <div className="relative shrink-0">
          <button
            id="ai-status-indicator"
            onClick={() => setShowAiDropdown(!showAiDropdown)}
            className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11.5px] font-medium transition-colors cursor-pointer ${
              ollamaAvailable
                ? 'border-violet-400/25 text-violet-300 bg-violet-500/[0.08] hover:bg-violet-500/[0.12]'
                : 'border-slate-600/30 text-slate-500 bg-slate-500/[0.05] hover:bg-slate-500/[0.08]'
            }`}
          >
            <Brain className="w-3 h-3" />
            <span className={ollamaAvailable ? 'status-dot-online' : 'status-dot-offline'} style={{ width: 5, height: 5 }} />
            {ollamaAvailable ? 'AI' : 'AI off'}
          </button>

          {showAiDropdown && aiStatus && (
            <div
                className="absolute top-full right-0 mt-2 w-80 rounded-xl overflow-hidden z-50"
              style={{
                background: 'rgba(10,15,30,0.95)',
                border: '1px solid rgba(34,211,238,0.12)',
                backdropFilter: 'blur(16px)',
                boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
              }}
            >
              <div className="px-3 py-2 border-b border-cyan-400/[0.06]">
                <div className="text-[11px] font-semibold text-slate-300">Ollama AI Status</div>
                <div className="text-[10px] text-slate-600">{aiStatus.host}</div>
              </div>
              <div className="px-3 py-2 space-y-1.5">
                <div className="flex justify-between text-[10.5px]">
                  <span className="text-slate-500">Status</span>
                  <span className={ollamaAvailable ? 'text-emerald-400' : 'text-rose-400'}>
                    {ollamaAvailable ? 'Connected' : 'Offline'}
                  </span>
                </div>
                {aiStatus.version && (
                  <div className="flex justify-between text-[10.5px]">
                    <span className="text-slate-500">Version</span>
                    <span className="text-slate-300">{aiStatus.version}</span>
                  </div>
                )}
                <div className="flex justify-between text-[10.5px]">
                  <span className="text-slate-500">Default model</span>
                  <span className="text-slate-300 font-mono text-[10px]">{aiStatus.default_model}</span>
                </div>
                <div className="flex justify-between text-[10.5px]">
                  <span className="text-slate-500">Pulled models</span>
                  <span className="text-slate-300">{aiStatus.models.length}</span>
                </div>
                {aiStatus.total_calls > 0 && (
                  <>
                    <div className="flex justify-between text-[10.5px]">
                      <span className="text-slate-500">Total calls</span>
                      <span className="text-slate-300">{aiStatus.total_calls}</span>
                    </div>
                    {aiStatus.avg_latency_s != null && (
                      <div className="flex justify-between text-[10.5px]">
                        <span className="text-slate-500">Avg latency</span>
                        <span className="text-slate-300">{(aiStatus.avg_latency_s * 1000).toFixed(0)}ms</span>
                      </div>
                    )}
                  </>
                )}
                {aiStatus.models.length > 0 && (
                  <div className="pt-1 border-t border-white/[0.04]">
                    <div className="text-[9.5px] text-slate-600 mb-1">Available models</div>
                    {aiStatus.models.map((m) => (
                      <div key={m.name} className="flex justify-between text-[10px] py-0.5">
                        <span className="text-slate-400 font-mono">{m.name}</span>
                        <span className="text-slate-600">{m.parameter_size || formatBytes(m.size_bytes)}</span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="pt-2 mt-1 border-t border-white/[0.05] space-y-2">
                  <div className="text-[9.5px] uppercase tracking-wide text-slate-600">Feature assignment</div>
                  <div className="grid grid-cols-2 gap-1.5">
                    <select
                      value={selectedFeature}
                      onChange={(e) => setSelectedFeature(e.target.value)}
                      className="app-well rounded-md px-2 py-1.5 text-[10px] text-slate-300 outline-none"
                    >
                      {Object.keys(aiStatus.feature_models).map((feature) => (
                        <option key={feature} value={feature}>{feature}</option>
                      ))}
                    </select>
                    <select
                      value={aiStatus.feature_models[selectedFeature] ?? ''}
                      onChange={(e) => handleModelSelection(e.target.value)}
                      disabled={!ollamaAvailable || aiStatus.models.length === 0 || aiMutationLoading}
                      className="app-well rounded-md px-2 py-1.5 text-[10px] text-slate-300 outline-none disabled:opacity-50"
                    >
                      {aiStatus.models.length === 0 && <option value="">No pulled models</option>}
                      {aiStatus.feature_models[selectedFeature] && !aiStatus.models.some(
                        (model) => model.name === aiStatus.feature_models[selectedFeature]
                      ) && (
                        <option value={aiStatus.feature_models[selectedFeature]} disabled>
                          {aiStatus.feature_models[selectedFeature]} (not pulled)
                        </option>
                      )}
                      {aiStatus.models.map((model) => (
                        <option key={model.name} value={model.name}>{model.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="text-[9.5px] text-slate-600">
                    Recommended: <span className="font-data text-violet-300/70">{aiStatus.recommendations[selectedFeature]}</span>
                  </div>
                </div>
                <div className="pt-2 border-t border-white/[0.05] space-y-1.5">
                  <div className="text-[9.5px] uppercase tracking-wide text-slate-600">Pull a local model</div>
                  <div className="flex gap-1.5">
                    <input
                      value={pullModel}
                      onChange={(e) => setPullModel(e.target.value)}
                      placeholder="llama3.2:3b"
                      className="min-w-0 flex-1 app-well rounded-md px-2 py-1.5 font-data text-[10px] text-slate-300 outline-none"
                    />
                    <button
                      onClick={handlePullModel}
                      disabled={!pullModel.trim() || aiMutationLoading || !ollamaAvailable}
                      className="p-1.5 rounded-md border border-violet-400/20 bg-violet-500/[0.08] text-violet-300 disabled:opacity-40"
                      title="Pull with local Ollama"
                    >
                      {aiMutationLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                  {aiMutationMessage && <p className="text-[9.5px] text-slate-500 leading-relaxed">{aiMutationMessage}</p>}
                </div>
              </div>
            </div>
          )}
        </div>

        <div
          className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11.5px] font-medium shrink-0 ${
            apiOnline
              ? 'border-cyan-400/25 text-cyan-300 bg-cyan-500/[0.08]'
              : 'border-rose-500/30 text-rose-300 bg-rose-500/[0.08]'
          }`}
        >
          <span className={apiOnline ? 'status-dot-online' : 'status-dot-offline'} style={{ width: 6, height: 6 }} />
          {apiOnline ? 'Engine connected' : 'Engine offline'}
        </div>
      </div>
    </header>
  );
};

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}
