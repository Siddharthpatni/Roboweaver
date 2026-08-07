"""
Inspire RH56F1-E2 (RS485) Dexterous Hand Real-Time Kinematic & Physics Simulator.

Provides:
1. Real-time actuator motion & grasping force simulation
2. Object Contact & Grasp Stability Physics Engine (Vials, Bolts, Tools, Fragile items)
3. High-Tech ASCII Terminal Real-Time Visualizer
4. Automated Manipulation Sequence Runner
"""

from __future__ import annotations
from dataclasses import dataclass
from roboweaver.hardware.inspire_hand_rs485 import InspireHandRS485Driver, InspireHandState


@dataclass
class SimulatedObject:
    name: str
    diameter_mm: float
    compatible_gestures: list[str]
    min_hold_force_n: float
    max_safe_force_n: float
    slip_risk: float = 0.0
    status: str = "IDLE"


class InspireHandSimulator:
    """Real-Time Physics & Visual Simulation Engine for Inspire RH56F1-E2."""

    OBJECT_CATALOG = {
        "medical_vial": SimulatedObject("Medical Vial (25mm)", 25.0, ["precision_grip", "pinch", "fist"], 5.0, 30.0),
        "hex_bolt": SimulatedObject("M8 Hex Bolt (12mm)", 12.0, ["pinch", "fist"], 3.0, 45.0),
        "tool_handle": SimulatedObject("Drill Tool Handle (40mm)", 40.0, ["cylindrical_grip", "fist"], 15.0, 80.0),
        "fragile_egg": SimulatedObject("Fragile Specimen (45mm)", 45.0, ["precision_grip"], 2.0, 8.0),
    }

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 115200):
        self.driver = InspireHandRS485Driver(
            port=port,
            baudrate=baudrate,
            allow_simulation=True,
        )
        self.driver.connect()
        self.current_object: SimulatedObject | None = None
        self.time_elapsed: float = 0.0
        self.stability_score: float = 1.0

    def load_object(self, object_key: str) -> SimulatedObject:
        """Load a target object into the hand's grasping workspace."""
        if object_key not in self.OBJECT_CATALOG:
            raise KeyError(f"Unknown object: '{object_key}'. Available: {list(self.OBJECT_CATALOG.keys())}")
        self.current_object = self.OBJECT_CATALOG[object_key]
        self.current_object.status = "PRESENT IN WORKSPACE"
        return self.current_object

    def step(self, dt: float = 0.05) -> InspireHandState:
        """Advance the physics and grasp stability simulation by dt seconds."""
        self.time_elapsed += dt
        state = self.driver.read_state()
        total_force = sum(state.actuator_forces_n)

        if self.current_object:
            # Check gesture compatibility and force thresholds
            gesture = state.gesture_active
            if gesture in self.current_object.compatible_gestures and total_force >= self.current_object.min_hold_force_n:
                if total_force <= self.current_object.max_safe_force_n:
                    self.current_object.status = "STABLE GRASP"
                    self.stability_score = 1.0
                    self.current_object.slip_risk = 0.0
                else:
                    self.current_object.status = "CRUSH HAZARD - EXCESS FORCE"
                    self.stability_score = 0.3
            elif total_force > 0:
                self.current_object.status = "UNSTABLE / SLIPPING"
                self.stability_score = 0.5
                self.current_object.slip_risk = 0.8
            else:
                self.current_object.status = "RELEASED / IN WORKSPACE"
                self.stability_score = 1.0
                self.current_object.slip_risk = 0.0

        return state

    def render_ascii_frame(self) -> str:
        """Render a high-tech terminal ASCII visualizer frame of the Inspire hand."""
        state = self.driver.read_state()
        total_force = sum(state.actuator_forces_n)

        names = [
            "Thumb Flex  (Act 0)",
            "Thumb Roll  (Act 1)",
            "Index Flex  (Act 2)",
            "Middle Flex (Act 3)",
            "Ring Flex   (Act 4)",
            "Pinky Flex  (Act 5)",
        ]

        lines = [
            "╔═════════════════════════════════════════════════════════════════════════════════╗",
            "║             INSPIRE ROBOTS RH56F1-E2 (RS485) DEXTEROUS HAND SIMULATOR           ║",
            "╠═════════════════════════════════════════════════════════════════════════════════╣",
            "║ BUS STATUS : CONNECTED (115200 Baud)    SIMULATION MODE: HIGH-FIDELITY ACTIVE   ║",
            f"║ GESTURE    : {state.gesture_active.upper().ljust(15)}            ELAPSED TIME   : {self.time_elapsed:5.2f} s               ║",
            "╠═════════════════════════════════════════════════════════════════════════════════╣",
        ]

        for i in range(6):
            pos = state.actuator_positions[i]
            force = state.actuator_forces_n[i]
            pct = (pos / 1000.0) * 100.0
            bar_len = int(pos / 50)  # 0 to 20 chars
            bar = ("█" * bar_len).ljust(20, "░")
            line = f"║  {names[i]:19} [{bar}] {pct:5.1f}%  |  Force: {force:5.2f} N      ║"
            lines.append(line)

        lines.append("╠═════════════════════════════════════════════════════════════════════════════════╣")
        if self.current_object:
            lines.append(f"║ TARGET OBJECT  : {self.current_object.name.ljust(25)}  TOTAL FORCE: {total_force:6.2f} N          ║")
            lines.append(f"║ GRASP STATUS   : {self.current_object.status.ljust(35)}  STABILITY  : {(self.stability_score * 100.0):5.1f}%         ║")
        else:
            lines.append(f"║ TARGET OBJECT  : NONE                      TOTAL FORCE: {total_force:6.2f} N          ║")
            lines.append("║ GRASP STATUS   : OPEN WORKSPACE            STABILITY  : 100.0%         ║")
        lines.append("╚═════════════════════════════════════════════════════════════════════════════════╝")

        return "\n".join(lines)

    def run_manipulation_sequence(
        self,
        object_key: str = "medical_vial",
        gesture_sequence: list[str] | None = None,
        step_delay: float = 0.05,
        print_frames: bool = True,
    ) -> list[str]:
        """Run an automated dexterous manipulation simulation sequence and return visual frames."""
        self.load_object(object_key)
        gesture_sequence = gesture_sequence or ["open", "precision_grip", "open"]
        frames = []

        for gesture in gesture_sequence:
            self.driver.set_gesture(gesture)
            for _ in range(5):  # 5 simulation steps per posture
                self.step(dt=step_delay)
                frame = self.render_ascii_frame()
                frames.append(frame)
                if print_frames:
                    print(frame)
                    print("\n")

        return frames
