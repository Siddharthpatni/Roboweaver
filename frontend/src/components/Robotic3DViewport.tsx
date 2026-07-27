'use client';

import React, { useRef, useEffect, useState } from 'react';
import { Box, Activity } from 'lucide-react';

interface Robotic3DViewportProps {
  graspState: 'Open' | 'Precision Grip' | 'Pinch' | 'Power Grasp';
  activeRobot?: 'inspire_hand' | 'franka_arm' | 'turtlebot4_scanner';
  /** Real per-actuator positions (0-1000) from the backend InspireHandSimulator,
   * in FINGER_LABELS order: [Thumb Flex, Thumb Abduct, Index, Middle, Ring, Pinky].
   * When present, each finger's bend is driven by its own real telemetry value
   * instead of one shared state-based estimate. */
  actuatorPositions?: number[];
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

const FALLBACK_BEND: Record<string, number> = {
  Open: 0,
  'Precision Grip': 0.65,
  Pinch: 0.85,
  'Power Grasp': 0.95,
};

export const Robotic3DViewport: React.FC<Robotic3DViewportProps> = ({
  graspState,
  activeRobot = 'inspire_hand',
  actuatorPositions,
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

    // Perspective projection. The robot geometry below is authored in world units
    // spanning roughly ±25 to ±100 (palm block, arm reach, chassis radius) — the
    // per-unit pixel scale has to stay small or those coordinates land thousands of
    // pixels outside the canvas, leaving only a stray edge crossing the visible area.
    const distance = 400;
    const scale = (distance / (distance + z2 + 200)) * 3.6 * zoom;

    return {
      x: width / 2 + x2 * scale,
      y: height / 2 - y2 * scale,
      depth: z2,
    };
  };

  // Thin reference line (grid, axes, telemetry arrows) — not for robot geometry.
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

  // A solid, shaded "limb" segment: fills a screen-space quad between two projected
  // points with a cylindrical-looking gradient and rounded end caps, so a segment
  // reads as a machined part with volume instead of a bare stroked line.
  const draw3DThickLine = (
    ctx: CanvasRenderingContext2D,
    p1: Point3D,
    p2: Point3D,
    color: string,
    shadeColor: string,
    width: number,
    w: number,
    h: number
  ) => {
    const pr1 = project3D(p1, w, h);
    const pr2 = project3D(p2, w, h);
    const dx = pr2.x - pr1.x;
    const dy = pr2.y - pr1.y;
    const len = Math.max(Math.hypot(dx, dy), 0.0001);
    const nx = (-dy / len) * (width / 2);
    const ny = (dx / len) * (width / 2);

    const grad = ctx.createLinearGradient(pr1.x - nx, pr1.y - ny, pr1.x + nx, pr1.y + ny);
    grad.addColorStop(0, shadeColor);
    grad.addColorStop(0.5, color);
    grad.addColorStop(1, shadeColor);

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.moveTo(pr1.x - nx, pr1.y - ny);
    ctx.lineTo(pr1.x + nx, pr1.y + ny);
    ctx.lineTo(pr2.x + nx, pr2.y + ny);
    ctx.lineTo(pr2.x - nx, pr2.y - ny);
    ctx.closePath();
    ctx.fill();

    ctx.beginPath();
    ctx.arc(pr1.x, pr1.y, width / 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(pr2.x, pr2.y, width / 2, 0, Math.PI * 2);
    ctx.fill();
  };

  // A filled, flat-shaded polygon face — used to give the palm block and chassis
  // actual surfaces instead of open wireframe edges.
  const fillFace3D = (ctx: CanvasRenderingContext2D, pts: Point3D[], color: string, w: number, h: number) => {
    const proj = pts.map((p) => project3D(p, w, h));
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(proj[0].x, proj[0].y);
    for (let i = 1; i < proj.length; i++) ctx.lineTo(proj[i].x, proj[i].y);
    ctx.closePath();
    ctx.fill();
  };

  const drawJointNode = (ctx: CanvasRenderingContext2D, pt: Point3D, radius: number, w: number, h: number) => {
    const pr = project3D(pt, w, h);
    const grad = ctx.createRadialGradient(pr.x - radius * 0.3, pr.y - radius * 0.3, 0.5, pr.x, pr.y, radius);
    grad.addColorStop(0, '#ffdd7a');
    grad.addColorStop(0.55, '#d6291c');
    grad.addColorStop(1, '#5c0f09');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(pr.x, pr.y, radius, 0, Math.PI * 2);
    ctx.fill();
  };

  // A single glowing-azure energy accent (arc reactor / repulsor). Used sparingly —
  // everywhere else on the model is red, gold, or gunmetal.
  const drawGlowDot = (ctx: CanvasRenderingContext2D, pt: Point3D, radius: number, w: number, h: number) => {
    const pr = project3D(pt, w, h);
    const halo = ctx.createRadialGradient(pr.x, pr.y, 0, pr.x, pr.y, radius * 2.4);
    halo.addColorStop(0, 'rgba(191,244,255,0.9)');
    halo.addColorStop(0.4, 'rgba(34,211,238,0.5)');
    halo.addColorStop(1, 'rgba(34,211,238,0)');
    ctx.fillStyle = halo;
    ctx.beginPath();
    ctx.arc(pr.x, pr.y, radius * 2.4, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#bff4ff';
    ctx.beginPath();
    ctx.arc(pr.x, pr.y, radius * 0.5, 0, Math.PI * 2);
    ctx.fill();
  };

  // Draw 6-DOF Inspire Hand RH56F1-E2 — driven by the real per-actuator positions
  // returned by the backend InspireHandSimulator when available.
  const draw3DInspireHand = (
    ctx: CanvasRenderingContext2D,
    w: number,
    h: number,
    state: string,
    positions?: number[]
  ) => {
    const stateBend = FALLBACK_BEND[state] ?? 0;
    const bendOf = (idx: number, fallback: number) =>
      positions && positions[idx] !== undefined ? positions[idx] / 1000 : fallback;

    const thumbBend = bendOf(0, stateBend);
    const indexBend = bendOf(2, stateBend);
    const middleBend = bendOf(3, stateBend);
    const ringBend = bendOf(4, stateBend * 0.6);
    const pinkyBend = bendOf(5, stateBend * 0.4);

    // Palm 8 corners
    const c: Point3D[] = [
      { x: -25, y: -20, z: -10 }, // 0
      { x: 25, y: -20, z: -10 }, // 1
      { x: 25, y: 10, z: -10 }, // 2
      { x: -25, y: 10, z: -10 }, // 3
      { x: -25, y: -20, z: 10 }, // 4
      { x: 25, y: -20, z: 10 }, // 5
      { x: 25, y: 10, z: 10 }, // 6
      { x: -25, y: 10, z: 10 }, // 7
    ];

    // Solid casing faces, darkest to brightest to fake a top-left light source
    fillFace3D(ctx, [c[1], c[2], c[6], c[5]], '#1c1a17', w, h); // right side
    fillFace3D(ctx, [c[4], c[5], c[6], c[7]], '#2c2925', w, h); // front
    fillFace3D(ctx, [c[3], c[2], c[6], c[7]], '#3a352c', w, h); // top (knuckle face)

    // Gold trim outline
    const edges: [number, number][] = [
      [0, 1], [1, 2], [2, 3], [3, 0],
      [4, 5], [5, 6], [6, 7], [7, 4],
      [0, 4], [1, 5], [2, 6], [3, 7],
    ];
    edges.forEach(([a, b]) => draw3DLine(ctx, c[a], c[b], 'rgba(255,179,0,0.55)', 1.5, w, h));

    // Palm-center repulsor — the hand's one glowing-azure accent
    drawGlowDot(ctx, { x: 0, y: -5, z: 11 }, 6, w, h);

    // Draw 5 Finger Kinematic Chains (Thumb, Index, Middle, Ring, Pinky)
    const fingers = [
      { baseX: -30, baseY: 0, baseZ: 5, bend: thumbBend, isThumb: true, width: 9 },
      { baseX: -15, baseY: 12, baseZ: 0, bend: indexBend, isThumb: false, width: 8 },
      { baseX: -5, baseY: 14, baseZ: 0, bend: middleBend, isThumb: false, width: 8 },
      { baseX: 7, baseY: 13, baseZ: 0, bend: ringBend, isThumb: false, width: 7.5 },
      { baseX: 18, baseY: 11, baseZ: 0, bend: pinkyBend, isThumb: false, width: 7 },
    ];

    fingers.forEach((f) => {
      const pBase = { x: f.baseX, y: f.baseY, z: f.baseZ };
      const len1 = 25;
      const len2 = 20;

      const theta1 = f.isThumb ? f.bend * 1.1 : f.bend * 1.25;
      const pMid = {
        x: pBase.x + (f.isThumb ? Math.cos(theta1) * len1 * 0.5 : 0),
        y: pBase.y + Math.cos(theta1) * len1,
        z: pBase.z - Math.sin(theta1) * len1,
      };

      const theta2 = theta1 * 1.4;
      const pTip = {
        x: pMid.x + (f.isThumb ? 6 : 0),
        y: pMid.y + Math.cos(theta2) * len2,
        z: pMid.z - Math.sin(theta2) * len2,
      };

      draw3DThickLine(ctx, pBase, pMid, '#ffb300', '#8a5c00', f.width, w, h);
      draw3DThickLine(ctx, pMid, pTip, '#d6291c', '#5c0f09', f.width * 0.82, w, h);
      drawJointNode(ctx, pMid, f.width * 0.62, w, h);
      drawJointNode(ctx, pTip, f.width * 0.48, w, h);
    });

    // Draw Grasp Object in Palm Center if gripping
    if (state !== 'Open') {
      const objCenter = { x: -5, y: 25, z: -5 };
      const prObj = project3D(objCenter, w, h);
      ctx.strokeStyle = '#ffc94d';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(prObj.x, prObj.y, 16, 0, Math.PI * 2);
      ctx.stroke();

      draw3DLine(ctx, { x: -25, y: 20, z: 0 }, objCenter, 'rgba(214,41,28,0.85)', 2, w, h);
      draw3DLine(ctx, { x: -15, y: 32, z: -10 }, objCenter, 'rgba(214,41,28,0.85)', 2, w, h);
    }
  };

  // Draw 7-DOF Franka Emika Panda Arm
  const draw3DFrankaArm = (ctx: CanvasRenderingContext2D, w: number, h: number, time: number) => {
    const sw = Math.sin(time * 0.001) * 15;
    const cw = Math.cos(time * 0.001) * 15;

    const base = { x: 0, y: -40, z: 0 };
    const j1 = { x: 0, y: -20, z: 0 };
    const j2 = { x: 0, y: 10, z: 10 };
    const j3 = { x: sw, y: 35, z: 5 };
    const j4 = { x: sw + cw, y: 60, z: -10 };
    const eff = { x: sw + cw, y: 75, z: -15 };

    draw3DThickLine(ctx, base, j1, '#5c5650', '#221f1b', 13, w, h);
    draw3DThickLine(ctx, j1, j2, '#ffb300', '#8a5c00', 11, w, h);
    draw3DThickLine(ctx, j2, j3, '#e0960a', '#6e4700', 9.5, w, h);
    draw3DThickLine(ctx, j3, j4, '#d6291c', '#5c0f09', 8, w, h);
    draw3DThickLine(ctx, j4, eff, '#ffdd7a', '#c8c8c8', 6.5, w, h);

    drawJointNode(ctx, j1, 8, w, h);
    drawJointNode(ctx, j2, 7.5, w, h);
    drawJointNode(ctx, j3, 6.5, w, h);
    drawJointNode(ctx, j4, 5.5, w, h);

    // Parallel Gripper Claws
    draw3DThickLine(ctx, eff, { x: eff.x - 8, y: eff.y + 10, z: eff.z }, '#c8c8c8', '#3a3a3a', 4.5, w, h);
    draw3DThickLine(ctx, eff, { x: eff.x + 8, y: eff.y + 10, z: eff.z }, '#c8c8c8', '#3a3a3a', 4.5, w, h);

    // Tool-center-point status light — the arm's one glowing-azure accent
    drawGlowDot(ctx, eff, 4, w, h);
  };

  // Draw TurtleBot 4 Card Scanner Mobile Robot
  const draw3DTurtleBot = (ctx: CanvasRenderingContext2D, w: number, h: number, time: number) => {
    // Round Chassis Perimeter
    const center = { x: 0, y: -25, z: 0 };
    const radius = 30;
    const steps = 20;
    for (let i = 0; i < steps; i++) {
      const a1 = (i / steps) * Math.PI * 2;
      const a2 = ((i + 1) / steps) * Math.PI * 2;
      const p1 = { x: Math.cos(a1) * radius, y: -25, z: Math.sin(a1) * radius };
      const p2 = { x: Math.cos(a2) * radius, y: -25, z: Math.sin(a2) * radius };
      draw3DThickLine(ctx, p1, p2, '#ffb300', '#8a5c00', 7, w, h);
    }

    // Rotating LiDAR Top Scanner
    const lidarAngle = (time * 0.004) % (Math.PI * 2);
    const lidarTop = { x: 0, y: -5, z: 0 };
    const lidarBeam = {
      x: Math.cos(lidarAngle) * 45,
      y: -5,
      z: Math.sin(lidarAngle) * 45,
    };
    draw3DThickLine(ctx, center, lidarTop, '#5c5650', '#221f1b', 9, w, h);
    drawJointNode(ctx, lidarTop, 7, w, h);
    draw3DLine(ctx, lidarTop, lidarBeam, 'rgba(214,41,28,0.8)', 2, w, h);

    // Card Scanner Module Front
    draw3DThickLine(ctx, { x: 28, y: -25, z: -8 }, { x: 28, y: -25, z: 8 }, '#ffdd7a', '#8a5c00', 5, w, h);
    draw3DThickLine(ctx, { x: 28, y: -10, z: -8 }, { x: 28, y: -10, z: 8 }, '#ffdd7a', '#8a5c00', 5, w, h);
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

      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const width = canvas.width;
      const height = canvas.height;

      // Clear canvas — true black, matches the rest of the app's surfaces
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = '#060606';
      ctx.fillRect(0, 0, width, height);

      // Grid floor
      ctx.strokeStyle = 'rgba(255, 179, 0, 0.09)';
      ctx.lineWidth = 1;
      const gridSize = 100;
      const step = 20;
      for (let i = -gridSize; i <= gridSize; i += step) {
        const p1 = project3D({ x: i, y: -40, z: -gridSize }, width, height);
        const p2 = project3D({ x: i, y: -40, z: gridSize }, width, height);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();

        const p3 = project3D({ x: -gridSize, y: -40, z: i }, width, height);
        const p4 = project3D({ x: gridSize, y: -40, z: i }, width, height);
        ctx.beginPath();
        ctx.moveTo(p3.x, p3.y);
        ctx.lineTo(p4.x, p4.y);
        ctx.stroke();
      }

      // 3D axes HUD indicator (bottom-left corner projection)
      const orig = project3D({ x: -80, y: -40, z: -80 }, width, height);
      const xAxis = project3D({ x: -50, y: -40, z: -80 }, width, height);
      const yAxis = project3D({ x: -80, y: -10, z: -80 }, width, height);
      const zAxis = project3D({ x: -80, y: -40, z: -50 }, width, height);

      ctx.strokeStyle = '#d6291c';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(orig.x, orig.y);
      ctx.lineTo(xAxis.x, xAxis.y);
      ctx.stroke();

      ctx.strokeStyle = '#ffb300';
      ctx.beginPath();
      ctx.moveTo(orig.x, orig.y);
      ctx.lineTo(yAxis.x, yAxis.y);
      ctx.stroke();

      ctx.strokeStyle = '#7c8794';
      ctx.beginPath();
      ctx.moveTo(orig.x, orig.y);
      ctx.lineTo(zAxis.x, zAxis.y);
      ctx.stroke();

      // Draw selected 3D robot
      if (selectedRobot === 'inspire_hand') {
        draw3DInspireHand(ctx, width, height, graspState, actuatorPositions);
      } else if (selectedRobot === 'franka_arm') {
        draw3DFrankaArm(ctx, width, height, time);
      } else {
        draw3DTurtleBot(ctx, width, height, time);
      }

      // Targeting radar HUD crosshair
      ctx.strokeStyle = 'rgba(255, 179, 0, 0.2)';
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [yaw, pitch, zoom, selectedRobot, graspState, actuatorPositions]);

  return (
    <div className="app-card p-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3.5 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <Box className="w-4 h-4 text-slate-500" />
          <span className="text-[13px] font-semibold text-slate-200">3D kinematic viewport</span>
          <span className="px-1.5 py-0.5 rounded bg-white/[0.04] text-slate-500 text-[10.5px] font-data">
            {fps} fps
          </span>
        </div>

        {/* Robot selector */}
        <div className="flex items-center gap-0.5 bg-black/20 p-0.5 rounded-lg">
          {(
            [
              { id: 'inspire_hand', label: 'RH56F1 Hand' },
              { id: 'franka_arm', label: 'Franka Arm' },
              { id: 'turtlebot4_scanner', label: 'TurtleBot 4' },
            ] as const
          ).map((item) => (
            <button
              key={item.id}
              onClick={() => setSelectedRobot(item.id)}
              className={`px-2.5 py-1 rounded-md text-[11.5px] font-medium transition-colors ${
                selectedRobot === item.id
                  ? 'bg-emerald-500/15 text-emerald-300'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* Canvas */}
      <div className="relative mt-3.5 flex items-center justify-center bg-app-surface rounded-lg border border-white/[0.06] overflow-hidden">
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

        {/* Telemetry overlay */}
        <div className="absolute top-3.5 left-3.5 px-3 py-2.5 rounded-lg bg-black/60 border border-white/[0.08] backdrop-blur-sm space-y-0.5 font-data text-[10.5px] text-slate-400 pointer-events-none">
          <div className="flex items-center gap-1.5 text-emerald-400 font-medium mb-1">
            <Activity className="w-3 h-3" />
            <span>Client-side render</span>
          </div>
          <div>model {selectedRobot}</div>
          <div>yaw {Math.round(yaw)}° · pitch {Math.round(pitch)}°</div>
          <div>grasp {graspState.toLowerCase()}</div>
        </div>

        {/* Viewport controls */}
        <div className="absolute bottom-3.5 right-3.5 flex items-center gap-1.5">
          <button
            onClick={() => {
              setYaw(35);
              setPitch(25);
              setZoom(1.1);
            }}
            className="px-2.5 py-1.5 rounded-md bg-black/60 hover:bg-black/80 border border-white/[0.08] text-[11px] font-medium text-slate-300 backdrop-blur-sm transition-colors"
            title="Reset to isometric view"
          >
            Isometric
          </button>
          <button
            onClick={() => {
              setYaw(0);
              setPitch(5);
            }}
            className="px-2.5 py-1.5 rounded-md bg-black/60 hover:bg-black/80 border border-white/[0.08] text-[11px] font-medium text-slate-300 backdrop-blur-sm transition-colors"
          >
            Front
          </button>
          <button
            onClick={() => {
              setYaw(90);
              setPitch(0);
            }}
            className="px-2.5 py-1.5 rounded-md bg-black/60 hover:bg-black/80 border border-white/[0.08] text-[11px] font-medium text-slate-300 backdrop-blur-sm transition-colors"
          >
            Side
          </button>
          <button
            onClick={() => setIsWireframe(!isWireframe)}
            className={`px-2.5 py-1.5 rounded-md border text-[11px] font-medium backdrop-blur-sm transition-colors ${
              isWireframe
                ? 'bg-amber-500/15 border-amber-500/30 text-amber-300'
                : 'bg-black/60 border-white/[0.08] text-slate-300 hover:bg-black/80'
            }`}
          >
            Wireframe
          </button>
        </div>
      </div>
    </div>
  );
};
