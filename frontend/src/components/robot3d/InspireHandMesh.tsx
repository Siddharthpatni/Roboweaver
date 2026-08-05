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

// Real Inspire RH56-series color language (from the manufacturer's own product
// photography): matte black rubber-clad fingers/palm, a bright chrome hinge
// bracket exposed at every knuckle, and a white wrist adapter -- not the gold/
// red "Iron Man" palette used elsewhere in this app for the arm robots, since
// that's a deliberate house style for THOSE models, not a claim about what this
// hand actually looks like.
const BODY_BLACK = '#161616';
const BODY_RIB = '#0c0c0c';
const CHROME = '#d7d8da';
const CHROME_SHADOW = '#8f9095';
const SENSOR_DARK = '#050505';
const WRIST_WHITE = '#e9e7e1';

function linkLength(links: RobotLinkSpec[], name: string, fallback: number): number {
  return links.find((l) => l.name === name)?.length ?? fallback;
}

/** The knuckle's exposed hinge bracket -- a bright chrome drum on the real bend
 * axis flanked by two slightly wider chrome cheek plates (a real clevis/fork
 * joint reads exactly this way: a shiny cylindrical pivot pinched between two
 * flat plates), plus a small dark sensor chip on one cheek, matching the flex
 * sensor cable module visible on the real hand's own joints. */
function ForkJoint({ radius, wireframe }: { radius: number; wireframe: boolean }) {
  const plateGap = radius * 1.5;
  return (
    <group rotation={[0, 0, Math.PI / 2]}>
      <mesh castShadow>
        <cylinderGeometry args={[radius * 0.62, radius * 0.62, plateGap * 0.92, 20]} />
        <meshStandardMaterial color={CHROME} metalness={0.95} roughness={0.12} wireframe={wireframe} />
      </mesh>
      {[-1, 1].map((side) => (
        <mesh key={side} position={[0, side * plateGap * 0.5, 0]} castShadow>
          <cylinderGeometry args={[radius * 0.95, radius * 0.95, radius * 0.32, 20]} />
          <meshStandardMaterial color={CHROME_SHADOW} metalness={0.9} roughness={0.2} wireframe={wireframe} />
        </mesh>
      ))}
      {/* Flex-sensor chip -- a small dark module on one cheek plate. */}
      <mesh position={[radius * 0.55, plateGap * 0.5 + radius * 0.16, 0]} rotation={[Math.PI / 2, 0, 0]} castShadow>
        <boxGeometry args={[radius * 0.5, radius * 0.9, radius * 0.14]} />
        <meshStandardMaterial color={SENSOR_DARK} metalness={0.3} roughness={0.6} wireframe={wireframe} />
      </mesh>
    </group>
  );
}

/** A matte black knuckle housing at the base of each finger -- fixed to the
 * palm, doesn't rotate with the finger, matching how the real actuator housing
 * is molded into the palm shell and only the finger itself pivots. */
function KnuckleHousing({ radius, wireframe }: { radius: number; wireframe: boolean }) {
  return (
    <mesh castShadow receiveShadow>
      <cylinderGeometry args={[radius, radius * 1.08, radius * 0.85, 20]} />
      <meshStandardMaterial color={BODY_BLACK} emissive={BODY_BLACK} emissiveIntensity={0.6} metalness={0.2} roughness={0.55} wireframe={wireframe} />
    </mesh>
  );
}

/** A finger phalanx -- matte black rubber-like body with a few thin darker rib
 * rings, matching the real hand's ribbed/pleated finger cladding instead of a
 * bare smooth cylinder. */
