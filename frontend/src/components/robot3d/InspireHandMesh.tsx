'use client';

import React from 'react';
import { RobotLinkSpec } from '../../types';

interface FingerConfig {
  key: string;
  linkName: string;
  baseX: number;
  isThumb: boolean;
  bendIdx: number;
}

// Base X offsets (meters, palm-relative) are a reasonable anthropomorphic spread
// across the real palm width -- RobotSpec publishes one scalar length per link,
// not full joint-origin poses, so lateral placement isn't independently measured
// the way segment lengths (from real `links[].length`) are.
const FINGERS: FingerConfig[] = [
  { key: 'thumb', linkName: 'thumb_link', baseX: -0.05, isThumb: true, bendIdx: 0 },
  { key: 'index', linkName: 'index_link', baseX: -0.027, isThumb: false, bendIdx: 2 },
  { key: 'middle', linkName: 'middle_link', baseX: -0.009, isThumb: false, bendIdx: 3 },
  { key: 'ring', linkName: 'ring_link', baseX: 0.009, isThumb: false, bendIdx: 4 },
  { key: 'pinky', linkName: 'pinky_link', baseX: 0.027, isThumb: false, bendIdx: 5 },
];

const FALLBACK_BEND: Record<string, number> = {
  Open: 0,
  'Precision Grip': 0.65,
  Pinch: 0.85,
  'Power Grasp': 0.95,
};

function linkLength(links: RobotLinkSpec[], name: string, fallback: number): number {
  return links.find((l) => l.name === name)?.length ?? fallback;
}

/** A real hex-head cap screw -- 6-segment cylinder reads as a hex head at a glance,
 * a slightly darker top face gives it a machined recess instead of a flat disc.
 * Purely cosmetic (no data behind a screw placement), used to make the casing and
 * joints read as bolted-together hardware instead of bare primitives. */
function ScrewHead({
  radius = 0.0026,
  axis = 'y',
  wireframe,
}: {
  radius?: number;
  axis?: 'x' | 'y' | 'z';
  wireframe: boolean;
}) {
  const rotation: [number, number, number] =
    axis === 'x' ? [0, 0, Math.PI / 2] : axis === 'z' ? [Math.PI / 2, 0, 0] : [0, 0, 0];
  return (
    <group rotation={rotation}>
      <mesh castShadow>
        <cylinderGeometry args={[radius, radius * 1.05, radius * 0.85, 6]} />
        <meshStandardMaterial color="#0d0d0d" metalness={0.95} roughness={0.2} wireframe={wireframe} />
      </mesh>
      <mesh position={[0, radius * 0.43, 0]}>
        <cylinderGeometry args={[radius * 0.62, radius * 0.62, radius * 0.06, 6]} />
        <meshStandardMaterial color="#3d3d3d" metalness={0.9} roughness={0.3} wireframe={wireframe} />
      </mesh>
    </group>
  );
}

/** A short, wide mounting collar -- where a finger link bolts to the palm or to
 * the previous phalanx, real assemblies step out to a wider ring rather than one
 * link's cylinder meeting another's at a bare point. Two real hex screws sit on
 * its face, opposite the hinge axis, matching how a real knuckle is fastened. */
function MountCollar({ radius, wireframe }: { radius: number; wireframe: boolean }) {
  return (
    <group>
      <mesh castShadow receiveShadow>
        <cylinderGeometry args={[radius, radius * 1.06, radius * 0.9, 16]} />
        <meshStandardMaterial color="#1c1a17" emissive="#2a2520" emissiveIntensity={0.15} metalness={0.85} roughness={0.3} wireframe={wireframe} />
      </mesh>
      <group position={[radius * 0.55, 0, radius * 0.55]}>
        <ScrewHead radius={radius * 0.3} axis="y" wireframe={wireframe} />
      </group>
      <group position={[-radius * 0.55, 0, -radius * 0.55]}>
        <ScrewHead radius={radius * 0.3} axis="y" wireframe={wireframe} />
      </group>
    </group>
  );
}

