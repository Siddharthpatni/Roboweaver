"""
Universal Skill Compiler Pipeline — converts natural language into robot skill packages.

Multi-stage pipeline:
1. Intent Parsing (Action, Target Object, Parameters)
2. Task Graph Decomposition (Industrial Skill Taxonomy)
3. Generalized N-DOF Kinematics & Motion Planning (Robotic Tooling)
4. Groot2 BehaviorTree XML Generation
"""

from __future__ import annotations

import re
from typing import Any, Sequence

from dataclasses import dataclass

from roboweaver.hardware import RobotSpec, NDOFIKSolver, get_robot_spec, get_franka_panda_spec
from roboweaver.skills import IndustrialSkillCategory, get_industrial_skill_template
from roboweaver.math3d import Mat3, Transform3D, Vec3
from roboweaver.types import (
    Action,
    BTNode,
    CompiledSkill,
    IKSolution,
    MotionPlan,
    MotionSegment,
    SkillIntent,
    TaskDecomposition,
    TaskGraph,
    TaskType,
)
from roboweaver.ir import (
    RoboIR,
    CompilerDiagnostic,
    SkillCompilationError,
    build_ir,
    OptimizationLevel,
    PassManager,
    PipelineTrace,
    RoboIRVerificationPass,
    CapabilityPass,
    SafetyPass,
)
from roboweaver.nlu import OllamaIntentParser, OllamaParseResult

# Single source of truth for Action -> IndustrialSkillCategory (was duplicated in
# _decompose_tasks and _compile_behavior_tree; the same drift risk that let
# Action.PLACE go unproducible for a whole compile stage -- see docs/REDESIGN.md).
ACTION_CATEGORY_MAP: dict[Action, IndustrialSkillCategory] = {
    Action.PICK: IndustrialSkillCategory.PICK_AND_PLACE,
    Action.PLACE: IndustrialSkillCategory.PICK_AND_PLACE,
    Action.TIGHTEN: IndustrialSkillCategory.TIGHTEN_BOLT,
    Action.OPEN_DOOR: IndustrialSkillCategory.OPEN_DOOR,
    Action.TOOL_EXCHANGE: IndustrialSkillCategory.TOOL_EXCHANGE,
    Action.INSPECT: IndustrialSkillCategory.INSPECT_SURFACE,
    Action.WELD: IndustrialSkillCategory.WELD_SEAM,
    Action.PEG_INSERT: IndustrialSkillCategory.PEGGING,
    Action.POUR: IndustrialSkillCategory.POURING_LIQUID,
    Action.PACKAGE: IndustrialSkillCategory.PACKAGING,
    Action.CNC_LOAD: IndustrialSkillCategory.CNC_LOADING,
    Action.SURGERY_ASSIST: IndustrialSkillCategory.SURGERY_ASSIST,
    Action.SORT: IndustrialSkillCategory.SORTING,
    Action.CLEAN: IndustrialSkillCategory.CLEANING,
}


@dataclass
class CompilationResult:
    """Bundles a compiled skill with the RoboIR (Stage 05) it was compiled from and
    any Compiler Debugger diagnostics (ir/diagnostics.py) raised while checking it.

    `pipeline` is additive (default None) -- the PipelineTrace the Pass Manager
    (ir/pass_manager.py) produced running RoboIRVerificationPass/CapabilityPass/
    SafetyPass over `ir`. Every existing caller reads `.skill`/`.ir`/`.diagnostics` by
    name, so this field can't break anything; `.diagnostics` is still the same flat
    list it always was (trace.diagnostics()), not a breaking change to that shape."""
    skill: CompiledSkill
    ir: RoboIR
    diagnostics: list[CompilerDiagnostic]
    pipeline: PipelineTrace | None = None


