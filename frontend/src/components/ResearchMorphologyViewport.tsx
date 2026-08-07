'use client';

import React, { useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { Grid, Line, OrbitControls } from '@react-three/drei';
import type { ExperimentJoint, ExperimentLink } from '../types';

type Point = [number, number, number];

function layoutLinks(links: ExperimentLink[], joints: ExperimentJoint[]): Map<string, Point> {
  const children = new Map<string, string[]>();
  const childNames = new Set(joints.map((joint) => joint.child));
  for (const joint of joints) {
    children.set(joint.parent, [...(children.get(joint.parent) ?? []), joint.child]);
  }
  const root = links.find((link) => !childNames.has(link.name))?.name ?? links[0]?.name;
  const positions = new Map<string, Point>();
  if (!root) return positions;
  positions.set(root, [0, 1.55, 0]);
  const queue: Array<{ name: string; depth: number }> = [{ name: root, depth: 0 }];
  while (queue.length) {
    const current = queue.shift();
    if (!current) break;
    const parent = positions.get(current.name) ?? [0, 0, 0];
    const descendants = children.get(current.name) ?? [];
    descendants.forEach((name, index) => {
      const spread = descendants.length === 1 ? 0 : (index - (descendants.length - 1) / 2) * 0.72;
      const inherited = current.depth > 0 ? parent[0] * 0.72 : 0;
      positions.set(name, [inherited + spread, parent[1] - 0.62, (index % 2) * 0.08]);
      queue.push({ name, depth: current.depth + 1 });
    });
  }
  return positions;
}

function LinkMesh({ link, position }: { link: ExperimentLink; position: Point }) {
  const [x, y, z] = link.size_m.map((value) => Math.max(0.11, value * 1.25)) as Point;
  return (
    <mesh position={position} castShadow receiveShadow>
      {link.shape === 'box' && <boxGeometry args={[x, y, z]} />}
      {link.shape === 'sphere' && <sphereGeometry args={[x / 2, 24, 16]} />}
      {link.shape === 'cylinder' && <cylinderGeometry args={[x / 2, x / 2, z, 20]} />}
      {link.shape === 'capsule' && <capsuleGeometry args={[x / 2, Math.max(0.08, z - x), 8, 16]} />}
      <meshStandardMaterial color="#38bdf8" roughness={0.32} metalness={0.42} />
    </mesh>
  );
}

export function ResearchMorphologyViewport({ links, joints }: { links: ExperimentLink[]; joints: ExperimentJoint[] }) {
  const positions = useMemo(() => layoutLinks(links, joints), [links, joints]);
  return (
    <div className="h-[320px] min-h-[260px] w-full overflow-hidden rounded-xl border border-white/[0.08] bg-[#07101b] sm:h-[400px] xl:h-full xl:min-h-[430px]">
      <Canvas camera={{ position: [2.8, 2.3, 4.2], fov: 42 }} shadows dpr={[1, 1.6]}>
        <color attach="background" args={['#07101b']} />
        <ambientLight intensity={0.75} />
        <directionalLight position={[4, 7, 3]} intensity={2.2} castShadow />
        {joints.map((joint) => {
          const parent = positions.get(joint.parent);
          const child = positions.get(joint.child);
          return parent && child ? <Line key={joint.name} points={[parent, child]} color="#64748b" lineWidth={2} /> : null;
        })}
        {links.map((link) => (
          <LinkMesh key={link.name} link={link} position={positions.get(link.name) ?? [0, 0, 0]} />
        ))}
        <Grid position={[0, -1.15, 0]} args={[8, 8]} cellColor="#17324a" sectionColor="#1f7898" fadeDistance={8} />
        <OrbitControls makeDefault enableDamping minDistance={2.3} maxDistance={8} target={[0, 0.45, 0]} />
      </Canvas>
    </div>
  );
}
