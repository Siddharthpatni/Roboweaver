'use client';

import React from 'react';
import { Search, Plus } from 'lucide-react';

interface TopBarProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  onLaunchBuilder: () => void;
  apiOnline: boolean;
}

export const TopBar: React.FC<TopBarProps> = ({
  searchQuery,
  onSearchChange,
  onLaunchBuilder,
  apiOnline,
}) => {
  return (
    <header className="h-16 shrink-0 border-b border-cyan-400/[0.08] bg-[#070b16]/70 backdrop-blur-xl px-6 flex items-center gap-4 sticky top-0 z-30">
      <div className="relative flex-1 min-w-0 max-w-md group">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 group-focus-within:text-cyan-400 transition-colors pointer-events-none z-10" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search robots, packages, skills…"
          className="w-full app-well rounded-lg pl-9 pr-3 py-2 text-[13px] text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-400/40 transition-all duration-300"
          style={{ boxShadow: 'none' }}
          onFocus={(e) => {
            e.currentTarget.style.boxShadow = '0 0 0 3px rgba(34,211,238,0.08), 0 0 18px -4px rgba(34,211,238,0.35)';
          }}
          onBlur={(e) => {
            e.currentTarget.style.boxShadow = 'none';
          }}
        />
      </div>

      <div className="flex-1" />

      <div
        className={`hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11.5px] font-medium shrink-0 transition-colors ${
          apiOnline
            ? 'border-cyan-400/25 text-cyan-300 bg-cyan-500/[0.08]'
            : 'border-rose-500/30 text-rose-300 bg-rose-500/[0.08]'
        }`}
      >
        <span className={apiOnline ? 'status-dot-online' : 'status-dot-offline'} style={{ width: 6, height: 6 }} />
        {apiOnline ? 'Connected' : 'Offline'}
      </div>

      <button
        onClick={onLaunchBuilder}
        className="shrink-0 flex items-center gap-1.5 px-3.5 py-2 btn-neon text-[13px]"
      >
        <Plus className="w-4 h-4" />
        New workcell
      </button>

      <div
        className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-[11px] font-bold text-[#030712]"
        style={{
          background: 'linear-gradient(135deg, #22d3ee, #8b5cf6)',
          boxShadow: '0 0 14px -3px rgba(34,211,238,0.5)',
        }}
      >
        RW
      </div>
    </header>
  );
};
