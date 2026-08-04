#!/usr/bin/env python3
"""
RoboWeaver Universal Developer Console CLI.

Usage:
    # Compile (runs RoboIR + safety checks; exits 2 on a blocking diagnostic)
    roboweaver compile "Pick up the red cube" --robot ur5e
    roboweaver compile "Tighten M8 bolt" --robot kuka_iiwa --json
    roboweaver compile "Pick up the red cube" --robot panda --explain-passes

    # RoboIR diff -- cross-robot, or across the compile pipeline's own passes
    roboweaver diff "Pick up the red cube" --robot panda --robot2 ur5e

    # 3D model generation -- URDF derived from the real kinematic spec
    roboweaver urdf --robot franka_panda --meshes --output ./out/panda.urdf

    # Network: find robots, bind one, or ask a model what it is
    roboweaver discover
    roboweaver discover --subnet 192.168.1.0/24
    roboweaver advise --host 192.168.1.40 --port 30002 --provider ollama
    roboweaver connect --robot ur5e --protocol sim --uri sim://192.168.1.40:30002

    # Everything else
    roboweaver robots
    roboweaver execute "Pick up the red cube" --robot panda
    roboweaver retarget "Pick up the red cube" --from panda --to ur5e
    roboweaver fleet "Pick up the red cube" --cell factory_cell_1
    roboweaver export "Pick up the red cube" --output ./output
    roboweaver dashboard --port 8080

Exit codes:
    0  success
    1  operation completed but the result was negative (e.g. not connected)
    2  refused: a blocking compiler diagnostic or an invalid argument

Add --json to compile/urdf/discover/connect/advise for machine-readable output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from roboweaver.compiler import SkillCompiler
from roboweaver.ir import SkillCompilationError, OptimizationLevel, diff_ir, diff_trace
from roboweaver.hardware import ROBOT_REGISTRY, get_robot_spec
from roboweaver.fleet import SkillRetargeter, FleetOrchestrator
from roboweaver.runtime import SkillRuntime
from roboweaver.registry.package import SkillPackage, SkillPackageMetadata
from roboweaver.registry.repository import SkillRepository


def cmd_robots(args) -> int:
    print(f"\n\033[1;35mRoboWeaver Universal Robot Hardware Profiles\033[0m ({len(ROBOT_REGISTRY)} registered):")
    print("─" * 75)
    for r_id, spec in ROBOT_REGISTRY.items():
        print(f"  • \033[1m{spec.name:<24}\033[0m | ID: \033[36m{spec.id:<14}\033[0m | {spec.dof}-DOF | Payload: {spec.payload_capacity_kg}kg | Reach: {spec.max_reach_m}m")
    print("─" * 75 + "\n")
    return 0


def cmd_compile(args) -> int:
    """Compile through the *full* pipeline, including RoboIR and the safety
    checks. This previously called compile() directly, which silently skipped
    Stage 05 and the Compiler Debugger -- meaning the CLI would happily emit a
    skill the dashboard would have refused to compile. A compiler that only
    validates on one of its two front-ends is not a validating compiler.
    """
    instruction = args.instruction
    robot_id = getattr(args, "robot", "panda")
    spec = get_robot_spec(robot_id)
    as_json = getattr(args, "json", False)
    explain_passes = getattr(args, "explain_passes", False)
    opt_level = OptimizationLevel(getattr(args, "opt_level", "O1"))

    compiler = SkillCompiler(target_robot=spec)
    try:
        result = compiler.compile_with_diagnostics(
            instruction, verbose=not as_json, optimization_level=opt_level
        )
    except SkillCompilationError as exc:
        if as_json:
            print(json.dumps({
                "ok": False,
                "instruction": instruction,
                "robot": spec.id,
                "diagnostics": [d.to_dict() for d in exc.diagnostics],
            }, indent=2))
        else:
            print(f"\n\033[1;31m✗ Compilation failed\033[0m — {len(exc.diagnostics)} blocking diagnostic(s):")
            for d in exc.diagnostics:
                print(f"  \033[31m{d.code}\033[0m {d.message}\n    {d.reason}")
                for fix in d.fixes:
                    print(f"      → {fix}")
            print()
        # Non-zero exit so CI and shell pipelines actually fail on a bad skill.
        return 2

    skill = result.skill

    if as_json:
        out = {
            "ok": True,
            "instruction": instruction,
            "robot": spec.id,
            "opt_level": opt_level.value,
            "intent": {
                "action": skill.intent.action.value,
                "object_name": skill.intent.object_name,
                "confidence": skill.intent.confidence,
                "parse_warnings": skill.intent.parse_warnings,
                "parameters": skill.intent.parameters,
            },
            "tasks": [{"type": t.type.value, "description": t.description} for t in skill.task_graph.tasks],
            "diagnostics": [d.to_dict() for d in result.diagnostics],
        }
        if explain_passes:
            if result.skill_pipeline is not None:
                out["skill_pipeline"] = result.skill_pipeline.to_dict()
            if result.pipeline is not None:
                out["pipeline"] = result.pipeline.to_dict()
        print(json.dumps(out, indent=2))
        return 0

    for w in skill.intent.parse_warnings:
        print(f"  \033[1;33m⚠ {w}\033[0m")
    if result.diagnostics:
        print(f"\n  \033[33m{len(result.diagnostics)} non-blocking diagnostic(s):\033[0m")
        for d in result.diagnostics:
            print(f"    \033[33m{d.code}\033[0m {d.message}")

    if explain_passes:
        def _print_pass_table(title: str, records) -> None:
            print(f"\n  \033[1;36m{title}\033[0m (opt-level {opt_level.value}):")
            for rec in records:
                status = "skipped" if rec.skipped else ("modified" if rec.modified else "unchanged")
                metrics_note = f"  {rec.metrics}" if rec.metrics else ""
                print(
                    f"    • {rec.pass_name:<28} {rec.timing_s * 1000:>7.3f}ms  "
                    f"[{status}]  {len(rec.diagnostics)} diagnostic(s){metrics_note}"
                )

        if result.skill_pipeline is not None:
            _print_pass_table("Optimization Pipeline (CompiledSkill)", result.skill_pipeline.records)
            print(f"    Total: {result.skill_pipeline.total_timing_s() * 1000:.3f}ms across {len(result.skill_pipeline.records)} pass(es)")
        if result.pipeline is not None:
            _print_pass_table("RoboIR Pipeline", result.pipeline.records)
            print(f"    Total: {result.pipeline.total_timing_s() * 1000:.3f}ms across {len(result.pipeline.records)} pass(es)")

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


def cmd_diff(args) -> int:
    """Compare two RoboIR snapshots (ir/diff.py). With --robot2, diffs the same
    instruction's IR compiled for two different robots -- a real, meaningful
    comparison over the fields RoboIR carries today (execution.dof, constraints.*,
    required_capabilities.*, ...). Without --robot2, diffs the compile pipeline's own
    trace pass-by-pass (ir/pass_manager.py) -- honestly reports "no differences" for
    today's diagnostics-only passes, since no IR-mutating pass exists yet."""
    instruction = args.instruction
    robot_id = getattr(args, "robot", "panda")
    robot2_id = getattr(args, "robot2", None)
    as_json = getattr(args, "json", False)
    spec = get_robot_spec(robot_id)

    compiler = SkillCompiler(target_robot=spec)
    try:
        result = compiler.compile_with_diagnostics(instruction, verbose=False)
    except SkillCompilationError as exc:
        print(f"\n\033[1;31m✗ Compilation failed for {robot_id}\033[0m — cannot diff.")
        for d in exc.diagnostics:
            print(f"  \033[31m{d.code}\033[0m {d.message}")
        return 2

    if robot2_id:
        spec2 = get_robot_spec(robot2_id)
        compiler2 = SkillCompiler(target_robot=spec2)
        try:
            result2 = compiler2.compile_with_diagnostics(instruction, verbose=False)
        except SkillCompilationError as exc:
            print(f"\n\033[1;31m✗ Compilation failed for {robot2_id}\033[0m — cannot diff.")
            for d in exc.diagnostics:
                print(f"  \033[31m{d.code}\033[0m {d.message}")
            return 2

        diff = diff_ir(result.ir, result2.ir)
        if as_json:
            print(json.dumps({
                "instruction": instruction, "from_robot": robot_id, "to_robot": robot2_id,
                "field_changes": {k: list(v) for k, v in diff.field_changes.items()},
                "objects_added": [o.to_dict() for o in diff.objects_added],
                "objects_removed": [o.to_dict() for o in diff.objects_removed],
            }, indent=2))
        else:
            print(f"\n\033[1;35mRoboIR Diff\033[0m — \"{instruction}\": \033[36m{robot_id}\033[0m → \033[32m{robot2_id}\033[0m")
            print("─" * 70)
            print(diff.pretty())
            print()
        return 0

    if result.pipeline is None:
        print("No pipeline trace available.")
        return 1
    pairs = diff_trace(result.pipeline)
    if as_json:
        print(json.dumps({
            "instruction": instruction, "robot": robot_id,
            "passes": [{"pass_name": name, "changed": not d.is_empty()} for name, d in pairs],
        }, indent=2))
        return 0

    print(f"\n\033[1;35mPipeline IR Diff\033[0m — \"{instruction}\" on \033[36m{robot_id}\033[0m")
    print("─" * 70)
    for name, d in pairs:
        print(f"  \033[1m{name}\033[0m: {d.pretty() if not d.is_empty() else 'no differences'}")
    print(
        "\n  \033[0;37mNo IR-mutating passes are registered yet -- Verification/"
        "Capability/Safety only emit diagnostics. Real IR diffs appear once an "
        "optimization pass (docs/COMPILER_ROADMAP.md Phase 4) mutates the IR.\033[0m\n"
    )
    return 0


