"""Generate the same deterministic URDF used by compiler/frontend evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

from roboweaver.codegen.urdf_gen import generate_urdf
from roboweaver.hardware import get_robot_spec


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--robot", default="franka_panda")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(generate_urdf(get_robot_spec(args.robot)), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
