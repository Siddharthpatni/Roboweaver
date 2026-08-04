'use client';

import React from 'react';
import { X } from 'lucide-react';
import { useTabs } from './TabsContext';
import { tabMetaFor } from './tabMeta';

/** VSCode-style row of open-tab pills above the editor area. Backed entirely
 * by `TabsContext` -- opening/closing here is the same state the
 * ActivityBar/ExplorerPanel mutate, so all three stay in sync. */
export const TabStrip: React.FC = () => {
  const { openTabs, activeTab, setActiveTab, closeTab } = useTabs();

  return (
    <div className="h-9 shrink-0 flex items-stretch border-b border-cyan-400/[0.08] bg-[#050810]/80 backdrop-blur-xl overflow-x-auto">
      {openTabs.map((tab) => {
        const meta = tabMetaFor(tab);
        const Icon = meta.icon;
        const isActive = tab === activeTab;
        return (
          <div
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`group relative flex items-center gap-2 px-3 min-w-[140px] max-w-[200px] cursor-pointer border-r border-white/[0.05] text-[12.5px] transition-colors shrink-0 ${
              isActive ? 'bg-[#0a0f1e] text-slate-100' : 'text-slate-500 hover:text-slate-300 hover:bg-white/[0.02]'
            }`}
          >
            {isActive && (
              <span
                className="absolute left-0 right-0 top-0 h-[2px]"
                style={{ background: 'linear-gradient(90deg, #22d3ee, #8b5cf6)' }}
              />
            )}
            <Icon className={`w-3.5 h-3.5 shrink-0 ${isActive ? 'text-cyan-400' : 'text-slate-600'}`} />
            <span className="flex-1 truncate">{meta.label}</span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                closeTab(tab);
              }}
              className={`shrink-0 w-4 h-4 rounded flex items-center justify-center hover:bg-white/[0.10] ${
                isActive ? 'opacity-70 hover:opacity-100' : 'opacity-0 group-hover:opacity-60 hover:!opacity-100'
              }`}
              title={`Close ${meta.label}`}
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        );
      })}
    </div>
  );
};