def cmd_compare(args) -> int:
    """Real multi-objective robot comparison (optimize/cost_model.py, item 8 of
    docs/COMPILER_ROADMAP.md's v2 vision): weighted ranking + a real Pareto-optimal
    subset, both computed from real compiled-skill data -- not a fabricated score."""
    from roboweaver.optimize.cost_model import compare_robots

    instruction = args.instruction
    robot_ids = [r.strip() for r in args.robots.split(",") if r.strip()]
    as_json = getattr(args, "json", False)

    comparison = compare_robots(instruction, robot_ids)

    if as_json:
        print(json.dumps({
            "instruction": instruction,
            "ranked": [
                {"robot": rid, "score": score, "cost": {
                    "estimated_cycle_time_s": cost.estimated_cycle_time_s,
                    "payload_margin_kg": cost.payload_margin_kg,
                    "total_joint_travel_rad": cost.total_joint_travel_rad,
                    "manipulability_margin": cost.manipulability_margin,
                    "historical_success_rate": cost.historical_success_rate,
                }}
                for rid, score, cost in comparison.ranked
            ],
            "pareto_optimal": comparison.pareto_optimal,
            "skipped": comparison.skipped,
        }, indent=2))
        return 0

    print(f"\n\033[1;35mRobot Comparison\033[0m — \"{instruction}\"")
    print("─" * 88)
    for rid, score, cost in comparison.ranked:
        pareto_mark = "\033[32m★ pareto-optimal\033[0m" if rid in comparison.pareto_optimal else ""
        print(f"  \033[1m{rid:<16}\033[0m score={score:>8.3f}  "
              f"cycle={cost.estimated_cycle_time_s:>6.2f}s  payload_margin={cost.payload_margin_kg:>6.2f}kg  "
              f"travel={cost.total_joint_travel_rad:>6.2f}rad  manip={cost.manipulability_margin:.4f}  {pareto_mark}")
    for rid, reason in comparison.skipped.items():
        print(f"  \033[33m{rid:<16}\033[0m skipped -- {reason}")
    print("─" * 88 + "\n")
    return 0


