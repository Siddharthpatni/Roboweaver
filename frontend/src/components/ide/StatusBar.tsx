'use client';

import React from 'react';
import { Cpu, Boxes, LayoutGrid } from 'lucide-react';
import { useTabs } from './TabsContext';
import { tabMetaFor } from './tabMeta';

interface StatusBarProps {
  apiOnline: boolean;
  robotCount: number;
  activeRobot: string;
  version?: string;
}

/** Bottom strip, VSCode-style: real connection state (the same `apiOnline`
 * probe the rest of the shell uses), the real active-robot the Terminal
 * panel targets, and the real open-tab count from `TabsContext`. */
export const StatusBar: React.FC<StatusBarProps> = ({ apiOnline, robotCount, activeRobot, version }) => {
  const { openTabs, activeTab } = useTabs();

  return (
    <footer
      className={`h-6 shrink-0 flex items-center gap-4 px-3 text-[11px] font-medium ${
        apiOnline ? 'bg-cyan-600/90 text-[#030712]' : 'bg-rose-600/90 text-white'
      }`}
    >
      <span className="flex items-center gap-1.5">
        <span className={apiOnline ? 'status-dot-online' : 'status-dot-offline'} style={{ width: 6, height: 6 }} />
        {apiOnline ? 'Engine connected' : 'Engine offline'}
      </span>
      <span className="flex items-center gap-1.5">
        <Boxes className="w-3 h-3" /> {robotCount} robots registered
      </span>
      <span className="flex items-center gap-1.5">
        <Cpu className="w-3 h-3" /> target: {activeRobot}
      </span>
      <div className="flex-1" />
      <span className="flex items-center gap-1.5">
        <LayoutGrid className="w-3 h-3" /> {openTabs.length} tab{openTabs.length === 1 ? '' : 's'} open — {tabMetaFor(activeTab).label}
      </span>
      {version && <span className="font-data">v{version}</span>}
    </footer>
  );
};
