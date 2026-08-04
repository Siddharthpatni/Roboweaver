'use client';

import React, { useEffect, useState } from 'react';
import { ChevronRight, ChevronDown, Boxes, Database, Radar, Wrench, LucideIcon } from 'lucide-react';
import { useTabs } from './TabsContext';
import { RoboWeaverAPI } from '../../lib/api';
import { RobotProfile, NexusPackage, DiscoveredRobot, KnowledgeGraphNode } from '../../types';

interface ExplorerPanelProps {
  robots: RobotProfile[];
  packages: NexusPackage[];
  discovered: DiscoveredRobot[];
}

interface SectionProps {
  title: string;
  icon: LucideIcon;
  count: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

const Section: React.FC<SectionProps> = ({ title, icon: Icon, count, defaultOpen = true, children }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="select-none">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-1.5 px-2 py-1.5 text-[11px] font-semibold tracking-wide text-slate-400 hover:text-slate-200 uppercase"
      >
        {open ? <ChevronDown className="w-3 h-3 shrink-0" /> : <ChevronRight className="w-3 h-3 shrink-0" />}
        <Icon className="w-3.5 h-3.5 shrink-0 text-cyan-400/80" />
        <span className="flex-1 text-left truncate">{title}</span>
        <span className="text-[10px] font-data text-slate-600">{count}</span>
      </button>
      {open && <div className="pl-6 pb-1">{children}</div>}
    </div>
  );
};

const Leaf: React.FC<{ label: string; sub?: string; onClick: () => void }> = ({ label, sub, onClick }) => (
  <button
    onClick={onClick}
    className="w-full flex items-center gap-2 px-2 py-1 rounded text-left text-[12px] text-slate-400 hover:text-slate-100 hover:bg-white/[0.04] transition-colors"
  >
    <span className="truncate flex-1">{label}</span>
    {sub && <span className="shrink-0 text-[10px] font-data text-slate-600">{sub}</span>}
  </button>
);

/**
 * A file-tree-style browser over the same real data the full-page views
 * (`FleetRegistryView`, `KnowledgeNexusView`, `RobotConnectView`) already
 * fetch -- this doesn't duplicate or re-derive it, it's the exact same
 * `RoboWeaverAPI` calls, just grouped as leaves instead of a page-sized grid.
 * The SKILLS section is the one genuinely new read: the real knowledge graph
 * (`/api/graph`, gap-fix item 2) has one SKILL node per NL-reachable
 * `IndustrialSkillCategory` -- nothing in the frontend consumed that endpoint
 * until now.
 */
export const ExplorerPanel: React.FC<ExplorerPanelProps> = ({ robots, packages, discovered }) => {
  const { openTab } = useTabs();
  const [skills, setSkills] = useState<KnowledgeGraphNode[]>([]);
  const [skillsError, setSkillsError] = useState(false);

  useEffect(() => {
    RoboWeaverAPI.graph()
      .then((g) => setSkills(g.nodes.filter((n) => n.type === 'SKILL')))
      .catch(() => setSkillsError(true));
  }, []);

  return (
    <aside className="w-64 shrink-0 flex flex-col h-full border-r border-cyan-400/[0.08] bg-[#070b16]/70 backdrop-blur-xl overflow-y-auto">
      <div className="px-3 py-2.5 shrink-0">
        <span className="text-[10.5px] font-bold tracking-[0.16em] text-slate-500 uppercase">Explorer</span>
      </div>

      <div className="flex-1 min-h-0 px-1 pb-3 space-y-0.5">
        <Section title="Robots" icon={Boxes} count={robots.length}>
          {robots.length === 0 && <p className="px-2 py-1 text-[11.5px] text-slate-600">No robots loaded.</p>}
          {robots.map((r) => (
            <Leaf key={r.id} label={r.name} sub={`${r.dof}-DOF`} onClick={() => openTab('fleet')} />
          ))}
        </Section>

        <Section title="Skills" icon={Wrench} count={skills.length}>
          {skillsError && <p className="px-2 py-1 text-[11.5px] text-slate-600">Backend offline.</p>}
          {!skillsError && skills.length === 0 && (
            <p className="px-2 py-1 text-[11.5px] text-slate-600">Loading…</p>
          )}
          {skills.map((s) => (
            <Leaf key={s.id} label={s.name} onClick={() => openTab('compiler')} />
          ))}
        </Section>

        <Section title="Knowledge" icon={Database} count={packages.length}>
          {packages.length === 0 && <p className="px-2 py-1 text-[11.5px] text-slate-600">No packages loaded.</p>}
          {packages.map((p) => (
            <Leaf key={p.id} label={p.name} sub={p.category} onClick={() => openTab('nexus')} />
          ))}
        </Section>

        <Section title="Discovered" icon={Radar} count={discovered.length} defaultOpen={discovered.length > 0}>
          {discovered.length === 0 && (
            <p className="px-2 py-1 text-[11.5px] text-slate-600">Nothing reachable on standard ports.</p>
          )}
          {discovered.map((d) => (
            <Leaf key={`${d.host}:${d.port}`} label={d.name} sub={`${d.host}:${d.port}`} onClick={() => openTab('connect')} />
          ))}
        </Section>
      </div>
    </aside>
  );
};
