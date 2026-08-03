"""
RobotBackend contract (docs/COMPILER_ROADMAP.md v2 vision, item 3) -- a richer
plugin contract than a bare "name -> class" codegen registry: metadata(),
capabilities(), validate(), compile(), deploy(). Two real implementations (ROS 2,
URScript), registered in the PluginRegistry built for item/Phase 13.

Explicitly not built: MoveIt/Isaac/Drake/Webots/CuRobo/BehaviorTree.CPP/ABB
RAPID/KUKA KRL/Fanuc TP backends -- each needs per-vendor protocol/controller
knowledge this session can't validate against real hardware. Adding one later means
registering another RobotBackend, not rewriting this module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TYPE_CHECKING

from roboweaver.hardware.registry_robots import get_robot_spec
from roboweaver.hardware.universal_driver import RobotConnectionStatus, resolve_bridge_class
from roboweaver.ir.diagnostics import CompilerDiagnostic
from roboweaver.plugins.registry import PluginRegistry

if TYPE_CHECKING:
    from roboweaver.compiler import CompilationResult
    from roboweaver.types import ExecutionResult


class DeploymentRefused(Exception):
    """Raised by RobotBackend.deploy() when simulation validation (item 5) or the
    Safety Kernel (item 9) refuses to let a deploy proceed. Carries the real
    ExecutionResult/diagnostics that caused the refusal, not just a message."""

    def __init__(self, message: str, *, execution_result: "ExecutionResult | None" = None):
        super().__init__(message)
        self.execution_result = execution_result


class RobotBackend(ABC):
    """What a real deployment target must answer: what it supports, whether a
    compiled skill is valid for it, how to generate code, and how to actually
    deploy -- using the real UniversalRobotDriver bridge underneath, not a mock."""

    name: str = "unnamed_backend"

    @abstractmethod
    def metadata(self) -> dict[str, Any]:
        raise NotImplementedError

    def capabilities(self) -> list[str]:
        return []

    def validate(self, result: "CompilationResult") -> list[CompilerDiagnostic]:
        """Default: the diagnostics the compile pipeline's Pass Managers already
        computed -- real, not re-implemented. Override to add backend-specific
        checks (e.g. "this format needs exactly 6 DOF")."""
        return list(result.diagnostics)

    @abstractmethod
    def compile(self, result: "CompilationResult", output_dir: Path) -> Path:
        raise NotImplementedError

    def deploy(
        self, result: "CompilationResult", protocol: str = "sim", uri: str = "sim://localhost",
        skip_simulation_check: bool = False,
    ) -> RobotConnectionStatus:
        """Real Compile -> Safety Kernel -> Twin -> Test -> Deploy gate.

        1. SafetyKernel.enforce() (item 9, plugins/safety_kernel.py) -- always runs,
           no opt-out. Defense in depth: compile_with_diagnostics() already refuses
           to hand back a CompilationResult with an error diagnostic, so this can
           never fire on the normal path -- it protects against a CompilationResult
           that reached deploy() some other way (constructed directly, deserialized).
        2. validate_in_simulation() (item 5, runtime/validation.py) -- raises
           DeploymentRefused if the real NativeTwin execution didn't succeed.
           `skip_simulation_check` is an explicit, visible opt-out for this step only
           (e.g. tests exercising just the connect/send path) -- the Safety Kernel
           step above has no such opt-out.
        3. Connects via the existing, honest UniversalRobotDriver bridge and sends
           every real compiled trajectory segment in order."""
        from roboweaver.plugins.safety_kernel import SafetyKernel
        SafetyKernel.enforce(result)

        robot_spec = get_robot_spec(result.ir.execution.robot_id)

        if not skip_simulation_check:
            from roboweaver.runtime.validation import validate_in_simulation
            sim_result = validate_in_simulation(result.skill, robot_spec)
            if not sim_result.success:
                raise DeploymentRefused(
                    f"Simulation validation failed before deploy to {protocol}://{uri} -- "
                    f"refusing to send trajectories to real hardware. "
                    f"height_gained={sim_result.height_gained:.4f}m, "
                    f"joint_limits_respected={sim_result.joint_limits_respected}.",
                    execution_result=sim_result,
                )

        bridge_cls = resolve_bridge_class(protocol)
        bridge = bridge_cls(robot_spec, uri)
        status = bridge.connect()

        if status.is_connected:
            for seg in result.skill.motion_plan.trajectories.values():
                dt = seg.duration / max(len(seg.waypoints) - 1, 1)
                bridge.send_trajectory(seg.waypoints, dt=dt)
            bridge.disconnect()

        return status


class Ros2Backend(RobotBackend):
    name = "ros2"

    def metadata(self) -> dict[str, Any]:
        return {
            "name": "ros2",
            "description": "ROS 2 package: action server, launch file, BehaviorTree XML",
            "output": "ros2_package_dir",
        }

    def capabilities(self) -> list[str]:
        return ["any_dof", "behavior_tree_xml", "action_server"]

    def compile(self, result: "CompilationResult", output_dir: Path) -> Path:
        from roboweaver.codegen.ros2_gen import generate_ros2_package
        return generate_ros2_package(result.skill, output_dir)


class UrScriptBackend(RobotBackend):
    name = "urscript"

    def metadata(self) -> dict[str, Any]:
        return {
            "name": "urscript",
            "description": "Universal Robots URScript (.script)",
            "output": ".script file",
        }

    def capabilities(self) -> list[str]:
        return ["ur_family_syntax"]

    def compile(self, result: "CompilationResult", output_dir: Path) -> Path:
        from roboweaver.codegen.urscript_gen import generate_urscript
        robot_spec = get_robot_spec(result.ir.execution.robot_id)
        out_path = Path(output_dir) / f"{result.ir.skill_id}.script"
        return generate_urscript(result.skill, robot_spec, out_path)


BACKEND_REGISTRY: PluginRegistry[RobotBackend] = PluginRegistry(kind="robot backend")
BACKEND_REGISTRY.register("ros2")(Ros2Backend())
BACKEND_REGISTRY.register("urscript")(UrScriptBackend())
