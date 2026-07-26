#!/usr/bin/env python3
"""
RoboWeaver Universal Developer Console CLI.

Usage:
    roboweaver compile "Pick up the red cube" --robot ur5e
    roboweaver compile "Tighten M8 bolt" --robot kuka_iiwa
    roboweaver execute "Pick up the red cube" --robot panda
    roboweaver robots list
    roboweaver retarget "Pick up the red cube" --from panda --to ur5e
    roboweaver fleet deploy "Pick up the red cube" --cell factory_cell_1
    roboweaver dashboard --port 8080
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware import ROBOT_REGISTRY, get_robot_spec
from roboweaver.fleet import SkillRetargeter, FleetOrchestrator
from roboweaver.runtime import SkillRuntime
from roboweaver.registry.package import SkillPackage, SkillPackageMetadata
from roboweaver.registry.repository import SkillRepository
from roboweaver.codegen.ros2_gen import generate_ros2_package


def cmd_robots(args) -> int:
    print(f"\n\033[1;35mRoboWeaver Universal Robot Hardware Profiles\033[0m ({len(ROBOT_REGISTRY)} registered):")
    print("─" * 75)
    for r_id, spec in ROBOT_REGISTRY.items():
        print(f"  • \033[1m{spec.name:<24}\033[0m | ID: \033[36m{spec.id:<14}\033[0m | {spec.dof}-DOF | Payload: {spec.payload_capacity_kg}kg | Reach: {spec.max_reach_m}m")
    print("─" * 75 + "\n")
    return 0


def cmd_compile(args) -> int:
    instruction = args.instruction
    robot_id = getattr(args, "robot", "panda")
    spec = get_robot_spec(robot_id)

    print(f"\n\033[1;35mRoboWeaver Skill Compiler\033[0m — Instruction: \033[1m\"{instruction}\"\033[0m")
    compiler = SkillCompiler(target_robot=spec)
    skill = compiler.compile(instruction)

    repo = SkillRepository()
    meta = SkillPackageMetadata(
        id=f"skill_{skill.intent.action.value.lower()}_{skill.intent.object_name}_{spec.id}",
        name=f"{skill.intent.action.value} {skill.intent.object_name} ({spec.name})",
        version="1.0.0",
        description=f"Auto-compiled skill for: {instruction} on {spec.name}",
        action=skill.intent.action.value,
        target_object=skill.intent.object_name,
    )
    pkg = SkillPackage(meta, skill)
    repo.register(pkg)
    print(f"  \033[0;32m✓ Registered skill package in repository: {meta.id}\033[0m\n")
    return 0


def cmd_retarget(args) -> int:
    instruction = args.instruction
    from_robot = getattr(args, "from_robot", "panda")
    to_robot = getattr(args, "to_robot", "ur5e")

    print(f"\n\033[1;35mRoboWeaver Cross-Embodiment Trajectory Retargeter\033[0m")
    print(f"  Retargeting: \033[1m\"{instruction}\"\033[0m")
    print(f"  Source Robot: \033[36m{from_robot}\033[0m ──▶ Target Robot: \033[32m{to_robot}\033[0m\n")

    compiler = SkillCompiler(target_robot=from_robot)
    src_skill = compiler.compile(instruction, verbose=False)

    retargeter = SkillRetargeter()
    res = retargeter.retarget(src_skill, to_robot)

    if res.success:
        print(f"  \033[1;32m✓ RETARGET SUCCESSFUL\033[0m — Skill retargeted from {res.source_robot_id} to {res.target_robot_id}")
        print(f"    Trajectories generated for target kinematic chain.\n")
        return 0
    else:
        print(f"  \033[1;31m✗ RETARGET FAILED\033[0m — Safety or IK Violations:")
        for v in res.safety_violations:
            print(f"    • {v}")
        print()
        return 1


def cmd_fleet(args) -> int:
    instruction = args.instruction
    cell_id = getattr(args, "cell", "factory_cell_1")

    print(f"\n\033[1;35mRoboWeaver Fleet Orchestrator Deployment\033[0m")
    print(f"  Deploying Skill: \033[1m\"{instruction}\"\033[0m to Workcell: \033[36m{cell_id}\033[0m\n")

    orchestrator = FleetOrchestrator()
    orchestrator.add_robot_to_workcell(cell_id, "node_panda_1", "panda")
    orchestrator.add_robot_to_workcell(cell_id, "node_ur5e_1", "ur5e")
    orchestrator.add_robot_to_workcell(cell_id, "node_kuka_1", "kuka_iiwa")

    compiler = SkillCompiler(target_robot="panda")
    skill = compiler.compile(instruction, verbose=False)
    meta = SkillPackageMetadata("skill_fleet_demo", "Fleet Demo", "1.0.0", "Fleet", "PICK", "red_cube")
    pkg = SkillPackage(meta, skill)

    results = orchestrator.deploy_skill_to_fleet(pkg, cell_id)
    print(f"  Workcell Status:")
    for node_id, ok in results.items():
        status = "\033[32m[DEPLOYED & EXECUTING]\033[0m" if ok else "\033[31m[FAILED]\033[0m"
        print(f"    • {node_id:<16} ──▶ {status}")
    print()
    return 0


def cmd_execute(args) -> int:
    instruction = args.instruction
    robot_id = getattr(args, "robot", "panda")
    spec = get_robot_spec(robot_id)

    compiler = SkillCompiler(target_robot=spec)
    skill = compiler.compile(instruction)

    runtime = SkillRuntime()
    result = runtime.execute(skill, verbose=True)
    return 0 if result.success else 1


def cmd_list(args) -> int:
    repo = SkillRepository()
    pkgs = repo.list_packages()
    print(f"\n\033[1;35mRoboWeaver Skill Registry Packages\033[0m ({len(pkgs)} total):")
    print("─" * 70)
    for p in pkgs:
        print(f"  • \033[1m{p.id:<30}\033[0m v{p.version:<6} | {p.name:<22} | Action: {p.action}")
    print("─" * 70 + "\n")
    return 0


def cmd_export(args) -> int:
    instruction = args.instruction
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    robot_id = getattr(args, "robot", "panda")
    spec = get_robot_spec(robot_id)

    compiler = SkillCompiler(target_robot=spec)
    skill = compiler.compile(instruction)

    ros2_pkg_dir = generate_ros2_package(skill, output_dir)
    meta = SkillPackageMetadata(
        id=f"skill_{skill.intent.action.value.lower()}_{skill.intent.object_name}_{spec.id}",
        name=f"{skill.intent.action.value} {skill.intent.object_name} ({spec.name})",
        version="1.0.0",
        description=f"Auto-compiled skill for: {instruction}",
        action=skill.intent.action.value,
        target_object=skill.intent.object_name,
    )
    pkg = SkillPackage(meta, skill)
    rwsp_file = pkg.export_archive(output_dir / f"{meta.id}.rwsp")

    print(f"  \033[0;32m✓ Generated ROS2 Package: {ros2_pkg_dir}\033[0m")
    print(f"  \033[0;32m✓ Exported Skill Package Archive: {rwsp_file}\033[0m\n")
    return 0


def cmd_dashboard(args) -> int:
    from roboweaver.dashboard.server import start_dashboard_server
    start_dashboard_server(port=args.port)
    return 0


def cmd_build_system(args) -> int:
    from roboweaver.fleet.prompt_builder import PromptToWorkcellBuilder
    prompt = args.prompt
    output_dir = getattr(args, "output", None)
    PromptToWorkcellBuilder.build_from_prompt(prompt, output_dir=output_dir, verbose=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="roboweaver",
        description="RoboWeaver — Robotics Skill Operating System CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # robots
    subparsers.add_parser("robots", help="List all registered industrial robot hardware profiles")

    # build / prompt (Prompt-to-System Multi-Robot Builder)
    p_build = subparsers.add_parser("build", help="Build complete multi-robot workcell system from natural language prompt")
    p_build.add_argument("prompt", type=str, help="System prompt (e.g. 'Build ShopMate-R connecting Temi, Pepper, and Franka')")
    p_build.add_argument("--output", type=str, default=None, help="Output directory path for ROS 2 package")

    p_prompt = subparsers.add_parser("prompt", help="Alias for 'build'")
    p_prompt.add_argument("prompt", type=str, help="System prompt")
    p_prompt.add_argument("--output", type=str, default=None, help="Output directory path for ROS 2 package")

    # compile
    p_compile = subparsers.add_parser("compile", help="Compile natural language instruction into a skill")
    p_compile.add_argument("instruction", type=str, help="Instruction (e.g. 'Pick up the red cube')")
    p_compile.add_argument("--robot", type=str, default="panda", help="Target robot profile (panda, ur5e, kuka_iiwa, kinova_gen3, abb_irb120)")

    # retarget
    p_retarget = subparsers.add_parser("retarget", help="Retarget skill trajectory across different robot embodiments")
    p_retarget.add_argument("instruction", type=str, help="Instruction to retarget")
    p_retarget.add_argument("--from", dest="from_robot", type=str, default="panda", help="Source robot profile")
    p_retarget.add_argument("--to", dest="to_robot", type=str, default="ur5e", help="Target robot profile")

    # fleet
    p_fleet = subparsers.add_parser("fleet", help="Deploy skill across multi-robot workcell fleet")
    p_fleet.add_argument("instruction", type=str, help="Instruction to deploy")
    p_fleet.add_argument("--cell", type=str, default="factory_cell_1", help="Target workcell ID")

    # execute
    p_execute = subparsers.add_parser("execute", help="Execute compiled skill in simulation")
    p_execute.add_argument("instruction", type=str, help="Instruction to execute")
    p_execute.add_argument("--robot", type=str, default="panda", help="Robot model")

    # list
    subparsers.add_parser("list", help="List registered skill packages")

    # export
    p_export = subparsers.add_parser("export", help="Export skill to ROS2 package and .rwsp archive")
    p_export.add_argument("instruction", type=str, help="Instruction to export")
    p_export.add_argument("--output", type=str, default="./output", help="Output directory path")
    p_export.add_argument("--robot", type=str, default="panda", help="Robot model")

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Launch web dashboard control center")
    p_dash.add_argument("--port", type=int, default=8080, help="HTTP port")

    args = parser.parse_args()

    if args.command == "robots":
        return cmd_robots(args)
    elif args.command in ("build", "prompt"):
        return cmd_build_system(args)
    elif args.command == "compile":
        return cmd_compile(args)
    elif args.command == "retarget":
        return cmd_retarget(args)
    elif args.command == "fleet":
        return cmd_fleet(args)
    elif args.command == "execute":
        return cmd_execute(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "export":
        return cmd_export(args)
    elif args.command == "dashboard":
        return cmd_dashboard(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
