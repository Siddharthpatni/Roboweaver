'use client';

import React, { useEffect, useState } from 'react';
import { Sidebar } from '../components/Sidebar';
import { TopBar } from '../components/TopBar';
import { CompilerView } from '../components/CompilerView';
import { WorkcellBuilderView } from '../components/WorkcellBuilderView';
import { KnowledgeNexusView } from '../components/KnowledgeNexusView';
import { FleetRegistryView } from '../components/FleetRegistryView';
import { LiveSimulationView } from '../components/LiveSimulationView';
import { RoboWeaverAPI } from '../lib/api';
import { TabType, RobotProfile, NexusPackage } from '../types';
import {
  Wand2,
  Code2,
  Database,
  Boxes,
  Cpu,
  ArrowUpRight,
  AlertTriangle,
  Info,
} from 'lucide-react';

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');
  const [searchQuery, setSearchQuery] = useState('');
  const [apiOnline, setApiOnline] = useState(false);
  const [robots, setRobots] = useState<RobotProfile[]>([]);
  const [packages, setPackages] = useState<NexusPackage[]>([]);

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
  }, []);

  return (
    <div className="flex h-screen w-screen bg-[#060a12] text-slate-100 overflow-hidden">
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        packageCount={packages.length}
        robotCount={robots.length}
        apiOnline={apiOnline}
      />

      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <TopBar
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onLaunchBuilder={() => setActiveTab('builder')}
          apiOnline={apiOnline}
        />

        <main className="flex-1 min-h-0 overflow-hidden relative">
          {activeTab === 'compiler' && <CompilerView />}
          {activeTab === 'builder' && <WorkcellBuilderView />}
          {activeTab === 'nexus' && <KnowledgeNexusView />}
          {activeTab === 'fleet' && <FleetRegistryView />}
          {activeTab === 'simulation' && <LiveSimulationView />}

          {activeTab === 'dashboard' && (
            <div className="h-full overflow-y-auto">
              <div className="max-w-6xl mx-auto p-8 space-y-8">
                {/* Hero */}
                <div className="app-card hud-corners p-7 flex flex-col md:flex-row md:items-center justify-between gap-5">
                  <div className="space-y-2 max-w-xl">
                    <span className="kicker">Sid Labs / RoboWeaver</span>
                    <h1 className="text-[22px] font-semibold text-white leading-snug text-balance">
                      Human intent → RoboIR → verified robot skill
                    </h1>
                    <p className="text-[13px] text-slate-400 leading-relaxed">
                      An LLVM-like compiler for robotics. Describe a skill in plain English — RoboWeaver
                      compiles it through RoboIR, checks it against the target robot&apos;s real capabilities,
                      and synthesizes a ROS 2 BehaviorTree package, live from the engine.
                    </p>
                  </div>
                  <div className="flex items-center gap-2.5 shrink-0">
                    <button
                      onClick={() => setActiveTab('compiler')}
                      className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-[#0a0c11] text-[13px] font-semibold transition-colors"
                    >
                      <Code2 className="w-4 h-4" />
                      Compile a skill
                    </button>
                    <button
                      onClick={() => setActiveTab('builder')}
                      className="px-4 py-2.5 rounded-lg border border-white/10 hover:border-white/20 hover:bg-white/[0.03] text-slate-300 text-[13px] font-medium transition-colors"
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
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                  {[
                    {
                      tab: 'compiler' as TabType,
                      label: 'RoboIR compiler',
                      value: 'Ready',
                      icon: Code2,
                      tint: 'text-emerald-400',
                    },
                    {
                      tab: 'builder' as TabType,
                      label: 'Workcell builder',
                      value: 'Ready',
                      icon: Wand2,
                      tint: 'text-emerald-400',
                    },
                    {
                      tab: 'nexus' as TabType,
                      label: 'Indexed ROS 2 packages',
                      value: String(packages.length),
                      icon: Database,
                      tint: 'text-emerald-400',
                    },
                    {
                      tab: 'fleet' as TabType,
                      label: 'Registered robots',
                      value: String(robots.length),
                      icon: Boxes,
                      tint: 'text-rose-400',
                    },
                    {
                      tab: 'simulation' as TabType,
                      label: 'Digital twin',
                      value: 'RH56F1-E2',
                      icon: Cpu,
                      tint: 'text-violet-400',
                    },
                  ].map((kpi) => (
                    <button
                      key={kpi.label}
                      onClick={() => setActiveTab(kpi.tab)}
                      className="app-card p-5 text-left hover:border-white/[0.14] transition-colors group"
                    >
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-[11.5px] text-slate-500 font-medium">{kpi.label}</span>
                        <kpi.icon className={`w-4 h-4 ${kpi.tint} opacity-80 group-hover:opacity-100 transition-opacity`} />
                      </div>
                      <div className="text-2xl font-semibold font-data text-white">{kpi.value}</div>
                    </button>
                  ))}
                </div>

                {/* Quick panels */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                  <div className="app-card p-6 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-[13.5px] font-semibold text-slate-200">Fleet registry</h3>
                      <button
                        onClick={() => setActiveTab('fleet')}
                        className="flex items-center gap-1 text-[12px] font-medium text-emerald-400 hover:text-emerald-300 transition-colors"
                      >
                        Open <ArrowUpRight className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="space-y-2">
                      {robots.slice(0, 4).map((r) => (
                        <div
                          key={r.id}
                          onClick={() => setActiveTab('fleet')}
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
                        onClick={() => setActiveTab('nexus')}
                        className="flex items-center gap-1 text-[12px] font-medium text-emerald-400 hover:text-emerald-300 transition-colors"
                      >
                        Open <ArrowUpRight className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {packages.slice(0, 4).map((pkg) => (
                        <div
                          key={pkg.id}
                          onClick={() => setActiveTab('nexus')}
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
                        onClick={() => setActiveTab('simulation')}
                        className="shrink-0 px-3 py-1.5 rounded-lg bg-violet-500/10 hover:bg-violet-500/15 text-violet-300 text-[12px] font-medium border border-violet-500/20 transition-colors"
                      >
                        Digital twin →
                      </button>
                    </div>
                  </div>
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
        </main>
      </div>
    </div>
  );
}
