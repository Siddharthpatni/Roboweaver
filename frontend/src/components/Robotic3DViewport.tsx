'use client';

import React, { useRef, useEffect, useState } from 'react';
import { 
  Box, 
  RotateCcw, 
  Eye, 
  Maximize2, 
  Layers, 
  Activity, 
  Cpu, 
  Compass,
  Radio,
  Sliders,
  ShieldCheck
} from 'lucide-react';

interface Robotic3DViewportProps {
  graspState: 'Open' | 'Precision Grip' | 'Pinch' | 'Power Grasp';
  activeRobot?: 'inspire_hand' | 'franka_arm' | 'turtlebot4_scanner';
}

interface Point3D {
  x: number;
  y: number;
  z: number;
}

interface Projected2D {
  x: number;
  y: number;
  depth: number;
}

export const Robotic3DViewport: React.FC<Robotic3DViewportProps> = ({
  graspState,
  activeRobot = 'inspire_hand',
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [selectedRobot, setSelectedRobot] = useState<'inspire_hand' | 'franka_arm' | 'turtlebot4_scanner'>(activeRobot);
  const [yaw, setYaw] = useState<number>(35);
  const [pitch, setPitch] = useState<number>(25);
  const [zoom, setZoom] = useState<number>(1.1);
  const [isWireframe, setIsWireframe] = useState<boolean>(false);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [lastMousePos, setLastMousePos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [fps, setFps] = useState<number>(60);
  const [animTime, setAnimTime] = useState<number>(0);

  // Project 3D coordinate (x,y,z) to 2D canvas (x,y) with camera yaw and pitch
  const project3D = (pt: Point3D, width: number, height: number): Projected2D => {
    const radYaw = (yaw * Math.PI) / 180;
    const radPitch = (pitch * Math.PI) / 180;

    // Rotate around Y axis (Yaw)
    const x1 = pt.x * Math.cos(radYaw) - pt.z * Math.sin(radYaw);
    const z1 = pt.x * Math.sin(radYaw) + pt.z * Math.cos(radYaw);
    const y1 = pt.y;

    // Rotate around X axis (Pitch)
    const y2 = y1 * Math.cos(radPitch) - z1 * Math.sin(radPitch);
    const z2 = y1 * Math.sin(radPitch) + z1 * Math.cos(radPitch);
    const x2 = x1;

    // Perspective projection
    const distance = 400;
    const scale = (distance / (distance + z2 + 200)) * 140 * zoom;

    return {
      x: width / 2 + x2 * scale,
      y: height / 2 - y2 * scale,
      depth: z2,
    };
  };

  // Handle Canvas Mouse Orbit
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    setIsDragging(true);
    setLastMousePos({ x: e.clientX, y: e.clientY });
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDragging) return;
    const dx = e.clientX - lastMousePos.x;
    const dy = e.clientY - lastMousePos.y;
    setYaw((prev) => (prev + dx * 0.6) % 360);
    setPitch((prev) => Math.max(-80, Math.min(80, prev + dy * 0.6)));
    setLastMousePos({ x: e.clientX, y: e.clientY });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Rendering Loop
  useEffect(() => {
    let animationFrameId: number;
    let lastTime = performance.now();

    const render = (time: number) => {
      const dt = time - lastTime;
      if (dt > 0) {
        setFps(Math.round(1000 / dt));
      }
      lastTime = time;
      setAnimTime(time * 0.002);

      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const width = canvas.width;
      const height = canvas.height;

      // Clear Canvas with Obsidian Mecha gradient
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = '#050914';
      ctx.fillRect(0, 0, width, height);

      // Draw Cyberpunk Grid Floor
      ctx.strokeStyle = 'rgba(16, 185, 129, 0.12)';
      ctx.lineWidth = 1;
      const gridSize = 100;
      const step = 20;
      for (let i = -gridSize; i <= gridSize; i += step) {
        // X lines
        const p1 = project3D({ x: i, y: -40, z: -gridSize }, width, height);
        const p2 = project3D({ x: i, y: -40, z: gridSize }, width, height);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();

        // Z lines
        const p3 = project3D({ x: -gridSize, y: -40, z: i }, width, height);
        const p4 = project3D({ x: gridSize, y: -40, z: i }, width, height);
        ctx.beginPath();
        ctx.moveTo(p3.x, p3.y);
        ctx.lineTo(p4.x, p4.y);
        ctx.stroke();
      }

      // Draw 3D Axes HUD Indicator (Bottom Left corner projection)
      const orig = project3D({ x: -80, y: -40, z: -80 }, width, height);
      const xAxis = project3D({ x: -50, y: -40, z: -80 }, width, height);
      const yAxis = project3D({ x: -80, y: -10, z: -80 }, width, height);
      const zAxis = project3D({ x: -80, y: -40, z: -50 }, width, height);

      // X arrow (Red)
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(orig.x, orig.y);
      ctx.lineTo(xAxis.x, xAxis.y);
      ctx.stroke();

      // Y arrow (Green)
      ctx.strokeStyle = '#10b981';
      ctx.beginPath();
      ctx.moveTo(orig.x, orig.y);
      ctx.lineTo(yAxis.x, yAxis.y);
      ctx.stroke();

      // Z arrow (Blue)
      ctx.strokeStyle = '#3b82f6';
      ctx.beginPath();
      ctx.moveTo(orig.x, orig.y);
      ctx.lineTo(zAxis.x, zAxis.y);
      ctx.stroke();

      // Draw Selected 3D Robot Kinematics
      if (selectedRobot === 'inspire_hand') {
        draw3DInspireHand(ctx, width, height, graspState, isWireframe);
      } else if (selectedRobot === 'franka_arm') {
        draw3DFrankaArm(ctx, width, height, time, isWireframe);
      } else {
        draw3DTurtleBot(ctx, width, height, time, isWireframe);
      }

      // Draw Targeting Radar HUD Crosshair in center
      ctx.strokeStyle = 'rgba(6, 182, 212, 0.25)';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.arc(width / 2, height / 2, 70, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);

      animationFrameId = requestAnimationFrame(render);
    };

    animationFrameId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animationFrameId);
  }, [yaw, pitch, zoom, isWireframe, selectedRobot, graspState]);

  // Helper: Draw 3D Line between two 3D points
  const draw3DLine = (
    ctx: CanvasRenderingContext2D,
    p1: Point3D,
    p2: Point3D,
    color: string,
    width: number,
    w: number,
    h: number
  ) => {
    const pr1 = project3D(p1, w, h);
    const pr2 = project3D(p2, w, h);
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.moveTo(pr1.x, pr1.y);
    ctx.lineTo(pr2.x, pr2.y);
    ctx.stroke();
  };

  // Draw 6-DOF Inspire Hand RH56F1-E2
  const draw3DInspireHand = (
    ctx: CanvasRenderingContext2D,
    w: number,
    h: number,
    state: string,
    wire: boolean
  ) => {
    // Kinematic bend factor based on Grasp Mode
    let bend = 0.0;
    let thumbBend = 0.0;
    if (state === 'Precision Grip') {
      bend = 0.65;
      thumbBend = 0.7;
    } else if (state === 'Pinch') {
      bend = 0.85;
      thumbBend = 0.85;
    } else if (state === 'Power Grasp') {
      bend = 0.95;
      thumbBend = 0.95;
    }

    // Draw Palm Box (Chassis)
    const palmColor = wire ? '#06b6d4' : '#0f172a';
    const edgeColor = '#10b981';

    // Palm 8 corners
    const corners: Point3D[] = [
      { x: -25, y: -20, z: -10 },
      { x: 25, y: -20, z: -10 },
      { x: 25, y: 10, z: -10 },
      { x: -25, y: 10, z: -10 },
      { x: -25, y: -20, z: 10 },
      { x: 25, y: -20, z: 10 },
      { x: 25, y: 10, z: 10 },
      { x: -25, y: 10, z: 10 },
    ];

    // Palm bounding frame
    const edges = [
      [0, 1], [1, 2], [2, 3], [3, 0],
      [4, 5], [5, 6], [6, 7], [7, 4],
      [0, 4], [1, 5], [2, 6], [3, 7]
    ];
    edges.forEach(([a, b]) => draw3DLine(ctx, corners[a], corners[b], edgeColor, 2, w, h));

    // Draw 5 Finger Kinematic Chains (Thumb, Index, Middle, Ring, Pinky)
    const fingers = [
      { name: 'Thumb', baseX: -30, baseY: 0, baseZ: 5, angleMult: thumbBend, isThumb: true },
      { name: 'Index', baseX: -15, baseY: 12, baseZ: 0, angleMult: bend, isThumb: false },
      { name: 'Middle', baseX: -5, baseY: 14, baseZ: 0, angleMult: bend, isThumb: false },
      { name: 'Ring', baseX: 7, baseY: 13, baseZ: 0, angleMult: bend * 0.5, isThumb: false },
      { name: 'Pinky', baseX: 18, baseY: 11, baseZ: 0, angleMult: bend * 0.3, isThumb: false },
    ];

    fingers.forEach((f) => {
      const pBase = { x: f.baseX, y: f.baseY, z: f.baseZ };
      const len1 = 25;
      const len2 = 20;

      // Proximal phalanx angle
      const theta1 = f.isThumb ? (f.angleMult * 1.1) : (f.angleMult * 1.25);
      const pMid = {
        x: pBase.x + (f.isThumb ? Math.cos(theta1) * len1 * 0.5 : 0),
        y: pBase.y + Math.cos(theta1) * len1,
        z: pBase.z - Math.sin(theta1) * len1,
      };

      // Distal phalanx angle
      const theta2 = theta1 * 1.4;
      const pTip = {
        x: pMid.x + (f.isThumb ? 6 : 0),
        y: pMid.y + Math.cos(theta2) * len2,
        z: pMid.z - Math.sin(theta2) * len2,
      };

      // Render finger segments
      draw3DLine(ctx, pBase, pMid, '#06b6d4', 5, w, h);
      draw3DLine(ctx, pMid, pTip, '#10b981', 4, w, h);

      // Render joint nodes as glowing dots
      const prMid = project3D(pMid, w, h);
      const prTip = project3D(pTip, w, h);
      ctx.fillStyle = '#10b981';
      ctx.beginPath();
      ctx.arc(prMid.x, prMid.y, 4, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#00f0ff';
      ctx.beginPath();
      ctx.arc(prTip.x, prTip.y, 3, 0, Math.PI * 2);
      ctx.fill();
    });

    // Draw Grasp Object in Palm Center if gripping
    if (state !== 'Open') {
      const objCenter = { x: -5, y: 25, z: -5 };
      const prObj = project3D(objCenter, w, h);
      ctx.strokeStyle = '#f59e0b';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(prObj.x, prObj.y, 16, 0, Math.PI * 2);
      ctx.stroke();

      // Force Vector Arrows from thumb and index
      draw3DLine(ctx, { x: -25, y: 20, z: 0 }, objCenter, '#ef4444', 2, w, h);
      draw3DLine(ctx, { x: -15, y: 32, z: -10 }, objCenter, '#ef4444', 2, w, h);
    }
  };

  // Draw 7-DOF Franka Emika Panda Arm
  const draw3DFrankaArm = (
    ctx: CanvasRenderingContext2D,
    w: number,
    h: number,
    time: number,
    wire: boolean
  ) => {
    const sw = Math.sin(time * 0.001) * 15;
    const cw = Math.cos(time * 0.001) * 15;

    const base = { x: 0, y: -40, z: 0 };
    const j1 = { x: 0, y: -20, z: 0 };
    const j2 = { x: 0, y: 10, z: 10 };
    const j3 = { x: sw, y: 35, z: 5 };
    const j4 = { x: sw + cw, y: 60, z: -10 };
    const eff = { x: sw + cw, y: 75, z: -15 };

    draw3DLine(ctx, base, j1, '#64748b', 8, w, h);
    draw3DLine(ctx, j1, j2, '#06b6d4', 7, w, h);
    draw3DLine(ctx, j2, j3, '#06b6d4', 6, w, h);
    draw3DLine(ctx, j3, j4, '#10b981', 5, w, h);
    draw3DLine(ctx, j4, eff, '#f59e0b', 4, w, h);

    // Parallel Gripper Claws
    draw3DLine(ctx, eff, { x: eff.x - 8, y: eff.y + 10, z: eff.z }, '#10b981', 3, w, h);
    draw3DLine(ctx, eff, { x: eff.x + 8, y: eff.y + 10, z: eff.z }, '#10b981', 3, w, h);
  };

  // Draw TurtleBot 4 Card Scanner Mobile Robot
  const draw3DTurtleBot = (
    ctx: CanvasRenderingContext2D,
    w: number,
    h: number,
    time: number,
    wire: boolean
  ) => {
    // Round Chassis Perimeter
    const center = { x: 0, y: -25, z: 0 };
    const radius = 30;
    const steps = 16;
    for (let i = 0; i < steps; i++) {
      const a1 = (i / steps) * Math.PI * 2;
      const a2 = ((i + 1) / steps) * Math.PI * 2;
      const p1 = { x: Math.cos(a1) * radius, y: -25, z: Math.sin(a1) * radius };
      const p2 = { x: Math.cos(a2) * radius, y: -25, z: Math.sin(a2) * radius };
      draw3DLine(ctx, p1, p2, '#10b981', 3, w, h);
    }

    // Rotating LiDAR Top Scanner
    const lidarAngle = (time * 0.004) % (Math.PI * 2);
    const lidarTop = { x: 0, y: -5, z: 0 };
    const lidarBeam = {
      x: Math.cos(lidarAngle) * 45,
      y: -5,
      z: Math.sin(lidarAngle) * 45
    };
    draw3DLine(ctx, center, lidarTop, '#06b6d4', 6, w, h);
    draw3DLine(ctx, lidarTop, lidarBeam, '#ef4444', 2, w, h);

    // Card Scanner Module Front
    const cardReader = { x: 28, y: -15, z: 0 };
    draw3DLine(ctx, { x: 28, y: -25, z: -8 }, { x: 28, y: -25, z: 8 }, '#f59e0b', 4, w, h);
    draw3DLine(ctx, { x: 28, y: -10, z: -8 }, { x: 28, y: -10, z: 8 }, '#f59e0b', 4, w, h);
  };

  return (
    <div className="robotic-card p-4 rounded-2xl border border-slate-800 bg-[#050914] overflow-hidden">
      {/* Top Header Controls HUD */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
        <div className="flex items-center gap-2">
          <Box className="w-5 h-5 text-emerald-400 animate-pulse" />
          <span className="text-sm font-bold text-slate-100 font-mono tracking-wider">
            [SYS_HUD] 3D KINEMATICS DIGITAL TWIN VIEWPORT
          </span>
          <span className="px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[10px] font-mono">
            FPS: {fps}
          </span>
        </div>

        {/* Robot Selector Buttons */}
        <div className="flex items-center gap-1.5 bg-slate-900/90 p-1 rounded-xl border border-slate-800">
          {(
            [
              { id: 'inspire_hand', label: 'RH56F1 Hand (6-DOF)' },
              { id: 'franka_arm', label: 'Franka Arm (7-DOF)' },
              { id: 'turtlebot4_scanner', label: 'TurtleBot 4 Scanner' },
            ] as const
          ).map((item) => (
            <button
              key={item.id}
              onClick={() => setSelectedRobot(item.id)}
              className={`px-3 py-1 rounded-lg text-xs font-mono font-bold transition-all ${
                selectedRobot === item.id
                  ? 'bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/20'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* 3D Canvas Container */}
      <div className="relative mt-4 flex items-center justify-center bg-robotic-grid rounded-xl border border-slate-800/60 overflow-hidden">
        <canvas
          ref={canvasRef}
          width={760}
          height={380}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          className="w-full h-[380px] cursor-grab active:cursor-grabbing"
        />

        {/* Floating Top Left Telemetry Overlay */}
        <div className="absolute top-4 left-4 p-3 rounded-xl bg-slate-950/85 border border-slate-800/80 backdrop-blur-md space-y-1 font-mono text-[11px] text-slate-300 pointer-events-none">
          <div className="flex items-center gap-2 text-emerald-400 font-bold">
            <Activity className="w-3.5 h-3.5" />
            <span>ROBOTIC TELEMETRY LINK</span>
          </div>
          <div>MODEL: {selectedRobot.toUpperCase()}</div>
          <div>CAMERA ROT: YAW {Math.round(yaw)}° / PITCH {Math.round(pitch)}°</div>
          <div>GRASP PRESET: {graspState.toUpperCase()}</div>
          <div className="text-cyan-400">MODBUS RTU: OK (1.1 ms)</div>
        </div>

        {/* Floating Bottom Right Viewport Controls */}
        <div className="absolute bottom-4 right-4 flex items-center gap-2">
          <button
            onClick={() => {
              setYaw(35);
              setPitch(25);
              setZoom(1.1);
            }}
            className="px-3 py-1.5 rounded-lg bg-slate-900/90 hover:bg-slate-800 border border-slate-700 text-xs font-mono text-slate-200 shadow-md"
            title="Reset to Isometric View"
          >
            [ ISOMETRIC 3D ]
          </button>
          <button
            onClick={() => {
              setYaw(0);
              setPitch(5);
            }}
            className="px-3 py-1.5 rounded-lg bg-slate-900/90 hover:bg-slate-800 border border-slate-700 text-xs font-mono text-slate-200 shadow-md"
          >
            [ FRONT ]
          </button>
          <button
            onClick={() => {
              setYaw(90);
              setPitch(0);
            }}
            className="px-3 py-1.5 rounded-lg bg-slate-900/90 hover:bg-slate-800 border border-slate-700 text-xs font-mono text-slate-200 shadow-md"
          >
            [ SIDE ]
          </button>
          <button
            onClick={() => setIsWireframe(!isWireframe)}
            className={`px-3 py-1.5 rounded-lg border text-xs font-mono shadow-md ${
              isWireframe
                ? 'bg-cyan-500/20 border-cyan-500 text-cyan-400'
                : 'bg-slate-900/90 border-slate-700 text-slate-300'
            }`}
          >
            [ WIREFRAME ]
          </button>
        </div>
      </div>
    </div>
  );
};