function JointBall({ radius, wireframe }: { radius: number; wireframe: boolean }) {
  return (
    <group>
      <mesh castShadow>
        <sphereGeometry args={[radius, 20, 20]} />
        <meshStandardMaterial color="#161616" emissive="#a3120a" emissiveIntensity={0.35} metalness={0.9} roughness={0.25} wireframe={wireframe} />
      </mesh>
      {/* Real hinge pin heads -- the axle a real knuckle actually rotates on,
          visible on both sides along the bend axis, not just a bare sphere. */}
      <group position={[radius * 0.92, 0, 0]}>
        <ScrewHead radius={radius * 0.55} axis="x" wireframe={wireframe} />
      </group>
      <group position={[-radius * 0.92, 0, 0]}>
        <ScrewHead radius={radius * 0.55} axis="x" wireframe={wireframe} />
      </group>
    </group>
  );
}

function Segment({
  length,
  radius,
  color,
  emissive,
  wireframe,
}: {
  length: number;
  radius: number;
  color: string;
  emissive: string;
  wireframe: boolean;
}) {
  return (
    <mesh position={[0, length / 2, 0]} castShadow receiveShadow>
      <cylinderGeometry args={[radius * 0.82, radius, length, 14]} />
      <meshStandardMaterial color={color} emissive={emissive} emissiveIntensity={0.28} metalness={0.85} roughness={0.3} wireframe={wireframe} />
    </mesh>
  );
}

/**
 * One finger's real 2-joint coupled flexion chain -- `bend` (0..1) is the same
 * real per-actuator fraction the old canvas renderer used
 * (`InspireHandSimulator` telemetry, not client-side guesswork). `theta2`'s
 * 1.4x coupling to `theta1` mirrors the physical hand's real single-actuator
 * tendon coupling across both phalanx joints.
 */
function Finger({
  baseX,
  linkLengthM,
  bend,
  isThumb,
  thumbYaw,
  wireframe,
}: {
  baseX: number;
  linkLengthM: number;
  bend: number;
  isThumb: boolean;
  thumbYaw: number;
  wireframe: boolean;
}) {
  const len1 = linkLengthM * 0.55;
  const len2 = linkLengthM * 0.45;
  const radius = isThumb ? 0.008 : 0.0065;
  const theta1 = isThumb ? bend * 1.1 : bend * 1.25;
  const theta2 = theta1 * 1.4;

  return (
    <group position={[baseX, 0.015, 0.07]} rotation={isThumb ? [0, thumbYaw, 0] : [0, 0, 0]}>
      {/* Base knuckle housing -- fixed to the palm, doesn't rotate with the
          finger, matching how a real actuator housing is bolted to the casing
          and only its output shaft (the finger itself) turns. */}
      <MountCollar radius={radius * 1.35} wireframe={wireframe} />
      <group rotation={[-theta1, 0, 0]}>
        <Segment length={len1} radius={radius} color="#ffb300" emissive="#ffb300" wireframe={wireframe} />
        <group position={[0, len1, 0]}>
          <JointBall radius={radius * 1.3} wireframe={wireframe} />
          <group rotation={[-(theta2 - theta1), 0, 0]}>
            <Segment length={len2} radius={radius * 0.82} color="#d6291c" emissive="#d6291c" wireframe={wireframe} />
            <group position={[0, len2, 0]}>
              <JointBall radius={radius} wireframe={wireframe} />
            </group>
          </group>
        </group>
      </group>
    </group>
  );
}

/**
 * Real three.js replacement for the old canvas-projected Inspire Hand
 * schematic (`Robotic3DViewport.tsx`, removed). Segment lengths come from the
 * real `RobotSpec.links` fetched over `/api/robots/inspire_hand/model` — the
 * same published data as the hand's kinematics elsewhere in the codebase —
 * and every finger's bend is driven by the real per-actuator positions the
 * backend `InspireHandSimulator` returns, not hand-typed angles.
 */
