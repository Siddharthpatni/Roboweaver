'use client';

import React, { useEffect, useMemo } from 'react';
import { useLoader } from '@react-three/fiber';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import * as THREE from 'three';

const MESH_BASE = '/models/inspire_hand/visual';

/*
 * Real CAD replacement for the procedural `InspireHandMesh` primitives --
 * meshes and joint origins below come unmodified from dex-urdf's
 * `inspire_hand_right.urdf` (MIT, DexSuite); see
 * public/models/inspire_hand/NOTICE.md for full provenance. Every revolute
 * joint here rotates about its own local +Z (URDF `<axis xyz="0 0 ±1"/>`),
 * so each is represented below as a single scalar angle + an axis sign.
 */

const FILES = [
  'right_base_link',
  'right_thumb_proximal_base',
  'right_thumb_proximal',
  'right_thumb_intermediate',
  'right_thumb_distal',
  'right_index_proximal',
  'right_index_intermediate',
  'right_middle_intermediate',
  'right_pinky_intermediate',
] as const;
type FileKey = (typeof FILES)[number];

interface Origin {
  xyz: THREE.Vector3Tuple;
  rpy: THREE.Vector3Tuple;
}

// `base` -> `hand_base_link` (URDF `base_joint`, fixed).
const BASE_ORIGIN: Origin = { xyz: [0, 0, 0], rpy: [-1.57079, 0, 3.14159] };

// Thumb: 2 real driven joints (yaw/abduction, pitch/flex) plus 2 mimic joints
// coupled off the pitch joint -- matches the 2 real actuator channels
// (`actuatorPositions[0]` flex, `[1]` abduction) already used elsewhere.
const THUMB_YAW: Origin & { axisSign: 1 | -1; upper: number } = {
  xyz: [-0.01696, -0.0691, -0.02045],
  rpy: [1.5708, -1.5708, 0],
  axisSign: -1,
  upper: 1.308,
};
const THUMB_PITCH: Origin & { axisSign: 1 | -1; upper: number } = {
  xyz: [-0.0088099, 0.010892, -0.00925],
  rpy: [1.5708, 0, 2.8587],
  axisSign: 1,
  upper: 0.6,
};
const THUMB_INTERMEDIATE: Origin & { multiplier: number; offset: number } = {
  xyz: [0.04407, 0.034553, -0.0008],
  rpy: [0, 0, 0],
  multiplier: 1.334,
  offset: 0,
};
const THUMB_DISTAL: Origin & { multiplier: number; offset: number } = {
  xyz: [0.020248, 0.010156, -0.0012],
  rpy: [0, 0, 0],
  multiplier: 0.667,
  offset: 0,
};

interface FingerDef {
  key: string;
  bendIdx: number;
  fallbackWeight: number;
  proximalMesh: FileKey;
  intermediateMesh: FileKey;
  proximalOrigin: Origin;
  proximalUpper: number;
  intermediateOrigin: Origin;
  mimicMultiplier: number;
  mimicOffset: number;
}

// Real per-finger joint origins from the same URDF -- every proximal/
// intermediate joint here rotates about local +Z (axisSign always +1),
// with the intermediate joint mechanically mimicking the proximal one
// (single-actuator tendon coupling), matching this hand's real single-motor-
// per-finger design.
const FINGERS: FingerDef[] = [
  {
    key: 'index',
    bendIdx: 2,
    fallbackWeight: 1,
    proximalMesh: 'right_index_proximal',
    intermediateMesh: 'right_index_intermediate',
    proximalOrigin: { xyz: [0.00028533, -0.13653, -0.032268], rpy: [-3.1067, 0, 0] },
    proximalUpper: 1.47,
    intermediateOrigin: { xyz: [-0.0026138, 0.032026, -0.001], rpy: [0, 0, 0] },
    mimicMultiplier: 1.06399,
    mimicOffset: -0.04545,
  },
  {
    key: 'middle',
    bendIdx: 3,
    fallbackWeight: 1,
    proximalMesh: 'right_index_proximal',
    intermediateMesh: 'right_middle_intermediate',
    proximalOrigin: { xyz: [0.00028533, -0.1371, -0.01295], rpy: [-3.1416, 0, 0] },
    proximalUpper: 1.47,
    intermediateOrigin: { xyz: [-0.0024229, 0.032041, -0.001], rpy: [0, 0, 0] },
    mimicMultiplier: 1.06399,
    mimicOffset: -0.04545,
  },
  {
    key: 'ring',
    bendIdx: 4,
    fallbackWeight: 0.6,
    proximalMesh: 'right_index_proximal',
    intermediateMesh: 'right_index_intermediate',
    proximalOrigin: { xyz: [0.00028533, -0.13691, 0.0062872], rpy: [3.0892, 0, 0] },
    proximalUpper: 1.47,
    intermediateOrigin: { xyz: [-0.0024229, 0.032041, -0.001], rpy: [0, 0, 0] },
    mimicMultiplier: 1.06399,
    mimicOffset: -0.04545,
  },
  {
    key: 'pinky',
    bendIdx: 5,
    fallbackWeight: 0.4,
    proximalMesh: 'right_index_proximal',
    intermediateMesh: 'right_pinky_intermediate',
    proximalOrigin: { xyz: [0.00028533, -0.13571, 0.025488], rpy: [3.0369, 0, 0] },
    proximalUpper: 1.47,
    intermediateOrigin: { xyz: [-0.0024229, 0.032041, -0.001], rpy: [0, 0, 0] },
    mimicMultiplier: 1.06399,
    mimicOffset: -0.04545,
  },
];

