#!/usr/bin/env python3
"""
RoboWeaver Demo — Proof of the core thesis:

  "Can a machine take human intent and convert it
   into an executable robot capability?"

Usage:
    python -m roboweaver.demo "Pick up the red cube"
    python -m roboweaver.demo                          # uses default instruction

This script:
  1. Loads robot simulation environment (Native 3D Engine or MuJoCo)
  2. Compiles natural-language intent into a structured robot skill
  3. Solves inverse kinematics and generates minimum-jerk trajectories
  4. Executes the skill in physics simulation
  5. Validates that the cube was actually picked up
  6. Saves an interactive HTML/Visual replay of the execution
"""

from __future__ import annotations

import sys
import time
from pathlib import Path


def print_banner(instruction: str) -> None:
    w = 62
    print()
    print(f"\033[1;35m╔{'═' * w}╗\033[0m")
    print(f"\033[1;35m║\033[0m{'RoboWeaver v0.1.0':^{w}}\033[1;35m║\033[0m")
    print(f"\033[1;35m║\033[0m\033[0;37m{'Compile Robotics Knowledge into Executable Intelligence':^{w}}\033[1;35m║\033[0m")
    print(f"\033[1;35m╠{'═' * w}╣\033[0m")
    label = f'INPUT: "{instruction}"'
    print(f"\033[1;35m║\033[0m\033[1;37m{label:^{w}}\033[1;35m║\033[0m")
    print(f"\033[1;35m╚{'═' * w}╝\033[0m")


def print_validation(result) -> None:
    """Print stage 6: validation results."""
    print("\n\033[1;36m━━━ STAGE 6/6: Validate \033[0m")

    checks = [
        (result.height_gained > 0.03,
         f"Cube lifted by: {result.height_gained:.3f}m (threshold: ≥0.03m)"),
        (result.joint_limits_respected,
         "Joint limits respected: all 6 joints"),
        (True,
         f"Cycle time: {result.cycle_time:.1f}s"),
        (True,
         f"Initial height: {result.initial_object_height:.3f}m → Final: {result.final_object_height:.3f}m"),
    ]

    for ok, msg in checks:
        sym = "\033[0;32m✓\033[0m" if ok else "\033[0;31m✗\033[0m"
        print(f"  {sym} {msg}")


def print_result(result, video_path: str | None) -> None:
    """Print the final success/failure banner."""
    w = 62
    print()
    print(f"\033[1;35m{'═' * (w + 2)}\033[0m")

    if result.success:
        print("  \033[1;32m✅ SUCCESS — Robot picked up the red cube.\033[0m")
    else:
        print("  \033[1;31m❌ FAILURE — Cube was not successfully lifted.\033[0m")
        print(f"     Height gained: {result.height_gained:.3f}m (need ≥0.03m)")

    if video_path:
        print(f"  \033[0;37m📹 Replay Saved: {video_path}\033[0m")

    print(f"\033[1;35m{'═' * (w + 2)}\033[0m")
    print()


def main(instruction: str | None = None) -> int:
    """Run the full RoboWeaver demo."""

    if instruction is None:
        instruction = "Pick up the red cube"

    print_banner(instruction)

    # Try optional MuJoCo initialization
    model = None
    data = None
    try:
        import mujoco
        model_path = Path(__file__).resolve().parent.parent.parent / "models" / "tabletop.xml"
        if model_path.exists():
            model = mujoco.MjModel.from_xml_path(str(model_path))
            data = mujoco.MjData(model)
            mujoco.mj_forward(model, data)
            for _ in range(100):
                mujoco.mj_step(model, data)
    except Exception:
        model = None
        data = None

    # ── Compile ──
    from roboweaver.compiler import SkillCompiler

    compiler = SkillCompiler(model, data)

    t0 = time.perf_counter()
    skill = compiler.compile(instruction)
    compile_time = time.perf_counter() - t0

    # ── Execute ──
    from roboweaver.runtime import SkillRuntime

    runtime = SkillRuntime(model, data)

    t0 = time.perf_counter()
    result = runtime.execute(skill, verbose=True)
    exec_time = time.perf_counter() - t0

    # ── Validate ──
    print_validation(result)

    # ── Save video / replay ──
    output_dir = Path(__file__).resolve().parent.parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    video_path = str(output_dir / "pick_red_cube.html")

    runtime.save_video(video_path)

    # ── Result ──
    print_result(result, video_path)
    print(f"  \033[0;90mCompile: {compile_time:.2f}s  |  Execute: {exec_time:.2f}s  |  "
          f"Frames Captured: {len(result.frames)}\033[0m")
    print()

    return 0 if result.success else 1


if __name__ == "__main__":
    instruction = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    sys.exit(main(instruction))
