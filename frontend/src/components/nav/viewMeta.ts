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
  FlaskConical,
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
  { id: 'overview', label: 'Start here', icon: LayoutDashboard, group: 'support', description: 'What RoboWeaver does and what to do next' },
  { id: 'compile', label: 'Build a program', icon: Code2, group: 'pipeline', description: 'Describe a task and test robot targets' },
  { id: 'compare', label: 'Choose a robot', icon: GitCompare, group: 'pipeline', description: 'Find the best compatible target' },
  { id: 'workcell', label: 'Plan multiple robots', icon: Wand2, group: 'pipeline', description: 'Coordinate a shared job' },
  { id: 'benchmark', label: 'Test the compiler', icon: Gauge, group: 'pipeline', description: 'Measure speed and reliability' },
  { id: 'research', label: 'Research lab', icon: FlaskConical, group: 'pipeline', description: 'Design and isolate new robot embodiments' },
  { id: 'robots', label: 'Robot library', icon: Boxes, group: 'support', description: 'Robot capabilities and limits' },
  { id: 'connect', label: 'Connect hardware', icon: Radar, group: 'support', description: 'Find and test robot endpoints' },
  { id: 'twin', label: 'Hand simulator', icon: Cpu, group: 'support', description: 'Test modeled Inspire Hand grasps' },
  { id: 'graph', label: 'Capability evidence', icon: Share2, group: 'support', description: 'See why robots and tools match' },
  { id: 'packages', label: 'ROS package library', icon: Database, group: 'support', description: 'Browse indexed robot software' },
  { id: 'settings', label: 'Settings', icon: Settings, group: 'support', description: 'Runtime, AI, and connections' },
];

export function viewMetaFor(view: ViewType): ViewMeta {
  return VIEW_META.find((v) => v.id === view) ?? VIEW_META[0];
}
