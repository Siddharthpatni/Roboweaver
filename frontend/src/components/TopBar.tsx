'use client';

import React from 'react';
import { Search, Bell, Shield, Radio, ChevronDown, CheckCircle2 } from 'lucide-react';

interface TopBarProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  onOpenIncidentModal: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  searchQuery,
  onSearchChange,
  onOpenIncidentModal
}) => {
  return (
    <header className="h-16 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-30">
      {/* Search Input */}
      <div className="flex items-center gap-3 w-96">
        <div className="relative w-full">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search incidents, ROS 2 packages, or robots..."
            className="w-full bg-slate-900/90 border border-slate-800 rounded-xl pl-10 pr-4 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/30 transition-all"
          />
        </div>
      </div>

      {/* Right User & System Status Controls */}
      <div className="flex items-center gap-4">
        {/* Quick Launch HITL Diff Viewer Button */}
        <button
          onClick={onOpenIncidentModal}
          className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-emerald-500/20 to-teal-500/10 hover:from-emerald-500/30 hover:to-teal-500/20 text-emerald-400 border border-emerald-500/30 text-xs font-semibold shadow-sm transition-all"
        >
          <Radio className="w-3.5 h-3.5 animate-pulse text-emerald-400" />
          <span>Launch HITL Panel</span>
        </button>

        {/* Live On-Call Badge */}
        <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-slate-300 font-medium">Lead SRE & Robotics On-Call</span>
        </div>

        {/* Notification Bell */}
        <button 
          title="Notifications"
          className="relative p-2 rounded-xl bg-slate-900 hover:bg-slate-800/80 border border-slate-800 text-slate-300 transition-colors"
        >
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-rose-500 ring-2 ring-slate-950" />
        </button>

        {/* User Avatar */}
        <div className="flex items-center gap-3 pl-2 border-l border-slate-800">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold text-xs shadow-md">
            JS
          </div>
          <div className="hidden lg:block">
            <div className="text-xs font-semibold text-slate-200">John Smith</div>
            <div className="text-[10px] text-slate-400">Principal MLOps Lead</div>
          </div>
        </div>
      </div>
    </header>
  );
};