const FALLBACK_BEND: Record<string, number> = {
  Open: 0,
  'Precision Grip': 0.65,
  Pinch: 0.85,
  'Power Grasp': 0.95,
};

function applyOrigin(group: THREE.Object3D, origin: Origin) {
  group.position.set(...origin.xyz);
  group.rotation.set(...origin.rpy);
}

export function InspireHandCADModel({
  actuatorPositions,
  graspState,
  heldObjectDiameterM,
}: {
  actuatorPositions?: number[];
  graspState: string;
  heldObjectDiameterM?: number;
}) {
  const urls = useMemo(() => FILES.map((f) => `${MESH_BASE}/${f}.glb`), []);
  const results = useLoader(GLTFLoader, urls);

  const built = useMemo(() => {
    // useLoader only resolves via Suspense once every file has parsed, so
    // `.scene` is never actually undefined here despite the loose typing.
    const scenes = Object.fromEntries(FILES.map((f, i) => [f, results[i]!.scene])) as Record<FileKey, THREE.Group>;
    const cloneOf = (key: FileKey) => {
      const clone = scenes[key].clone(true);
      clone.traverse((o) => {
        if ((o as THREE.Mesh).isMesh) {
          o.castShadow = true;
          o.receiveShadow = true;
        }
      });
      return clone;
    };

    const rootGroup = new THREE.Group();
    applyOrigin(rootGroup, BASE_ORIGIN);
    rootGroup.add(cloneOf('right_base_link'));

    // Thumb chain: yaw (abduction) -> pitch (flex, driven) -> intermediate
    // (mimic) -> distal (mimic).
    const thumbYaw = new THREE.Group();
    applyOrigin(thumbYaw, THUMB_YAW);
    thumbYaw.add(cloneOf('right_thumb_proximal_base'));
    rootGroup.add(thumbYaw);

    const thumbPitch = new THREE.Group();
    applyOrigin(thumbPitch, THUMB_PITCH);
    thumbPitch.add(cloneOf('right_thumb_proximal'));
    thumbYaw.add(thumbPitch);

    const thumbIntermediate = new THREE.Group();
    applyOrigin(thumbIntermediate, THUMB_INTERMEDIATE);
    thumbIntermediate.add(cloneOf('right_thumb_intermediate'));
    thumbPitch.add(thumbIntermediate);

    const thumbDistal = new THREE.Group();
    applyOrigin(thumbDistal, THUMB_DISTAL);
    thumbDistal.add(cloneOf('right_thumb_distal'));
    thumbIntermediate.add(thumbDistal);

    const fingerProximal: Record<string, THREE.Group> = {};
    const fingerIntermediate: Record<string, THREE.Group> = {};

    FINGERS.forEach((f) => {
      const proximal = new THREE.Group();
      applyOrigin(proximal, f.proximalOrigin);
      proximal.add(cloneOf(f.proximalMesh));
      rootGroup.add(proximal);

      const intermediate = new THREE.Group();
      applyOrigin(intermediate, f.intermediateOrigin);
      intermediate.add(cloneOf(f.intermediateMesh));
      proximal.add(intermediate);

      fingerProximal[f.key] = proximal;
      fingerIntermediate[f.key] = intermediate;
    });

    return {
      root: rootGroup,
      // A plain array (not named fields) so the pose effect below can assign
      // through a forEach callback parameter, same as the finger joints and
      // FrankaMeshModel's own joint-posing effect -- assigning a nested
      // property straight off the useMemo-returned binding trips the
      // react-hooks/immutability lint rule.
      thumbJoints: [thumbYaw, thumbPitch, thumbIntermediate, thumbDistal],
      fingerProximal,
      fingerIntermediate,
    };
  }, [results]);

  useEffect(() => {
    const stateBend = FALLBACK_BEND[graspState] ?? 0;
    const bendOf = (idx: number, fallback: number) =>
      actuatorPositions && actuatorPositions[idx] !== undefined ? actuatorPositions[idx] / 1000 : fallback;

    const thumbFlex = bendOf(0, stateBend);
    const thumbAbduct = bendOf(1, graspState === 'Open' ? 0.15 : 0.75);

    const pitchAngle = thumbFlex * THUMB_PITCH.upper;
    const thumbAngles = [
      THUMB_YAW.axisSign * thumbAbduct * THUMB_YAW.upper,
      THUMB_PITCH.axisSign * pitchAngle,
      THUMB_INTERMEDIATE.multiplier * pitchAngle + THUMB_INTERMEDIATE.offset,
      THUMB_DISTAL.multiplier * pitchAngle + THUMB_DISTAL.offset,
    ];
    built.thumbJoints.forEach((g, i) => {
      g.rotation.z = thumbAngles[i];
    });

    FINGERS.forEach((f) => {
      const bend = bendOf(f.bendIdx, stateBend * f.fallbackWeight);
      const proximalAngle = bend * f.proximalUpper;
      built.fingerProximal[f.key].rotation.z = proximalAngle;
      built.fingerIntermediate[f.key].rotation.z = f.mimicMultiplier * proximalAngle + f.mimicOffset;
    });
  }, [actuatorPositions, graspState, built]);

  return (
    <group>
      <primitive object={built.root} />
      {graspState !== 'Open' && (
        <mesh position={[0.06, -0.07, -0.02]} castShadow>
          <sphereGeometry args={[(heldObjectDiameterM ?? 0.03) / 2, 20, 20]} />
          <meshStandardMaterial color="#ffc94d" emissive="#ffb300" emissiveIntensity={0.25} metalness={0.3} roughness={0.5} transparent opacity={0.85} />
        </mesh>
      )}
    </group>
  );
}
