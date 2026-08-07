"""Run a guarded physical HIL acceptance and write evidence only on success."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware import UniversalRobotDriver, get_robot_spec
from roboweaver.hil import HILRunner


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robot", required=True)
    parser.add_argument("--protocol", default="ros2")
    parser.add_argument("--uri", default="ros2://localhost")
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--confirmation", required=True, help=f"Must equal: {HILRunner.CONFIRMATION}")
    args = parser.parse_args()

    spec = get_robot_spec(args.robot)
    result = SkillCompiler(spec).compile_with_diagnostics(args.instruction, verbose=False)
    segments = list(result.skill.motion_plan.trajectories.values())
    if not segments:
        raise SystemExit("compiled skill has no trajectory to exercise")
    bridge = UniversalRobotDriver.connect_robot(spec, args.protocol, args.uri)
    try:
        evidence = HILRunner(bridge).run(
            result.ir,
            [list(point) for point in segments[0].waypoints],
            operator=args.operator,
            confirmation=args.confirmation,
        )
        args.output.write_text(json.dumps(evidence.to_dict(), indent=2) + "\n", encoding="utf-8")
    finally:
        bridge.disconnect()


if __name__ == "__main__":
    main()
