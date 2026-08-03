"""
Digital twin interface (docs/COMPILER_ROADMAP.md v2 vision, items 4-5).

`roboweaver.simulation` (a different, existing package) is the real Inspire Hand
RS485 simulator; this package is the general DigitalTwin contract any robot/skill can
run through -- native (real, pure-Python kinematics/grasp-physics execution) today,
with an honest, non-fabricating placeholder for remote engines (Isaac/Gazebo/Webots)
that aren't reachable in this environment.
"""

from roboweaver.simulation_backends.twin import DigitalTwin, NativeTwin, RemoteTwin, TWIN_REGISTRY

__all__ = ["DigitalTwin", "NativeTwin", "RemoteTwin", "TWIN_REGISTRY"]
