"""Build the generated ROS 2 Python package as a wheel in CI."""

import subprocess
import sys

import pytest

from roboweaver.codegen.ros2_gen import generate_ros2_package
from roboweaver.compiler import SkillCompiler


def test_generated_ros2_package_builds_as_python_distribution(tmp_path):
    pytest.importorskip("build.__main__")
    result = SkillCompiler("ur5e").compile_with_diagnostics(
        "Pick up the red cube at x=0.30 y=0.02 z=0.12",
        verbose=False,
    )
    package = generate_ros2_package(result.ir, tmp_path / "workspace")
    completed = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation"],
        cwd=package,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
    wheels = list((package / "dist").glob("*.whl"))
    assert len(wheels) == 1
