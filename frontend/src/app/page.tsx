'use client';

import React, { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { TabsProvider, useTabs } from '../components/ide/TabsContext';
import { ActivityBar } from '../components/ide/ActivityBar';
import { ExplorerPanel } from '../components/ide/ExplorerPanel';
import { TabStrip } from '../components/ide/TabStrip';
import { TerminalPanel } from '../components/ide/TerminalPanel';
import { StatusBar } from '../components/ide/StatusBar';
import { RoboWeaverAPI } from '../lib/api';
import { TabType, RobotProfile, NexusPackage, DiscoveredRobot, VersionInfo } from '../types';
import {
  Wand2,
  Code2,
  Database,
  Share2,
  Boxes,
  Cpu,
  Radar,
  ArrowUpRight,
  AlertTriangle,
  Info,
} from 'lucide-react';

// Every tab body is loaded on demand rather than bundled into the initial
// page. LiveSimulationView alone pulls in three.js + @react-three/fiber +
// @react-three/drei -- a ~1MB chunk -- via DigitalTwinViewport/Robot3DModel.
// Before this, that shipped to every visitor on first paint even if they
// never opened Digital Twin. `ssr: false` on all of them because every view
// fetches its own data client-side (RoboWeaverAPI) and renders nothing
// meaningful without a browser; the shared loading fallback keeps the tab
// switch from looking broken while the chunk streams in.
const tabLoading = () => (
  <div className="h-full flex items-center justify-center">
    <div className="flex items-center gap-2.5 text-slate-500 text-[13px]">
      <div className="w-4 h-4 rounded-full border-2 border-cyan-400/30 border-t-cyan-400 animate-spin" />
      Loading…
    </div>
  </div>
);

const CompilerView = dynamic(() => import('../components/CompilerView').then((m) => m.CompilerView), {
  ssr: false, loading: tabLoading,
});
const WorkcellBuilderView = dynamic(
  () => import('../components/WorkcellBuilderView').then((m) => m.WorkcellBuilderView),
  { ssr: false, loading: tabLoading }
);
const KnowledgeNexusView = dynamic(
  () => import('../components/KnowledgeNexusView').then((m) => m.KnowledgeNexusView),
  { ssr: false, loading: tabLoading }
);
const KnowledgeGraphView = dynamic(
  () => import('../components/KnowledgeGraphView').then((m) => m.KnowledgeGraphView),
  { ssr: false, loading: tabLoading }
);
const FleetRegistryView = dynamic(
  () => import('../components/FleetRegistryView').then((m) => m.FleetRegistryView),
  { ssr: false, loading: tabLoading }
);
// The heaviest one: three.js + react-three-fiber + drei live behind this import.
const LiveSimulationView = dynamic(
  () => import('../components/LiveSimulationView').then((m) => m.LiveSimulationView),
  { ssr: false, loading: tabLoading }
);
const RobotConnectView = dynamic(
  () => import('../components/RobotConnectView').then((m) => m.RobotConnectView),
  { ssr: false, loading: tabLoading }
);

export default function Home() {
  return (
    <TabsProvider initialTab="dashboard">
      <Workbench />
    </TabsProvider>
  );
}

function Workbench() {
  const { activeTab, openTab } = useTabs();
  const [apiOnline, setApiOnline] = useState(false);
  const [robots, setRobots] = useState<RobotProfile[]>([]);
  const [packages, setPackages] = useState<NexusPackage[]>([]);
  const [discovered, setDiscovered] = useState<DiscoveredRobot[]>([]);
  const [version, setVersion] = useState<VersionInfo | null>(null);
  const [graphNodeCount, setGraphNodeCount] = useState(0);
  const [explorerOpen, setExplorerOpen] = useState(true);
  const [terminalRobot, setTerminalRobot] = useState('franka_panda');

  useEffect(() => {
    RoboWeaverAPI.robots()
      .then((data) => {
        setRobots(data);
        setApiOnline(true);
      })
      .catch(() => setApiOnline(false));

    RoboWeaverAPI.nexusPackages()
      .then(setPackages)
      .catch(() => {});

    // One passive scan on load so the sidebar badge and the dashboard card
    // reflect what is actually reachable. RobotConnectView re-scans on demand.
    RoboWeaverAPI.discover()
      .then((res) => setDiscovered(res.discovered))
      .catch(() => setDiscovered([]));

    // Real version/uptime/self-heal status straight from the running
    // process -- the sidebar previously hardcoded "v2.0.0", which didn't even
    // match the real package version (0.1.0). null while unknown, never a
    // fabricated placeholder.
    RoboWeaverAPI.version()
      .then(setVersion)
      .catch(() => setVersion(null));

    RoboWeaverAPI.graph()
      .then((g) => setGraphNodeCount(g.nodes.length))
      .catch(() => {});
  }, []);

  return (
    <div className="flex flex-col h-screen w-screen bg-app-surface text-slate-100 overflow-hidden">
      <div className="flex flex-1 min-h-0">
        <ActivityBar
          explorerOpen={explorerOpen}
          onToggleExplorer={() => setExplorerOpen((o) => !o)}
          apiOnline={apiOnline}
        />

        {explorerOpen && <ExplorerPanel robots={robots} packages={packages} discovered={discovered} />}

        <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
          <TabStrip />

          <main className="flex-1 min-h-0 overflow-hidden relative">
        <ErrorBoundary resetKey={activeTab}>
          {activeTab === 'compiler' && <CompilerView />}
          {activeTab === 'builder' && <WorkcellBuilderView />}
          {activeTab === 'nexus' && <KnowledgeNexusView />}
          {activeTab === 'graph' && <KnowledgeGraphView />}
          {activeTab === 'fleet' && <FleetRegistryView />}
          {activeTab === 'connect' && <RobotConnectView />}
          {activeTab === 'simulation' && <LiveSimulationView />}

          {activeTab === 'dashboard' && (
            <div className="h-full overflow-y-auto">
              <div className="max-w-6xl mx-auto p-8 space-y-8">
                {/* Hero */}
                <div className="app-card hud-corners p-7 flex flex-col md:flex-row md:items-center justify-between gap-5 relative overflow-hidden animate-fade-in-up">
                  {/* Ambient particle-like glow field */}
                  <div
                    className="absolute inset-0 pointer-events-none opacity-60"
                    style={{
                      backgroundImage:
                        'radial-gradient(circle at 18% 30%, rgba(34,211,238,0.10) 0%, transparent 45%), radial-gradient(circle at 82% 70%, rgba(139,92,246,0.10) 0%, transparent 45%)',
                    }}
                  />
                  <div className="space-y-2 max-w-xl relative">
                    <span className="kicker">Sid Labs / RoboWeaver</span>
                    <h1 className="text-[22px] font-semibold leading-snug text-balance text-gradient animate-gradient-shift">
                      Human intent → RoboIR → verified robot skill
                    </h1>
                    <p className="text-[13px] text-slate-400 leading-relaxed">
                      An LLVM-like compiler for robotics. Describe a skill in plain English — RoboWeaver
                      compiles it through RoboIR, checks it against the target robot&apos;s real capabilities,
                      and synthesizes a ROS 2 BehaviorTree package, live from the engine.
                    </p>
                  </div>
                  <div className="flex items-center gap-2.5 shrink-0 relative">
                    <button
                      onClick={() => openTab('compiler')}
                      className="flex items-center gap-2 px-4 py-2.5 btn-neon text-[13px]"
                    >
                      <Code2 className="w-4 h-4" />
                      Compile a skill
                    </button>
                    <button
                      onClick={() => openTab('builder')}
                      className="px-4 py-2.5 rounded-lg border border-cyan-400/15 hover:border-cyan-400/35 hover:bg-cyan-500/[0.06] text-slate-300 hover:text-cyan-200 text-[13px] font-medium transition-all"
                    >
                      Build a workcell
                    </button>
                  </div>
                </div>

                {!apiOnline && (
                  <div className="flex items-center gap-2.5 px-4 py-3 rounded-lg bg-amber-500/[0.07] border border-amber-500/20 text-amber-300 text-[13px]">
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                    <span>
                      Backend offline. Start it with <code className="font-data">roboweaver dashboard --port 8080</code> to
                      load live data.
                    </span>
                  </div>
                )}

                {/* KPI row */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-7 gap-4 stagger-children">
                  {[
                    {
                      tab: 'compiler' as TabType,
                      label: 'RoboIR compiler',
                      // Reflects the real health check (apiOnline, from the
                      // /api/robots probe on mount) instead of a permanent
                      // "Ready" that stayed true even with the backend down.
                      value: apiOnline ? 'Ready' : 'Offline',
                      icon: Code2,
                      tint: apiOnline ? 'text-cyan-400' : 'text-rose-400',
                    },
                    {
                      tab: 'builder' as TabType,
                      label: 'Workcell builder',
                      value: apiOnline ? 'Ready' : 'Offline',
                      icon: Wand2,
                      tint: apiOnline ? 'text-cyan-400' : 'text-rose-400',
                    },
                    {
                      tab: 'nexus' as TabType,
                      label: 'Indexed ROS 2 packages',
                      value: String(packages.length),
                      icon: Database,
                      tint: 'text-cyan-400',
                    },
                    {
                      tab: 'graph' as TabType,
                      label: 'Knowledge graph nodes',
                      value: String(graphNodeCount),
                      icon: Share2,
                      tint: 'text-cyan-400',
                    },
                    {
                      tab: 'fleet' as TabType,
                      label: 'Registered robots',
                      value: String(robots.length),
                      icon: Boxes,
                      tint: 'text-rose-400',
                    },
                    {
                      tab: 'connect' as TabType,
                      label: 'Reachable endpoints',
                      value: String(discovered.length),
                      icon: Radar,
                      tint: 'text-violet-400',
                    },
                    {
                      tab: 'simulation' as TabType,
                      label: 'Digital twin',
                      value: apiOnline ? 'Ready' : 'Offline',
                      icon: Cpu,
                      tint: apiOnline ? 'text-violet-400' : 'text-rose-400',
                    },
                  ].map((kpi) => (
                    <button
                      key={kpi.label}
                      onClick={() => openTab(kpi.tab)}
                      className="app-card p-5 text-left group hover:-translate-y-0.5 transition-transform duration-200"
                    >
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-[11.5px] text-slate-500 font-medium">{kpi.label}</span>
                        <kpi.icon className={`w-4 h-4 ${kpi.tint} opacity-80 group-hover:opacity-100 transition-opacity`} />
                      </div>
                      <div className="text-2xl font-semibold font-data text-white truncate">{kpi.value}</div>
                    </button>
                  ))}
                </div>

                {/* Quick panels */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                  <div className="app-card p-6 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-[13.5px] font-semibold text-slate-200">Fleet registry</h3>
                      <button
                        onClick={() => openTab('fleet')}
                        className="flex items-center gap-1 text-[12px] font-medium text-emerald-400 hover:text-emerald-300 transition-colors"
                      >
                        Open <ArrowUpRight className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="space-y-2">
                      {robots.slice(0, 4).map((r) => (
                        <div
                          key={r.id}
                          onClick={() => openTab('fleet')}
                          className="app-well rounded-lg px-3.5 py-2.5 cursor-pointer hover:border-white/[0.12] transition-colors flex items-center justify-between gap-3"
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-[11px] font-data text-rose-400 shrink-0">{r.dof}-DOF</span>
                              <span className="text-[12.5px] font-medium text-slate-200 truncate">{r.name}</span>
                            </div>
                            <div className="text-[11px] text-slate-500 truncate">{r.manufacturer}</div>
                          </div>
                          <span className="text-[10.5px] font-data text-slate-500 shrink-0">{r.id}</span>
                        </div>
                      ))}
                      {robots.length === 0 && (
                        <div className="text-[12.5px] text-slate-500 py-3">
                          No robots loaded — start the backend to see the live registry.
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="app-card p-6 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-[13.5px] font-semibold text-slate-200">Indexed packages</h3>
                      <button
                        onClick={() => openTab('nexus')}
                        className="flex items-center gap-1 text-[12px] font-medium text-emerald-400 hover:text-emerald-300 transition-colors"
                      >
                        Open <ArrowUpRight className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {packages.slice(0, 4).map((pkg) => (
                        <div
                          key={pkg.id}
                          onClick={() => openTab('nexus')}
                          className="app-well rounded-lg px-3.5 py-2.5 cursor-pointer hover:border-white/[0.12] transition-colors"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[12.5px] font-medium text-slate-200 truncate">{pkg.name}</span>
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.05] text-slate-500 shrink-0">
                              {pkg.category}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-500 mt-1 line-clamp-2">{pkg.description}</p>
                        </div>
                      ))}
                      {packages.length === 0 && (
                        <div className="text-[12.5px] text-slate-500 py-3 col-span-2">
                          No packages loaded — start the backend to see the live catalog.
                        </div>
                      )}
                    </div>

                    <div className="pt-3 border-t border-white/[0.06] flex items-center justify-between gap-3">
                      <span className="text-[12px] text-slate-500">Test grasp kinematics before deploy?</span>
                      <button
                        onClick={() => openTab('simulation')}
                        className="shrink-0 px-3 py-1.5 rounded-lg bg-violet-500/10 hover:bg-violet-500/15 text-violet-300 text-[12px] font-medium border border-violet-500/20 transition-colors"
                      >
                        Digital twin →
                      </button>
                    </div>
                  </div>
                </div>

                {/* Robot connection status */}
                <div className="app-card p-6 space-y-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <Radar className="w-4 h-4 text-cyan-400" />
                      <h3 className="text-[13.5px] font-semibold text-slate-200">Robot connections</h3>
                    </div>
                    <button
                      onClick={() => openTab('connect')}
                      className="flex items-center gap-1 text-[12px] font-medium text-cyan-400 hover:text-cyan-300 transition-colors"
                    >
                      Open <ArrowUpRight className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {discovered.length > 0 ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {discovered.slice(0, 4).map((d) => (
                        <div
                          key={`${d.host}:${d.port}`}
                          onClick={() => openTab('connect')}
                          className="app-well rounded-lg px-3.5 py-2.5 cursor-pointer hover:border-cyan-400/25 transition-colors flex items-center justify-between gap-3"
                        >
                          <div className="min-w-0">
                            <div className="text-[12.5px] font-medium text-slate-200 truncate">{d.name}</div>
                            <div className="text-[11px] font-data text-slate-500 truncate">
                              {d.host}:{d.port}
                            </div>
                          </div>
                          <span className="text-[11px] font-data text-cyan-300 shrink-0">{d.latency_ms} ms</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[12.5px] text-slate-500 leading-relaxed">
                      No robots or simulators are listening on the standard control ports. Open Robot
                      Connect to run a fresh scan — an empty result there is a real result, not a
                      failed scan.
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'activity' && (
            <div className="h-full overflow-y-auto">
              <div className="max-w-3xl mx-auto p-8 space-y-5">
                <div>
                  <span className="kicker">Agent Activity</span>
                  <h2 className="text-[19px] font-semibold text-white mt-1">What the pipeline actually does</h2>
                  <p className="text-[13px] text-slate-400 mt-1.5 leading-relaxed">
                    RoboWeaver keeps no synthetic activity log. This is the real compile pipeline that runs
                    whenever you submit a prompt from the Workcell Builder.
                  </p>
                </div>
                <div className="space-y-2">
                  {[
                    ['SystemPromptParser', 'Extracts the robot fleet and task clauses from your prompt.'],
                    ['SkillCompiler', 'Resolves each instruction into an intent, task graph, and N-DOF IK solution per target robot.'],
                    ['MultiRobotChoreographer', 'Topologically sorts steps into parallel and sequential DAG execution tiers.'],
                    ['Groot2 BehaviorTree + ROS 2 codegen', 'Synthesizes a composite BehaviorTree XML and a multi-namespace ROS 2 package.'],
                  ].map(([name, desc], i) => (
                    <div key={name} className="app-card px-4 py-3 flex items-start gap-3">
                      <span className="text-[11px] font-data text-slate-600 shrink-0 mt-0.5">{i + 1}</span>
                      <p className="text-[13px] text-slate-300 leading-relaxed">
                        <span className="text-emerald-400 font-medium">{name}</span> — {desc}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'settings' && (
            <div className="h-full overflow-y-auto">
              <div className="max-w-2xl mx-auto p-8 space-y-6">
                <div>
                  <span className="kicker">Settings</span>
                  <h2 className="text-[19px] font-semibold text-white mt-1">Connection & scope</h2>
                </div>

                <div className="app-card divide-y divide-white/[0.06]">
                  <div className="px-4 py-3.5 flex items-center justify-between gap-3">
                    <span className="text-[13px] text-slate-400">Backend API base URL</span>
                    <code className="text-[12.5px] font-data text-emerald-400">{RoboWeaverAPI.baseUrl}</code>
                  </div>
                  <div className="px-4 py-3.5 flex items-center justify-between gap-3">
                    <span className="text-[13px] text-slate-400">Connection status</span>
                    <span className={`text-[13px] font-medium ${apiOnline ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {apiOnline ? 'Connected' : 'Offline'}
                    </span>
                  </div>
                </div>

                <div>
                  <span className="kicker">System</span>
                  <h2 className="text-[15px] font-semibold text-white mt-1">Compiler &amp; runtime version</h2>
                </div>

                {version ? (
                  <div className="app-card divide-y divide-white/[0.06]">
                    <div className="px-4 py-3.5 flex items-center justify-between gap-3">
                      <span className="text-[13px] text-slate-400">RoboWeaver version</span>
                      <code className="text-[12.5px] font-data text-cyan-400">v{version.roboweaver_version}</code>
                    </div>
                    <div className="px-4 py-3.5 flex items-center justify-between gap-3">
                      <span className="text-[13px] text-slate-400">RoboIR schema version</span>
                      <code className="text-[12.5px] font-data text-cyan-400">v{version.ir_version}</code>
                    </div>
                    <div className="px-4 py-3.5 flex items-center justify-between gap-3">
                      <span className="text-[13px] text-slate-400">Python</span>
                      <code className="text-[12.5px] font-data text-slate-300">{version.python_version}</code>
                    </div>
                    <div className="px-4 py-3.5 flex items-center justify-between gap-3">
                      <span className="text-[13px] text-slate-400">Platform</span>
                      <code className="text-[12.5px] font-data text-slate-300">{version.platform}</code>
                    </div>
                    <div className="px-4 py-3.5 flex items-center justify-between gap-3">
                      <span className="text-[13px] text-slate-400">Registered robots</span>
                      <code className="text-[12.5px] font-data text-slate-300">{version.registered_robots}</code>
                    </div>
                    <div className="px-4 py-3.5 flex items-center justify-between gap-3">
                      <span className="text-[13px] text-slate-400">Self-healing supervisor</span>
                      <span className={`text-[12.5px] font-medium ${version.self_healing_active ? 'text-cyan-400' : 'text-amber-400'}`}>
                        {version.self_healing_active ? 'Active — auto-restarts on crash' : 'Off (--no-self-heal)'}
                      </span>
                    </div>
                    <div className="px-4 py-3.5 flex items-center justify-between gap-3">
                      <span className="text-[13px] text-slate-400">Process uptime</span>
                      <code className="text-[12.5px] font-data text-slate-300">
                        {version.uptime_seconds !== null ? `${Math.floor(version.uptime_seconds)}s` : 'unknown'}
                      </code>
                    </div>
                  </div>
                ) : (
                  <p className="text-[12.5px] text-slate-500">
                    No version info — the backend isn&apos;t reachable at {RoboWeaverAPI.baseUrl}.
                  </p>
                )}

                <p className="text-[12.5px] text-slate-500 leading-relaxed">
                  Override the backend location with the{' '}
                  <code className="font-data text-slate-400">NEXT_PUBLIC_ROBOWEAVER_API</code> environment variable
                  at build time if the dashboard server runs on a different host or port.
                </p>

                <div className="flex items-start gap-3 px-4 py-3.5 rounded-lg bg-white/[0.02] border border-white/[0.06]">
                  <Info className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
                  <p className="text-[12.5px] text-slate-500 leading-relaxed">
                    This workbench drives the RoboWeaver compiler and its built-in simulators only. No physical
                    robot or live ROS 2/DDS network is attached — the hardware bridges attempt a real connection
                    and honestly report when nothing answers.
                  </p>
                </div>
              </div>
            </div>
          )}
        </ErrorBoundary>
          </main>

            <TerminalPanel robots={robots} robot={terminalRobot} onRobotChange={setTerminalRobot} />
          </div>
        </div>

      <StatusBar
        apiOnline={apiOnline}
        robotCount={robots.length}
        activeRobot={terminalRobot}
        version={version?.roboweaver_version}
      />
    </div>
  );
}