def cmd_benchmark(args) -> int:
    """RoboBench (benchmark/robobench.py, item 11 of docs/COMPILER_ROADMAP.md's v2
    vision): real compile-pipeline measurement across every distinct registered
    robot x every reachable skill category."""
    from roboweaver.benchmark import run_benchmark

    robot_ids = [r.strip() for r in args.robots.split(",") if r.strip()] if getattr(args, "robots", None) else None
    report = run_benchmark(robot_ids=robot_ids)
    as_json = getattr(args, "json", False)

    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        data = report.to_dict()
        print(f"\n\033[1;35mRoboBench\033[0m — {data['scope']}")
        print("─" * 88)
        for cell in report.cells:
            mark = "\033[32m✓\033[0m" if cell.success else "\033[31m✗\033[0m"
            reduction = f"{cell.waypoint_pct_reduction:.1f}%" if cell.waypoint_pct_reduction is not None else "n/a"
            print(f"  {mark} {cell.category:<16} {cell.robot_id:<20} {cell.compile_time_s * 1000:>7.3f}ms  "
                  f"errors={cell.error_count} warnings={cell.warning_count} waypoint_reduction={reduction}")
        print("─" * 88)
        print(f"  {data['success_count']}/{data['total_cells']} cells compiled successfully, "
              f"total {data['total_compile_time_s']:.3f}s\n")

    if getattr(args, "output", None):
        Path(args.output).write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        print(f"  \033[0;32m✓ Report written to {args.output}\033[0m\n")

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


