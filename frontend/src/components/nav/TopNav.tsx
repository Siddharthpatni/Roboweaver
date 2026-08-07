'use client';

import React, { useEffect, useState } from 'react';
import {
  Activity,
  Bot,
  Brain,
  ChevronRight,
  Download,
  Loader2,
  Menu,
  Settings2,
  X,
} from 'lucide-react';
import { ViewType } from '../../types';
import type { AIStatusResult } from '../../types';
import { RoboWeaverAPI } from '../../lib/api';
import { VIEW_META } from './viewMeta';

interface TopNavProps {
  active: ViewType;
  onNavigate: (view: ViewType) => void;
  apiOnline: boolean;
}

export const TopNav: React.FC<TopNavProps> = ({ active, onNavigate, apiOnline }) => {
  const pipelineViews = VIEW_META.filter((view) => view.group === 'pipeline');
  const supportViews = VIEW_META.filter(
    (view) => view.group === 'support' && view.id !== 'overview' && view.id !== 'settings'
  );
  const overview = VIEW_META.find((view) => view.id === 'overview')!;
  const settings = VIEW_META.find((view) => view.id === 'settings')!;

  const [mobileOpen, setMobileOpen] = useState(false);
  const [aiStatus, setAiStatus] = useState<AIStatusResult | null>(null);
  const [showAiPanel, setShowAiPanel] = useState(false);
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
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMobileOpen(false);
        setShowAiPanel(false);
      }
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, []);

  const ollamaAvailable = aiStatus?.available ?? false;

  const refreshAIStatus = async () => setAiStatus(await RoboWeaverAPI.aiStatus());

  const handleModelSelection = async (model: string) => {
    setAiMutationLoading(true);
    setAiMutationMessage(null);
    try {
      await RoboWeaverAPI.aiConfigureModel(selectedFeature, model);
      await refreshAIStatus();
      setAiMutationMessage(`${selectedFeature} now uses ${model}`);
    } catch (error) {
      setAiMutationMessage(error instanceof Error ? error.message : 'Could not change model.');
    } finally {
      setAiMutationLoading(false);
    }
  };

  const handlePullModel = async () => {
    const model = pullModel.trim();
    if (!model) return;
    setAiMutationLoading(true);
    setAiMutationMessage(`Pulling ${model}…`);
    try {
      const result = await RoboWeaverAPI.aiPullModel(model);
      await refreshAIStatus();
      setAiMutationMessage(result.message ?? `Pulled ${result.model}`);
    } catch (error) {
      setAiMutationMessage(error instanceof Error ? error.message : 'Could not pull model.');
    } finally {
      setAiMutationLoading(false);
    }
  };

  const navigate = (view: ViewType) => {
    setMobileOpen(false);
    onNavigate(view);
  };

  const navButton = (view: (typeof VIEW_META)[number], step?: number) => {
    const Icon = view.icon;
    const isActive = active === view.id;
    return (
      <button
        key={view.id}
        onClick={() => navigate(view.id)}
        aria-current={isActive ? 'page' : undefined}
        className={`group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
          isActive
            ? 'bg-cyan-400/[0.11] text-cyan-100 ring-1 ring-inset ring-cyan-300/15'
            : 'text-slate-400 hover:bg-white/[0.045] hover:text-slate-100'
        }`}
      >
        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
          isActive ? 'bg-cyan-300 text-slate-950' : 'bg-white/[0.045] text-slate-400 group-hover:text-slate-100'
        }`}>
          <Icon className="h-4 w-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[13px] font-semibold leading-5">{view.label}</span>
          <span className="block truncate text-[10.5px] leading-4 text-slate-500">{view.description}</span>
        </span>
        {step !== undefined ? (
          <span className="font-data text-[10px] text-slate-600">0{step}</span>
        ) : (
          <ChevronRight className={`h-3.5 w-3.5 ${isActive ? 'text-cyan-300' : 'text-slate-700'}`} />
        )}
      </button>
    );
  };

  const sidebarContent = (
    <>
      <div className="flex h-20 items-center gap-3 border-b border-white/[0.065] px-4">
        <button
          onClick={() => navigate('overview')}
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          aria-label="Open RoboWeaver overview"
        >
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-cyan-300 text-slate-950 shadow-[0_8px_24px_rgba(34,211,238,0.16)]">
            <Bot className="h-5 w-5" />
          </span>
          <span className="min-w-0">
            <span className="block text-[10px] font-bold uppercase tracking-[0.19em] text-cyan-300">Sid Labs</span>
            <span className="block truncate text-[15px] font-semibold tracking-tight text-white">RoboWeaver</span>
          </span>
        </button>
        <button
          onClick={() => setMobileOpen(false)}
          className="rounded-lg p-2 text-slate-500 hover:bg-white/[0.05] hover:text-white lg:hidden"
          aria-label="Close navigation"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4">
        <nav aria-label="RoboWeaver workspaces" className="space-y-5">
          <div>{navButton(overview)}</div>
          <div>
            <div className="mb-2 flex items-center justify-between px-3">
              <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-600">Main workflow</span>
              <span className="text-[9px] text-slate-700">4 stages</span>
            </div>
            <div className="space-y-1">{pipelineViews.map((view, index) => navButton(view, index + 1))}</div>
          </div>
          <div>
            <div className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-600">More tools</div>
            <div className="space-y-1">{supportViews.map((view) => navButton(view))}</div>
          </div>
        </nav>
      </div>

      <div className="space-y-2 border-t border-white/[0.065] p-3">
        <button
          onClick={() => setShowAiPanel((current) => !current)}
          aria-expanded={showAiPanel}
          className="flex w-full items-center gap-3 rounded-xl border border-white/[0.065] bg-white/[0.025] px-3 py-2.5 text-left hover:border-violet-300/20 hover:bg-violet-400/[0.05]"
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-400/10 text-violet-300">
            <Brain className="h-4 w-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[12px] font-semibold text-slate-200">Optional AI helper</span>
            <span className="block truncate text-[10.5px] text-slate-500">
              {ollamaAvailable ? `${aiStatus?.models.length ?? 0} models ready` : 'Ollama offline'}
            </span>
          </span>
          <span className={ollamaAvailable ? 'status-dot-online' : 'status-dot-offline'} />
        </button>

        {navButton(settings)}

        <div className="flex items-center gap-2 px-3 pt-1 text-[10.5px] text-slate-500">
          <Activity className={`h-3.5 w-3.5 ${apiOnline ? 'text-cyan-300' : 'text-rose-400'}`} />
          <span className="flex-1">Engine</span>
          <span className={apiOnline ? 'text-cyan-300' : 'text-rose-300'}>
            {apiOnline ? 'Connected' : 'Offline'}
          </span>
        </div>
      </div>
    </>
  );

  return (
    <>
      <header className="flex h-16 shrink-0 items-center justify-between border-b border-white/[0.065] bg-[#0b111b]/95 px-4 lg:hidden">
        <button
          onClick={() => setMobileOpen(true)}
          className="rounded-xl border border-white/[0.08] bg-white/[0.035] p-2.5 text-slate-300"
          aria-label="Open navigation"
        >
          <Menu className="h-4 w-4" />
        </button>
        <button onClick={() => navigate('overview')} className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-300 text-slate-950">
            <Bot className="h-4 w-4" />
          </span>
          <span className="text-sm font-semibold text-white">RoboWeaver</span>
        </button>
        <button
          onClick={() => setShowAiPanel((current) => !current)}
          className="relative rounded-xl border border-white/[0.08] bg-white/[0.035] p-2.5 text-violet-300"
          aria-label="Manage local AI"
        >
          <Brain className="h-4 w-4" />
          <span className={`absolute right-1.5 top-1.5 ${ollamaAvailable ? 'status-dot-online' : 'status-dot-offline'}`} />
        </button>
      </header>

      <aside className="hidden h-full w-[clamp(15rem,18vw,20rem)] shrink-0 flex-col border-r border-white/[0.065] bg-[#0b111b] lg:flex">
        {sidebarContent}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-[70] lg:hidden">
          <button
            className="absolute inset-0 bg-slate-950/75 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          />
          <aside className="relative flex h-full w-[min(19rem,88vw)] flex-col border-r border-white/[0.08] bg-[#0b111b] shadow-2xl">
            {sidebarContent}
          </aside>
        </div>
      )}

      {showAiPanel && (
        <div className="fixed bottom-4 left-4 right-4 z-[80] rounded-2xl border border-white/[0.09] bg-[#111a27] p-4 shadow-2xl sm:left-auto sm:w-[24rem] lg:bottom-5 lg:left-[17rem] lg:right-auto">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <Settings2 className="h-4 w-4 text-violet-300" /> Local AI runtime
              </div>
              <p className="mt-1 text-[11px] text-slate-500">{aiStatus?.host ?? 'Ollama status unavailable'}</p>
            </div>
            <button
              onClick={() => setShowAiPanel(false)}
              className="rounded-lg p-1.5 text-slate-500 hover:bg-white/[0.05] hover:text-white"
              aria-label="Close AI settings"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {aiStatus ? (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-2">
                <StatusCell label="Status" value={ollamaAvailable ? 'Ready' : 'Offline'} />
                <StatusCell label="Models" value={String(aiStatus.models.length)} />
                <StatusCell label="Calls" value={String(aiStatus.total_calls)} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  Feature
                  <select
                    value={selectedFeature}
                    onChange={(event) => setSelectedFeature(event.target.value)}
                    className="app-well mt-1.5 w-full rounded-lg px-2.5 py-2 text-[11px] normal-case tracking-normal text-slate-200"
                  >
                    {Object.keys(aiStatus.feature_models).map((feature) => (
                      <option key={feature} value={feature}>{feature}</option>
                    ))}
                  </select>
                </label>
                <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  Assigned model
                  <select
                    value={aiStatus.feature_models[selectedFeature] ?? ''}
                    onChange={(event) => handleModelSelection(event.target.value)}
                    disabled={!ollamaAvailable || aiStatus.models.length === 0 || aiMutationLoading}
                    className="app-well mt-1.5 w-full rounded-lg px-2.5 py-2 text-[11px] normal-case tracking-normal text-slate-200 disabled:opacity-50"
                  >
                    {aiStatus.models.length === 0 && <option value="">No models</option>}
                    {aiStatus.models.map((model) => (
                      <option key={model.name} value={model.name}>{model.name}</option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="block text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                Pull a model
                <span className="mt-1.5 flex gap-2">
                  <input
                    value={pullModel}
                    onChange={(event) => setPullModel(event.target.value)}
                    className="app-well min-w-0 flex-1 rounded-lg px-2.5 py-2 font-data text-[11px] normal-case tracking-normal text-slate-200"
                    placeholder="llama3.2:3b"
                  />
                  <button
                    onClick={handlePullModel}
                    disabled={!pullModel.trim() || aiMutationLoading || !ollamaAvailable}
                    className="rounded-lg bg-violet-300 px-3 text-slate-950 disabled:cursor-not-allowed disabled:opacity-40"
                    aria-label="Pull model"
                  >
                    {aiMutationLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                  </button>
                </span>
              </label>
              {aiMutationMessage && <p className="text-[11px] leading-relaxed text-slate-400">{aiMutationMessage}</p>}
            </div>
          ) : (
            <p className="rounded-xl bg-rose-400/[0.06] p-3 text-[12px] leading-relaxed text-rose-200">
              AI status is unavailable. Start Ollama and check the configured server URL.
            </p>
          )}
        </div>
      )}
    </>
  );
};

function StatusCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="app-well rounded-xl px-3 py-2.5">
      <div className="text-[9px] font-semibold uppercase tracking-wide text-slate-600">{label}</div>
      <div className="mt-0.5 truncate text-[12px] font-semibold text-slate-200">{value}</div>
    </div>
  );
}
