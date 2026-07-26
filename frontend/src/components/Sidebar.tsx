'use client';

import React from 'react';
import { 
  ShieldCheck, 
  LayoutDashboard, 
  AlertTriangle, 
  Database, 
  Cpu, 
  Activity, 
  Settings,
  Sparkles,
  Bot
} from 'lucide-react';
import { TabType } from '../types';

interface SidebarProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  activeIncidentsCount: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  activeIncidentsCount
}) => {
  const navItems = [
    {
      id: 'dashboard' as TabType,
      label: 'Dashboard',
      icon: LayoutDashboard,
      badge: null
    },
    {
      id: 'incidents' as TabType,
      label: 'HITL Diff Viewer',
      icon: AlertTriangle,
      badge: {
        text: `${activeIncidentsCount} Active`,
        color: 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
      }
    },
    {
      id: 'nexus' as TabType,
      label: 'Knowledge Nexus',
      icon: Database,
      badge: {
        text: '6 Pkgs',
        color: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
      }
    },
    {
      id: 'simulation' as TabType,
      label: 'Live Simulation',
      icon: Cpu,
      badge: {
        text: 'RH56F1',
        color: 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
      }
    },
    {
      id: 'activity' as TabType,
      label: 'Agent Activity',
      icon: Activity,
      badge: null
    },
    {
      id: 'settings' as TabType,
      label: 'Settings',
      icon: Settings,
      badge: null
    }
  ];

  return (
    <aside className="w-64 bg-slate-950 border-r border-slate-800/80 flex flex-col justify-between select-none z-20">
      <div>
        {/* Brand Logo Header */}
        <div className="h-16 flex items-center px-6 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 flex items-center justify-center shadow-lg shadow-emerald-500/20">
              <ShieldCheck className="w-5 h-5 text-slate-950 font-bold" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-slate-100 tracking-tight text-base">OpsSentinel</span>
                <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                  AI-HITL
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-medium tracking-wide">
                RoboWeaver OS Nexus
              </p>
            </div>
          </div>
        </div>

        {/* Navigation Menu */}
        <div className="px-3 py-4 space-y-1">
          <p className="px-3 pb-2 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
            Control Center
          </p>
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 ${
                  isActive
                    ? 'bg-gradient-to-r from-emerald-500/15 to-teal-500/5 text-emerald-400 border border-emerald-500/30 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/80 border border-transparent'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-emerald-400' : 'text-slate-400'}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge && (
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${item.badge.color}`}>
                    {item.badge.text}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Footer System Status Card */}
      <div className="p-4 m-3 rounded-2xl bg-slate-900/60 border border-slate-800/80">
        <div className="flex items-center gap-2.5 mb-2">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-semibold text-slate-200">System Healthy</span>
        </div>
        <p className="text-[11px] text-slate-400 leading-relaxed mb-3">
          Agent pipeline active. 3 autonomous nodes & 6 ROS 2 packages indexed.
        </p>
        <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-[10px] text-slate-400">
          <span>ROS Distro</span>
          <span className="font-mono text-emerald-400 font-semibold">ROS 2 Humble / Jazzy</span>
        </div>
      </div>
    </aside>
  );
};