def cmd_sim(args) -> int:
    robot_id = getattr(args, "robot", "inspire_hand").lower()
    if robot_id in ("inspire_hand", "inspire", "rh56f1", "rh56f1_e2", "inspire_hand_rh56f1_e2"):
        from roboweaver.simulation import InspireHandSimulator, generate_inspire_urdf

        print("\n\033[1;36m━━━ RoboWeaver Real-Time Inspire Hand RH56F1-E2 (RS485) Simulation ━━━\033[0m")
        sim = InspireHandSimulator()
        object_key = getattr(args, "object", "medical_vial")
        gestures_str = getattr(args, "gestures", "open,precision_grip,open")
        gestures = [g.strip() for g in gestures_str.split(",") if g.strip()]

        sim.run_manipulation_sequence(
            object_key=object_key,
            gesture_sequence=gestures,
            step_delay=0.03,
            print_frames=True,
        )

        if getattr(args, "export_urdf", None):
            urdf_path = Path(args.export_urdf)
            generate_inspire_urdf(urdf_path)
            print(f"  ✓ Exported Inspire RH56F1-E2 URDF to: \033[1m{urdf_path}\033[0m")

        if getattr(args, "export_html", None):
            from roboweaver.simulation import export_html_simulation_report
            html_path = Path(args.export_html)
            export_html_simulation_report(html_path, object_key=object_key, gestures=gestures)
            print(f"  ✓ Exported Interactive HTML Simulation Dashboard to: \033[1m{html_path}\033[0m\n")
        return 0
    else:
        print(f"Simulation currently specialized for 'inspire_hand' (received '{robot_id}').")
        return 1


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
    """Compile through the *full* pipeline (compile_with_diagnostics, not bare
    compile()) and generate code via the RobotBackend registry (plugins/backend.py)
    -- the same "don't validate on only one front-end" fix cmd_compile already got
    (see its docstring); export used to skip Stage 05/the Compiler Debugger too."""
    from roboweaver.plugins.backend import BACKEND_REGISTRY
    from roboweaver.plugins.safety_kernel import SafetyKernel

    instruction = args.instruction
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    robot_id = getattr(args, "robot", "panda")
    spec = get_robot_spec(robot_id)
    backend_name = getattr(args, "backend", "ros2")

    compiler = SkillCompiler(target_robot=spec)
    try:
        result = compiler.compile_with_diagnostics(instruction, verbose=False)
    except SkillCompilationError as exc:
        print(f"\n\033[1;31m✗ Compilation failed\033[0m — {len(exc.diagnostics)} blocking diagnostic(s):")
        for d in exc.diagnostics:
            print(f"  \033[31m{d.code}\033[0m {d.message}\n    {d.reason}")
        return 2

    backend = BACKEND_REGISTRY.get(backend_name)
    backend_output = backend.compile(result, output_dir)

    skill = result.skill
    meta = SkillPackageMetadata(
        id=f"skill_{skill.intent.action.value.lower()}_{skill.intent.object_name}_{spec.id}",
        name=f"{skill.intent.action.value} {skill.intent.object_name} ({spec.name})",
        version="1.0.0",
        description=f"Auto-compiled skill for: {instruction}",
        action=skill.intent.action.value,
        target_object=skill.intent.object_name,
    )
    pkg = SkillPackage(meta, skill)
    manifest = SafetyKernel.build_deployment_manifest(result, backend_name)
    rwsp_file = pkg.export_archive(output_dir / f"{meta.id}.rwsp", deployment_manifest=manifest)
    print(f"\n\033[1;32m✓ Skill Successfully Exported\033[0m ({backend_name}):")
    print(f"  • Backend output: \033[1m{backend_output}\033[0m")
    print(f"  • Skill Package Archive: \033[1m{rwsp_file}\033[0m")
    print(f"  • Deployment manifest: safety_kernel_verified={manifest['safety_kernel_verified']}, "
          f"{len(manifest['capability_claims'])} capability claim(s)\n")
    return 0


def cmd_urdf(args) -> int:
    """Generate a loadable 3D model (URDF, optionally with STL meshes) from the
    robot's real kinematic spec -- the same numbers the IK solver plans against."""
    from roboweaver.codegen.urdf_gen import export_urdf

    robot_id = getattr(args, "robot", "franka_panda")
    spec = get_robot_spec(robot_id)
    out = Path(getattr(args, "output", None) or f"./output/urdf/{spec.id}.urdf")

    urdf_path, meshes = export_urdf(spec, out, with_meshes=getattr(args, "meshes", False))

    if getattr(args, "json", False):
        print(json.dumps({
            "robot": spec.id, "dof": spec.dof,
            "urdf": str(urdf_path), "meshes": [str(m) for m in meshes],
        }, indent=2))
        return 0

    print(f"\n\033[1;35mRoboWeaver 3D Model Generation\033[0m — {spec.name} ({spec.dof}-DOF)")
    print(f"  \033[0;32m✓\033[0m URDF: \033[1m{urdf_path}\033[0m ({urdf_path.stat().st_size} bytes)")
    if meshes:
        print(f"  \033[0;32m✓\033[0m {len(meshes)} STL link meshes in \033[1m{meshes[0].parent}\033[0m")
    print("\n  Load it with:")
    print(f"    ros2 launch urdf_tutorial display.launch.py model:={urdf_path}")
    print(f"    python -c \"import pybullet as p; p.connect(p.GUI); p.loadURDF('{urdf_path}')\"")
    print("\n  \033[0;37mGeometry is a cylinder approximation of the real kinematic chain,")
    print("  not vendor CAD. Joint axes, limits, masses and inertias are exact.\033[0m\n")
    return 0


