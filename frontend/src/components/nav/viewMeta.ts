import {
  LayoutDashboard,
  Code2,
  GitCompare,
  Wand2,
  Boxes,
  Cpu,
  Share2,
  Database,
  Radar,
  Gauge,
  Settings,
  LucideIcon,
} from 'lucide-react';
import { ViewType } from '../../types';

export interface ViewMeta {
  id: ViewType;
  label: string;
  icon: LucideIcon;
  /** Groups the pipeline-shaped destinations separately from supporting ones in
   * the nav bar -- Compile/Compare read as the compiler's own stages, the rest
   * are real supporting views (fleet data, connectivity, settings). */
  group: 'pipeline' | 'support';
}

export const VIEW_META: ViewMeta[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, group: 'support' },
  { id: 'compile', label: 'Compile', icon: Code2, group: 'pipeline' },
  { id: 'compare', label: 'Compare', icon: GitCompare, group: 'pipeline' },
  { id: 'workcell', label: 'Workcell', icon: Wand2, group: 'pipeline' },
  { id: 'robots', label: 'Robots', icon: Boxes, group: 'support' },
  { id: 'twin', label: 'Digital Twin', icon: Cpu, group: 'support' },
  { id: 'graph', label: 'Knowledge Graph', icon: Share2, group: 'support' },
  { id: 'packages', label: 'Packages', icon: Database, group: 'support' },
  { id: 'connect', label: 'Connect', icon: Radar, group: 'support' },
  { id: 'benchmark', label: 'Benchmark', icon: Gauge, group: 'pipeline' },
  { id: 'settings', label: 'Settings', icon: Settings, group: 'support' },
];

export function viewMetaFor(view: ViewType): ViewMeta {
  return VIEW_META.find((v) => v.id === view) ?? VIEW_META[0];
}
