"""
DigitalTwin contract -- item 4 of docs/COMPILER_ROADMAP.md's v2 vision.

`NativeTwin` is a real implementation: it wraps runtime/engine.py::SkillRuntime,
which already does real kinematics, grasp-contact physics, and telemetry recording
(not a stub). `RemoteTwin` wraps the existing, already-honest
hardware/universal_driver.py::SimulationHardwareBridge -- which only verifies TCP
reachability to an Isaac/Gazebo/Webots process, never a real physics handshake.
RemoteTwin.execute() reports that plainly rather than fabricating a simulated
execution outcome for an engine that was never actually driven.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from roboweaver.hardware.robot_spec import RobotSpec
from roboweaver.plugins.registry import PluginRegistry
from roboweaver.types import CompiledSkill, ExecutionResult


class DigitalTwin(ABC):
    """Compile -> Twin -> Test -> Deploy: `execute()` is the "Test" step. Every
    implementation must return a real ExecutionResult -- never a placeholder."""

    name: str = "unnamed_twin"

    @abstractmethod
    def load_robot(self, robot_spec: RobotSpec) -> None:
        raise NotImplementedError

    @abstractmethod
    def execute(self, skill: CompiledSkill) -> ExecutionResult:
        raise NotImplementedError

    def collect_metrics(self) -> dict:
        return {}


class NativeTwin(DigitalTwin):
    """Real: wraps the already-working, pure-Python SkillRuntime (kinematics, grasp
    physics, telemetry). Not a stub -- the only twin that actually executes today."""

    name = "native"

    def __init__(self):
        self._robot_spec: RobotSpec | None = None
        self._runtime = None

    def load_robot(self, robot_spec: RobotSpec) -> None:
        from roboweaver.runtime.engine import SkillRuntime
        self._robot_spec = robot_spec
        self._runtime = SkillRuntime(robot_spec=robot_spec)

    def execute(self, skill: CompiledSkill) -> ExecutionResult:
        if self._runtime is None:
            raise RuntimeError("NativeTwin.load_robot() must be called before execute()")
        return self._runtime.execute(skill, verbose=False)

    def collect_metrics(self) -> dict:
        if self._runtime is None:
            return {}
        return {
            "telemetry_frame_count": len(self._runtime.telemetry.frames),
            "step_count": self._runtime.step_count,
        }


class RemoteTwin(DigitalTwin):
    """Honest placeholder for Isaac/Gazebo/Webots: only verifies the sim process is
    TCP-reachable (hardware/universal_driver.py::SimulationHardwareBridge, already
    real and already honest about this limit). execute() never fabricates a
    simulated physics outcome for an engine it never actually drove."""

    name = "remote"

    def __init__(self, protocol: str = "sim", uri: str = "sim://localhost"):
        self._protocol = protocol
        self._uri = uri
        self._robot_spec: RobotSpec | None = None

    def load_robot(self, robot_spec: RobotSpec) -> None:
        self._robot_spec = robot_spec

    def execute(self, skill: CompiledSkill) -> ExecutionResult:
        from roboweaver.hardware.universal_driver import resolve_bridge_class

        if self._robot_spec is None:
            raise RuntimeError("RemoteTwin.load_robot() must be called before execute()")

        bridge_cls = resolve_bridge_class(self._protocol)
        bridge = bridge_cls(self._robot_spec, self._uri)
        status = bridge.connect()
        bridge.disconnect()

        # Deliberately not a real execution result: only reachability was checked.
        # success=False is the honest outcome, not a fabricated pass/fail on physics
        # that never ran.
        message = (
            f"RemoteTwin only verifies TCP reachability to {self._uri} "
            f"(connected={status.is_connected}); no real physics simulation ran -- "
            f"Isaac/Gazebo/Webots aren't reachable/integrated in this environment."
        )
        return ExecutionResult(
            success=False,
            initial_object_height=0.0,
            final_object_height=0.0,
            height_gained=0.0,
            cycle_time=0.0,
            joint_limits_respected=False,
            frames=[message],
        )

    def collect_metrics(self) -> dict:
        return {"note": "RemoteTwin collects no real metrics -- reachability check only"}


# Registers classes, not instances -- each twin holds mutable per-use state
# (load_robot() sets it), so every consumer must instantiate its own
# (TWIN_REGISTRY.get("native")()) rather than sharing one stateful singleton.
TWIN_REGISTRY: PluginRegistry[type[DigitalTwin]] = PluginRegistry(kind="digital twin")
TWIN_REGISTRY.register("native")(NativeTwin)
TWIN_REGISTRY.register("remote")(RemoteTwin)
