'use client';

import React from 'react';
import { Bot, PanelLeft } from 'lucide-react';
import { useTabs } from './TabsContext';
import { TAB_META } from './tabMeta';

interface ActivityBarProps {
  explorerOpen: boolean;
  onToggleExplorer: () => void;
  apiOnline: boolean;
}

/** The old Sidebar.tsx's nav list, narrowed to an icon-only strip -- same nine
 * real destinations, same real badge-free click targets, just VSCode-shaped:
 * an activity bar picks the view, the Explorer panel next to it browses real
 * data within it. */
export const ActivityBar: React.FC<ActivityBarProps> = ({ explorerOpen, onToggleExplorer, apiOnline }) => {
  const { activeTab, openTab } = useTabs();

  return (
    <aside className="w-12 shrink-0 flex flex-col items-center h-full border-r border-cyan-400/[0.08] bg-[#070b16]/90 backdrop-blur-xl py-2">
      <div className="relative w-8 h-8 shrink-0 flex items-center justify-center mb-2">
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

      <button
        onClick={onToggleExplorer}
        title="Toggle Explorer"
        className={`w-9 h-9 mb-1.5 rounded-lg flex items-center justify-center transition-colors ${
          explorerOpen ? 'text-cyan-300 bg-cyan-500/[0.10]' : 'text-slate-500 hover:text-slate-200 hover:bg-white/[0.05]'
        }`}
      >
        <PanelLeft className="w-[18px] h-[18px]" />
      </button>

      <div className="w-6 h-px bg-white/[0.08] mb-1.5" />

      <nav className="flex-1 min-h-0 overflow-y-auto flex flex-col items-center gap-0.5 w-full">
        {TAB_META.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => openTab(item.id)}
              title={item.label}
              className={`relative w-9 h-9 rounded-lg flex items-center justify-center transition-colors ${
                isActive ? 'text-cyan-300 bg-cyan-500/[0.10]' : 'text-slate-500 hover:text-slate-200 hover:bg-white/[0.05]'
              }`}
              style={isActive ? { boxShadow: '0 0 14px -6px rgba(34,211,238,0.5)' } : undefined}
            >
              {isActive && (
                <span
                  className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full"
                  style={{
                    background: 'linear-gradient(180deg, #22d3ee, #8b5cf6)',
                    boxShadow: '0 0 8px 1px rgba(34,211,238,0.5)',
                  }}
                />
              )}
              <Icon className="w-[18px] h-[18px]" />
            </button>
          );
        })}
      </nav>

      <div className="shrink-0 pb-1">
        <span
          className={apiOnline ? 'status-dot-online' : 'status-dot-offline'}
          title={apiOnline ? 'Engine online' : 'Engine offline'}
        />
      </div>
    </aside>
  );
};
