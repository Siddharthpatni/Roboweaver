'use client';

import React, { useEffect, useMemo } from 'react';
import { useLoader } from '@react-three/fiber';
import { ColladaLoader } from 'three/examples/jsm/loaders/ColladaLoader.js';
import * as THREE from 'three';

const MESH_BASE = '/models/franka_panda/visual';
const LINK_FILES = ['link0', 'link1', 'link2', 'link3', 'link4', 'link5', 'link6', 'link7', 'hand', 'finger'];

/* Real DH-consistent joint origins for the Franka arm (FER, the current
   production successor sharing the Panda's link geometry) -- taken from
   franka_description/robots/fer/kinematics.yaml (Apache-2.0, Franka Robotics
   GmbH), not a procedural approximation. Every joint rotates about its own
   local +Z after this fixed origin, matching the real URDF convention;
   see public/models/franka_panda/NOTICE.md for provenance. */
const JOINT_ORIGINS: Array<{ xyz: THREE.Vector3Tuple; rpy: THREE.Vector3Tuple }> = [
  { xyz: [0, 0, 0.333], rpy: [0, 0, 0] },
  { xyz: [0, 0, 0], rpy: [-Math.PI / 2, 0, 0] },
  { xyz: [0, -0.316, 0], rpy: [Math.PI / 2, 0, 0] },
  { xyz: [0.0825, 0, 0], rpy: [Math.PI / 2, 0, 0] },
  { xyz: [-0.0825, 0.384, 0], rpy: [-Math.PI / 2, 0, 0] },
  { xyz: [0, 0, 0], rpy: [Math.PI / 2, 0, 0] },
  { xyz: [0.088, 0, 0], rpy: [Math.PI / 2, 0, 0] },
];
const FLANGE_TO_HAND = { xyz: [0, 0, 0.107] as THREE.Vector3Tuple, rpy: [0, 0, -Math.PI / 4] as THREE.Vector3Tuple };
// Real franka_hand finger mount height; fingers held at a static half-open gap
// since the 7-value `q` this viewer receives is the arm only, not gripper state.
const FINGER_Z = 0.0584;
const FINGER_HALF_OPEN = 0.02;

export function FrankaMeshModel({ q }: { q: number[] }) {
  const urls = useMemo(() => LINK_FILES.map((f) => `${MESH_BASE}/${f}.dae`), []);
  const results = useLoader(ColladaLoader, urls);

  const built = useMemo(() => {
    // useLoader only resolves via Suspense once every file has fully parsed, so
    // neither the result nor `.scene` is ever actually null here despite the
    // loader's loose typing.
    const clones = results.map((r) => r!.scene!.clone(true)) as THREE.Object3D[];
    const [link0, link1, link2, link3, link4, link5, link6, link7, hand, finger] = clones;
    const links = [link1, link2, link3, link4, link5, link6, link7];
    const joints: THREE.Group[] = [];

    const base = new THREE.Group();
    base.add(link0);

    let parent: THREE.Object3D = base;
    links.forEach((linkMesh, i) => {
      const origin = new THREE.Group();
      origin.position.set(...JOINT_ORIGINS[i].xyz);
      origin.rotation.set(...JOINT_ORIGINS[i].rpy);

      const joint = new THREE.Group();
      joint.add(linkMesh);
      origin.add(joint);
      parent.add(origin);

      joints.push(joint);
      parent = joint;
    });

    const flange = new THREE.Group();
    flange.position.set(...FLANGE_TO_HAND.xyz);
    flange.rotation.set(...FLANGE_TO_HAND.rpy);
    flange.add(hand);

    const finger2 = finger.clone(true);
    finger.position.set(0, FINGER_HALF_OPEN, FINGER_Z);
    finger2.position.set(0, -FINGER_HALF_OPEN, FINGER_Z);
    finger2.rotation.z = Math.PI;
    flange.add(finger, finger2);

    parent.add(flange);
    return { base, joints };
  }, [results]);

  useEffect(() => {
    built.joints.forEach((g, i) => {
      g.rotation.z = q[i] ?? 0;
    });
  }, [q, built]);

  return <primitive object={built.base} />;
}
