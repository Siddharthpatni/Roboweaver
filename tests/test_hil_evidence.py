import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware.universal_driver import (
    AbstractRobotBridge,
    RobotConnectionStatus,
    SimulationHardwareBridge,
)
from roboweaver.hardware import get_robot_spec
from roboweaver.hil import HILAcceptanceError, HILRunner


class FeedbackBridge(AbstractRobotBridge):
    def __init__(self, spec):
        super().__init__(spec, "physical-test://controller")
        self.state = [0.0] * spec.dof

    def connect(self):
        self._connected = True
        return RobotConnectionStatus(True, "test physical", self.spec.id, self.spec.dof, ["joint"], 1.0, "live")

    def send_trajectory(self, waypoints, dt=0.01):
        self.state = list(waypoints[-1])
        return self._connected

    def read_joint_state(self):
        return list(self.state)

    def read_safety_state(self):
        return {
            "available": True,
            "estop_released": True,
            "watchdog_ok": True,
            "protective_stop_clear": True,
        }

    def disconnect(self):
        self._connected = False


def test_hil_evidence_requires_feedback_and_has_verifiable_digest():
    result = SkillCompiler("ur5e").compile_with_diagnostics(
        "Pick cube x=0.3 y=0.02 z=0.12", verbose=False,
    )
    bridge = FeedbackBridge(get_robot_spec("ur5e"))
    bridge.connect()
    target = [0.02] * bridge.spec.dof
    evidence = HILRunner(bridge).run(
        result.ir, [target], operator="test_operator",
        confirmation=HILRunner.CONFIRMATION, settle_s=0,
    )
    assert evidence.passed is True
    assert evidence.verify_digest()
    assert evidence.before_joint_state != evidence.after_joint_state


def test_hil_rejects_simulation_and_missing_confirmation():
    spec = get_robot_spec("ur5e")
    with pytest.raises(HILAcceptanceError, match="simulation"):
        HILRunner(SimulationHardwareBridge(spec, "sim://localhost"))
    bridge = FeedbackBridge(spec)
    bridge.connect()
    result = SkillCompiler(spec).compile_with_diagnostics(
        "Pick cube x=0.3 y=0.02 z=0.12", verbose=False,
    )
    with pytest.raises(HILAcceptanceError, match="confirmation"):
        HILRunner(bridge).run(
            result.ir, [[0.02] * spec.dof], operator="operator",
            confirmation="no", settle_s=0,
        )
