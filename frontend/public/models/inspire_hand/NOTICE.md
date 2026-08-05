# Third-party mesh assets

The glTF binary (`.glb`) files in `visual/` are the real visual CAD meshes for
the Inspire Robots RH56 dexterous hand (right-hand variant), taken unmodified
from:

- Source: https://github.com/dexsuite/dex-urdf
- Path: `robots/hands/inspire_hand/meshes/visual/`
- License: MIT License (see `LICENSE` in this directory)
- Copyright (c) 2023-2024 DexSuite

These are not procedural approximations — they are the same mesh files
referenced by that repository's own `inspire_hand_right.urdf`. The kinematic
chain that poses them (`frontend/src/components/robot3d/InspireHandCADModel.tsx`)
uses that URDF's real joint origins, axes, and mimic-joint coupling
(`meshes/visual/right_*.glb`, `inspire_hand_right.urdf` at the path above),
driven by the same real per-actuator grasp state
(`InspireHandSimulator`/`actuatorPositions`) the rest of RoboWeaver's digital
twin uses.
