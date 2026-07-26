'use client';

import React, { useState } from 'react';
import { Sidebar } from '../components/Sidebar';
import { TopBar } from '../components/TopBar';
import { IncidentControlPanel } from '../components/IncidentControlPanel';
import { KnowledgeNexusView } from '../components/KnowledgeNexusView';
import { LiveSimulationView } from '../components/LiveSimulationView';
import { MOCK_INCIDENTS, MOCK_ROBOTICS_PACKAGES } from '../data/mockData';
import { TabType, Incident, WorkflowStep } from '../types';
import { 
  AlertTriangle, 
  Database, 
  Cpu, 
  Activity, 
  ShieldCheck, 
  ArrowUpRight, 
  CheckCircle2, 
  Bot,
  Sparkles,
  Layers,
  Terminal
} from 'lucide-react';

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabType>('incidents');
  const [incidents, setIncidents] = useState<Incident[]>(MOCK_INCIDENTS);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string>('INC-2026-894');
  const [searchQuery, setSearchQuery] = useState('');

  const activeIncidentsCount = incidents.filter((inc) => inc.status === 'pending_review').length;

  const handleUpdateStatus = (
    id: string,
    status: 'approved' | 'rejected' | 'escalated',
    note?: string
  ) => {
    setIncidents((prev) =>
      prev.map((inc) => {
        if (inc.id !== id) return inc;
        const updatedSteps = inc.steps.map((step) =>
          step.id === 6
            ? {
                ...step,
                status: (status === 'approved' ? 'approved' : 'rejected') as WorkflowStep['status'],
                detail: note || `Updated to ${status}`,
              }
            : step
        );
        return {
          ...inc,
          status,
          steps: updatedSteps,
        };
      })
    );
  };

  const handleResetDemo = () => {
    setIncidents(MOCK_INCIDENTS);
    setSelectedIncidentId('INC-2026-894');
  };

  return (
    <div className="flex h-screen w-screen bg-[#090d16] text-slate-100 overflow-hidden font-sans">
      {/* Left Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        activeIncidentsCount={activeIncidentsCount}
      />

      {/* Main Workspace Column */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <TopBar
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onOpenIncidentModal={() => setActiveTab('incidents')}
        />

        {/* Dynamic Tab Body Render */}
        <main className="flex-1 min-h-0 overflow-hidden relative">
          {activeTab === 'incidents' && (
            <IncidentControlPanel
              incidents={incidents}
              selectedId={selectedIncidentId}
              onSelectIncident={setSelectedIncidentId}
              onUpdateStatus={handleUpdateStatus}
              onResetDemo={handleResetDemo}
            />
          )}

          {activeTab === 'nexus' && (
            <KnowledgeNexusView packages={MOCK_ROBOTICS_PACKAGES} />
          )}

          {activeTab === 'simulation' && <LiveSimulationView />}

          {activeTab === 'dashboard' && (
            <div className="h-full overflow-y-auto p-6 space-y-8 bg-[#090d16]">
              {/* Executive Welcome Banner */}
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 rounded-3xl bg-gradient-to-r from-slate-900 via-slate-900/90 to-slate-950 border border-slate-800 shadow-2xl">
                <div className="space-y-2">
                  <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-semibold">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    <span>OpsSentinel Executive Dashboard • Lead SRE & Robotics On-Call</span>
                  </div>
                  <h1 className="text-2xl font-extrabold tracking-tight text-white">
                    RoboWeaver Multi-Robot OS & HITL Governance Center
                  </h1>
                  <p className="text-sm text-slate-400 max-w-2xl leading-relaxed">
                    Unifying autonomous error remediation, ROS 2 dependency knowledge graphs, and real-time Inspire Hand RS485 kinematics simulation.
                  </p>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <button
                    onClick={() => setActiveTab('incidents')}
                    className="px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs shadow-lg shadow-emerald-500/20 transition-all flex items-center gap-2"
                  >
                    <AlertTriangle className="w-4 h-4" />
                    <span>Review {activeIncidentsCount} Active Incidents</span>
                  </button>
                  <button
                    onClick={() => setActiveTab('nexus')}
                    className="px-5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-200 font-semibold text-xs transition-colors"
                  >
                    Open Knowledge Nexus
                  </button>
                </div>
              </div>

              {/* Top KPI Cards Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div
                  onClick={() => setActiveTab('incidents')}
                  className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800 hover:border-rose-500/40 transition-all cursor-pointer group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-400">HITL Review Queue</span>
                    <AlertTriangle className="w-4 h-4 text-rose-400 group-hover:scale-110 transition-transform" />
                  </div>
                  <div className="text-3xl font-extrabold font-mono text-white mt-2">
                    {activeIncidentsCount} Active
                  </div>
                  <div className="text-[11px] text-rose-400 mt-1">Requires human sign-off</div>
                </div>

                <div
                  onClick={() => setActiveTab('nexus')}
                  className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800 hover:border-emerald-500/40 transition-all cursor-pointer group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-400">Indexed ROS 2 Pkgs</span>
                    <Database className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
                  </div>
                  <div className="text-3xl font-extrabold font-mono text-white mt-2">
                    {MOCK_ROBOTICS_PACKAGES.length} Packages
                  </div>
                  <div className="text-[11px] text-emerald-400 mt-1">
                    Humble & Jazzy Distros
                  </div>
                </div>

                <div
                  onClick={() => setActiveTab('simulation')}
                  className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800 hover:border-purple-500/40 transition-all cursor-pointer group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-400">Live Hardware Sim</span>
                    <Cpu className="w-4 h-4 text-purple-400 group-hover:scale-110 transition-transform" />
                  </div>
                  <div className="text-3xl font-extrabold font-mono text-white mt-2">
                    RH56F1-E2
                  </div>
                  <div className="text-[11px] text-purple-400 mt-1">6-DOF RS485 Active</div>
                </div>

                <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-400">Agent Auto-Fix Rate</span>
                    <Activity className="w-4 h-4 text-teal-400" />
                  </div>
                  <div className="text-3xl font-extrabold font-mono text-white mt-2">94.8%</div>
                  <div className="text-[11px] text-teal-400 mt-1">3.0s avg fix generation</div>
                </div>
              </div>

              {/* Quick Jump Sections */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Recent Incidents Card */}
                <div className="p-6 rounded-3xl bg-slate-900/70 border border-slate-800 shadow-xl space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-rose-400" />
                      <h3 className="text-sm font-bold text-slate-100">
                        Pending HITL Remediation Queue
                      </h3>
                    </div>
                    <button
                      onClick={() => setActiveTab('incidents')}
                      className="text-xs font-semibold text-emerald-400 hover:underline flex items-center gap-1"
                    >
                      <span>Open Diff Viewer</span>
                      <ArrowUpRight className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <div className="space-y-3">
                    {incidents.map((inc) => (
                      <div
                        key={inc.id}
                        onClick={() => {
                          setSelectedIncidentId(inc.id);
                          setActiveTab('incidents');
                        }}
                        className="p-4 rounded-2xl bg-slate-950/80 hover:bg-slate-950 border border-slate-800/80 hover:border-slate-700 transition-all cursor-pointer flex items-center justify-between group"
                      >
                        <div className="min-w-0 pr-4">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-bold text-emerald-400">
                              {inc.id}
                            </span>
                            <span className="text-xs font-bold text-slate-200 truncate group-hover:text-white">
                              {inc.title}
                            </span>
                          </div>
                          <div className="text-[11px] text-slate-500 font-mono mt-0.5">
                            {inc.service} • {inc.timestamp}
                          </div>
                        </div>

                        <span
                          className={`text-[10px] px-2.5 py-1 rounded-full font-bold uppercase shrink-0 ${
                            inc.status === 'approved'
                              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                              : inc.status === 'escalated'
                              ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                              : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                          }`}
                        >
                          {inc.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Quick Knowledge Nexus & Simulation Card */}
                <div className="p-6 rounded-3xl bg-slate-900/70 border border-slate-800 shadow-xl space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Database className="w-4 h-4 text-emerald-400" />
                      <h3 className="text-sm font-bold text-slate-100">
                        Indexed Robotics Packages & Hardware
                      </h3>
                    </div>
                    <button
                      onClick={() => setActiveTab('nexus')}
                      className="text-xs font-semibold text-emerald-400 hover:underline flex items-center gap-1"
                    >
                      <span>Explore Nexus</span>
                      <ArrowUpRight className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {MOCK_ROBOTICS_PACKAGES.slice(0, 4).map((pkg) => (
                      <div
                        key={pkg.id}
                        onClick={() => setActiveTab('nexus')}
                        className="p-3.5 rounded-2xl bg-slate-950/80 hover:bg-slate-950 border border-slate-800/80 hover:border-emerald-500/30 transition-all cursor-pointer group"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs font-bold text-white group-hover:text-emerald-400 truncate">
                            {pkg.name}
                          </span>
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 uppercase">
                            {pkg.category}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-400 mt-1 line-clamp-2">
                          {pkg.description}
                        </p>
                      </div>
                    ))}
                  </div>

                  <div className="pt-2 border-t border-slate-800 flex items-center justify-between">
                    <div className="text-xs text-slate-400">
                      Need to test Inspire Hand kinematics before deploy?
                    </div>
                    <button
                      onClick={() => setActiveTab('simulation')}
                      className="px-3.5 py-1.5 rounded-xl bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 font-semibold text-xs border border-purple-500/30 transition-all"
                    >
                      Launch Digital Twin →
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'activity' && (
            <div className="p-6 space-y-4 overflow-y-auto h-full">
              <h2 className="text-lg font-bold text-white">Agent Activity & Audit Logs</h2>
              <div className="space-y-2 font-mono text-xs text-slate-300">
                <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl">
                  [14:02:16] AI Remediation Node generated fix for DB pool manager (Tokens: 1300)
                </div>
                <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl">
                  [13:48:07] RS485 CRC driver fix generated for Inspire Hand Modbus RTU
                </div>
                <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl">
                  [13:21:04] TurtleBot4 card_scanner_ws EKF drift fix approved by John Smith
                </div>
              </div>
            </div>
          )}

          {activeTab === 'settings' && (
            <div className="p-6 space-y-4 overflow-y-auto h-full">
              <h2 className="text-lg font-bold text-white">OpsSentinel Governance Settings</h2>
              <p className="text-xs text-slate-400">
                Configure automated Human-in-the-Loop thresholds, ROS 2 RAG vector indexing paths, and Modbus serial baud rates.
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