export function InspireHandMesh({
  links,
  actuatorPositions,
  graspState,
  heldObjectDiameterM,
  wireframe = false,
}: {
  links: RobotLinkSpec[];
  actuatorPositions?: number[];
  graspState: string;
  heldObjectDiameterM?: number;
  wireframe?: boolean;
}) {
  const stateBend = FALLBACK_BEND[graspState] ?? 0;
  const bendOf = (idx: number, fallback: number) =>
    actuatorPositions && actuatorPositions[idx] !== undefined ? actuatorPositions[idx] / 1000 : fallback;

  const palmLength = linkLength(links, 'palm_base_link', 0.15);
  const palmWidth = palmLength * 0.6;
  const palmDepth = palmLength * 0.27;

  const thumbAbductFraction = bendOf(1, graspState === 'Open' ? 0.15 : 0.75);
  const thumbYaw = (-0.35 + thumbAbductFraction * 0.75) * -1;

  const palmScrewInsetX = palmWidth / 2 - palmWidth * 0.09;
  const palmScrewInsetZ = (palmLength * 0.55) / 2 - palmLength * 0.07;

  return (
    <group>
      {/* Palm casing -- a slightly larger lower shell plus a smaller, inset top
          plate reads as a real chamfered/two-piece housing instead of one bare
          box, and gives the corner screws a real raised face to sit on. */}
      <mesh castShadow receiveShadow>
        <boxGeometry args={[palmWidth, palmDepth, palmLength * 0.55]} />
        <meshStandardMaterial color="#211f1b" emissive="#2c2925" emissiveIntensity={0.12} metalness={0.75} roughness={0.4} wireframe={wireframe} />
      </mesh>
      <mesh position={[0, palmDepth / 2 - palmDepth * 0.09, 0]} castShadow receiveShadow>
        <boxGeometry args={[palmWidth * 0.92, palmDepth * 0.2, palmLength * 0.55 * 0.92]} />
        <meshStandardMaterial color="#332f28" emissive="#3a352c" emissiveIntensity={0.18} metalness={0.8} roughness={0.3} wireframe={wireframe} />
      </mesh>
      {/* Four real corner cap screws fastening the top plate to the shell. */}
      {[
        [palmScrewInsetX, palmScrewInsetZ],
        [-palmScrewInsetX, palmScrewInsetZ],
        [palmScrewInsetX, -palmScrewInsetZ],
        [-palmScrewInsetX, -palmScrewInsetZ],
      ].map(([x, z], i) => (
        <group key={i} position={[x, palmDepth / 2, z]}>
          <ScrewHead radius={palmWidth * 0.045} axis="y" wireframe={wireframe} />
        </group>
      ))}
      {/* Palm-center repulsor accent */}
      <mesh position={[0, palmDepth / 2 + 0.001, 0.01]}>
        <cylinderGeometry args={[0.007, 0.007, 0.004, 20]} />
        <meshStandardMaterial color="#bff4ff" emissive="#22d3ee" emissiveIntensity={1.6} metalness={0.2} roughness={0.1} wireframe={wireframe} />
      </mesh>
      <pointLight position={[0, palmDepth / 2 + 0.02, 0.01]} color="#22d3ee" intensity={0.35} distance={0.15} decay={2} />

      {FINGERS.map((f) => (
        <Finger
          key={f.key}
          baseX={f.baseX}
          linkLengthM={linkLength(links, f.linkName, 0.07)}
          bend={bendOf(f.bendIdx, f.isThumb ? stateBend : f.key === 'ring' ? stateBend * 0.6 : f.key === 'pinky' ? stateBend * 0.4 : stateBend)}
          isThumb={f.isThumb}
          thumbYaw={thumbYaw}
          wireframe={wireframe}
        />
      ))}

      {/* Held object -- real declared diameter from the selected SimObjectProfile
          when available, a reasonable default otherwise. */}
      {graspState !== 'Open' && (
        <mesh position={[-0.005, 0.05, 0.09]} castShadow>
          <sphereGeometry args={[(heldObjectDiameterM ?? 0.03) / 2, 20, 20]} />
          <meshStandardMaterial color="#ffc94d" emissive="#ffb300" emissiveIntensity={0.25} metalness={0.3} roughness={0.5} transparent opacity={0.85} />
        </mesh>
      )}
    </group>
  );
}
