"""RoboWeaver Hardware Abstraction Subsystem."""

from roboweaver.hardware.robot_spec import RobotSpec, JointSpec, LinkSpec
from roboweaver.hardware.registry_robots import (
    ROBOT_REGISTRY,
    distinct_robot_specs,
    get_robot_spec,
    get_franka_panda_spec,
    get_ur5e_spec,
    get_kuka_iiwa_spec,
    get_kinova_gen3_spec,
    get_abb_irb120_spec,
)
from roboweaver.hardware.kinematics_ndof import forward_kinematics_ndof, forward_kinematics_chain_ndof, NDOFIKSolver
from roboweaver.hardware.safety_guard import WorkspaceSafetyGuard, SafetyCheckResult
from roboweaver.hardware.inspire_hand_rs485 import InspireHandRS485Driver, InspireHandState
from roboweaver.hardware.universal_driver import UniversalRobotDriver

__all__ = [
    "RobotSpec",
    "JointSpec",
    "LinkSpec",
    "ROBOT_REGISTRY",
    "distinct_robot_specs",
    "get_robot_spec",
    "get_franka_panda_spec",
    "get_ur5e_spec",
    "get_kuka_iiwa_spec",
    "get_kinova_gen3_spec",
    "get_abb_irb120_spec",
    "forward_kinematics_ndof",
    "forward_kinematics_chain_ndof",
    "NDOFIKSolver",
    "WorkspaceSafetyGuard",
    "SafetyCheckResult",
    "InspireHandRS485Driver",
    "InspireHandState",
    "UniversalRobotDriver",
]
