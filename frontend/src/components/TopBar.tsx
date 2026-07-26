'use client';

import React from 'react';
import { Search, Bell, Shield, Radio, ChevronDown, CheckCircle2, AlertOctagon, Cpu } from 'lucide-react';

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
    <header className="h-16 border-b border-emerald-500/30 bg-[#060b17]/90 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-30 font-mono">
      {/* Search Input HUD */}
      <div className="flex items-center gap-3 w-96">
        <div className="relative w-full">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-emerald-500/70" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="[ SEARCH ROBO_OS TOPICS, PKGS, OR SKILLS... ]"
            className="w-full bg-slate-950 border border-emerald-500/40 rounded-lg pl-10 pr-4 py-2 text-xs text-emerald-300 placeholder-slate-500 font-mono focus:outline-none focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400/50 transition-all shadow-inner"
          />
        </div>
      </div>

      {/* Right User & System Status Controls */}
      <div className="flex items-center gap-3">
        {/* Quick Launch HITL Diff Viewer Button */}
        <button
          onClick={onOpenIncidentModal}
          className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/60 text-xs font-bold uppercase tracking-wider shadow-sm transition-all"
        >
          <Radio className="w-3.5 h-3.5 animate-pulse text-emerald-400" />
          <span>[ LAUNCH HITL PANEL ]</span>
        </button>

        {/* Live On-Call Mecha Telemetry Badge */}
        <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-950 border border-emerald-500/40 text-xs font-bold">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-emerald-400 tracking-wider">ROS2 HUMBLE: DDS OK</span>
        </div>

        {/* E-STOP Standby Badge */}
        <div className="hidden xl:flex items-center gap-1.5 px-3 py-1 rounded-md bg-rose-500/10 border border-rose-500/40 text-rose-400 text-xs font-bold uppercase tracking-widest">
          <AlertOctagon className="w-3.5 h-3.5 text-rose-400" />
          <span>[ E-STOP: STANDBY ]</span>
        </div>

        {/* Notification Bell */}
        <button 
          title="Notifications"
          className="relative p-2 rounded-lg bg-slate-950 hover:bg-slate-900 border border-emerald-500/40 text-emerald-400 transition-colors"
        >
          <Bell className="w-4 h-4" />
          <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-rose-500 ring-2 ring-slate-950" />
        </button>

        {/* User Avatar HUD */}
        <div className="flex items-center gap-3 pl-3 border-l border-emerald-500/30">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center text-slate-950 font-black text-xs shadow-md border border-emerald-400">
            OP
          </div>
          <div className="hidden lg:block">
            <div className="text-xs font-bold text-white uppercase tracking-wider">SRE MECHA LEAD</div>
            <div className="text-[10px] text-emerald-400/80 uppercase">ROS2 SECURITY ON-CALL</div>
          </div>
        </div>
      </div>
    </header>
  );
};
