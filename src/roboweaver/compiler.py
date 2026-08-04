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
from typing import Any

from dataclasses import dataclass

from roboweaver.hardware import RobotSpec, get_robot_spec, get_franka_panda_spec
from roboweaver.skills import IndustrialSkillCategory, get_industrial_skill_template
from roboweaver.math3d import Mat3, Transform3D
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
from roboweaver.optimize import (
    SkillPassManager,
    SkillPipelineTrace,
    CompiledSkillVerificationPass,
    WaypointDecimationPass,
    RedundantSegmentElisionPass,
)
from roboweaver.optimize.motion_cache import compute_motion_primitives
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
    Action.PALLETIZE: IndustrialSkillCategory.PALLETIZING,
    Action.POLISH: IndustrialSkillCategory.POLISHING,
    Action.DISASSEMBLE: IndustrialSkillCategory.DISASSEMBLY,
    Action.NAVIGATE: IndustrialSkillCategory.MOBILE_NAV,
}


@dataclass
class CompilationResult:
    """Bundles a compiled skill with the RoboIR (Stage 05) it was compiled from and
    any Compiler Debugger diagnostics (ir/diagnostics.py) raised while checking it.

    `pipeline` is additive (default None) -- the PipelineTrace the Pass Manager
    (ir/pass_manager.py) produced running RoboIRVerificationPass/CapabilityPass/
    SafetyPass over `ir`. `skill_pipeline` is the same idea for the optimization
    pipeline (optimize/pass_manager.py) that runs over `skill` *before* `ir` is even
    built -- see compile_with_diagnostics(). Every existing caller reads
    `.skill`/`.ir`/`.diagnostics` by name, so these additive fields can't break
    anything; `.diagnostics` is still the same flat list it always was
    (skill_pipeline.diagnostics() + ir_pipeline.diagnostics()), not a breaking change
    to that shape. `skill` is the (possibly optimized) CompiledSkill the optimization
    pipeline produced, not necessarily the same object compile() returned."""
    skill: CompiledSkill
    ir: RoboIR
    diagnostics: list[CompilerDiagnostic]
    pipeline: PipelineTrace | None = None
    skill_pipeline: SkillPipelineTrace | None = None


