'use client';

import React from 'react';
import {
  Bot,
  LayoutDashboard,
  Code2,
  Wand2,
  Database,
  Boxes,
  Cpu,
  Activity,
  Settings,
} from 'lucide-react';
import { TabType } from '../types';

interface SidebarProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  packageCount: number;
  robotCount: number;
  apiOnline: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  packageCount,
  robotCount,
  apiOnline,
}) => {
  const navItems = [
    { id: 'dashboard' as TabType, label: 'Overview', icon: LayoutDashboard, badge: null },
    { id: 'compiler' as TabType, label: 'Compiler', icon: Code2, badge: null },
    { id: 'builder' as TabType, label: 'Workcell Builder', icon: Wand2, badge: null },
    {
      id: 'nexus' as TabType,
      label: 'Knowledge Nexus',
      icon: Database,
      badge: packageCount > 0 ? String(packageCount) : null,
    },
    {
      id: 'fleet' as TabType,
      label: 'Fleet Registry',
      icon: Boxes,
      badge: robotCount > 0 ? String(robotCount) : null,
    },
    { id: 'simulation' as TabType, label: 'Digital Twin', icon: Cpu, badge: null },
    { id: 'activity' as TabType, label: 'Agent Activity', icon: Activity, badge: null },
    { id: 'settings' as TabType, label: 'Settings', icon: Settings, badge: null },
  ];

  return (
    <aside className="w-64 shrink-0 bg-[#0d0806] border-r border-amber-500/10 flex flex-col h-full">
      {/* Brand — gold housing ring around a literal arc-reactor cyan core */}
      <div className="h-16 flex items-center gap-3 px-5 border-b border-amber-500/10 shrink-0">
        <div className="relative w-9 h-9 rounded-full bg-[#1a0f06] border-2 border-amber-500/70 flex items-center justify-center shrink-0">
          <div className="absolute inset-[5px] rounded-full bg-cyan-400/90 animate-arc-pulse" />
          <Bot className="relative w-[15px] h-[15px] text-[#0c0705]" />
        </div>
        <div className="min-w-0">
          <div className="text-[10px] font-bold tracking-[0.18em] text-amber-400 leading-tight truncate">SID LABS</div>
          <div className="text-[13px] font-semibold text-slate-100 leading-tight truncate">RoboWeaver</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 min-h-0 overflow-y-auto px-3 py-4">
        <div className="space-y-0.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                className={`group w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] font-medium transition-colors ${
                  isActive
                    ? 'bg-emerald-500/10 text-emerald-300'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                }`}
              >
                <Icon
                  className={`w-4 h-4 shrink-0 ${isActive ? 'text-emerald-400' : 'text-slate-500 group-hover:text-slate-300'}`}
                />
                <span className="flex-1 min-w-0 truncate text-left">{item.label}</span>
                {item.badge && (
                  <span
                    className={`shrink-0 text-[10.5px] font-data px-1.5 py-0.5 rounded-md ${
                      isActive ? 'bg-emerald-500/15 text-emerald-300' : 'bg-white/[0.05] text-slate-500'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </nav>

      {/* Footer: connection status */}
      <div className="shrink-0 px-3 pb-3">
        <div className="app-card px-3 py-2.5 space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span
                className={`w-1.5 h-1.5 rounded-full shrink-0 ${apiOnline ? 'bg-emerald-400' : 'bg-rose-500'}`}
              />
              <span className="text-[12px] font-medium text-slate-300 truncate">
                {apiOnline ? 'Engine online' : 'Engine offline'}
              </span>
            </div>
            <span className="text-[10.5px] font-data text-slate-600 shrink-0">v1.0.0</span>
          </div>
          {!apiOnline && (
            <p className="text-[11px] text-slate-500 leading-snug">
              Start the backend:{' '}
              <code className="text-slate-400">roboweaver dashboard --port 8080</code>
            </p>
          )}
        </div>
      </div>
    </aside>
  );
};