def cmd_discover(args) -> int:
    from roboweaver.hardware.discovery import RobotDiscoveryService

    subnet = getattr(args, "subnet", None)
    scanner = RobotDiscoveryService(timeout=0.3 if subnet else 0.8)
    try:
        result = scanner.scan_subnet(subnet) if subnet else scanner.scan()
    except ValueError as exc:
        print(f"\033[1;31m✗\033[0m {exc}")
        return 2

    if getattr(args, "json", False):
        print(json.dumps(scanner.to_dict(result), indent=2))
        return 0

    scope = result.scanned_range or "this machine (127.0.0.1, localhost)"
    print(f"\n\033[1;35mRoboWeaver Robot Discovery\033[0m — scanned {scope}")
    print(f"  {result.hosts_scanned} host(s) x {result.ports_scanned} ports in {result.scan_duration_ms:.0f} ms")
    print("─" * 88)
    if not result.discovered:
        print("  No endpoints responded. That is a real result, not a failed scan.")
    for e in result.discovered:
        flag = "\033[33m?\033[0m" if e.confidence < 0.5 else "\033[32m✓\033[0m"
        print(f"  {flag} \033[1m{e.host}:{e.port}\033[0m  {e.name:<22} {int(e.confidence*100):>3}%  {e.latency_ms:>6.1f}ms  {e.hostname}")
        if e.caveat:
            print(f"      \033[33m{e.caveat}\033[0m")
    print("─" * 88)

    if result.local_transports:
        print(f"\n  Local transports ({result.platform_name}, scannable: {', '.join(result.supported_transports)}):")
        for t in result.local_transports:
            state = "\033[32maccessible\033[0m" if t.readable else "\033[33mpermission denied\033[0m"
            print(f"    [{t.kind:<12}] {t.device:<40} {state}")
            if t.detail:
                print(f"        {t.detail}")
    print()
    return 0


def cmd_connect(args) -> int:
    from roboweaver.hardware.universal_driver import UniversalRobotDriver

    spec = get_robot_spec(args.robot)
    bridge = UniversalRobotDriver.connect_robot(spec, protocol=args.protocol, uri=args.uri)
    status = bridge.connect()

    if getattr(args, "json", False):
        print(json.dumps({
            "robot_id": status.robot_id, "is_connected": status.is_connected,
            "protocol": status.protocol, "dof": status.dof,
            "active_controllers": status.active_controllers,
            "latency_ms": status.latency_ms, "message": status.message,
        }, indent=2))
        return 0 if status.is_connected else 1

    mark = "\033[1;32m✓ CONNECTED\033[0m" if status.is_connected else "\033[1;31m✗ NOT CONNECTED\033[0m"
    print(f"\n{mark} — {spec.name} via {args.protocol} at {args.uri}")
    print(f"  Transport : {status.protocol}")
    print(f"  Message   : {status.message}")
    if status.active_controllers:
        print(f"  Controllers: {', '.join(status.active_controllers)}")
    print()
    return 0 if status.is_connected else 1


def cmd_advise(args) -> int:
    """Ask a local or hosted model to map a discovered endpoint onto a registry
    robot. The suggestion is validated against ROBOT_REGISTRY before display."""
    from roboweaver.nlu.connection_advisor import build_advisor

    endpoint = {
        "host": args.host, "port": args.port, "banner": getattr(args, "banner", "") or "",
        "hostname": getattr(args, "hostname", "") or "",
        "robot_type_guess": getattr(args, "guess", "") or "",
        "latency_ms": getattr(args, "latency", 0.0),
    }
    advice = build_advisor(args.provider, getattr(args, "model", None)).advise(endpoint)

    if getattr(args, "json", False):
        print(json.dumps({
            "robot_id": advice.robot_id, "protocol": advice.protocol, "uri": advice.uri,
            "confidence": advice.confidence, "reasoning": advice.reasoning,
            "provider": advice.provider, "model": advice.model, "error": advice.error,
        }, indent=2))
        return 0 if advice.robot_id else 1

    if advice.error:
        print(f"\n\033[1;31m✗ No usable advice\033[0m ({advice.provider}): {advice.error}\n")
        return 1
    print(f"\n\033[1;35mConnection advice\033[0m ({advice.provider} / {advice.model})")
    print(f"  Robot      : \033[1;36m{advice.robot_id}\033[0m")
    print(f"  Protocol   : {advice.protocol}")
    print(f"  URI        : {advice.uri}")
    print(f"  Confidence : {advice.confidence:.0%}")
    print(f"  Reasoning  : {advice.reasoning}")
    print(f"\n  \033[0;37mA suggestion, not a verification. Confirm before connecting:\033[0m")
    print(f"    roboweaver connect --robot {advice.robot_id} --protocol {advice.protocol} --uri {advice.uri}\n")
    return 0


