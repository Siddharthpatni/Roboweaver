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
import hashlib
import json
from typing import Any, TYPE_CHECKING

from dataclasses import dataclass

from roboweaver.hardware import RobotSpec, get_robot_spec, get_franka_panda_spec
from roboweaver.skills import IndustrialSkillCategory, get_industrial_skill_template
from roboweaver.math3d import Vec3
from roboweaver.types import (
    Action,
    BTNode,
    CompiledSkill,
    MotionPlan,
    PortableSkill,
    SkillIntent,
    TaskDecomposition,
    TaskGraph,
    TaskType,
    supplied_pose_satisfies_perception,
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
    check_required_capabilities,
)
from roboweaver.optimize import (
    SkillPassManager,
    SkillPipelineTrace,
    CompiledSkillVerificationPass,
    BoundedFormalVerificationPass,
    WaypointDecimationPass,
    RedundantSegmentElisionPass,
    CollisionPlanningPass,
)
from roboweaver.nlu import OllamaIntentParser, OllamaParseResult
from roboweaver.lowering import TargetLoweringError, get_motion_lowerer
from roboweaver.planning import CollisionPlanningError
from roboweaver.upstream import MLIRBridgeError, NativeMLIREvidence, run_native_mlir

if TYPE_CHECKING:
    from roboweaver.perception import ObservationProvider
    from roboweaver.planning import Scene

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
    portable: PortableSkill | None = None
    pipeline: PipelineTrace | None = None
    skill_pipeline: SkillPipelineTrace | None = None
    native_mlir: NativeMLIREvidence | None = None


@dataclass
class UniversalCompilationResult:
    """One parsed program independently lowered to multiple concrete targets."""

    portable: PortableSkill
    source_digest: str
    results: dict[str, CompilationResult]
    failures: dict[str, list[CompilerDiagnostic]]


