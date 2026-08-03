'use client';

import React, { useEffect, useState } from 'react';
import { Gauge, Weight, Ruler, Loader2, AlertTriangle, Box, Download } from 'lucide-react';
import { RoboWeaverAPI } from '../lib/api';
import { RobotProfile } from '../types';

export const FleetRegistryView: React.FC = () => {
  const [robots, setRobots] = useState<RobotProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [downloading, setDownloading] = useState<Record<string, boolean>>({});
  const [downloadError, setDownloadError] = useState<Record<string, string>>({});

  useEffect(() => {
    RoboWeaverAPI.robots()
      .then((data) => {
        setRobots(data);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, []);

  const handleDownloadUrdf = async (robot: RobotProfile) => {
    setDownloading((d) => ({ ...d, [robot.id]: true }));
    setDownloadError((d) => ({ ...d, [robot.id]: '' }));
    try {
      const xml = await RoboWeaverAPI.robotUrdf(robot.id);
      const blob = new Blob([xml], { type: 'application/xml' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${robot.id}.urdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setDownloadError((d) => ({
        ...d,
        [robot.id]: 'Could not reach the backend to generate the URDF.',
      }));
    } finally {
      setDownloading((d) => ({ ...d, [robot.id]: false }));
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-6xl mx-auto p-8 space-y-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <span className="kicker">Fleet Registry</span>
            <h1 className="text-[19px] font-semibold text-white mt-1">Hardware abstraction layer</h1>
            <p className="text-[13px] text-slate-400 mt-1.5 leading-relaxed max-w-xl">
              Every embodiment in the robot registry, from 3-DOF service AMRs to 20-DOF dexterous hands — each
              with its own N-DOF kinematic chain, joint limits, and payload envelope.
            </p>
          </div>
          <div className="app-card px-4 py-3 text-right shrink-0">
            <div className="text-[10.5px] text-slate-500">Registered embodiments</div>
            <div className="text-xl font-semibold font-data text-cyan-400">{robots.length}</div>
          </div>
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-slate-500 text-[13px]">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading fleet registry…
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2.5 px-4 py-3 rounded-lg bg-rose-500/[0.07] border border-rose-500/20 text-rose-300 text-[13px]">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>Could not reach the RoboWeaver backend. Start it with: roboweaver dashboard --port 8080</span>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {robots.map((r) => (
            <div key={r.id} className="app-card p-5 flex flex-col justify-between hover:border-white/[0.14] transition-colors">
              <div className="space-y-3.5">
                <div>
                  <h3 className="text-[13.5px] font-semibold text-slate-100">{r.name}</h3>
                  <div className="text-[11px] text-slate-500 mt-0.5">{r.manufacturer}</div>
                </div>

                <p className="text-[12px] text-slate-400 leading-relaxed min-h-[36px]">{r.description}</p>

                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="app-well rounded-lg py-2">
                    <Gauge className="w-3.5 h-3.5 text-cyan-400 mx-auto mb-1" />
                    <div className="text-[13px] font-semibold font-data text-white">{r.dof}</div>
                    <div className="text-[9.5px] text-slate-500">DOF</div>
                  </div>
                  <div className="app-well rounded-lg py-2">
                    <Weight className="w-3.5 h-3.5 text-emerald-400 mx-auto mb-1" />
                    <div className="text-[13px] font-semibold font-data text-white">{r.payload_capacity_kg}</div>
                    <div className="text-[9.5px] text-slate-500">kg</div>
                  </div>
                  <div className="app-well rounded-lg py-2">
                    <Ruler className="w-3.5 h-3.5 text-violet-400 mx-auto mb-1" />
                    <div className="text-[13px] font-semibold font-data text-white">{r.max_reach_m}</div>
                    <div className="text-[9.5px] text-slate-500">m reach</div>
                  </div>
                </div>
              </div>

              <div className="pt-3 mt-3.5 border-t border-white/[0.06] space-y-2.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-slate-500 capitalize">{r.gripper_type.replace(/_/g, ' ')}</span>
                  <span className="px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 font-data">{r.id}</span>
                </div>

                <button
                  onClick={() => handleDownloadUrdf(r)}
                  disabled={downloading[r.id]}
                  className="w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-md bg-violet-500/10 hover:bg-violet-500/15 border border-violet-500/20 text-violet-300 text-[11.5px] font-medium disabled:opacity-50 transition-colors"
                  title="Generate a URDF from this robot's real kinematic spec — the same numbers the IK solver plans against, not an invented mesh"
                >
                  {downloading[r.id] ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Box className="w-3.5 h-3.5" />
                  )}
                  {downloading[r.id] ? 'Generating…' : 'Download URDF'}
                  <Download className="w-3 h-3 opacity-60" />
                </button>
                {downloadError[r.id] && (
                  <p className="text-[10.5px] text-rose-400 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3 shrink-0" />
                    {downloadError[r.id]}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
