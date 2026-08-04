'use client';

import React, { useEffect, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Grid, ContactShadows, Bounds } from '@react-three/drei';
import { Box } from 'lucide-react';
import { RoboWeaverAPI } from '../lib/api';
import { RobotLinkSpec } from '../types';
import { InspireHandMesh } from './robot3d/InspireHandMesh';
import { TurtleBotMesh } from './robot3d/TurtleBotMesh';

type TwinRobot = 'inspire_hand' | 'turtlebot4';

interface DigitalTwinViewportProps {
  graspState: 'Open' | 'Precision Grip' | 'Pinch' | 'Power Grasp';
  actuatorPositions?: number[];
  heldObjectDiameterM?: number;
}

/**
 * Real three.js viewport -- replaces the old `Robotic3DViewport` canvas-2D
 * projection. Real geometry: each robot's `RobotSpec.links` (real published
 * lengths) fetched once per selection over `/api/robots/<id>/model`, same
 * OrbitControls/lighting/auto-fit rig already proven in `Robot3DModel.tsx`
 * for the Franka arm, so every 3D view in the app now behaves identically.
 */
export function DigitalTwinViewport({ graspState, actuatorPositions, heldObjectDiameterM }: DigitalTwinViewportProps) {
  const [selected, setSelected] = useState<TwinRobot>('inspire_hand');
  const [links, setLinks] = useState<Partial<Record<TwinRobot, RobotLinkSpec[]>>>({});
  const [error, setError] = useState(false);
  const [wireframe, setWireframe] = useState(false);

  useEffect(() => {
    if (links[selected]) return;
    RoboWeaverAPI.robotModel(selected)
      .then((m) => setLinks((prev) => ({ ...prev, [selected]: m.links })))
      .catch(() => setError(true));
  }, [selected, links]);

  const currentLinks = links[selected];

  return (
    <div className="app-card p-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3.5 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <Box className="w-4 h-4 text-slate-500" />
          <span className="text-[13px] font-semibold text-slate-200">Digital twin viewport</span>
          <span className="px-1.5 py-0.5 rounded bg-white/[0.04] text-slate-500 text-[10.5px] font-data">three.js</span>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-0.5 bg-black/20 p-0.5 rounded-lg">
            {(
              [
                { id: 'inspire_hand' as const, label: 'RH56F1 Hand' },
                { id: 'turtlebot4' as const, label: 'TurtleBot 4' },
              ]
            ).map((item) => (
              <button
                key={item.id}
                onClick={() => setSelected(item.id)}
                className={`px-2.5 py-1 rounded-md text-[11.5px] font-medium transition-colors ${
                  selected === item.id ? 'bg-emerald-500/15 text-emerald-300' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <button
            onClick={() => setWireframe((w) => !w)}
            className={`px-2.5 py-1.5 rounded-md border text-[11px] font-medium transition-colors ${
              wireframe
                ? 'bg-amber-500/15 border-amber-500/30 text-amber-300'
                : 'bg-black/20 border-white/[0.08] text-slate-300 hover:bg-black/40'
            }`}
          >
            Wireframe
          </button>
        </div>
      </div>

      {error && (
        <p className="text-[11.5px] text-rose-300 pt-3">
          Could not load real link dimensions from the backend for {selected}.
        </p>
      )}

      <div className="mt-3.5 rounded-lg overflow-hidden border border-white/[0.06] bg-app-surface" style={{ height: 380 }}>
        <Canvas camera={{ position: [0.28, 0.22, 0.28], fov: 45 }}>
          <ambientLight intensity={0.5} />
          <directionalLight position={[0.6, 0.9, 0.6]} intensity={1.15} />
          <directionalLight position={[-0.6, 0.45, -0.3]} intensity={0.4} color="#ffb300" />
          <directionalLight position={[0, -0.3, 0.6]} intensity={0.15} color="#d81f10" />
          <Grid args={[1.2, 1.2]} cellColor="#1c1c1c" sectionColor="#3d2e05" fadeDistance={2} infiniteGrid position={[0, -0.005, 0]} />
          {currentLinks && (
            <Bounds key={selected} fit clip margin={1.35}>
              {selected === 'inspire_hand' ? (
                <InspireHandMesh
                  links={currentLinks}
                  actuatorPositions={actuatorPositions}
                  graspState={graspState}
                  heldObjectDiameterM={heldObjectDiameterM}
                  wireframe={wireframe}
                />
              ) : (
                <TurtleBotMesh links={currentLinks} wireframe={wireframe} />
              )}
            </Bounds>
          )}
          <ContactShadows position={[0, -0.003, 0]} opacity={0.5} scale={1} blur={2} far={0.5} color="#000000" />
          <OrbitControls enableDamping dampingFactor={0.1} />
        </Canvas>
      </div>

      <p className="text-[11px] text-slate-600 pt-2.5">
        Segment lengths come from the real, published <code className="font-data">RobotSpec.links</code> for{' '}
        {selected === 'inspire_hand' ? 'the RH56F1-E2 hand' : 'the TurtleBot 4'} — drag to orbit, scroll to zoom.
      </p>
    </div>
  );
}
