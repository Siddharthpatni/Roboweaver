# Third-party mesh assets

The Collada (`.dae`) files in `visual/` are the real visual CAD meshes for the
Franka Emika Research (FER) arm — the current production successor to the
original Panda, sharing the same link geometry — taken unmodified from:

- Source: https://github.com/frankarobotics/franka_description
- Path: `meshes/robots/fer/visual/`
- License: Apache License, Version 2.0 (see `LICENSE` in this directory)
- Copyright (C) 2024 Franka Robotics GmbH

These are not procedural approximations — they are the same mesh files used by
Franka's own MoveIt/Gazebo/RViz descriptions. The kinematic chain that poses
them (`frontend/src/components/FrankaMeshModel.tsx`) uses the arm's real,
publicly published DH joint offsets from
`franka_description/robots/fer/kinematics.yaml` in the same repository, driven
by the same joint-angle values (`q`) the rest of RoboWeaver's 3D viewer uses.
