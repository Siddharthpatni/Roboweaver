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
      label: '3D Digital Twin HUD',
      icon: Cpu,
      badge: {
        text: '3D-SIM',
        color: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
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
    <aside className="w-64 bg-[#03060d] border-r border-emerald-500/30 flex flex-col justify-between select-none z-20 font-mono">
      <div>
        {/* Mecha Brand Logo Header */}
        <div className="h-16 flex items-center px-5 border-b border-emerald-500/30 bg-[#060b17] backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-emerald-500/20 border border-emerald-500 flex items-center justify-center shadow-lg shadow-emerald-500/20">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-white tracking-wider text-sm uppercase">OpsSentinel</span>
                <span className="text-[9px] uppercase font-bold px-1.5 py-0.5 rounded bg-emerald-500 text-slate-950">
                  MECHA
                </span>
              </div>
              <p className="text-[10px] text-emerald-400/80 font-mono tracking-widest uppercase">
                // ROBO_OS_V4 //
              </p>
            </div>
          </div>
        </div>

        {/* Navigation Menu */}
        <div className="px-3 py-4 space-y-1">
          <p className="px-3 pb-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            [ COMMAND COCKPIT ]
          </p>
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-bold uppercase transition-all duration-150 ${
                  isActive
                    ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/60 shadow-md shadow-emerald-500/10'
                    : 'text-slate-400 hover:text-white hover:bg-slate-900/80 border border-transparent'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-emerald-400 animate-pulse' : 'text-slate-400'}`} />
                  <span className="tracking-wider">{isActive ? `▶ ${item.label}` : item.label}</span>
                </div>
                {item.badge && (
                  <span className={`text-[10px] px-2 py-0.5 rounded-md font-bold font-mono ${item.badge.color}`}>
                    {item.badge.text}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Footer System Diagnostics Card */}
      <div className="p-4 m-3 rounded-xl bg-slate-950 border border-emerald-500/30 text-[11px] space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-xs font-bold text-white uppercase tracking-wider">[ DDS LINK: OK ]</span>
          </div>
          <span className="text-emerald-400 font-bold">100Hz</span>
        </div>
        <p className="text-[10px] text-slate-400 leading-relaxed font-mono">
          TURTLEBOT4 LiDAR: SCANNING<br/>
          INSPIRE RH56F1: RS485 ACTIVE<br/>
          FRANKA ARM: AUTO-SYNC
        </p>
        <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-[10px] text-slate-400">
          <span>PWR VOLTAGE</span>
          <span className="font-mono text-emerald-400 font-bold">24.2V DC</span>
        </div>
      </div>
    </aside>
  );
};