class SkillCompiler:
    """Universal Skill Compiler Pipeline targeting arbitrary N-DOF robot embodiments."""

    def __init__(self, target_robot: str | RobotSpec | None = None):
        if target_robot is None:
            self.robot_spec = get_franka_panda_spec()
        elif isinstance(target_robot, str):
            self.robot_spec = get_robot_spec(target_robot)
        else:
            self.robot_spec = target_robot

    def classify_category(self, instruction: str) -> IndustrialSkillCategory:
        """The real skill category `compile()` itself will route this instruction
        to -- Stage 1's intent parse plus `ACTION_CATEGORY_MAP`, with no robot
        embodiment involved (intent parsing never reads `self.robot_spec`). A
        public entry point to that classification alone, so callers that need to
        know *what kind of skill this is* (e.g. a knowledge-graph candidate-robot
        lookup, before any robot is even chosen) don't have to duplicate the
        keyword-scoring logic in `_parse_intent` -- or fully compile just to get
        an Action out of it."""
        intent = self._parse_intent(instruction)
        return ACTION_CATEGORY_MAP.get(intent.action, IndustrialSkillCategory.PICK_AND_PLACE)

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

    # Default RoboIR pipeline order: verify the IR's own structural shape before
    # checking it against a robot's declared capabilities, then run the (data-heavier)
    # safety checks last. See ir/pass_manager.py / ir/passes.py for what each does.
    _DEFAULT_PASSES = (RoboIRVerificationPass, CapabilityPass, SafetyPass)

    # Default CompiledSkill (optimization) pipeline: verify structure, optimize,
    # verify structure again -- the same before/after pattern RoboIRVerificationPass
    # established, proving the optimizers didn't break anything they touched. See
    # optimize/passes.py.
    _DEFAULT_SKILL_PASSES = (
        CompiledSkillVerificationPass,
        WaypointDecimationPass,
        RedundantSegmentElisionPass,
        CompiledSkillVerificationPass,
    )

    def compile_with_diagnostics(
        self,
        instruction: str,
        verbose: bool = True,
        optimization_level: OptimizationLevel = OptimizationLevel.O1,
    ) -> CompilationResult:
        """Stage 05 (RoboIR Generation) + both Pass Managers, on top of Stage 04's
        SkillIntent and Stage 06's compiled skill (compile()).

        Pipeline order matters here: the CompiledSkill optimization pipeline
        (optimize/pass_manager.py) runs *before* build_ir()/the RoboIR pipeline, so
        that SafetyPass verifies the final, possibly-optimized trajectories -- not
        the pre-optimization ones. RoboIR is built from the optimized skill's intent
        (unaffected by optimization today, but this keeps the ordering correct as
        RoboIR eventually absorbs more of CompiledSkill -- docs/COMPILER_ROADMAP.md
        Phase 2's deferred list).

        Raises SkillCompilationError if a required capability (e.g. sensing.force_torque)
        isn't declared on the target robot -- a compiler that silently produced a skill
        the robot can't execute would be worse than refusing to compile it. Non-blocking
        warnings (e.g. missing perception) are returned on the CompilationResult instead.

        `optimization_level` at O0 disables WaypointDecimationPass/
        RedundantSegmentElisionPass (matching GCC/LLVM convention) -- the first real
        payoff of the plumbing Phase 2 added.
        """
        skill = self.compile(instruction, verbose=verbose)

        skill_pass_manager = SkillPassManager([cls() for cls in self._DEFAULT_SKILL_PASSES])
        skill_trace = skill_pass_manager.run(skill, self.robot_spec, optimization_level)
        optimized_skill = skill_trace.final_skill

        initial_ir = build_ir(
            optimized_skill.intent, self.robot_spec, raw_instruction=instruction, skill=optimized_skill,
        )

        pass_manager = PassManager([cls() for cls in self._DEFAULT_PASSES])
        trace = pass_manager.run(initial_ir, optimized_skill, self.robot_spec, optimization_level)

        # CompiledSkillVerificationPass runs both before and after optimization
        # (verify-before/after, see _DEFAULT_SKILL_PASSES) -- a real, unmodified gap
        # like RW502 fires identically both times. Deduped here for a clean
        # user-facing diagnostics list; skill_trace itself (CompilationResult.
        # skill_pipeline) still records both raw runs for inspection.
        seen: set[tuple[str, str, str]] = set()
        diagnostics: list[CompilerDiagnostic] = []
        for d in skill_trace.diagnostics() + trace.diagnostics():
            key = (d.code, d.message, d.reason)
            
            if key not in seen:
                seen.add(key)
                diagnostics.append(d)

        errors = [d for d in diagnostics if d.severity == "error"]
        if errors:
            if verbose:
                for d in errors:
                    print(f"\n\033[1;31m✗ {d.code}\033[0m {d.message}\n  {d.reason}")
            raise SkillCompilationError(errors)

        if verbose:
            for d in diagnostics:
                print(f"\n\033[1;33m⚠ {d.code}\033[0m {d.message}")

        return CompilationResult(
            skill=optimized_skill, ir=trace.final_ir, diagnostics=diagnostics,
            pipeline=trace, skill_pipeline=skill_trace,
        )

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
        Action.PALLETIZE:      [("palletize", 3.0), ("palletizing", 3.0), ("pallet", 2.5), ("stack", 2.0)],
        Action.POLISH:         [("polish", 3.0), ("polishing", 3.0), ("buff", 2.5), ("burnish", 2.0)],
        Action.DISASSEMBLE:    [("disassemble", 3.0), ("disassembly", 3.0), ("remove fastener", 3.0), ("extract fastener", 3.0), ("unscrew", 2.0)],
        Action.NAVIGATE:       [("navigate", 3.0), ("navigation", 3.0), ("drive to", 2.5), ("go to", 2.0), ("move to location", 2.5)],
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
        Action.PALLETIZE:      {"grip_force_n": 30.0},
        Action.POLISH:         {"force_nm": 10.0},
        Action.DISASSEMBLE:    {},
        Action.NAVIGATE:       {"goal_tolerance_m": 0.05},
    }

    _ACTION_DEFAULT_OBJ: dict[Action, str] = {
        Action.TIGHTEN: "m8_bolt", Action.OPEN_DOOR: "door_handle",
        Action.TOOL_EXCHANGE: "gripper_v2", Action.CLEAN: "work_surface",
        Action.INSPECT: "machine_panel", Action.WELD: "steel_bracket",
        Action.PEG_INSERT: "alignment_peg", Action.POUR: "liquid_container",
        Action.PACKAGE: "shipment_item", Action.CNC_LOAD: "workpiece",
        Action.SURGERY_ASSIST: "surgical_instrument", Action.SORT: "item",
        Action.PLACE: "object", Action.PICK: "red_cube",
        Action.PALLETIZE: "shipment_box", Action.POLISH: "metal_panel",
        Action.DISASSEMBLE: "assembly_unit", Action.NAVIGATE: "destination_waypoint",
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
        """Stage 3: IK + trajectory generation -- one real, IK-solved trajectory
        segment per MOVE_TO task in the compiled skill's real template (gap-fix
        batch, item 1a), not a fixed 3-pose pick/place plan. This closes RW502
        (optimize/passes.py) for every skill category: every MOVE_TO task now has a
        real motion_plan entry, keyed by that task's own real description --
        runtime/engine.py already looks trajectories/ik_results up generically by
        task.description, so no downstream change was needed (confirmed by grep: no
        code anywhere hardcoded the old "grasp"/"approach"/"lift" keys or the
        "Approach above X" strings). The IK/trajectory math lives in
        optimize/motion_cache.py; this method only labels the results with real task
        descriptions and prints verbosely."""
        move_to_tasks = [t for t in task_graph.tasks if t.type is TaskType.MOVE_TO]

        if verbose:
            print(f"\n\033[1;36m━━━ STAGE 3/4: Motion Planning ({self.robot_spec.name}) \033[0m")

        if not move_to_tasks:
            if verbose:
                print("  (no MOVE_TO tasks in this skill's template -- nothing to plan)")
            return MotionPlan(trajectories={}, ik_results={}, robot_model=self.robot_spec.id)

        primitives, cache_hit = compute_motion_primitives(self.robot_spec, len(move_to_tasks))
        note = " \033[2m(cached)\033[0m" if cache_hit else ""

        ik_results: dict[str, IKSolution] = {}
        trajectories: dict[str, MotionSegment] = {}
        for i, task in enumerate(move_to_tasks):
            ik = primitives.ik_solutions[i]
            ik_results[task.description] = ik
            trajectories[task.description] = MotionSegment(
                primitives.start_configs[i], ik.joint_angles,
                primitives.trajectory_waypoints[i], primitives.trajectory_durations[i],
            )
            if verbose:
                print(
                    f"  ✓ IK target {i + 1}/{len(move_to_tasks)} ({task.description}){note}    "
                    f"(residual: {ik.residual:.4f}m, {ik.iterations} iters)"
                )

        if verbose:
            print()
            for task in move_to_tasks:
                seg = trajectories[task.description]
                print(f"  → Trajectory: {task.description}    ({seg.duration:.2f}s, {len(seg.waypoints)} waypoints)")

        return MotionPlan(trajectories=trajectories, ik_results=ik_results, robot_model=self.robot_spec.id)

    def _compile_behavior_tree(self, intent: SkillIntent, task_graph: TaskGraph) -> BTNode:
        cat = ACTION_CATEGORY_MAP.get(intent.action, IndustrialSkillCategory.PICK_AND_PLACE)
        tmpl = get_industrial_skill_template(cat, intent.object_name)
        return tmpl.behavior_tree_root

    def _print_bt(self, node: BTNode, prefix: str = "", is_last: bool = True) -> None:
        connector = "└─ " if is_last else "├─ "
        print(f"  {prefix}{connector}{node.type}: {node.name}")
        child_prefix = prefix + ("   " if is_last else "│  ")
        for i, child in enumerate(node.children):
            self._print_bt(child, child_prefix, i == len(node.children) - 1)