class SkillCompiler:
    """Universal Skill Compiler Pipeline targeting arbitrary N-DOF robot embodiments."""

    def __init__(self, target_robot: str | RobotSpec | None = None):
        if target_robot is None:
            self.robot_spec = get_franka_panda_spec()
        elif isinstance(target_robot, str):
            self.robot_spec = get_robot_spec(target_robot)
        else:
            self.robot_spec = target_robot

    def compile(self, instruction: str, verbose: bool = True) -> CompiledSkill:
        """Compile natural language instruction into a CompiledSkill."""
        if verbose:
            print(f"\n\033[1;34mRoboWeaver Universal Compiler\033[0m — Instruction: \033[1m\"{instruction}\"\033[0m")
            print(f"  Target Robot: \033[36m{self.robot_spec.name}\033[0m ({self.robot_spec.dof}-DOF, Payload: {self.robot_spec.payload_capacity_kg}kg)")

        intent = self._parse_intent(instruction)
        if verbose:
            print(f"\n\033[1;36m━━━ STAGE 1/4: Parse Intent (deterministic) \033[0m")
            print(f"  → Action:     {intent.action.value}")
            print(f"  → Object:     {intent.object_name}")
            print(f"  → Confidence: {intent.confidence:.2f}")
            for k, v in intent.parameters.items():
                print(f"  → Parameter:  {k} = {v}")
            for w in intent.parse_warnings:
                print(f"  \033[1;33m⚠ {w}\033[0m")

        return self._compile_from_intent(intent, task_graph_verbose=verbose)

    def compile_with_llm_parser(
        self,
        instruction: str,
        model: str = "llama3.1:8b",
        host: str = "http://localhost:11434",
        verbose: bool = True,
    ) -> tuple[CompiledSkill, OllamaParseResult]:
        """Stage 1 via a local, offline Ollama model instead of the deterministic
        keyword parser -- opt-in only, called explicitly, never the default path.

        Falls back to the deterministic parser -- honestly, not silently -- if
        Ollama is unreachable or its output can't be trusted (see
        nlu/ollama_parser.py's module docstring for the full reasoning). The
        returned OllamaParseResult always reflects what actually happened: check
        `.error` to see whether the LLM path was used or the fallback fired.
        """
        parser = OllamaIntentParser(model=model, host=host)
        result = parser.parse(instruction)

        if result.intent is not None:
            intent = result.intent
            if verbose:
                print(f"\n\033[1;36m━━━ STAGE 1/4: Parse Intent (Ollama: {model}) \033[0m")
                print(f"  → Action:     {intent.action.value}")
                print(f"  → Object:     {intent.object_name}")
        else:
            if verbose:
                print(f"\n\033[1;33m⚠ Ollama parse failed ({result.error}) -- falling back to the deterministic parser.\033[0m")
            intent = self._parse_intent(instruction)

        skill = self._compile_from_intent(intent, task_graph_verbose=verbose)
        return skill, result

    def _compile_from_intent(self, intent: SkillIntent, task_graph_verbose: bool = True) -> CompiledSkill:
        verbose = task_graph_verbose
        # Stage 2: Task Decomposition
        task_graph = self._decompose_tasks(intent)
        if verbose:
            print(f"\n\033[1;36m━━━ STAGE 2/4: Task Decomposition \033[0m")
            for i, task in enumerate(task_graph.tasks):
                print(f"  → [{i+1}] {task.type.value:<14} → {task.description}")

        # Stage 3: Motion Planning with N-DOF Kinematics Engine
        motion_plan = self._plan_motion(intent, task_graph, verbose=verbose)

        # Stage 4: Behavior Tree Compiler
        behavior_tree = self._compile_behavior_tree(intent, task_graph)
        if verbose:
            print(f"\n\033[1;36m━━━ STAGE 4/4: Behavior Tree \033[0m")
            self._print_bt(behavior_tree)
            print()

        return CompiledSkill(
            intent=intent,
            task_graph=task_graph,
            motion_plan=motion_plan,
            behavior_tree=behavior_tree,
        )

    # Default pipeline order: verify the IR's own structural shape before checking it
    # against a robot's declared capabilities, then run the (data-heavier) safety
    # checks last. See ir/pass_manager.py / ir/passes.py for what each pass does.
    _DEFAULT_PASSES = (RoboIRVerificationPass, CapabilityPass, SafetyPass)

    def compile_with_diagnostics(
        self,
        instruction: str,
        verbose: bool = True,
        optimization_level: OptimizationLevel = OptimizationLevel.O1,
    ) -> CompilationResult:
        """Stage 05 (RoboIR Generation) + Pass Manager (ir/pass_manager.py), on top of
        Stage 04's SkillIntent and Stage 06's compiled skill (compile()).

        Raises SkillCompilationError if a required capability (e.g. sensing.force_torque)
        isn't declared on the target robot -- a compiler that silently produced a skill
        the robot can't execute would be worse than refusing to compile it. Non-blocking
        warnings (e.g. missing perception) are returned on the CompilationResult instead.

        `optimization_level` is plumbed through to every pass's PassContext but, as of
        this phase, gates zero registered passes -- no real optimization pass exists
        yet (docs/COMPILER_ROADMAP.md Phase 4). Passing it is forward-compatible, not
        yet behavior-changing.
        """
        skill = self.compile(instruction, verbose=verbose)
        initial_ir = build_ir(skill.intent, self.robot_spec, raw_instruction=instruction)

        pass_manager = PassManager([cls() for cls in self._DEFAULT_PASSES])
        trace = pass_manager.run(initial_ir, skill, self.robot_spec, optimization_level)
        diagnostics = trace.diagnostics()

        errors = [d for d in diagnostics if d.severity == "error"]
        if errors:
            if verbose:
                for d in errors:
                    print(f"\n\033[1;31m✗ {d.code}\033[0m {d.message}\n  {d.reason}")
            raise SkillCompilationError(errors)

        if verbose:
            for d in diagnostics:
                print(f"\n\033[1;33m⚠ {d.code}\033[0m {d.message}")

        return CompilationResult(skill=skill, ir=trace.final_ir, diagnostics=diagnostics, pipeline=trace)

    # ── Synonym / keyword scoring table ──────────────────────────────────
    # Each Action maps to a list of (keyword, score) pairs.  The parser
    # scans every keyword against the lowered instruction, sums per-Action
    # scores, and picks the winner (ties break to the first match).  This
    # replaces the old fragile if/elif chain and makes it trivial to add
    # new verbs or objects without re-ordering branches.
    _ACTION_KEYWORDS: dict[Action, list[tuple[str, float]]] = {
        Action.TIGHTEN:        [("tighten", 3.0), ("bolt", 2.5), ("screw", 2.5), ("fasten", 2.5), ("torque", 2.0), ("nut", 1.5), ("wrench", 1.5)],
        Action.OPEN_DOOR:      [("door", 3.0), ("open door", 4.0), ("handle", 1.5)],
        Action.TOOL_EXCHANGE:  [("tool exchange", 4.0), ("swap tool", 4.0), ("change tool", 4.0), ("tool change", 4.0), ("exchange", 2.0)],
        Action.CLEAN:          [("clean", 3.0), ("wipe", 3.0), ("sweep", 2.5), ("scrub", 2.5), ("mop", 2.0), ("sanitize", 2.0)],
        Action.INSPECT:        [("inspect", 3.0), ("scan", 2.5), ("examine", 2.5), ("check surface", 3.0), ("quality check", 3.0), ("surface", 1.0)],
        Action.WELD:           [("weld", 3.0), ("seam", 2.5), ("solder", 2.0), ("braze", 2.0), ("arc weld", 4.0)],
        Action.PEG_INSERT:     [("peg", 3.0), ("insert", 2.5), ("insertion", 2.5), ("assemble", 2.0), ("drill", 2.0), ("press fit", 3.0), ("plug", 2.0)],
        Action.POUR:           [("pour", 3.0), ("decant", 2.5), ("dispense", 2.0), ("fill", 1.5)],
        Action.PACKAGE:        [("pack", 3.0), ("package", 3.0), ("carton", 2.5), ("box", 2.0), ("wrap", 2.0), ("seal", 1.5)],
        Action.CNC_LOAD:       [("cnc", 3.0), ("machine tend", 3.5), ("chuck", 2.5), ("lathe", 2.5), ("mill", 2.0)],
        Action.SURGERY_ASSIST: [("surgery", 3.0), ("surgical", 3.0), ("scalpel", 2.5), ("retract", 2.0), ("suture", 2.5)],
        Action.SORT:           [("sort", 3.0), ("classify", 3.0), ("separate", 2.5), ("categorize", 2.5), ("bin", 1.0)],
        Action.PLACE:          [("place", 2.5), ("put", 2.0), ("set down", 2.5), ("deposit", 2.0)],
        Action.PICK:           [("pick", 2.0), ("grab", 2.5), ("grasp", 2.5), ("fetch", 2.0), ("carry", 2.0), ("lift", 1.5), ("take", 1.5), ("get", 1.0)],
    }

    # Default parameters per action so we never produce an empty param dict
    _ACTION_DEFAULT_PARAMS: dict[Action, dict[str, float]] = {
        Action.TIGHTEN:        {"target_torque_nm": 25.0, "socket_size_mm": 13.0},
        Action.OPEN_DOOR:      {"rotation_deg": 30.0, "pull_distance_m": 0.4},
        Action.TOOL_EXCHANGE:  {"dock_slot": 1},
        Action.CLEAN:          {"force_n": 5.0},
        Action.INSPECT:        {"scan_area_m2": 0.25, "resolution_mm": 2.0},
        Action.WELD:           {"current_a": 120.0, "speed_mm_s": 5.0},
        Action.PEG_INSERT:     {"force_limit_n": 8.0},
        Action.POUR:           {"tilt_deg": 100.0},
        Action.PACKAGE:        {},
        Action.CNC_LOAD:       {},
        Action.SURGERY_ASSIST: {},
        Action.SORT:           {},
        Action.PLACE:          {"approach_height": 0.12, "lift_height": 0.18, "grip_force": 10.0, "settle_time": 0.5},
        Action.PICK:           {"approach_height": 0.12, "lift_height": 0.18, "grip_force": 10.0, "settle_time": 0.5},
    }

    _ACTION_DEFAULT_OBJ: dict[Action, str] = {
        Action.TIGHTEN: "m8_bolt", Action.OPEN_DOOR: "door_handle",
        Action.TOOL_EXCHANGE: "gripper_v2", Action.CLEAN: "work_surface",
        Action.INSPECT: "machine_panel", Action.WELD: "steel_bracket",
        Action.PEG_INSERT: "alignment_peg", Action.POUR: "liquid_container",
        Action.PACKAGE: "shipment_item", Action.CNC_LOAD: "workpiece",
        Action.SURGERY_ASSIST: "surgical_instrument", Action.SORT: "item",
        Action.PLACE: "object", Action.PICK: "red_cube",
    }

    def _parse_intent(self, instruction: str) -> SkillIntent:
        inst_lower = instruction.lower().strip()

        # ── 1. Compound pick-and-place detection (broadened regex) ─────
        # Handles:  "pick X and place it in/into/on/onto Y"
        #           "pick X from A and place it in Y"
        #           "grab X off the shelf and put it on Y"
        compound = re.search(
            r"(?:pick(?:\s+up)?|grab|grasp|fetch|take|get|carry)"
            r"\s+(?:the\s+)?(.+?)"
            r"\s+(?:and\s+)?(?:then\s+)?(?:place|put|set|deposit|drop)"
            r"\s+(?:it|them|that)?\s*"
            r"(?:into|in|on|onto|at|inside)\s+(?:the\s+)?(.+?)[\.\!\s]*$",
            inst_lower,
        )
        if compound:
            obj_name = compound.group(1).strip()
            # Strip trailing "from ..." in the source object
            obj_name = re.sub(r"\s+(?:from|off)\s+.*$", "", obj_name)
            obj_name = obj_name.replace(" ", "_")
            dest = compound.group(2).strip().replace(" ", "_")
            params = dict(self._ACTION_DEFAULT_PARAMS.get(Action.PLACE, {}))
            params["destination_object"] = dest
            # A matched compound structure ("pick X ... place it in Y") is a far
            # stronger signal than any single keyword, hence the high confidence.
            return SkillIntent(
                action=Action.PLACE, object_name=obj_name, parameters=params, confidence=0.95
            )

        # ── 2. Scored keyword matching ────────────────────────────────
        scores: dict[Action, float] = {}
        for action, keywords in self._ACTION_KEYWORDS.items():
            total = 0.0
            for kw, weight in keywords:
                if kw in inst_lower:
                    total += weight
            if total > 0:
                scores[action] = total

        warnings: list[str] = []
        if scores:
            action = max(scores, key=scores.get)  # type: ignore[arg-type]
            best = scores[action]
            rivals = sorted((v for a, v in scores.items() if a is not action), reverse=True)
            second = rivals[0] if rivals else 0.0

            # Confidence blends how strongly the winner matched (a single 3.0-weight
            # verb is a full-strength hit) with how far clear of the runner-up it
            # finished. Both matter: "weld" alone is confident, whereas an
            # instruction hitting WELD and TIGHTEN nearly equally is not.
            strength = min(1.0, best / 3.0)
            separation = 1.0 if second == 0.0 else (best - second) / best
            confidence = round(0.5 * strength + 0.5 * separation, 2)

            if confidence < 0.5:
                runner_up = max(
                    (a for a in scores if a is not action), key=lambda a: scores[a], default=None
                )
                warnings.append(
                    f"Ambiguous instruction: parsed as {action.value} "
                    f"(confidence {confidence:.2f})"
                    + (f", close runner-up was {runner_up.value}" if runner_up else "")
                    + ". Rephrase with an explicit verb if this is wrong."
                )
        else:
            # Nothing matched at all. Still return a usable intent so the caller
            # can proceed, but never let this look like a confident parse.
            action = Action.PICK
            confidence = 0.0
            warnings.append(
                "No known action verb recognised in the instruction; defaulting to "
                "PICK. This is a fallback, not a parse -- verify the intent before "
                "deploying the generated skill."
            )

        # ── 3. Object name extraction ─────────────────────────────────
        obj_name = self._ACTION_DEFAULT_OBJ.get(action, "object")

        # Try to extract a specific object name from the instruction
        # Pattern: "<verb> (the) <object name>" — skip articles, capture noun phrase
        # Verb alternation mirrors the synonyms in _ACTION_KEYWORDS -- when a verb
        # scores an Action but is missing here, the object silently falls back to
        # that action's placeholder ("assemble the bracket" -> alignment_peg).
        obj_match = re.search(
            r"(?:pick(?:\s+up)?|grab|grasp|fetch|take|get|carry|lift|tighten|fasten|screw|weld"
            r"|solder|braze|insert|assemble|drill|plug|pour|decant|dispense|fill|inspect|scan"
            r"|examine|clean|wipe|scrub|sweep|mop|sanitize|sort|classify|separate|categorize"
            r"|pack|package|wrap|seal|place|put|deposit|load)"
            r"\s+(?:the\s+|a\s+|an\s+)?([a-z][a-z0-9\s]{1,40}?)(?:\s+(?:and|from|off|on|onto|into|in|to|with|at)\b|$|[\.\!\,])",
            inst_lower,
        )
        if obj_match:
            extracted = obj_match.group(1).strip()
            if extracted and len(extracted) > 1 and extracted != "it":
                obj_name = extracted.replace(" ", "_")

        params = dict(self._ACTION_DEFAULT_PARAMS.get(action, {}))

        return SkillIntent(
            action=action,
            object_name=obj_name,
            parameters=params,
            confidence=confidence,
            parse_warnings=warnings,
        )

    def _decompose_tasks(self, intent: SkillIntent) -> TaskGraph:
        cat = ACTION_CATEGORY_MAP.get(intent.action, IndustrialSkillCategory.PICK_AND_PLACE)
        tmpl = get_industrial_skill_template(cat, intent.object_name)
        return TaskGraph(tasks=tmpl.tasks)

    def _plan_motion(self, intent: SkillIntent, task_graph: TaskGraph, verbose: bool = True) -> MotionPlan:
        if verbose:
            print(f"\n\033[1;36m━━━ STAGE 3/4: Motion Planning ({self.robot_spec.name}) \033[0m")

        solver = NDOFIKSolver(self.robot_spec)
        ik_results = {}
        trajectories = {}

        # Default pose targets
        grasp_target = Vec3(0.35, 0.0, 0.13)
        approach_target = Vec3(0.35, 0.0, 0.25)
        lift_target = Vec3(0.35, 0.0, 0.31)

        ok1, q_grasp, res1, iters1 = solver.solve(grasp_target)
        if verbose:
            print(f"  ✓ IK Grasp pose ({intent.object_name})    (residual: {res1:.4f}m, {iters1} iters)")

        ok2, q_approach, res2, iters2 = solver.solve(approach_target)
        if verbose:
            print(f"  ✓ IK Approach pose                   (residual: {res2:.4f}m, {iters2} iters)")

        ok3, q_lift, res3, iters3 = solver.solve(lift_target)
        if verbose:
            print(f"  ✓ IK Lift/Retract pose                (residual: {res3:.4f}m, {iters3} iters)")

        ik_results["grasp"] = IKSolution(joint_angles=q_grasp, residual=res1, iterations=iters1, success=ok1)
        ik_results["approach"] = IKSolution(joint_angles=q_approach, residual=res2, iterations=iters2, success=ok2)
        ik_results["lift"] = IKSolution(joint_angles=q_lift, residual=res3, iterations=iters3, success=ok3)

        # Generate smooth trajectories. The zero configuration isn't a valid seed for
        # every robot -- Franka's panda_joint4 range (-3.0718, -0.0698) doesn't include
        # 0 -- so "home" clamps into each joint's declared range rather than assuming 0
        # is always reachable (RW302, ir/safety.py, caught this the first time it ran).
        # Bounded to `dof`, not len(joints): some registry entries (turtlebot4) list
        # more joints than their declared dof (a fixed, non-actuated camera joint is
        # included in the joints list) -- the same bound get_joint_limits()/
        # get_max_velocities() callers already apply everywhere else in this codebase.
        home_q = [
            max(j.lower_limit, min(j.upper_limit, 0.0)) for j in self.robot_spec.joints[: self.robot_spec.dof]
        ]

        dur_approach = self._min_safe_duration(home_q, q_approach, default=1.0)
        dur_grasp = self._min_safe_duration(q_approach, q_grasp, default=0.4)
        dur_lift = self._min_safe_duration(q_grasp, q_lift, default=0.5)

        traj_approach = self._generate_min_jerk_traj(home_q, q_approach, steps=100)
        traj_grasp = self._generate_min_jerk_traj(q_approach, q_grasp, steps=40)
        traj_lift = self._generate_min_jerk_traj(q_grasp, q_lift, steps=50)

        trajectories[f"Approach above {intent.object_name}"] = MotionSegment(home_q, q_approach, traj_approach, dur_approach)
        trajectories[f"Grasp pose at {intent.object_name}"] = MotionSegment(q_approach, q_grasp, traj_grasp, dur_grasp)
        trajectories["Lift target to transfer height"] = MotionSegment(q_grasp, q_lift, traj_lift, dur_lift)

        if verbose:
            print(f"\n  → Trajectory: home → approach    ({dur_approach:.2f}s, {len(traj_approach)} waypoints)")
            print(f"  → Trajectory: approach → grasp   ({dur_grasp:.2f}s, {len(traj_grasp)} waypoints)")
            print(f"  → Trajectory: grasp → lift       ({dur_lift:.2f}s, {len(traj_lift)} waypoints)")

        return MotionPlan(trajectories=trajectories, ik_results=ik_results, robot_model=self.robot_spec.id)

    def _compile_behavior_tree(self, intent: SkillIntent, task_graph: TaskGraph) -> BTNode:
        cat = ACTION_CATEGORY_MAP.get(intent.action, IndustrialSkillCategory.PICK_AND_PLACE)
        tmpl = get_industrial_skill_template(cat, intent.object_name)
        return tmpl.behavior_tree_root

    def _min_safe_duration(self, start_q: Sequence[float], end_q: Sequence[float], default: float) -> float:
        """Shortest duration for a min-jerk blend between start_q and end_q that keeps
        every joint's peak velocity within its declared max_velocity (ir/safety.py's
        RW304 checks the result of this, finite-difference, against the same limits).

        The min-jerk profile s(t) = 10t^3 - 15t^4 + 6t^5 has its peak slope ds/dt = 1.875
        at t=0.5, so peak joint velocity = 1.875 * |delta_q_j| / duration. A 10% margin
        covers the gap between that closed-form peak and the discrete finite-difference
        estimate RW304 computes over a finite number of waypoints.
        """
        max_vels = self.robot_spec.get_max_velocities()
        required = default
        for j in range(min(len(start_q), len(end_q), len(max_vels))):
            if max_vels[j] <= 0:
                continue
            delta = abs(end_q[j] - start_q[j])
            needed = (1.875 * delta / max_vels[j]) * 1.1
            required = max(required, needed)
        return required

    def _generate_min_jerk_traj(self, start_q: list[float], end_q: list[float], steps: int = 50) -> list[list[float]]:
        waypoints = []
        n = len(start_q)
        for i in range(steps + 1):
            t = i / steps
            s = 10 * (t ** 3) - 15 * (t ** 4) + 6 * (t ** 5)
            wp = [start_q[j] + s * (end_q[j] - start_q[j]) for j in range(n)]
            waypoints.append(wp)
        return waypoints

    def _print_bt(self, node: BTNode, prefix: str = "", is_last: bool = True) -> None:
        connector = "└─ " if is_last else "├─ "
        print(f"  {prefix}{connector}{node.type}: {node.name}")
        child_prefix = prefix + ("   " if is_last else "│  ")
        for i, child in enumerate(node.children):
            self._print_bt(child, child_prefix, i == len(node.children) - 1)
