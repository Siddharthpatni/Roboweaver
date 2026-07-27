'use client';

import React, { useEffect, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Grid, ContactShadows } from '@react-three/drei';
import * as THREE from 'three';
import { Loader2, AlertTriangle, RotateCcw, Box } from 'lucide-react';
import { RoboWeaverAPI } from '../lib/api';
import { RobotProfile, RobotModel } from '../types';

type Vec3Tuple = [number, number, number];

/* A limb segment: a tapered gold housing cylinder with a stark-red racing
   stripe down one face, so a link reads as an actual machined arm segment
   instead of a thin wireframe rod. */
function LinkSegment({ from, to }: { from: Vec3Tuple; to: Vec3Tuple }) {
  const start = new THREE.Vector3(...from);
  const end = new THREE.Vector3(...to);
  const mid = start.clone().add(end).multiplyScalar(0.5);
  const dir = end.clone().sub(start);
  const length = Math.max(dir.length(), 0.001);
  const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize());

  return (
    <group position={mid} quaternion={quat}>
      <mesh castShadow receiveShadow>
        <cylinderGeometry args={[0.024, 0.032, length, 16]} />
        <meshStandardMaterial color="#e0960a" emissive="#ffb300" emissiveIntensity={0.22} metalness={0.85} roughness={0.3} />
      </mesh>
      <mesh position={[0.029, 0, 0]}>
        <boxGeometry args={[0.009, Math.max(length - 0.03, 0.001), 0.011]} />
        <meshStandardMaterial color="#a3120a" emissive="#d81f10" emissiveIntensity={0.45} metalness={0.6} roughness={0.4} />
      </mesh>
    </group>
  );
}

/* A joint motor housing: dark actuator body with a stark-red collar ring,
   sized well above the link radius so each rotation point reads as a solid
   assembled part. */
function JointNode({ pos, size = 0.04 }: { pos: Vec3Tuple; size?: number }) {
  return (
    <group position={pos}>
      <mesh castShadow>
        <sphereGeometry args={[size, 20, 20]} />
        <meshStandardMaterial color="#161616" emissive="#a3120a" emissiveIntensity={0.35} metalness={0.9} roughness={0.25} />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[size * 0.84, size * 0.16, 10, 24]} />
        <meshStandardMaterial color="#d81f10" emissive="#d81f10" emissiveIntensity={0.5} metalness={0.7} roughness={0.3} />
      </mesh>
    </group>
  );
}

/* Terminal end effector: a palm block with two gripper fingers oriented
   along the final link's direction, so the tip of the chain reads as a
   hand/gripper rather than a floating dot. */
function Gripper({ positions }: { positions: Vec3Tuple[] }) {
  if (positions.length < 2) return null;
  const tip = new THREE.Vector3(...positions[positions.length - 1]);
  const prev = new THREE.Vector3(...positions[positions.length - 2]);
  const dir = tip.clone().sub(prev);
  if (dir.lengthSq() < 1e-8) dir.set(0, 1, 0);
  dir.normalize();
  const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
  const perp = new THREE.Vector3(1, 0, 0).applyQuaternion(quat);
  const forward = dir.clone().multiplyScalar(0.028);

  const finger1 = tip.clone().add(perp.clone().multiplyScalar(0.03)).add(forward);
  const finger2 = tip.clone().add(perp.clone().multiplyScalar(-0.03)).add(forward);

  const repulsorPos = tip.clone().sub(forward.clone().multiplyScalar(0.15));

  return (
    <group>
      <mesh position={tip} quaternion={quat} castShadow>
        <boxGeometry args={[0.07, 0.026, 0.045]} />
        <meshStandardMaterial color="#c8c8c8" metalness={0.9} roughness={0.25} />
      </mesh>
      {[finger1, finger2].map((f, i) => (
        <mesh key={i} position={f} quaternion={quat} castShadow>
          <boxGeometry args={[0.014, 0.05, 0.02]} />
          <meshStandardMaterial color="#ffdd7a" emissive="#ffb300" emissiveIntensity={0.4} metalness={0.85} roughness={0.2} />
        </mesh>
      ))}
      {/* Repulsor emitter — the one deliberate glowing-azure accent on the model,
          echoing the arc reactor core in the Sidebar logo. Everything else on the
          robot stays red/gold/gunmetal. */}
      <mesh position={repulsorPos} quaternion={quat}>
        <cylinderGeometry args={[0.017, 0.017, 0.006, 20]} />
        <meshStandardMaterial color="#bff4ff" emissive="#22d3ee" emissiveIntensity={1.6} metalness={0.2} roughness={0.1} />
      </mesh>
      <pointLight position={repulsorPos} color="#22d3ee" intensity={0.4} distance={0.18} decay={2} />
    </group>
  );
}

/* Fixed mounting base at the root of the chain — grounds the arm instead of
   letting it appear to float in empty space. */
function BasePlatform({ pos }: { pos: Vec3Tuple }) {
  return (
    <group position={[pos[0], pos[1] - 0.02, pos[2]]}>
      <mesh castShadow receiveShadow>
        <cylinderGeometry args={[0.09, 0.11, 0.04, 28]} />
        <meshStandardMaterial color="#131313" metalness={0.8} roughness={0.35} />
      </mesh>
      <mesh position={[0, 0.021, 0]}>
        <torusGeometry args={[0.095, 0.006, 8, 32]} />
        <meshStandardMaterial color="#ffb300" emissive="#ffb300" emissiveIntensity={0.5} metalness={0.6} roughness={0.3} />
      </mesh>
    </group>
  );
}