function Segment({
  length,
  radius,
  wireframe,
}: {
  length: number;
  radius: number;
  wireframe: boolean;
}) {
  const ribCount = 3;
  return (
    <group>
      <mesh position={[0, length / 2, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[radius * 0.86, radius, length, 16]} />
        <meshStandardMaterial color={BODY_BLACK} emissive={BODY_BLACK} emissiveIntensity={0.6} metalness={0.15} roughness={0.6} wireframe={wireframe} />
      </mesh>
      {Array.from({ length: ribCount }).map((_, i) => {
        const t = (i + 1) / (ribCount + 1);
        const y = length * t;
        const r = radius * (1 - t) + radius * 0.86 * t;
        return (
          <mesh key={i} position={[0, y, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[r * 0.98, r * 0.1, 8, 20]} />
            <meshStandardMaterial color={BODY_RIB} emissive={BODY_RIB} emissiveIntensity={0.5} metalness={0.1} roughness={0.7} wireframe={wireframe} />
          </mesh>
        );
      })}
    </group>
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
  const radius = isThumb ? 0.0085 : 0.007;
  const theta1 = isThumb ? bend * 1.1 : bend * 1.25;
  const theta2 = theta1 * 1.4;

  return (
    <group position={[baseX, 0.015, 0.07]} rotation={isThumb ? [0, thumbYaw, 0] : [0, 0, 0]}>
      <KnuckleHousing radius={radius * 1.3} wireframe={wireframe} />
      <group rotation={[-theta1, 0, 0]}>
        <Segment length={len1} radius={radius} wireframe={wireframe} />
        <group position={[0, len1, 0]}>
          <ForkJoint radius={radius * 1.05} wireframe={wireframe} />
          <group rotation={[-(theta2 - theta1), 0, 0]}>
            <Segment length={len2} radius={radius * 0.8} wireframe={wireframe} />
            <group position={[0, len2, 0]}>
              <ForkJoint radius={radius * 0.68} wireframe={wireframe} />
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
 * backend `InspireHandSimulator` returns, not hand-typed angles. Color/material
 * choices (matte black body, chrome knuckle brackets, white wrist adapter)
 * follow the manufacturer's own real product photography, not this app's
 * separate gold/red "Iron Man" palette used for the arm robots.
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
  const palmFrontBack = palmLength * 0.55;

  const thumbAbductFraction = bendOf(1, graspState === 'Open' ? 0.15 : 0.75);
  const thumbYaw = (-0.35 + thumbAbductFraction * 0.75) * -1;

  const wristRadius = palmWidth * 0.32;
  const wristLength = palmLength * 0.3;

  return (
    <group>
      {/* Palm shell -- a single smooth black wedge (real hand's palm has no
          visible screws or seams on its face), very slightly narrower at the
          bottom to suggest the real tapered profile down to the wrist. */}
      <mesh castShadow receiveShadow>
        <boxGeometry args={[palmWidth, palmDepth, palmFrontBack]} />
        <meshStandardMaterial color={BODY_BLACK} emissive={BODY_BLACK} emissiveIntensity={0.6} metalness={0.2} roughness={0.5} wireframe={wireframe} />
      </mesh>
      <mesh position={[0, -palmDepth * 0.02, -palmFrontBack * 0.02]} castShadow receiveShadow>
        <boxGeometry args={[palmWidth * 0.94, palmDepth * 0.96, palmFrontBack * 0.9]} />
        <meshStandardMaterial color={BODY_RIB} emissive={BODY_RIB} emissiveIntensity={0.5} metalness={0.15} roughness={0.55} wireframe={wireframe} />
      </mesh>

      {/* Wrist adapter -- white plastic sleeve with a chrome retaining ring and
          a small central sensor button, matching the real hand's real
          arm-mount interface (distinct in both color and material from the
          black hand body). */}
      <mesh position={[0, -palmDepth / 2 - wristLength / 2, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[wristRadius, wristRadius * 1.08, wristLength, 24]} />
        <meshStandardMaterial color={WRIST_WHITE} metalness={0.15} roughness={0.4} wireframe={wireframe} />
      </mesh>
      <mesh position={[0, -palmDepth / 2 - wristLength * 0.86, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[wristRadius * 1.05, wristRadius * 0.08, 10, 32]} />
        <meshStandardMaterial color={CHROME} metalness={0.9} roughness={0.15} wireframe={wireframe} />
      </mesh>
      <mesh position={[0, -palmDepth / 2 - wristLength - 0.001, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <circleGeometry args={[wristRadius * 0.28, 24]} />
        <meshStandardMaterial color={SENSOR_DARK} metalness={0.3} roughness={0.5} wireframe={wireframe} />
      </mesh>

      {/* Palm-center repulsor accent -- small and subtle, the one deliberate
          cross-app cyan signature, not a dominant feature on this otherwise
          realistic black/white/chrome hand. */}
      <mesh position={[0, palmDepth / 2 + 0.0008, 0.01]}>
        <cylinderGeometry args={[0.004, 0.004, 0.003, 16]} />
        <meshStandardMaterial color="#bff4ff" emissive="#22d3ee" emissiveIntensity={1.4} metalness={0.2} roughness={0.1} wireframe={wireframe} />
      </mesh>
      <pointLight position={[0, palmDepth / 2 + 0.006, 0.01]} color="#22d3ee" intensity={0.05} distance={0.03} decay={2} />

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
