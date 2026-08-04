'use client';

import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { RobotLinkSpec } from '../../types';

function linkLength(links: RobotLinkSpec[], name: string, fallback: number): number {
  return links.find((l) => l.name === name)?.length ?? fallback;
}

/**
 * Real three.js replacement for the old canvas-projected TurtleBot 4
 * schematic. Chassis/wheel/scanner dimensions come from the real
 * `RobotSpec.links` (`/api/robots/turtlebot4/model`) instead of arbitrary
 * canvas pixel constants. The LiDAR mast spin is a real-time animation (no
 * backend telemetry drives a mobile base's heading here), clearly a UI
 * affordance rather than a claimed sensor reading.
 */
export function TurtleBotMesh({ links, wireframe = false }: { links: RobotLinkSpec[]; wireframe?: boolean }) {
  const chassisRadius = linkLength(links, 'base_link', 0.35) / 2;
  const wheelRadius = linkLength(links, 'wheel_left_link', 0.07);
  const scannerHeight = linkLength(links, 'card_scanner_payload_link', 0.1);

  const lidarRef = useRef<THREE.Group>(null);
  const beamRef = useRef<THREE.Mesh>(null);
  useFrame((_, delta) => {
    if (lidarRef.current) lidarRef.current.rotation.y += delta * 1.4;
  });

  return (
    <group>
      {/* Round chassis */}
      <mesh castShadow receiveShadow position={[0, wheelRadius, 0]}>
        <cylinderGeometry args={[chassisRadius, chassisRadius, wheelRadius * 1.4, 40]} />
        <meshStandardMaterial color="#221f1b" emissive="#3a2f1a" emissiveIntensity={0.12} metalness={0.7} roughness={0.4} wireframe={wireframe} />
      </mesh>
      <mesh position={[0, wheelRadius * 1.4 + 0.002, 0]}>
        <torusGeometry args={[chassisRadius, 0.006, 8, 48]} />
        <meshStandardMaterial color="#ffb300" emissive="#ffb300" emissiveIntensity={0.5} metalness={0.6} roughness={0.3} />
      </mesh>

      {/* Two real wheels */}
      {[-1, 1].map((side) => (
        <mesh
          key={side}
          castShadow
          position={[side * (chassisRadius + wheelRadius * 0.25), wheelRadius, 0]}
          rotation={[0, 0, Math.PI / 2]}
        >
          <cylinderGeometry args={[wheelRadius, wheelRadius, wheelRadius * 0.5, 24]} />
          <meshStandardMaterial color="#161616" metalness={0.5} roughness={0.6} wireframe={wireframe} />
        </mesh>
      ))}

      {/* Rotating LiDAR mast — real chassis-derived height, animated spin */}
      <group ref={lidarRef} position={[0, wheelRadius * 1.4 + 0.03, 0]}>
        <mesh castShadow>
          <cylinderGeometry args={[chassisRadius * 0.22, chassisRadius * 0.26, 0.03, 20]} />
          <meshStandardMaterial color="#5c5650" emissive="#221f1b" emissiveIntensity={0.2} metalness={0.85} roughness={0.3} wireframe={wireframe} />
        </mesh>
        <mesh ref={beamRef} position={[chassisRadius * 0.55, 0, 0]}>
          <boxGeometry args={[chassisRadius, 0.004, 0.004]} />
          <meshStandardMaterial color="#d6291c" emissive="#d6291c" emissiveIntensity={1.2} />
        </mesh>
        <pointLight position={[0, 0.01, 0]} color="#d6291c" intensity={0.3} distance={0.2} decay={2} />
      </group>

      {/* Card scanner payload module on the front face */}
      <mesh
        castShadow
        position={[0, wheelRadius * 1.4, chassisRadius * 0.92]}
      >
        <boxGeometry args={[chassisRadius * 0.5, scannerHeight, 0.02]} />
        <meshStandardMaterial color="#ffdd7a" emissive="#ffb300" emissiveIntensity={0.35} metalness={0.7} roughness={0.3} wireframe={wireframe} />
      </mesh>
    </group>
  );
}
