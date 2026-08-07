"""Generate one representative RoboWeaver ROS 2 package for the colcon CI gate."""

from __future__ import annotations

import argparse
from pathlib import Path

from roboweaver.codegen.ros2_gen import generate_ros2_package
from roboweaver.compiler import SkillCompiler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    result = SkillCompiler("ur5e").compile_with_diagnostics(
        "Pick up the red cube at x=0.30 y=0.02 z=0.12",
        verbose=False,
    )
    package = generate_ros2_package(result.ir, args.output)
    print(package)


if __name__ == "__main__":
    main()
