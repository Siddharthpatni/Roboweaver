'use client';

import React from 'react';
import { Bot, ArrowRight } from 'lucide-react';
import { ViewType } from '../../types';
import { VIEW_META } from './viewMeta';

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
