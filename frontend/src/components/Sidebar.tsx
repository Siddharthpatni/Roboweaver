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
  Radar,
} from 'lucide-react';
import { TabType } from '../types';

interface SidebarProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  packageCount: number;
  robotCount: number;
  apiOnline: boolean;
  discoveredCount?: number;
  /** Real version string from /api/version — undefined while unknown (backend
   * offline or not yet answered), never a fabricated placeholder. */
  version?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  packageCount,
  robotCount,
  apiOnline,
  discoveredCount = 0,
  version,
}) => {
  const navItems = [
    { id: 'dashboard' as TabType, label: 'Overview', icon: LayoutDashboard, badge: null, pulse: false },
    { id: 'compiler' as TabType, label: 'Compiler', icon: Code2, badge: null, pulse: false },
    { id: 'builder' as TabType, label: 'Workcell Builder', icon: Wand2, badge: null, pulse: false },
    {
      id: 'nexus' as TabType,
      label: 'Knowledge Nexus',
      icon: Database,
      badge: packageCount > 0 ? String(packageCount) : null,
      pulse: false,
    },
    {
      id: 'fleet' as TabType,
      label: 'Fleet Registry',
      icon: Boxes,
      badge: robotCount > 0 ? String(robotCount) : null,
      pulse: false,
    },
    {
      id: 'connect' as TabType,
      label: 'Robot Connect',
      icon: Radar,
      badge: discoveredCount > 0 ? String(discoveredCount) : null,
      pulse: discoveredCount > 0,
    },
    { id: 'simulation' as TabType, label: 'Digital Twin', icon: Cpu, badge: null, pulse: false },
    { id: 'activity' as TabType, label: 'Agent Activity', icon: Activity, badge: null, pulse: false },
    { id: 'settings' as TabType, label: 'Settings', icon: Settings, badge: null, pulse: false },
  ];

  return (
    <aside className="w-64 shrink-0 flex flex-col h-full border-r border-cyan-400/[0.08] bg-[#070b16]/80 backdrop-blur-xl">
      {/* Brand — sleek rotating orbital ring around the mark */}
      <div className="h-16 flex items-center gap-3 px-5 border-b border-cyan-400/[0.08] shrink-0">
        <div className="relative w-9 h-9 shrink-0 flex items-center justify-center">
          <span
            className="absolute inset-0 rounded-full animate-spin-slow"
            style={{
              background:
                'conic-gradient(from 0deg, transparent 0deg, rgba(34,211,238,0.7) 90deg, rgba(139,92,246,0.7) 180deg, transparent 300deg)',
              WebkitMask: 'radial-gradient(circle, transparent 13px, black 14px)',
              mask: 'radial-gradient(circle, transparent 13px, black 14px)',
            }}
          />
          <span
            className="absolute inset-[3px] rounded-full bg-[#0a0f1e] border border-cyan-400/20"
            style={{ boxShadow: 'inset 0 0 10px rgba(34,211,238,0.15)' }}
          />
          <Bot className="relative w-4 h-4 text-cyan-300" />
        </div>
        <div className="min-w-0">
          <div className="text-[10px] font-bold tracking-[0.18em] leading-tight truncate kicker">
            SID LABS
          </div>
          <div className="text-[13px] font-semibold text-slate-100 leading-tight truncate">
            RoboWeaver
          </div>
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
                className={`group relative w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-cyan-500/[0.10] text-cyan-300'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-white/[0.04] hover:translate-x-0.5'
                }`}
                style={
                  isActive
                    ? { boxShadow: '0 0 16px -6px rgba(34,211,238,0.45)' }
                    : undefined
                }
              >
                {/* Gradient accent line on the active item */}
                {isActive && (
                  <span
                    className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full"
                    style={{
                      background: 'linear-gradient(180deg, #22d3ee, #8b5cf6)',
                      boxShadow: '0 0 8px 1px rgba(34,211,238,0.5)',
                    }}
                  />
                )}
                <Icon
                  className={`w-4 h-4 shrink-0 transition-colors ${
                    isActive ? 'text-cyan-400' : 'text-slate-500 group-hover:text-cyan-300'
                  }`}
                />
                <span className="flex-1 min-w-0 truncate text-left">{item.label}</span>
                {item.badge && (
                  <span
                    className={`shrink-0 text-[10.5px] font-data px-1.5 py-0.5 rounded-md transition-colors ${
                      item.pulse
                        ? 'bg-cyan-500/20 text-cyan-300 animate-glow-pulse'
                        : isActive
                        ? 'bg-cyan-500/15 text-cyan-300'
                        : 'bg-white/[0.05] text-slate-500'
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
              <span className={apiOnline ? 'status-dot-online' : 'status-dot-offline'} />
              <span className="text-[12px] font-medium text-slate-300 truncate">
                {apiOnline ? 'Engine online' : 'Engine offline'}
              </span>
            </div>
            <span className="text-[10.5px] font-data text-slate-600 shrink-0">
              {version ? `v${version}` : '—'}
            </span>
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