def cmd_dashboard(args) -> int:
    if getattr(args, "no_self_heal", False):
        from roboweaver.dashboard.server import start_dashboard_server
        start_dashboard_server(port=args.port, host=args.host)
    else:
        # Default: a crashed server restarts itself automatically (exponential
        # backoff, no cap on retries) -- no human needs to notice it died and
        # rerun this command. Ctrl+C still stops it; that is the deliberate
        # off switch, not something the loop requires to keep running.
        from roboweaver.dashboard.server import run_dashboard_supervised
        run_dashboard_supervised(port=args.port, host=args.host)
    return 0


def cmd_nexus(args) -> int:
    from roboweaver.knowledge.package_nexus import RoboticsPackageNexus
    action = getattr(args, "action", "list")
    query_str = getattr(args, "query", "")

    if action == "list" or not query_str:
        pkgs = RoboticsPackageNexus.get_all_packages()
        print(f"\n\033[1;35m━━━ RoboWeaver Universal Robotics Package Nexus ({len(pkgs)} Cataloged Packages) ━━━\033[0m")
        print("─" * 85)
        for p in pkgs:
            robots_str = ", ".join(p.compatible_robots[:3])
            print(f"  • \033[1m{p.name:<38}\033[0m | ID: \033[36m{p.id:<18}\033[0m | Cat: {p.category.upper():<11} | Robots: {robots_str}")
        print("─" * 85 + "\n")
        return 0
    elif action == "query":
        results = RoboticsPackageNexus.query_by_keyword(query_str)
        if not results:
            results = RoboticsPackageNexus.query_by_category(query_str)
        if not results:
            results = RoboticsPackageNexus.query_by_robot(query_str)
        print(f"\n\033[1;35m━━━ Knowledge Nexus Search Results for '{query_str}' ({len(results)} matches) ━━━\033[0m")
        print("─" * 85)
        for p in results:
            print(f"  • \033[1m{p.name}\033[0m (\033[36m{p.id}\033[0m) — [{p.category.upper()}]")
            print(f"    Description  : {p.description}")
            print(f"    ROS 2 Topics : {', '.join(p.default_topics) or 'None'}")
            print(f"    Dependencies : {', '.join(p.ros2_dependencies)}")
            print("─" * 85)
        print()
        return 0
    elif action == "recommend":
        rec = RoboticsPackageNexus.recommend_stack_for_prompt(query_str)
        print(f"\n\033[1;35m━━━ Knowledge Nexus Architecture Recommendation ━━━\033[0m")
        print(f"  Input Prompt         : \"{query_str}\"")
        print(f"  Matched Robot Models : {', '.join(rec['matched_robots'])}")
        print(f"  Recommended Packages : \033[1;32m{', '.join(rec['recommended_packages'])}\033[0m")
        print(f"  ROS 2 Topics Active  : {', '.join(rec['ros2_topics'])}")
        print(f"  ROS 2 Actions Active : {', '.join(rec['ros2_actions'])}")
        print(f"  package.xml Depends  : {', '.join(rec['package_xml_dependencies'])}\n")
        return 0
    return 0


def cmd_build_system(args) -> int:
    from roboweaver.fleet.prompt_builder import PromptToWorkcellBuilder
    prompt = args.prompt
    output_dir = getattr(args, "output", None)
    PromptToWorkcellBuilder.build_from_prompt(prompt, output_dir=output_dir, verbose=True)
    return 0


