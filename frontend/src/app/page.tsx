'use client';

import React, { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { TopNav } from '../components/nav/TopNav';
import { viewMetaFor } from '../components/nav/viewMeta';
import { AICopilotPanel } from '../components/AICopilotPanel';
import { RoboWeaverAPI } from '../lib/api';
import { AccessInfo, ViewType, RobotProfile, NexusPackage, DiscoveredRobot, VersionInfo } from '../types';
import {
  Code2,
  Database,
  Boxes,
  Radar,
  ArrowUpRight,
  AlertTriangle,
  Activity,
  Info,
} from 'lucide-react';

// Every view body is loaded on demand rather than bundled into the initial
// page. LiveSimulationView alone pulls in three.js + @react-three/fiber +
// @react-three/drei -- a ~1MB chunk -- via DigitalTwinViewport/Robot3DModel.
// `ssr: false` on all of them because every view fetches its own data
// client-side (RoboWeaverAPI) and renders nothing meaningful without a
// browser; the shared loading fallback keeps navigation from looking broken
// while the chunk streams in.
const viewLoading = () => (
  <div className="h-full flex items-center justify-center">
    <div className="flex items-center gap-2.5 text-slate-500 text-[13px]">
      <div className="w-4 h-4 rounded-full border-2 border-cyan-400/30 border-t-cyan-400 animate-spin" />
      Loading…
    </div>
  </div>
);

const CompilerView = dynamic(() => import('../components/CompilerView').then((m) => m.CompilerView), {
  ssr: false, loading: viewLoading,
});
const CompareView = dynamic(() => import('../components/CompareView').then((m) => m.CompareView), {
  ssr: false, loading: viewLoading,
});
const BenchmarkView = dynamic(() => import('../components/BenchmarkView').then((m) => m.BenchmarkView), {
  ssr: false, loading: viewLoading,
});
const WorkcellBuilderView = dynamic(
  () => import('../components/WorkcellBuilderView').then((m) => m.WorkcellBuilderView),
  { ssr: false, loading: viewLoading }
);
const KnowledgeNexusView = dynamic(
  () => import('../components/KnowledgeNexusView').then((m) => m.KnowledgeNexusView),
  { ssr: false, loading: viewLoading }
);
const KnowledgeGraphView = dynamic(
  () => import('../components/KnowledgeGraphView').then((m) => m.KnowledgeGraphView),
  { ssr: false, loading: viewLoading }
);
const FleetRegistryView = dynamic(
  () => import('../components/FleetRegistryView').then((m) => m.FleetRegistryView),
  { ssr: false, loading: viewLoading }
);
// The heaviest one: three.js + react-three-fiber + drei live behind this import.
const LiveSimulationView = dynamic(
  () => import('../components/LiveSimulationView').then((m) => m.LiveSimulationView),
  { ssr: false, loading: viewLoading }
);
const RobotConnectView = dynamic(
  () => import('../components/RobotConnectView').then((m) => m.RobotConnectView),
  { ssr: false, loading: viewLoading }
);
const ResearchLabView = dynamic(
  () => import('../components/ResearchLabView').then((m) => m.ResearchLabView),
  { ssr: false, loading: viewLoading }
);

export default function Home() {
  const [activeView, setActiveView] = useState<ViewType>('overview');
  const [apiOnline, setApiOnline] = useState(false);
  const [robots, setRobots] = useState<RobotProfile[]>([]);
  const [packages, setPackages] = useState<NexusPackage[]>([]);
  const [discovered, setDiscovered] = useState<DiscoveredRobot[]>([]);
  const [version, setVersion] = useState<VersionInfo | null>(null);
  const [access, setAccess] = useState<AccessInfo | null>(null);
  const [graphNodeCount, setGraphNodeCount] = useState(0);
  const activeMeta = viewMetaFor(activeView);

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

    // One passive scan on load so the overview KPI reflects what is actually
    // reachable. RobotConnectView re-scans on demand.
    RoboWeaverAPI.discover()
      .then((res) => setDiscovered(res.discovered))
      .catch(() => setDiscovered([]));

    // Real version/uptime/self-heal status straight from the running process --
    // null while unknown, never a fabricated placeholder.
    RoboWeaverAPI.version()
      .then(setVersion)
      .catch(() => setVersion(null));

    RoboWeaverAPI.access()
      .then(setAccess)
      .catch(() => setAccess(null));

    RoboWeaverAPI.graph()
      .then((g) => setGraphNodeCount(g.nodes.length))
      .catch(() => {});
  }, []);

  return (
    <div className="flex h-dvh w-full flex-col overflow-hidden bg-app-surface text-slate-100 lg:flex-row">
      <TopNav active={activeView} onNavigate={setActiveView} apiOnline={apiOnline} />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="workspace-header hidden h-20 shrink-0 items-center justify-between gap-5 px-6 lg:flex xl:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.035] text-cyan-300">
              <activeMeta.icon className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <h1 className="truncate text-[15px] font-semibold text-white">{activeMeta.label}</h1>
              <p className="truncate text-[11.5px] text-slate-500">{activeMeta.description}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.025] px-3 py-1.5 text-[11px] text-slate-400">
              <Activity className={`h-3.5 w-3.5 ${apiOnline ? 'text-cyan-300' : 'text-rose-400'}`} />
              {apiOnline ? 'Runtime healthy' : 'Runtime unavailable'}
            </div>
            <button
              onClick={() => setActiveView('compile')}
              className="btn-neon flex items-center gap-2 px-3.5 py-2 text-[12px]"
            >
              <Code2 className="h-3.5 w-3.5" /> Build a program
            </button>
          </div>
        </header>

        {/* AI Co-Pilot — persistent floating panel across all views */}
        <AICopilotPanel activeView={activeView} />

        <main className="relative min-h-0 flex-1 overflow-hidden">
        <ErrorBoundary resetKey={activeView}>
          {activeView === 'compile' && <CompilerView />}
          {activeView === 'compare' && <CompareView />}
          {activeView === 'workcell' && <WorkcellBuilderView />}
          {activeView === 'packages' && <KnowledgeNexusView />}
          {activeView === 'graph' && <KnowledgeGraphView />}
          {activeView === 'robots' && <FleetRegistryView />}
          {activeView === 'connect' && <RobotConnectView />}
          {activeView === 'twin' && <LiveSimulationView />}
          {activeView === 'benchmark' && <BenchmarkView />}
          {activeView === 'research' && <ResearchLabView />}

          {activeView === 'overview' && (
            <div className="h-full overflow-y-auto">
              <div className="w-full space-y-8 px-4 py-5 sm:px-6 sm:py-7 xl:px-8">
                <section className="app-card grid overflow-hidden lg:grid-cols-[1.25fr_0.75fr]">
                  <div className="relative flex flex-col justify-center border-b border-white/[0.07] p-6 sm:p-8 lg:border-b-0 lg:border-r">
                    <div className="pointer-events-none absolute -left-28 -top-28 h-64 w-64 rounded-full bg-cyan-300/[0.055] blur-3xl" />
                    <div className="relative max-w-2xl">
                      <div className="mb-4 flex flex-wrap items-center gap-2">
                        <span className="kicker">Start here</span>
                        <span className={`rounded-full border px-2 py-1 text-[10px] font-semibold ${
                          apiOnline
                            ? 'border-cyan-300/20 bg-cyan-300/[0.07] text-cyan-200'
                            : 'border-rose-300/20 bg-rose-300/[0.07] text-rose-200'
                        }`}>
                          {apiOnline ? 'Runtime ready' : 'Runtime offline'}
                        </span>
                      </div>
                      <h2 className="max-w-xl text-balance text-2xl font-semibold leading-tight tracking-[-0.025em] text-white sm:text-[32px]">
                        Describe one job. See which robots can run it.
                      </h2>
                      <p className="mt-4 max-w-xl text-[13px] leading-6 text-slate-400">
                        RoboWeaver turns your sentence into ordered robot actions, checks each selected
                        robot, calculates motion, and prepares downloadable code. Assumptions and missing
                        evidence are always shown separately.
                      </p>
                      <div className="mt-6 flex flex-col gap-2.5 sm:flex-row">
                        <button
                          onClick={() => setActiveView('compile')}
                          className="btn-neon flex items-center justify-center gap-2 px-4 py-2.5 text-[13px]"
                        >
                          <Code2 className="h-4 w-4" /> Build a robot program
                        </button>
                        <button
                          onClick={() => setActiveView('compare')}
                          className="flex items-center justify-center gap-2 rounded-[0.625rem] border border-white/[0.1] bg-white/[0.035] px-4 py-2.5 text-[13px] font-semibold text-slate-200 hover:border-white/[0.18] hover:bg-white/[0.06]"
                        >
                          Help me choose a robot <ArrowUpRight className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="bg-[#0b121d]/70 p-5 sm:p-6">
                    <div className="mb-4 flex items-center justify-between">
                      <div>
                        <p className="text-[12px] font-semibold text-slate-200">What happens after you click compile</p>
                        <p className="mt-0.5 text-[10.5px] text-slate-600">A real compiler workflow, in plain language</p>
                      </div>
                      <span className="font-data text-[10px] text-cyan-300">RoboIR v{version?.ir_version ?? '—'}</span>
                    </div>
                    <div className="space-y-2">
                      {[
                        { view: 'compile' as ViewType, step: '01', label: 'Understand the request', detail: 'Find the action, objects, and limits' },
                        { view: 'compile' as ViewType, step: '02', label: 'Make an action plan', detail: 'Create ordered executable tasks' },
                        { view: 'compare' as ViewType, step: '03', label: 'Check each robot', detail: 'Plan motion and reject unsafe targets' },
                        { view: 'compile' as ViewType, step: '04', label: 'Prepare the download', detail: 'Generate robot-ready output' },
                      ].map((stage) => (
                        <button
                          key={stage.step}
                          onClick={() => setActiveView(stage.view)}
                          className="app-well group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:border-cyan-300/20"
                        >
                          <span className="font-data text-[10px] font-semibold text-cyan-300">{stage.step}</span>
                          <span className="min-w-0 flex-1">
                            <span className="block text-[12px] font-semibold text-slate-200">{stage.label}</span>
                            <span className="block truncate text-[10.5px] text-slate-600">{stage.detail}</span>
                          </span>
                          <ArrowUpRight className="h-3.5 w-3.5 text-slate-700 group-hover:text-cyan-300" />
                        </button>
                      ))}
                    </div>
                  </div>
                </section>

                {!apiOnline && (
                  <div className="flex items-center gap-2.5 px-4 py-3 rounded-lg bg-amber-500/[0.07] border border-amber-500/20 text-amber-300 text-[13px]">
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                    <span>
                      Backend offline. Start it with <code className="font-data">roboweaver dashboard --port 8080</code> to
                      load live data.
                    </span>
                  </div>
                )}

                <section aria-label="System metrics" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4 stagger-children">
                  {[
                    {
                      view: 'compile' as ViewType,
                      label: 'Compiler runtime',
                      value: apiOnline ? 'Ready' : 'Offline',
                      detail: version ? `v${version.roboweaver_version} · ${Math.floor(version.uptime_seconds ?? 0)}s uptime` : 'Awaiting runtime metadata',
                      icon: Code2,
                      tint: apiOnline ? 'text-cyan-400' : 'text-rose-400',
                    },
                    {
                      view: 'robots' as ViewType,
                      label: 'Fleet coverage',
                      value: String(robots.length),
                      detail: `${discovered.length} endpoint${discovered.length === 1 ? '' : 's'} currently reachable`,
                      icon: Boxes,
                      tint: 'text-cyan-400',
                    },
                    {
                      view: 'packages' as ViewType,
                      label: 'Knowledge assets',
                      value: String(packages.length),
                      detail: `${graphNodeCount} evidence graph node${graphNodeCount === 1 ? '' : 's'}`,
                      icon: Database,
                      tint: 'text-violet-400',
                    },
                    {
                      view: 'connect' as ViewType,
                      label: 'Connection scan',
                      value: discovered.length > 0 ? 'Active' : 'Clear',
                      detail: discovered.length > 0 ? 'Review discovered controllers' : 'No standard control ports answered',
                      icon: Radar,
                      tint: discovered.length > 0 ? 'text-amber-400' : 'text-cyan-400',
                    },
                  ].map((kpi) => (
                    <button
                      key={kpi.label}
                      onClick={() => setActiveView(kpi.view)}
                      className="app-card group p-5 text-left hover:-translate-y-0.5"
                    >
                      <div className="mb-4 flex items-center justify-between">
                        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">{kpi.label}</span>
                        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/[0.04]">
                          <kpi.icon className={`h-4 w-4 ${kpi.tint}`} />
                        </span>
                      </div>
                      <div className="font-data text-2xl font-semibold text-white">{kpi.value}</div>
                      <p className="mt-1 truncate text-[10.5px] text-slate-600">{kpi.detail}</p>
                    </button>
                  ))}
                </section>

                {/* Quick panels */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                  <div className="app-card p-6 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-[13.5px] font-semibold text-slate-200">Fleet registry</h3>
                      <button
                        onClick={() => setActiveView('robots')}
                        className="flex items-center gap-1 text-[12px] font-medium text-emerald-400 hover:text-emerald-300 transition-colors"
                      >
                        Open <ArrowUpRight className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="space-y-2">
                      {robots.slice(0, 4).map((r) => (
                        <div
                          key={r.id}
                          onClick={() => setActiveView('robots')}
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
                        onClick={() => setActiveView('packages')}
                        className="flex items-center gap-1 text-[12px] font-medium text-emerald-400 hover:text-emerald-300 transition-colors"
                      >
                        Open <ArrowUpRight className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {packages.slice(0, 4).map((pkg) => (
                        <div
                          key={pkg.id}
                          onClick={() => setActiveView('packages')}
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
                      <span className="text-[12px] text-slate-500">Test a modeled Inspire Hand grasp?</span>
                      <button
                        onClick={() => setActiveView('twin')}
                        className="shrink-0 px-3 py-1.5 rounded-lg bg-violet-500/10 hover:bg-violet-500/15 text-violet-300 text-[12px] font-medium border border-violet-500/20 transition-colors"
                      >
                        Hand simulator →
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
                      onClick={() => setActiveView('connect')}
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
                          onClick={() => setActiveView('connect')}
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

          {activeView === 'settings' && (
            <div className="h-full overflow-y-auto">
              <div className="w-full space-y-6 px-4 py-5 sm:px-6 sm:py-7 xl:px-8">
                <div>
                  <span className="kicker">Settings</span>
                  <h2 className="text-[19px] font-semibold text-white mt-1">Runtime connection and versions</h2>
                </div>

                <div className="app-card divide-y divide-white/[0.06]">
                  <div className="px-4 py-3.5 flex items-center justify-between gap-3">
                    <span className="text-[13px] text-slate-400">Backend API base URL</span>
                    <code className="text-[12.5px] font-data text-emerald-400">{RoboWeaverAPI.baseUrl}</code>
                  </div>
                  <div className="px-4 py-3.5 flex items-center justify-between gap-3">
                    <span className="text-[13px] text-slate-400">Access mode</span>
                    <span className="text-right text-[12.5px] font-medium text-cyan-300">
                      {access?.mode === 'lan' ? 'LAN · shared compiler' : access ? 'Local workstation' : 'Unknown'}
                    </span>
                  </div>
                  <div className="px-4 py-3.5 flex items-center justify-between gap-3">
                    <span className="text-[13px] text-slate-400">Physical control from browsers</span>
                    <span className={`text-[12.5px] font-medium ${access?.hardware_control ? 'text-amber-300' : 'text-emerald-400'}`}>
                      {access?.hardware_control ? 'Explicitly enabled' : 'Blocked'}
                    </span>
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
                      <span className="text-[13px] text-slate-400">Native LLVM/MLIR tool</span>
                      <code className={`text-[12.5px] font-data ${version.native_mlir.available ? 'text-emerald-400' : 'text-amber-300'}`}>
                        {version.native_mlir.available ? version.native_mlir.version ?? 'available' : 'not installed'}
                      </code>
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
                  Requests use the same-origin server proxy by default, keeping the API token out of browser
                  JavaScript. For local development only, override the backend location with the{' '}
                  <code className="font-data text-slate-400">NEXT_PUBLIC_ROBOWEAVER_API</code> environment variable
                  at build time.
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
      </div>
    </div>
  );
}