def _portable_digest(portable: PortableSkill) -> str:
    def behavior(node: BTNode) -> dict[str, Any]:
        return {
            "type": node.type,
            "name": node.name,
            "children": [behavior(child) for child in node.children],
        }

    payload = {
        "raw_instruction": portable.raw_instruction,
        "intent": {
            "action": portable.intent.action.value,
            "object_name": portable.intent.object_name,
            "parameters": portable.intent.parameters,
            "confidence": portable.intent.confidence,
            "warnings": portable.intent.parse_warnings,
        },
        "tasks": [
            {"type": task.type.value, "description": task.description, "params": task.params}
            for task in portable.task_graph.tasks
        ],
        "behavior": behavior(portable.behavior_tree),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _verify_native_mlir(ir: RoboIR) -> NativeMLIREvidence:
    try:
        return run_native_mlir(ir)
    except MLIRBridgeError as exc:
        raise SkillCompilationError([CompilerDiagnostic(
            code="RW701",
            severity="error",
            message="Native MLIR verification failed.",
            reason=str(exc),
            required_capability="compiler.mlir-opt",
            fixes=[
                "Install a compatible mlir-opt executable or correct ROBOWEAVER_MLIR_OPT.",
                "Use ROBOWEAVER_MLIR_MODE=off only when native MLIR evidence is not required.",
            ],
        )]) from exc


class SkillCompiler:
    """Universal Skill Compiler Pipeline targeting arbitrary N-DOF robot embodiments."""

    def __init__(
        self,
        target_robot: str | RobotSpec | None = None,
        *,
        perception_provider: "ObservationProvider | None" = None,
        scene: "Scene | None" = None,
    ):
        if target_robot is None:
            self.robot_spec = get_franka_panda_spec()
        elif isinstance(target_robot, str):
            self.robot_spec = get_robot_spec(target_robot)
        else:
            violations = target_robot.validate()
            if violations:
                raise ValueError(
                    f"invalid RobotSpec {target_robot.id!r}: " + "; ".join(violations)
                )
            self.robot_spec = target_robot
        self.perception_provider = perception_provider
        self.scene = scene

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
        if self.perception_provider is not None:
            from roboweaver.perception import apply_observation

            intent = apply_observation(intent, self.perception_provider)
        return ACTION_CATEGORY_MAP.get(intent.action, IndustrialSkillCategory.PICK_AND_PLACE)

    @classmethod
    def compile_targets(
        cls,
        instruction: str,
        target_robots: list[str],
        *,
        verbose: bool = False,
        optimization_level: OptimizationLevel = OptimizationLevel.O1,
    ) -> UniversalCompilationResult:
        """Parse/decompose once and independently lower the same program per target."""
        if not target_robots:
            raise ValueError("compile_targets requires at least one concrete robot id")

        front_end = cls("universal")
        portable = front_end.compile_portable(instruction, verbose=verbose)
        results: dict[str, CompilationResult] = {}
        failures: dict[str, list[CompilerDiagnostic]] = {}
        for robot_id in dict.fromkeys(target_robots):
            compiler = cls(robot_id)
            try:
                results[robot_id] = compiler.lower_with_diagnostics(
                    portable,
                    verbose=verbose,
                    optimization_level=optimization_level,
                )
            except SkillCompilationError as exc:
                failures[robot_id] = list(exc.diagnostics)

        return UniversalCompilationResult(
            portable=portable,
            source_digest=_portable_digest(portable),
            results=results,
            failures=failures,
        )

    def compile_portable(self, instruction: str, verbose: bool = True) -> PortableSkill:
        """Run the target-independent front-end without selecting robot motion."""
        if verbose:
            print(f"\n\033[1;34mRoboWeaver Universal Compiler\033[0m — Instruction: \033[1m\"{instruction}\"\033[0m")
            print("  Front-end: \033[36mtarget independent\033[0m")

        intent = self._parse_intent(instruction)
        if self.perception_provider is not None:
            from roboweaver.perception import apply_observation

            intent = apply_observation(intent, self.perception_provider)
        if verbose:
            print("\n\033[1;36m━━━ FRONT-END 1/3: Parse Intent (deterministic) \033[0m")
            print(f"  → Action:     {intent.action.value}")
            print(f"  → Object:     {intent.object_name}")
            print(f"  → Confidence: {intent.confidence:.2f}")
            for k, v in intent.parameters.items():
                print(f"  → Parameter:  {k} = {v}")
            for w in intent.parse_warnings:
                print(f"  \033[1;33m⚠ {w}\033[0m")

        return self._portable_from_intent(intent, instruction, verbose=verbose)

    def compile(self, instruction: str, verbose: bool = True) -> CompiledSkill:
        """Compile source through the portable front-end and target lowering."""
        portable = self.compile_portable(instruction, verbose=verbose)
        return self.lower(portable, verbose=verbose)

    def compile_with_llm_parser(
        self,
        instruction: str,
        model: str | None = None,
        host: str | None = None,
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
                print(f"\n\033[1;36m━━━ STAGE 1/4: Parse Intent (Ollama: {parser.model}) \033[0m")
                print(f"  → Action:     {intent.action.value}")
                print(f"  → Object:     {intent.object_name}")
        else:
            if verbose:
                print(f"\n\033[1;33m⚠ Ollama parse failed ({result.error}) -- falling back to the deterministic parser.\033[0m")
            intent = self._parse_intent(instruction)

        portable = self._portable_from_intent(intent, instruction, verbose=verbose)
        try:
            skill = self.lower(portable, verbose=verbose)
        except TargetLoweringError as exc:
            raise SkillCompilationError([self._target_lowering_diagnostic(exc)]) from exc
        except CollisionPlanningError as exc:
            raise SkillCompilationError([self._collision_planning_diagnostic(exc)]) from exc
        return skill, result

    def _portable_from_intent(
        self, intent: SkillIntent, raw_instruction: str, *, verbose: bool = True,
    ) -> PortableSkill:
        """Build semantics without reading ``self.robot_spec``."""
        if intent.confidence <= 0.0:
            raise SkillCompilationError([
                CompilerDiagnostic(
                    code="RW101",
                    severity="error",
                    message="The source instruction does not contain a supported action.",
                    reason=(
                        "The deterministic frontend found no complete action keyword; "
                        "its internal PICK value is only a parser fallback and is not "
                        "safe to lower into a robot program."
                    ),
                    required_capability=None,
                    fixes=[
                        "Use an explicit supported action verb such as pick, place, "
                        "inspect, navigate, weld, clean, or tighten.",
                        "Use the opt-in model parser for a differently phrased request, "
                        "then inspect its returned intent before deployment.",
                        "Register and invoke a custom skill through an explicit typed "
                        "integration instead of relying on an unknown-language fallback.",
                    ],
                )
            ])
        task_graph = self._decompose_tasks(intent)
        if verbose:
            print("\n\033[1;36m━━━ FRONT-END 2/3: Task Decomposition \033[0m")
            for i, task in enumerate(task_graph.tasks):
                print(f"  → [{i+1}] {task.type.value:<14} → {task.description}")

        behavior_tree = self._compile_behavior_tree(intent, task_graph)
        if verbose:
            print("\n\033[1;36m━━━ FRONT-END 3/3: Behavior Program \033[0m")
            self._print_bt(behavior_tree)
            print()

        return PortableSkill(
            intent=intent,
            task_graph=task_graph,
            behavior_tree=behavior_tree,
            raw_instruction=raw_instruction,
        )

    def lower(self, portable: PortableSkill, *, verbose: bool = True) -> CompiledSkill:
        """Independently bind a PortableSkill to this compiler's RobotSpec."""
        if verbose:
            print(
                f"\n\033[1;36m━━━ TARGET LOWERING: {self.robot_spec.name} "
                f"({self.robot_spec.dof}-DOF) \033[0m"
            )
        motion_plan = self._plan_motion(
            portable.intent, portable.task_graph, verbose=verbose,
        )
        return CompiledSkill(
            intent=portable.intent,
            task_graph=portable.task_graph,
            motion_plan=motion_plan,
            behavior_tree=portable.behavior_tree,
        )

    def _compile_from_intent(self, intent: SkillIntent, task_graph_verbose: bool = True) -> CompiledSkill:
        """Compatibility wrapper for internal callers with an already-parsed intent."""
        portable = self._portable_from_intent(
            intent, intent.object_name, verbose=task_graph_verbose,
        )
        return self.lower(portable, verbose=task_graph_verbose)

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
        BoundedFormalVerificationPass,
        WaypointDecimationPass,
        RedundantSegmentElisionPass,
        CompiledSkillVerificationPass,
        BoundedFormalVerificationPass,
    )

    def compile_with_diagnostics(
        self,
        instruction: str,
        verbose: bool = True,
        optimization_level: OptimizationLevel = OptimizationLevel.O1,
    ) -> CompilationResult:
        """Compile source once, then lower and verify it for this target."""
        portable = self.compile_portable(instruction, verbose=verbose)
        return self.lower_with_diagnostics(
            portable,
            verbose=verbose,
            optimization_level=optimization_level,
        )

    def lower_with_diagnostics(
        self,
        portable: PortableSkill,
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
        instruction = portable.raw_instruction
        # Capability diagnostics are target facts and do not require motion data.
        # Run this preflight before target legality so a missing physical sensor is
        # reported as the primary cause instead of being masked by a later lowering
        # failure (for example TIGHTEN on a sensorless mobile base).
        preflight_ir = build_ir(
            portable.intent, self.robot_spec, raw_instruction=instruction, skill=None,
        )
        preflight_errors = [
            diagnostic
            for diagnostic in check_required_capabilities(preflight_ir, self.robot_spec)
            if diagnostic.severity == "error"
        ]
        if preflight_errors:
            raise SkillCompilationError(preflight_errors)
        try:
            skill = self.lower(portable, verbose=verbose)
        except TargetLoweringError as exc:
            raise SkillCompilationError([self._target_lowering_diagnostic(exc)]) from exc
        except CollisionPlanningError as exc:
            raise SkillCompilationError([self._collision_planning_diagnostic(exc)]) from exc

        try:
            skill_trace = self._run_skill_passes(skill, optimization_level)
        except CollisionPlanningError as exc:
            raise SkillCompilationError([self._collision_planning_diagnostic(exc)]) from exc
        optimized_skill = skill_trace.final_skill

        initial_ir = build_ir(
            optimized_skill.intent, self.robot_spec, raw_instruction=instruction, skill=optimized_skill,
        )

        pass_manager = PassManager([cls() for cls in self._DEFAULT_PASSES])
        trace = pass_manager.run(initial_ir, optimized_skill, self.robot_spec, optimization_level)

        native_mlir = _verify_native_mlir(trace.final_ir)

        # Structural and bounded forbidden-zone verification run both before and
        # after optimization (see _DEFAULT_SKILL_PASSES). Deduped here for a clean
        # user-facing diagnostics list; skill_trace itself (CompilationResult.
        # skill_pipeline) still records both raw runs for inspection.
        diagnostics = self._deduplicate_diagnostics(
            skill_trace.diagnostics() + trace.diagnostics()
        )

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
            portable=portable, pipeline=trace, skill_pipeline=skill_trace,
            native_mlir=native_mlir,
        )

    def _run_skill_passes(
        self, skill: CompiledSkill, optimization_level: OptimizationLevel,
    ) -> SkillPipelineTrace:
        skill_passes = [pass_type() for pass_type in self._DEFAULT_SKILL_PASSES]
        if self.scene is not None:
            # Waypoint optimization changes the swept path, so collision planning
            # is always the final trajectory-transforming pass.
            skill_passes.append(CollisionPlanningPass(self.scene))
        return SkillPassManager(skill_passes).run(
            skill, self.robot_spec, optimization_level,
        )

    def _target_lowering_diagnostic(
        self, error: TargetLoweringError,
    ) -> CompilerDiagnostic:
        return CompilerDiagnostic(
            code="RW601",
            severity="error",
            message=(
                f"{self.robot_spec.name} cannot lower this portable program "
                f"through the {self.robot_spec.motion_model} target dialect."
            ),
            reason=str(error),
            required_capability=f"motion_model.{self.robot_spec.motion_model}",
            fixes=[
                "Choose an embodiment whose motion model supports this action.",
                "Register a target lowering plugin that legalizes the required operations.",
            ],
        )

    def _collision_planning_diagnostic(
        self, error: CollisionPlanningError,
    ) -> CompilerDiagnostic:
        return CompilerDiagnostic(
            code="RW307",
            severity="error",
            message=f"No verified collision-free path was produced for {self.robot_spec.name}.",
            reason=str(error),
            required_capability="planning.environment_collision",
            fixes=[
                "Correct the scene frame or obstacle geometry and compile again.",
                "Choose a compatible motion model or provide the missing parent transform.",
                "Do not deploy by bypassing the collision-planning failure.",
            ],
        )

    @staticmethod
    def _deduplicate_diagnostics(
        raw: list[CompilerDiagnostic],
    ) -> list[CompilerDiagnostic]:
        seen: set[tuple[str, str, str]] = set()
        diagnostics: list[CompilerDiagnostic] = []
        for diagnostic in raw:
            key = (diagnostic.code, diagnostic.message, diagnostic.reason)
            if key not in seen:
                seen.add(key)
                diagnostics.append(diagnostic)
        return diagnostics

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

    @staticmethod
    def _parse_coordinates(text: str) -> tuple[dict[str, float], str | None]:
        matches = {
            axis: float(value)
            for axis, value in re.findall(
                r"\b([xyz])\s*=\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:m\b)?",
                text,
            )
        }
        if not matches:
            return {}, None
        missing = sorted({"x", "y", "z"} - set(matches))
        if missing:
            return {}, f"Ignoring partial Cartesian pose; missing coordinate(s): {', '.join(missing)}."
        return {f"{axis}_m": value for axis, value in matches.items()}, None

    @staticmethod
    def _contains_action_keyword(text: str, keyword: str) -> bool:
        """Match complete words/phrases, never accidental substrings.

        The previous ``keyword in text`` rule classified "unpack" as PACKAGE via
        ``pack`` and "refill" as POUR via ``fill``. Word-boundary matching keeps the
        deterministic parser inspectable without accepting those plausible-looking
        false positives.
        """
        return re.search(
            rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])",
            text,
        ) is not None

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
            coordinates, coordinate_warning = self._parse_coordinates(inst_lower)
            params.update(coordinates)
            # A matched compound structure ("pick X ... place it in Y") is a far
            # stronger signal than any single keyword, hence the high confidence.
            return SkillIntent(
                action=Action.PLACE,
                object_name=obj_name,
                parameters=params,
                confidence=0.95,
                parse_warnings=[coordinate_warning] if coordinate_warning else [],
            )

        # ── 2. Scored keyword matching ────────────────────────────────
        action, confidence, warnings = self._score_action(inst_lower)

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
        extracted = obj_match.group(1).strip() if obj_match else ""
        if extracted and len(extracted) > 1 and extracted != "it":
            obj_name = extracted.replace(" ", "_")

        params = dict(self._ACTION_DEFAULT_PARAMS.get(action, {}))
        coordinates, coordinate_warning = self._parse_coordinates(inst_lower)
        params.update(coordinates)
        if coordinate_warning:
            warnings.append(coordinate_warning)

        return SkillIntent(
            action=action,
            object_name=obj_name,
            parameters=params,
            confidence=confidence,
            parse_warnings=warnings,
        )

    def _score_action(self, text: str) -> tuple[Action, float, list[str]]:
        scores = {
            action: sum(
                weight for keyword, weight in keywords
                if self._contains_action_keyword(text, keyword)
            )
            for action, keywords in self._ACTION_KEYWORDS.items()
        }
        scores = {action: score for action, score in scores.items() if score > 0}
        if not scores:
            return Action.PICK, 0.0, [
                "No known action verb recognised in the instruction; defaulting to "
                "PICK. This is a fallback, not a parse -- verify the intent before deploying "
                "the generated skill."
            ]
        action = max(scores, key=scores.get)  # type: ignore[arg-type]
        best = scores[action]
        rivals = sorted((value for candidate, value in scores.items() if candidate is not action), reverse=True)
        second = rivals[0] if rivals else 0.0
        strength = min(1.0, best / 3.0)
        separation = 1.0 if second == 0.0 else (best - second) / best
        confidence = round(0.5 * strength + 0.5 * separation, 2)
        if confidence >= 0.5:
            return action, confidence, []
        runner_up = max(
            (candidate for candidate in scores if candidate is not action),
            key=lambda candidate: scores[candidate], default=None,
        )
        rival_text = f", close runner-up was {runner_up.value}" if runner_up else ""
        return action, confidence, [
            f"Ambiguous instruction: parsed as {action.value} (confidence {confidence:.2f})"
            f"{rival_text}. Rephrase with an explicit verb if this is wrong."
        ]

    def _decompose_tasks(self, intent: SkillIntent) -> TaskGraph:
        cat = ACTION_CATEGORY_MAP.get(intent.action, IndustrialSkillCategory.PICK_AND_PLACE)
        tmpl = get_industrial_skill_template(cat, intent.object_name)
        supplied_pose = supplied_pose_satisfies_perception(intent)
        semantic_tasks = [
            task for task in tmpl.tasks
            if not (supplied_pose and task.type is TaskType.PERCEIVE)
        ]
        move_count = sum(task.type is TaskType.MOVE_TO for task in semantic_tasks)
        targets = self._cartesian_targets(intent, move_count) if move_count else []
        pose_source = (
            str(intent.parameters.get("_pose_source", "user_specified"))
            if all(key in intent.parameters for key in ("x_m", "y_m", "z_m"))
            else "assumed_default"
        )
        target_index = 0
        tasks: list[TaskDecomposition] = []
        for task in semantic_tasks:
            params = dict(task.params)
            if task.type is TaskType.MOVE_TO:
                target = targets[target_index]
                params.update({
                    "target_pose_m": [target.x, target.y, target.z],
                    "pose_source": pose_source,
                    "motion_index": target_index,
                    "motion_action": intent.action.value,
                })
                target_index += 1
            tasks.append(TaskDecomposition(task.type, task.description, params))
        return TaskGraph(tasks=tasks)

    @staticmethod
    def _resample_cartesian_path(points: list[Vec3], count: int) -> list[Vec3]:
        if count <= 0:
            return []
        if count == 1:
            return [points[len(points) // 2]]
        if len(points) == count:
            return points
        sampled: list[Vec3] = []
        for index in range(count):
            position = index * (len(points) - 1) / (count - 1)
            left = int(position)
            right = min(left + 1, len(points) - 1)
            alpha = position - left
            a, b = points[left], points[right]
            sampled.append(Vec3(
                a.x + (b.x - a.x) * alpha,
                a.y + (b.y - a.y) * alpha,
                a.z + (b.z - a.z) * alpha,
            ))
        return sampled

    def _cartesian_targets(self, intent: SkillIntent, count: int) -> list[Vec3]:
        """Build action-specific Cartesian lowering inputs with explicit provenance."""
        x = float(intent.parameters.get("x_m", 0.35))
        y = float(intent.parameters.get("y_m", 0.0))
        z = float(intent.parameters.get("z_m", 0.13))
        approach = float(intent.parameters.get("approach_height", 0.12))
        source = Vec3(x, y, z)

        if intent.action in (Action.PICK, Action.PLACE, Action.SORT, Action.PACKAGE, Action.PALLETIZE):
            destination_x = float(intent.parameters.get("destination_x_m", x + 0.18))
            destination_y = float(intent.parameters.get("destination_y_m", y + 0.08))
            path = [
                Vec3(x, y, z + approach), source,
                Vec3(x, y, z + max(approach, 0.18)),
                Vec3(destination_x, destination_y, z + max(approach, 0.18)),
            ]
        elif intent.action == Action.WELD:
            path = [Vec3(x - 0.08, y, z + 0.04), Vec3(x + 0.08, y, z + 0.04), Vec3(x + 0.08, y, z + 0.16)]
        elif intent.action in (Action.INSPECT, Action.CLEAN, Action.POLISH):
            stand_off = 0.10 if intent.action == Action.INSPECT else 0.03
            path = [
                Vec3(x - 0.07, y - 0.05, z + stand_off),
                Vec3(x + 0.07, y + 0.05, z + stand_off),
                Vec3(x, y, z + approach),
            ]
        elif intent.action == Action.OPEN_DOOR:
            path = [Vec3(x, y, z + 0.08), source, Vec3(x - 0.12, y + 0.12, z - 0.03)]
        elif intent.action == Action.TOOL_EXCHANGE:
            path = [Vec3(x, y, z + approach), source, Vec3(x, y, z + 0.20), Vec3(x + 0.16, y, z + approach)]
        elif intent.action in (Action.TIGHTEN, Action.PEG_INSERT, Action.CNC_LOAD, Action.DISASSEMBLE):
            path = [Vec3(x, y, z + approach), source, Vec3(x, y, z + 0.18)]
        elif intent.action == Action.POUR:
            path = [Vec3(x, y, z + approach), source, Vec3(x + 0.15, y, z + 0.18), Vec3(x + 0.15, y, z + 0.10)]
        elif intent.action == Action.NAVIGATE:
            path = [Vec3(x * 0.5, y * 0.5, max(z, 0.10)), Vec3(x, y, max(z, 0.10))]
        else:
            path = [Vec3(x, y, z + approach), source, Vec3(x, y, z + 0.18)]
        return self._resample_cartesian_path(path, count)

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
            return MotionPlan(
                trajectories={}, ik_results={}, robot_model=self.robot_spec.id,
                lowerer=self.robot_spec.motion_model,
            )

        targets = self._typed_motion_targets(move_to_tasks)

        lowerer = get_motion_lowerer(self.robot_spec)
        plan = lowerer.lower(intent, task_graph.tasks, targets)
        if self.scene is not None:
            from roboweaver.planning import CollisionAwarePlanner

            plan = CollisionAwarePlanner(self.robot_spec, self.scene).replan(plan)
        if verbose:
            self._print_motion_plan(move_to_tasks, plan)

        return plan

    @staticmethod
    def _typed_motion_targets(move_to_tasks: list[TaskDecomposition]) -> list[Vec3]:
        targets: list[Vec3] = []
        for task in move_to_tasks:
            raw_target = task.params.get("target_pose_m")
            if not isinstance(raw_target, (list, tuple)) or len(raw_target) != 3:
                raise ValueError(f"MOVE_TO task '{task.description}' has no typed 3D target_pose_m.")
            targets.append(Vec3(*(float(value) for value in raw_target)))
        return targets

    @staticmethod
    def _print_motion_plan(move_to_tasks: list[TaskDecomposition], plan: MotionPlan) -> None:
        for index, task in enumerate(move_to_tasks, start=1):
            solution = plan.ik_results[task.description]
            print(
                f"  ✓ {solution.solver} target {index}/{len(move_to_tasks)} ({task.description}) "
                f"(residual: {solution.residual:.4f}m, {solution.iterations} iters)"
            )
        print()
        for task in move_to_tasks:
            segment = plan.trajectories[task.description]
            print(
                f"  → Trajectory: {task.description}    "
                f"({segment.duration:.2f}s, {len(segment.waypoints)} waypoints)"
            )

    def _compile_behavior_tree(self, intent: SkillIntent, task_graph: TaskGraph) -> BTNode:
        cat = ACTION_CATEGORY_MAP.get(intent.action, IndustrialSkillCategory.PICK_AND_PLACE)
        tmpl = get_industrial_skill_template(cat, intent.object_name)
        active_descriptions = {task.description for task in task_graph.tasks}
        removed_perception = {
            task.description
            for task in tmpl.tasks
            if task.type is TaskType.PERCEIVE and task.description not in active_descriptions
        }

        def clone_without_removed_perception(node: BTNode) -> BTNode | None:
            if not node.children and node.name in removed_perception:
                return None
            children = [
                cloned
                for child in node.children
                if (cloned := clone_without_removed_perception(child)) is not None
            ]
            return BTNode(type=node.type, name=node.name, children=children)

        return clone_without_removed_perception(tmpl.behavior_tree_root) or BTNode(
            type="Sequence", name=f"{intent.action.value.lower()}_{intent.object_name}"
        )

    def _print_bt(self, node: BTNode, prefix: str = "", is_last: bool = True) -> None:
        connector = "└─ " if is_last else "├─ "
        print(f"  {prefix}{connector}{node.type}: {node.name}")
        child_prefix = prefix + ("   " if is_last else "│  ")
        for i, child in enumerate(node.children):
            self._print_bt(child, child_prefix, i == len(node.children) - 1)
