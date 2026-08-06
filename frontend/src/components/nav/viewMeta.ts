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
  description: string;
}

export const VIEW_META: ViewMeta[] = [
  { id: 'overview', label: 'Control center', icon: LayoutDashboard, group: 'support', description: 'System health and next actions' },
  { id: 'compile', label: 'Compile', icon: Code2, group: 'pipeline', description: 'Intent to verified RoboIR' },
  { id: 'compare', label: 'Compare', icon: GitCompare, group: 'pipeline', description: 'Rank compatible robots' },
  { id: 'workcell', label: 'Workcell', icon: Wand2, group: 'pipeline', description: 'Coordinate multiple robots' },
  { id: 'benchmark', label: 'Benchmark', icon: Gauge, group: 'pipeline', description: 'Measure compiler performance' },
  { id: 'robots', label: 'Fleet registry', icon: Boxes, group: 'support', description: 'Capabilities and constraints' },
  { id: 'connect', label: 'Connections', icon: Radar, group: 'support', description: 'Discover robot endpoints' },
  { id: 'twin', label: 'Digital twin', icon: Cpu, group: 'support', description: 'Inspect motion before deploy' },
  { id: 'graph', label: 'Knowledge graph', icon: Share2, group: 'support', description: 'Trace capability evidence' },
  { id: 'packages', label: 'Package catalog', icon: Database, group: 'support', description: 'Browse indexed ROS 2 assets' },
  { id: 'settings', label: 'Settings', icon: Settings, group: 'support', description: 'Runtime and connection scope' },
];

export function viewMetaFor(view: ViewType): ViewMeta {
  return VIEW_META.find((v) => v.id === view) ?? VIEW_META[0];
}
