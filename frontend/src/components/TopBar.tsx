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
    <header className="h-16 shrink-0 border-b border-amber-500/10 bg-[#0d0806]/95 backdrop-blur px-6 flex items-center gap-4 sticky top-0 z-30">
      <div className="relative flex-1 min-w-0 max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 pointer-events-none" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search robots, packages, skills…"
          className="w-full app-well rounded-lg pl-9 pr-3 py-2 text-[13px] text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/40 transition-colors"
        />
      </div>

      <div className="flex-1" />

      <div
        className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11.5px] font-medium shrink-0"
        style={
          apiOnline
            ? { borderColor: 'rgba(255,179,0,0.28)', color: '#ffc94d', background: 'rgba(255,179,0,0.08)' }
            : { borderColor: 'rgba(214,41,28,0.3)', color: '#ff8a80', background: 'rgba(214,41,28,0.08)' }
        }
      >
        <span className={`w-1.5 h-1.5 rounded-full ${apiOnline ? 'bg-emerald-400' : 'bg-rose-400'}`} />
        {apiOnline ? 'Connected' : 'Offline'}
      </div>

      <button
        onClick={onLaunchBuilder}
        className="shrink-0 flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-[#0a0c11] text-[13px] font-semibold transition-colors"
      >
        <Plus className="w-4 h-4" />
        New workcell
      </button>

      <div className="shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-emerald-400 to-teal-600 flex items-center justify-center text-[11px] font-bold text-[#0a0c11]">
        RW
      </div>
    </header>
  );
};