def cmd_graph(args) -> int:
    """Real knowledge graph (knowledge/ingest_registry.py, gap-fix batch item 2):
    build (real nodes/edges from ROBOT_REGISTRY/PACKAGE_CATALOG/skill taxonomy),
    path (real multi-hop BFS), export-obsidian (real Obsidian-compatible notes)."""
    from roboweaver.knowledge.ingest_registry import build_graph_from_registry

    action = args.graph_action
    graph = build_graph_from_registry()

    if action == "build":
        as_json = getattr(args, "json", False)
        if as_json:
            print(json.dumps(graph.to_dict(), indent=2))
        else:
            print(f"\n\033[1;35mRoboWeaver Knowledge Graph\033[0m — real ingestion from live registries")
            print(f"  Nodes: {len(graph.nodes)}  Edges: {len(graph.edges)}")
        if getattr(args, "output", None):
            graph.save(args.output)
            print(f"  \033[0;32m✓ Saved to {args.output}\033[0m\n")
        return 0

    if action == "path":
        path = graph.find_path(args.from_id, args.to_id, max_hops=getattr(args, "max_hops", 6))
        if path is None:
            print(f"\n\033[1;31m✗ No path\033[0m found from '{args.from_id}' to '{args.to_id}' "
                  f"within {getattr(args, 'max_hops', 6)} hops.\n")
            return 1
        print(f"\n\033[1;35mPath\033[0m: " + " → ".join(f"\033[36m{n}\033[0m" for n in path) + "\n")
        return 0

    if action == "export-obsidian":
        from roboweaver.knowledge.obsidian_export import export_to_obsidian
        out = export_to_obsidian(graph, args.output_dir)
        print(f"\n\033[1;32m✓ Exported {len(graph.nodes)} real, cross-linked Obsidian notes\033[0m to {out}\n")
        return 0

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RoboWeaver: Compile Robotics Knowledge into Executable Intelligence"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # robots
    subparsers.add_parser("robots", help="List supported robot profiles in registry")

    # nexus (Universal Robotics Knowledge & Package Nexus)
    p_nexus = subparsers.add_parser("nexus", help="Query Universal Robotics Package & Knowledge Nexus")
    p_nexus.add_argument("action", type=str, nargs="?", default="list", choices=["list", "query", "recommend"], help="Action: list, query, or recommend")
    p_nexus.add_argument("query", type=str, nargs="?", default="", help="Keyword, category, robot ID, or prompt string")

    # build / prompt (Prompt-to-System Multi-Robot Builder)
    p_build = subparsers.add_parser("build", aliases=["prompt"], help="Build complete multi-robot system from natural language prompt")
    p_build.add_argument("prompt", type=str, help="System description prompt (e.g., 'Build ShopMate-R retail assistant with Temi, Pepper, and Franka')")
    p_build.add_argument("--output", type=str, default="./ros2_ws/src", help="Output directory path for ROS 2 package")

    # graph (real knowledge graph: build / path / export-obsidian)
    p_graph = subparsers.add_parser("graph", help="Real knowledge graph: build, find a path, or export to Obsidian")
    graph_sub = p_graph.add_subparsers(dest="graph_action", required=True)

    p_graph_build = graph_sub.add_parser("build", help="Build the real knowledge graph from live registries")
    p_graph_build.add_argument("--output", type=str, default=None, help="Optional JSON file path to save the graph to")
    p_graph_build.add_argument("--json", action="store_true", help="Print the graph as JSON")

    p_graph_path = graph_sub.add_parser("path", help="Find a real multi-hop path between two node ids")
    p_graph_path.add_argument("from_id", type=str, help="Source node id, e.g. skill_tighten_bolt")
    p_graph_path.add_argument("to_id", type=str, help="Target node id, e.g. package_nav2_bringup")
    p_graph_path.add_argument("--max-hops", dest="max_hops", type=int, default=6)

    p_graph_obsidian = graph_sub.add_parser("export-obsidian", help="Export the real graph as Obsidian-compatible markdown notes")
    p_graph_obsidian.add_argument("output_dir", type=str, help="Output directory for the .md notes")

    # sim (Real-Time Kinematic & Force Simulation)
    p_sim = subparsers.add_parser("sim", help="Run real-time kinematic and grasping force simulation")
    p_sim.add_argument("--robot", type=str, default="inspire_hand", help="Target robot or dexterous hand profile")
    p_sim.add_argument("--object", type=str, default="medical_vial", help="Target grasping object (medical_vial, hex_bolt, tool_handle, fragile_egg)")
    p_sim.add_argument("--gestures", type=str, default="open,precision_grip,open", help="Comma-separated gesture sequence")
    p_sim.add_argument("--export-urdf", type=str, default=None, help="Optional output file path to generate URDF model")
    p_sim.add_argument("--export-html", type=str, default=None, help="Optional output file path to generate interactive HTML simulation dashboard")

    # compile
    p_compile = subparsers.add_parser("compile", help="Compile natural language instruction into a skill")
    p_compile.add_argument("instruction", type=str, help="Instruction (e.g. 'Pick up the red cube')")
    p_compile.add_argument("--robot", type=str, default="panda", help="Target robot profile (panda, ur5e, kuka_iiwa, kinova_gen3, abb_irb120)")
    p_compile.add_argument(
        "--opt-level", dest="opt_level", type=str, default="O1",
        choices=["O0", "O1", "O2", "O3", "Os", "Oenergy", "Osafe"],
        help="Optimization level passed to the Pass Manager (no registered pass reads this yet)",
    )
    p_compile.add_argument(
        "--explain-passes", dest="explain_passes", action="store_true",
        help="Print the Pass Manager's per-pass timing/diagnostic trace after compiling",
    )

    # diff
    p_diff = subparsers.add_parser("diff", help="Diff two RoboIR snapshots (cross-robot or across the compile pipeline's own passes)")
    p_diff.add_argument("instruction", type=str, help="Instruction to compile and diff")
    p_diff.add_argument("--robot", type=str, default="panda", help="Robot to compile against (baseline, or the 'from' side of --robot2)")
    p_diff.add_argument("--robot2", type=str, default=None, help="If given, diff --robot's IR against this second robot's IR instead of diffing the pipeline trace")

    # compare
    p_compare = subparsers.add_parser("compare", help="Compare an instruction's real compiled cost across multiple robots")
    p_compare.add_argument("instruction", type=str, help="Instruction to compile and compare")
    p_compare.add_argument("--robots", type=str, required=True, help="Comma-separated robot ids, e.g. panda,ur5e,kuka_iiwa")

    # benchmark
    p_bench = subparsers.add_parser("benchmark", help="RoboBench: real compile-pipeline measurement across robots x skill categories")
    p_bench.add_argument("--robots", type=str, default=None, help="Comma-separated robot ids (default: every distinct registered robot)")
    p_bench.add_argument("--output", type=str, default=None, help="Optional file path to also write the JSON report to")

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
    p_export.add_argument(
        "--backend", type=str, default="ros2", choices=["ros2", "urscript"],
        help="Codegen backend (plugins/backend.py's RobotBackend registry)",
    )

    # urdf (3D model generation)
    p_urdf = subparsers.add_parser("urdf", help="Generate a loadable URDF (+ optional STL meshes) for a robot")
    p_urdf.add_argument("--robot", type=str, default="franka_panda", help="Robot id from the registry")
    p_urdf.add_argument("--output", type=str, default=None, help="Output .urdf path")
    p_urdf.add_argument("--meshes", action="store_true", help="Also emit per-link binary STL meshes")

    # discover
    p_disc = subparsers.add_parser("discover", help="Scan for reachable robots and simulators")
    p_disc.add_argument("--subnet", type=str, default=None, help="CIDR range to sweep, e.g. 192.168.1.0/24")

    # connect
    p_conn = subparsers.add_parser("connect", help="Open a driver bridge to a robot endpoint")
    p_conn.add_argument("--robot", type=str, required=True, help="Robot id from the registry")
    p_conn.add_argument("--protocol", type=str, default="ros2", help="Bridge protocol: ros2 or sim")
    p_conn.add_argument("--uri", type=str, default="ros2://localhost", help="Target URI")

    # advise
    p_adv = subparsers.add_parser("advise", help="Ask an LLM which robot a discovered endpoint is")
    p_adv.add_argument("--host", type=str, required=True, help="Endpoint host/IP")
    p_adv.add_argument("--port", type=int, required=True, help="Endpoint port")
    p_adv.add_argument("--banner", type=str, default="", help="Observed TCP banner, if any")
    p_adv.add_argument("--hostname", type=str, default="", help="Reverse-DNS name, if any")
    p_adv.add_argument("--guess", type=str, default="", help="Port-convention guess")
    p_adv.add_argument("--latency", type=float, default=0.0, help="Measured latency in ms")
    p_adv.add_argument("--provider", type=str, default="ollama",
                       choices=["ollama", "openrouter", "anthropic", "openai"],
                       help="ollama is local and free; the others may bill per call")
    p_adv.add_argument("--model", type=str, default=None, help="Override the provider's default model")

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Launch web dashboard control center")
    p_dash.add_argument("--port", type=int, default=8080, help="HTTP port")
    p_dash.add_argument(
        "--host", type=str, default="127.0.0.1",
        help="Bind address (default 127.0.0.1, localhost-only). Pass 0.0.0.0 to "
             "expose on the LAN -- only do this on a trusted network.",
    )
    p_dash.add_argument(
        "--no-self-heal", action="store_true",
        help="Disable auto-restart on crash (self-healing is on by default)",
    )

    # Machine-readable output for scripting and CI, on every subcommand that
    # produces a result rather than a stream.
    for sub in (p_compile, p_diff, p_compare, p_bench, p_urdf, p_disc, p_conn, p_adv):
        sub.add_argument("--json", action="store_true", help="Emit JSON instead of formatted text")

    args = parser.parse_args()

    if args.command == "robots":
        return cmd_robots(args)
    elif args.command == "nexus":
        return cmd_nexus(args)
    elif args.command in ("build", "prompt"):
        return cmd_build_system(args)
    elif args.command == "graph":
        return cmd_graph(args)
    elif args.command == "sim":
        return cmd_sim(args)
    elif args.command == "compile":
        return cmd_compile(args)
    elif args.command == "diff":
        return cmd_diff(args)
    elif args.command == "compare":
        return cmd_compare(args)
    elif args.command == "benchmark":
        return cmd_benchmark(args)
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
    elif args.command == "urdf":
        return cmd_urdf(args)
    elif args.command == "discover":
        return cmd_discover(args)
    elif args.command == "connect":
        return cmd_connect(args)
    elif args.command == "advise":
        return cmd_advise(args)
    elif args.command == "dashboard":
        return cmd_dashboard(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
