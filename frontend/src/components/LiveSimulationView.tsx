'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { ShieldCheck, AlertTriangle, Cable, Hand, Radio, Loader2 } from 'lucide-react';
import { RoboWeaverAPI } from '../lib/api';
import { SimObjectProfile, SimulateResult } from '../types';
import { DigitalTwinViewport } from './DigitalTwinViewport';
import { Robot3DModel } from './Robot3DModel';

const FINGER_LABELS = ['Thumb Flex', 'Thumb Abduct', 'Index Finger', 'Middle Finger', 'Ring Finger', 'Pinky Finger'];

const GRASP_STATE_MAP: Record<string, 'Open' | 'Precision Grip' | 'Pinch' | 'Power Grasp'> = {
  open: 'Open',
  precision_grip: 'Precision Grip',
  pinch: 'Pinch',
  fist: 'Power Grasp',
  point: 'Power Grasp',
  cylindrical_grip: 'Power Grasp',
  relax: 'Open',
};

export const LiveSimulationView: React.FC = () => {
  const [gestures, setGestures] = useState<string[]>([]);
  const [objects, setObjects] = useState<SimObjectProfile[]>([]);
  const [gesture, setGesture] = useState('precision_grip');
  const [objectKey, setObjectKey] = useState('medical_vial');
  const [result, setResult] = useState<SimulateResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  const addLog = useCallback((msg: string) => {
    const timeStr = new Date().toTimeString().split(' ')[0];
    setLogs((prev) => [`[${timeStr}] ${msg}`, ...prev.slice(0, 8)]);
  }, []);

  useEffect(() => {
    Promise.all([RoboWeaverAPI.simulateGestures(), RoboWeaverAPI.simulateObjects()])
      .then(([g, o]) => {
        setGestures(g);
        setObjects(o);
      })
      .catch(() => setError(true));
  }, []);

  const runSimulation = useCallback(
    async (g: string, o: string) => {
      try {
        const data = await RoboWeaverAPI.simulate(g, o);
        setResult(data);
        setError(false);
        addLog(
          data.is_simulated
            ? `${g} on ${o} — software simulation (${data.connect_fallback_reason ?? 'no RS485 hardware detected'})`
            : `${g} on ${o} — real RS485 hardware round trip confirmed`
        );
        addLog(`Total actuator force ${data.total_force_n.toFixed(1)} N — ${data.object_status}`);
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    },
    [addLog]
  );

  useEffect(() => {
    // Standard mount-time data fetch (React's documented pattern for effects without a
    // fetching library). The static rule can't see that all setState calls inside
    // runSimulation happen after its first `await`, so this is a deliberate, safe exception.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    runSimulation(gesture, objectKey);
    // Intentionally mount-only: re-running on every gesture/objectKey change would duplicate
    // the fetch already triggered by handleGestureChange/handleObjectChange below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleGestureChange = (g: string) => {
    setGesture(g);
    setLoading(true);
    runSimulation(g, objectKey);
  };

  const handleObjectChange = (o: string) => {
    setObjectKey(o);
    setLoading(true);
    runSimulation(gesture, o);
  };

  const graspState = GRASP_STATE_MAP[gesture] ?? 'Open';
  const selectedObject = objects.find((o) => o.id === objectKey);

  return (
    <div className="h-full overflow-y-auto">
      <div className="w-full space-y-6 px-4 py-5 sm:px-6 sm:py-7 xl:px-8">
        <div>
          <span className="kicker">Hand simulator</span>
          <h1 className="text-[19px] font-semibold text-white mt-1">Test an Inspire Hand grasp in software</h1>
          <p className="text-[13px] text-slate-400 mt-1.5 leading-relaxed max-w-2xl">
            Choose a gesture and object to calculate actuator force, current draw, and slip risk.
            This view models Inspire Hand grasps only; it is not a universal physics simulator.
          </p>
        </div>

        {error && (
          <div className="flex items-center gap-2.5 px-4 py-3 rounded-lg bg-rose-500/[0.07] border border-rose-500/20 text-rose-300 text-[13px]">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>Could not reach the RoboWeaver backend. Start it with: roboweaver dashboard --port 8080</span>
          </div>
        )}

        {result && (
          <div
            className={`flex items-center gap-2.5 px-4 py-2.5 rounded-lg border text-[12.5px] font-medium ${
              result.is_simulated
                ? 'bg-amber-500/[0.07] border-amber-500/20 text-amber-300'
                : 'bg-emerald-500/[0.07] border-emerald-500/20 text-emerald-300'
            }`}
          >
            <Radio className={`w-3.5 h-3.5 shrink-0 ${result.is_simulated ? '' : 'animate-pulse'}`} />
            <span>
              {result.is_simulated
                ? `Software simulation — no physical hand detected (${result.connect_fallback_reason ?? 'unknown'})`
                : 'Real RS485 hardware — CRC-16 verified round trip'}
            </span>
          </div>
        )}

        <DigitalTwinViewport
          graspState={graspState}
          actuatorPositions={result?.actuator_positions}
          heldObjectDiameterM={selectedObject ? selectedObject.diameter_mm / 1000 : undefined}
        />

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          <div className="lg:col-span-8 space-y-5">
            <div className="app-card p-5 space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <Hand className="w-4 h-4 text-slate-500" />
                  <h3 className="text-[13px] font-semibold text-slate-200">Actuator telemetry</h3>
                </div>
                {loading && <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />}
              </div>

              <div className="space-y-2.5 pt-1 border-t border-white/[0.06]">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11.5px] text-slate-500 font-medium mr-1">Gesture</span>
                  {gestures.map((g) => (
                    <button
                      key={g}
                      onClick={() => handleGestureChange(g)}
                      className={`px-2.5 py-1 rounded-md text-[11.5px] font-medium capitalize transition-colors ${
                        gesture === g
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                      }`}
                    >
                      {g.replace(/_/g, ' ')}
                    </button>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11.5px] text-slate-500 font-medium mr-1">Object</span>
                  {objects.map((o) => (
                    <button
                      key={o.id}
                      onClick={() => handleObjectChange(o.id)}
                      className={`px-2.5 py-1 rounded-md text-[11.5px] font-medium transition-colors ${
                        objectKey === o.id
                          ? 'bg-violet-500/15 text-violet-300'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                      }`}
                    >
                      {o.name}
                    </button>
                  ))}
                </div>
              </div>

              {result && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                  {FINGER_LABELS.map((label, idx) => {
                    const pos = result.actuator_positions[idx] ?? 0;
                    const force = result.actuator_forces_n[idx] ?? 0;
                    const current = result.actuator_currents_ma[idx] ?? 0;
                    return (
                      <div key={label} className="app-well rounded-lg p-3.5 space-y-2.5">
                        <div className="flex items-center justify-between">
                          <span className="text-[12px] font-medium text-slate-200">{label}</span>
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                              force > 0 ? 'bg-emerald-500/15 text-emerald-400' : 'bg-white/[0.04] text-slate-500'
                            }`}
                          >
                            {force > 0 ? 'Contact' : 'No contact'}
                          </span>
                        </div>
                        <div className="space-y-1">
                          <div className="flex justify-between text-[10.5px] text-slate-500">
                            <span>Position</span>
                            <span className="font-data text-slate-300">{pos} / 1000</span>
                          </div>
                          <div className="h-1.5 w-full bg-black/30 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                              style={{ width: `${Math.min(100, pos / 10)}%` }}
                            />
                          </div>
                        </div>
                        <div className="space-y-1">
                          <div className="flex justify-between text-[10.5px] text-slate-500">
                            <span>Force / current</span>
                            <span className="font-data text-slate-300">
                              {force.toFixed(1)} N · {current} mA
                            </span>
                          </div>
                          <div className="h-1.5 w-full bg-black/30 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-violet-500 rounded-full transition-all duration-300"
                              style={{ width: `${Math.min(100, (force / 40) * 100)}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="app-card p-5 space-y-3">
              <div className="flex items-center gap-2">
                <Radio className="w-4 h-4 text-slate-500" />
                <h3 className="text-[13px] font-semibold text-slate-200">Simulation event log</h3>
              </div>
              <div className="app-well rounded-lg p-3.5 font-data text-[11.5px] text-slate-400 space-y-1 max-h-44 overflow-y-auto">
                {logs.length === 0 && <span className="text-slate-600">No events yet.</span>}
                {logs.map((log, idx) => (
                  <div key={idx} className="flex items-start gap-2">
                    <span className="text-emerald-600 select-none">›</span>
                    <span className="break-all">{log}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="lg:col-span-4 space-y-5">
            <div className="app-card p-5 space-y-4">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-slate-500" />
                <h3 className="text-[13px] font-semibold text-slate-200">Grasp stability</h3>
              </div>

              <div className="app-well rounded-lg py-5 text-center space-y-1.5">
                <div className="text-3xl font-semibold font-data text-emerald-400">
                  {result ? (result.slip_risk * 100).toFixed(1) : '--'}%
                </div>
                <div className="text-[11px] text-slate-500">Calculated slip risk</div>
                <div className="inline-block mt-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 text-[11px] font-medium">
                  {result?.object_status ?? 'Awaiting simulation'}
                </div>
              </div>

              <div className="space-y-2 pt-1 border-t border-white/[0.06] text-[12.5px]">
                <div className="flex justify-between">
                  <span className="text-slate-500">Object</span>
                  <span className="font-data text-slate-300">{result?.object_name ?? '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Stability score</span>
                  <span className="font-data text-slate-300">
                    {result ? `${(result.stability_score * 100).toFixed(0)}%` : '—'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Total actuator force</span>
                  <span className="font-data text-slate-300">{result ? `${result.total_force_n.toFixed(1)} N` : '—'}</span>
                </div>
              </div>
            </div>

            <div className="app-card p-5 space-y-2.5">
              <div className="flex items-center gap-2">
                <Cable className="w-4 h-4 text-slate-500" />
                <h3 className="text-[13px] font-semibold text-slate-200">Wire protocol</h3>
              </div>
              <p className="text-[12px] text-slate-400 leading-relaxed">
                Requests are framed with real CRC-16/MODBUS checksums over RS485 (115200 baud, 8N1). When no
                physical hand answers, the driver honestly falls back to a software grasp-physics model instead
                of faking a hardware link — see{' '}
                <code className="font-data text-slate-300">tests/test_inspire_hand_real_serial_protocol.py</code>{' '}
                for a proof against a virtual serial loopback.
              </p>
            </div>
          </div>
        </div>

        <Robot3DModel />
      </div>
    </div>
  );
};