function RobotMesh({ positions }: { positions: Vec3Tuple[] }) {
  return (
    <group>
      <BasePlatform pos={positions[0]} />
      {positions.slice(0, -1).map((p, i) => (
        <LinkSegment key={i} from={p} to={positions[i + 1]} />
      ))}
      {positions.slice(0, -1).map((p, i) => (
        <JointNode key={i} pos={p} />
      ))}
      <Gripper positions={positions} />
    </group>
  );
}

export const Robot3DModel: React.FC = () => {
  const [robots, setRobots] = useState<RobotProfile[]>([]);
  const [robotId, setRobotId] = useState('franka_panda');
  const [model, setModel] = useState<RobotModel | null>(null);
  const [q, setQ] = useState<number[]>([]);
  const [positions, setPositions] = useState<[number, number, number][]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    RoboWeaverAPI.robots()
      .then(setRobots)
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    // `loading` already starts true on mount; robotId-change handlers set it
    // themselves before updating robotId (see handleRobotChange below), so this
    // effect never needs to call setState synchronously in its own body.
    RoboWeaverAPI.robotModel(robotId)
      .then((m) => {
        setModel(m);
        setQ(new Array(m.dof).fill(0));
        setError(false);
      })
      .catch(() => setError(true));
  }, [robotId]);

  // Debounced: dragging a slider changes `q` on every tick, and each change should
  // trigger the real backend forward_kinematics_chain_ndof call -- the exact function
  // the compiler's motion planner uses -- without flooding it mid-drag.
  useEffect(() => {
    if (!model || q.length !== model.dof) return;
    const handle = setTimeout(() => {
      RoboWeaverAPI.robotFK(robotId, q)
        .then((fk) => {
          setPositions(fk.positions as [number, number, number][]);
          setLoading(false);
          setError(false);
        })
        .catch(() => setError(true));
    }, 60);
    return () => clearTimeout(handle);
  }, [model, q, robotId]);

  const handleJointChange = (idx: number, value: number) => {
    setQ((prev) => prev.map((v, i) => (i === idx ? value : v)));
  };

  const handleRobotChange = (id: string) => {
    setLoading(true);
    setRobotId(id);
  };

  const setPreset = (fraction: number) => {
    if (!model) return;
    setQ(model.joints.map((j) => j.lower_limit + (j.upper_limit - j.lower_limit) * fraction));
  };

  return (
    <div className="app-card p-5 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Box className="w-4 h-4 text-slate-500" />
          <h3 className="text-[13px] font-semibold text-slate-200">3D kinematic model</h3>
          {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-400" />}
        </div>
        <div className="flex items-center gap-2">
          <select
            value={robotId}
            onChange={(e) => handleRobotChange(e.target.value)}
            className="app-well rounded-lg px-3 py-1.5 text-[12px] text-slate-200 focus:outline-none focus:border-amber-500/40"
          >
            {robots.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          <button
            onClick={() => setPreset(0)}
            className="px-2.5 py-1.5 rounded-lg app-well text-[11.5px] text-slate-300 hover:text-white transition-colors"
          >
            Home
          </button>
          <button
            onClick={() => setPreset(0.4)}
            className="px-2.5 py-1.5 rounded-lg app-well text-[11.5px] text-slate-300 hover:text-white transition-colors"
          >
            Reach
          </button>
          <button
            onClick={() => setPreset(0)}
            className="p-1.5 rounded-lg app-well text-slate-400 hover:text-slate-200 transition-colors"
            title="Reset pose"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-[12px] text-rose-300">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          Could not reach the RoboWeaver backend for live kinematics.
        </div>
      )}

      <div className="rounded-lg overflow-hidden border border-white/[0.06] bg-app-surface" style={{ height: 340 }}>
        <Canvas camera={{ position: [1.0, 0.75, 1.0], fov: 45 }}>
          <ambientLight intensity={0.5} />
          <directionalLight position={[2, 3, 2]} intensity={1.15} />
          <directionalLight position={[-2, 1.5, -1]} intensity={0.4} color="#ffb300" />
          <directionalLight position={[0, -1, 2]} intensity={0.15} color="#d81f10" />
          <Grid
            args={[3, 3]}
            cellColor="#1c1c1c"
            sectionColor="#3d2e05"
            fadeDistance={5}
            infiniteGrid
            position={[0, -0.021, 0]}
          />
          {positions.length > 0 && <RobotMesh positions={positions} />}
          <ContactShadows position={[0, -0.02, 0]} opacity={0.55} scale={2.4} blur={2.2} far={1.2} color="#000000" />
          <OrbitControls enableDamping dampingFactor={0.1} target={[0, 0.4, 0]} />
        </Canvas>
      </div>

      {model && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 pt-1">
          {model.joints.map((j, i) => (
            <div key={j.name} className="space-y-1">
              <div className="flex items-center justify-between text-[10.5px] text-slate-500">
                <span className="font-data">{j.name}</span>
                <span className="font-data text-amber-300">{(q[i] ?? 0).toFixed(2)} rad</span>
              </div>
              <input
                type="range"
                min={j.lower_limit}
                max={j.upper_limit}
                step={0.01}
                value={q[i] ?? 0}
                onChange={(e) => handleJointChange(i, parseFloat(e.target.value))}
                className="w-full accent-amber-400"
              />
            </div>
          ))}
        </div>
      )}

      <p className="text-[11px] text-slate-600 pt-1 border-t border-white/[0.06]">
        Every joint position above is computed by the real N-DOF forward-kinematics chain
        (<code className="font-data">forward_kinematics_chain_ndof</code>) — the same function the compiler&apos;s
        motion planner uses — not a client-side approximation.
      </p>
    </div>
  );
};
