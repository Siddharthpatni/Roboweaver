import {
  LayoutDashboard,
  Code2,
  Wand2,
  Database,
  Boxes,
  Cpu,
  Activity,
  Settings,
  Radar,
  LucideIcon,
} from 'lucide-react';
import { TabType } from '../../types';

export interface TabMeta {
  id: TabType;
  label: string;
  icon: LucideIcon;
}

/** Single source of truth for tab display -- ActivityBar, ExplorerPanel, and
 * TabStrip all read from this instead of each hardcoding their own copy of
 * the nav list (which is how the pre-rebuild Sidebar.tsx did it). */
export const TAB_META: TabMeta[] = [
  { id: 'dashboard', label: 'Overview', icon: LayoutDashboard },
  { id: 'compiler', label: 'Compiler', icon: Code2 },
  { id: 'builder', label: 'Workcell Builder', icon: Wand2 },
  { id: 'nexus', label: 'Knowledge Nexus', icon: Database },
  { id: 'fleet', label: 'Fleet Registry', icon: Boxes },
  { id: 'connect', label: 'Robot Connect', icon: Radar },
  { id: 'simulation', label: 'Digital Twin', icon: Cpu },
  { id: 'activity', label: 'Agent Activity', icon: Activity },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export function tabMetaFor(tab: TabType): TabMeta {
  return TAB_META.find((t) => t.id === tab) ?? TAB_META[0];
}
