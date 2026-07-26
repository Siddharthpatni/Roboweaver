'use client';

import React, { useState } from 'react';
import { 
  Cpu, 
  Activity, 
  Play, 
  Pause, 
  RotateCcw, 
  ShieldCheck, 
  AlertTriangle, 
  Zap, 
  Thermometer, 
  Sliders, 
  Hand,
  Radio
} from 'lucide-react';
import { SimRobotState } from '../types';
import { INITIAL_SIM_ROBOT } from '../data/mockData';

export const LiveSimulationView: React.FC = () => {
  const [robot, setRobot] = useState<SimRobotState>(INITIAL_SIM_ROBOT);
  const [isSimulating, setIsSimulating] = useState(true);
  const [simLogs, setSimLogs] = useState<string[]>([
    '[14:05:01] ROS 2 Node /inspire_hand_driver initialized on /dev/ttyUSB0 (115200 baud)',
    '[14:05:02] Modbus CRC-16 Check: Passed. All 6 actuators reporting normal torque limits.',
    '[14:05:05] Grasp mode set to [Precision Grip]. Thumb + Index contact confirmed (24.0 N).'
  ]);

  const addLog = (msg: string) => {
    const timeStr = new Date().toTimeString().split(' ')[0];
    setSimLogs((prev) => [`[${timeStr}] ${msg}`, ...prev.slice(0, 8)]);
  };

  const handleGraspChange = (mode: 'Open' | 'Precision Grip' | 'Pinch' | 'Power Grasp') => {
    let updatedFingers = [...robot.fingers];
    let slipRisk = 12.0;

    if (mode === 'Open') {
      updatedFingers = updatedFingers.map((f) => ({ ...f, angleDeg: 0, forceN: 0, contact: false }));
      slipRisk = 0.0;
    } else if (mode === 'Precision Grip') {
      updatedFingers = [
        { name: 'Thumb (Rot)', angleDeg: 42, forceN: 18.5, targetN: 20.0, contact: true },
        { name: 'Thumb (Flex)', angleDeg: 55, forceN: 22.1, targetN: 22.0, contact: true },
        { name: 'Index Finger', angleDeg: 68, forceN: 24.0, targetN: 25.0, contact: true },
        { name: 'Middle Finger', angleDeg: 65, forceN: 21.8, targetN: 22.0, contact: true },
        { name: 'Ring Finger', angleDeg: 30, forceN: 4.2, targetN: 5.0, contact: false },
        { name: 'Little Finger', angleDeg: 28, forceN: 2.1, targetN: 2.0, contact: false },
      ];
      slipRisk = 14.2;
    } else if (mode === 'Pinch') {
      updatedFingers = [
        { name: 'Thumb (Rot)', angleDeg: 60, forceN: 25.0, targetN: 25.0, contact: true },
        { name: 'Thumb (Flex)', angleDeg: 75, forceN: 28.0, targetN: 28.0, contact: true },
        { name: 'Index Finger', angleDeg: 78, forceN: 26.5, targetN: 27.0, contact: true },
        { name: 'Middle Finger', angleDeg: 10, forceN: 0.0, targetN: 0.0, contact: false },
        { name: 'Ring Finger', angleDeg: 10, forceN: 0.0, targetN: 0.0, contact: false },
        { name: 'Little Finger', angleDeg: 10, forceN: 0.0, targetN: 0.0, contact: false },
      ];
      slipRisk = 8.5;
    } else if (mode === 'Power Grasp') {
      updatedFingers = updatedFingers.map((f) => ({
        ...f,
        angleDeg: 88,
        forceN: 35.0,
        targetN: 35.0,
        contact: true
      }));
      slipRisk = 3.1;
    }

    setRobot((prev) => ({
      ...prev,
      graspState: mode,
      slipRiskPercentage: slipRisk,
      fingers: updatedFingers
    }));
    addLog(`Commanded Modbus RTU Grasp Preset: [${mode}]. Updated actuator force targets.`);
  };

  const handleReset = () => {
    setRobot(INITIAL_SIM_ROBOT);
    addLog('Reset simulation kinematics to default Precision Grip state.');
  };

  return (
    <div className="flex flex-col h-full w-full bg-[#090d16] text-slate-100 overflow-y-auto p-6 space-y-6">
      {/* Hero Banner: Live Simulation Mode */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 rounded-3xl bg-gradient-to-r from-slate-900 via-slate-900/90 to-slate-950 border border-slate-800 shadow-2xl">
        <div className="space-y-2 max-w-2xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-500/10 border border-purple-500/30 text-purple-400 text-xs font-semibold">
            <Cpu className="w-3.5 h-3.5" />
            <span>RoboWeaver Dexterous Manipulation • Live Kinematics Sim</span>
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight text-white">
            Inspire Hand RH56F1-E2 Real-Time Digital Twin
          </h1>
          <p className="text-sm text-slate-400 leading-relaxed">
            Live hardware simulation testing RS485 Modbus RTU frame telemetry, 6-DOF finger joint angles, tactile force feedback, and slip risk prediction before deployment.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={() => setIsSimulating(!isSimulating)}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-xl font-bold text-xs shadow-lg transition-all ${
              isSimulating
                ? 'bg-amber-500 hover:bg-amber-400 text-slate-950 shadow-amber-500/20'
                : 'bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-emerald-500/20'
            }`}
          >
            {isSimulating ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
            <span>{isSimulating ? 'Pause Telemetry' : 'Resume Telemetry'}</span>
          </button>

          <button
            onClick={handleReset}
            className="p-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300"
            title="Reset Simulation"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Simulation Control Cards Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Hand Visualization & Actuator Status (8 cols) */}
        <div className="lg:col-span-8 space-y-6">
          {/* Actuator Fingers Card */}
          <div className="p-6 rounded-3xl bg-slate-900/70 border border-slate-800 shadow-xl space-y-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Hand className="w-5 h-5 text-emerald-400" />
                <h3 className="text-base font-bold text-slate-100">
                  6-DOF Actuator Finger Telemetry & Tactile Feedback
                </h3>
              </div>
              <span className="text-xs font-mono text-slate-400">
                Grasp Mode:{' '}
                <span className="text-emerald-400 font-semibold">{robot.graspState}</span>
              </span>
            </div>

            {/* Grasp Presets Bar */}
            <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-800/80">
              <span className="text-xs text-slate-400 font-semibold mr-2">Grasp Presets:</span>
              {(['Open', 'Precision Grip', 'Pinch', 'Power Grasp'] as const).map((mode) => {
                const isCurrent = robot.graspState === mode;
                return (
                  <button
                    key={mode}
                    onClick={() => handleGraspChange(mode)}
                    className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                      isCurrent
                        ? 'bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/20'
                        : 'bg-slate-950 text-slate-300 hover:text-white border border-slate-800'
                    }`}
                  >
                    {mode}
                  </button>
                );
              })}
            </div>

            {/* 6 Finger Bars Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
              {robot.fingers.map((finger, idx) => (
                <div
                  key={idx}
                  className="p-4 rounded-2xl bg-slate-950/80 border border-slate-800/80 space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold font-mono text-slate-200">
                      {finger.name}
                    </span>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                        finger.contact
                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                          : 'bg-slate-800 text-slate-500'
                      }`}
                    >
                      {finger.contact ? 'In Contact' : 'No Contact'}
                    </span>
                  </div>

                  {/* Joint Angle Bar */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-[11px] text-slate-400">
                      <span>Joint Angle</span>
                      <span className="font-mono text-slate-200 font-semibold">
                        {finger.angleDeg}°
                      </span>
                    </div>
                    <div className="h-2 w-full bg-slate-900 rounded-full overflow-hidden border border-slate-800">
                      <div
                        className="h-full bg-gradient-to-r from-teal-500 to-emerald-400 rounded-full transition-all duration-300"
                        style={{ width: `${Math.min(100, (finger.angleDeg / 90) * 100)}%` }}
                      />
                    </div>
                  </div>

                  {/* Tactile Force Bar */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-[11px] text-slate-400">
                      <span>Tactile Force</span>
                      <span className="font-mono text-emerald-400 font-semibold">
                        {finger.forceN.toFixed(1)} N / {finger.targetN.toFixed(1)} N
                      </span>
                    </div>
                    <div className="h-2 w-full bg-slate-900 rounded-full overflow-hidden border border-slate-800">
                      <div
                        className="h-full bg-gradient-to-r from-purple-500 to-indigo-400 rounded-full transition-all duration-300"
                        style={{ width: `${Math.min(100, (finger.forceN / 40) * 100)}%` }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ROS 2 Topic Console & Modbus Log Stream */}
          <div className="p-6 rounded-3xl bg-slate-900/70 border border-slate-800 shadow-xl space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Radio className="w-4 h-4 text-emerald-400 animate-pulse" />
                <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                  Live ROS 2 & RS485 Modbus Telemetry Stream
                </h3>
              </div>
              <span className="text-[10px] font-mono text-emerald-400">115200 Baud • CRC OK</span>
            </div>

            <div className="p-4 rounded-2xl bg-[#090d16] border border-slate-800/80 font-mono text-xs text-slate-300 space-y-1.5 max-h-44 overflow-y-auto">
              {simLogs.map((log, idx) => (
                <div key={idx} className="flex items-start gap-2">
                  <span className="text-emerald-500 select-none">&gt;</span>
                  <span className="break-all">{log}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column: Hardware Metrics & Slip Risk (4 cols) */}
        <div className="lg:col-span-4 space-y-6">
          {/* Slip Risk & Stability Card */}
          <div className="p-6 rounded-3xl bg-slate-900/70 border border-slate-800 shadow-xl space-y-5">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
              <h3 className="text-base font-bold text-slate-100">Grasp Stability & Slip Risk</h3>
            </div>

            <div className="flex flex-col items-center justify-center p-6 rounded-2xl bg-slate-950 border border-slate-800 text-center">
              <div className="text-4xl font-extrabold font-mono text-emerald-400">
                {robot.slipRiskPercentage.toFixed(1)}%
              </div>
              <div className="text-xs text-slate-400 mt-1">Calculated Slip Probability</div>
              <div className="mt-3 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-semibold">
                Stable • Friction Margin OK
              </div>
            </div>

            <div className="space-y-3 pt-2 border-t border-slate-800/80 text-xs">
              <div className="flex justify-between text-slate-300">
                <span>Protocol</span>
                <span className="font-mono text-slate-200">{robot.protocol}</span>
              </div>
              <div className="flex justify-between text-slate-300">
                <span>Bus Interface</span>
                <span className="font-mono text-slate-200">{robot.bus}</span>
              </div>
            </div>
          </div>

          {/* Environmental Sensors */}
          <div className="p-6 rounded-3xl bg-slate-900/70 border border-slate-800 shadow-xl space-y-4">
            <div className="flex items-center gap-2">
              <Thermometer className="w-5 h-5 text-purple-400" />
              <h3 className="text-base font-bold text-slate-100">Environmental Sensors</h3>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 text-center">
                <div className="text-xs text-slate-400">Motor Temp</div>
                <div className="text-xl font-mono font-bold text-white mt-1">
                  {robot.temperature} °C
                </div>
                <div className="text-[10px] text-emerald-400 mt-0.5">Optimal Range</div>
              </div>

              <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 text-center">
                <div className="text-xs text-slate-400">Bus Voltage</div>
                <div className="text-xl font-mono font-bold text-white mt-1">
                  {robot.voltage} V
                </div>
                <div className="text-[10px] text-emerald-400 mt-0.5">Nominal 24V</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
