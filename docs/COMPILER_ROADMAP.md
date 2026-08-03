# RoboWeaver — Compiler Infrastructure Roadmap

Tracks the multi-phase initiative to evolve RoboWeaver from a robotics framework
toward LLVM/MLIR/TVM-style compiler infrastructure: an immutable, versioned IR; a
pass manager; static analysis and optimization passes; multi-backend lowering; a cost
model; formal verification; and a reproducible benchmark suite.

This is a separate, differently-numbered roadmap from `docs/REDESIGN.md` §9's
"Phase 1–4" (deployment/runtime, multi-robot backend, memory/optimization) — that
roadmap is about shipping RoboWeaver as a product; this one is about RoboWeaver's
identity as compiler infrastructure. Where the two overlap (e.g. this roadmap's
Phase 6 runtime work vs. REDESIGN.md's Phase 2), each doc notes it. Follows this
codebase's documentation convention (REDESIGN.md §11): every "done" claim is cited by
file and, where relevant, by test; every phase states what's still open rather than
letting a partial implementation read as complete.

**Written 2026-08-03**, when Phase 2 was completed; **updated 2026-08-04** when Phase
3 and Phase 4 were completed together (they turned out to share one architectural
decision — see Phase 3's writeup); **updated again 2026-08-04** when the original
Phase 5–14 roadmap below was superseded, before any of it was built, by a more
ambitious 14-item "v2 vision" the user proposed after seeing Phase 13 (plugin
registry) — see "v2 Vision (replaces Phase 5–14)" below for what was actually built
under that revised scope, and why several of its most ambitious pieces (a compiler
that has *learned* from executions, live Isaac/Gazebo/Webots simulator integration,
SMT/temporal-logic proofs) are real infrastructure with an honestly-empty or
bounded payload today, not the full capability as originally described. A future
session should treat every "not started"/"deferred" item as a starting brief, not a
fixed spec, and re-verify the codebase state before resuming (this file decays like
any other design doc).

## Maturity scorecard

Self-assessed against LLVM/MLIR/TVM/TensorRT as a reference point. Re-score after each
phase rather than trusting this snapshot.

| Area | Maturity |
|---|---|
| Compiler pipeline | 8.5/10 |
| RoboIR | 8/10 → improved by Phase 2 (frozen, pass-managed, diffable) |
| Safety verification | 8.5/10 → Phase 4's WaypointDecimationPass is independently re-verified against it (see below) |
| Runtime execution | 8/10 |
| Runtime recovery | 8.5/10 |
| Multi-robot support | 7.5/10 → 8/10: Phase 3 added real cycle/resource-conflict detection over the DAG |
| Backend abstraction | 8/10 |
| Code generation | 8/10 |
| Knowledge layer | 7.5/10 |
| Optimization framework | 4/10 → 7/10: 2 real optimization passes + a motion-plan cache + a real cost model/Pareto filter (v2 item 8) |
| Static analysis | 5/10 → 6/10: RW501/502/505/506 (CompiledSkill) + RW601/602/605 (choreography DAG) + RW507 (bounded forbidden-zone, v2 item 10); collision/dynamics-dependent checks still deferred |
| Formal verification | 3/10 → 4/10: a real, bounded, discrete check (v2 item 10) — explicitly not a temporal-logic/SMT proof |
| Benchmarking | 2/10 → 5/10: RoboBench (v2 item 11) is real compile-time measurement over every distinct robot × every NL-reachable skill category — not simulator-execution benchmarking |
| Plugin ecosystem | 3/10 → 7/10: a real `PluginRegistry` (v2 item 3) backs both robot bridges and `RobotBackend`s; `CodegenBackend`/`DigitalTwin` both registry-based |
| RoboIR (task/motion layer) | (new row) 3/10: real summary fields only (v2 item 1) — not the full task/motion/BT absorption |
| Capability ontology | (new row) 6/10: real `CapabilityClaim`s with confidence/verified grounded in declared `RobotSpec` fields (v2 item 2) |
| Digital twin | (new row) 4/10: one fully-real twin (native execution), one honest reachability-only placeholder (v2 item 4) |
| Execution memory | (new row) 5/10: real, persisted, queryable — zero accumulated history yet (v2 item 6) |
| Safety kernel | (new row) 5/10: real, mandatory at the one new enforcement point that exists (`deploy()`); not (yet) mandatory at `SkillRuntime.execute()` (v2 item 9) |
| Self-improvement | (new row) 2/10: a real, tested mechanism (v2 item 12) that honestly returns nothing until real usage data exists |

## Phase 1 — Existing Foundation

Not tracked here in detail — see `docs/REDESIGN.md` (§11 "What Actually Got Built")
and `.agents/knowledge/roboweaver-architecture/artifacts/architecture_map.md` for the
current, real module inventory (compiler pipeline, RoboIR, safety verification,
hardware abstraction, runtime, fleet, codegen, skills, knowledge). This roadmap starts
numbering at Phase 2 to match the original planning conversation; there is no gap.

## Phase 2 — Pass Manager + Immutable RoboIR — **Done** (2026-08-03)

**Real, cited by file:**

- **Frozen RoboIR.** `src/roboweaver/ir/schema.py` — `RoboIR` and every nested
  dataclass (`ObjectRef`, `Constraints`, `RequiredCapabilities`, `ExecutionSpec`,
  `VerificationSpec`) are `frozen=True`. Confirmed by grep that nothing in the
  codebase mutated a built RoboIR in place before this change; one test
  (`tests/test_safety_verification.py::test_payload_violation_detected`) did, via
  direct field assignment, and was updated to `dataclasses.replace()` instead — the
  same pattern any future IR-mutating pass must use.
- **Pass Manager.** `src/roboweaver/ir/pass_manager.py` — `CompilerPass` (ABC),
  `PassContext`, `PassResult`, `PassRecord`, `PipelineTrace`, `PassManager`. Threads a
  RoboIR generation-to-generation across an ordered list of passes; records real,
  manager-measured timing (`time.perf_counter()`, not self-reported) plus
  diagnostics/metrics/modified-flag per pass. `PipelineTrace.snapshot_at(generation)`
  gives rollback/debugging to any point in the chain.
- **`OptimizationLevel`** (`O0, O1, O2, O3, Os, Oenergy, Osafe`) in the same file —
  plumbing only. No registered pass reads it to change behavior yet, because no real
  optimization pass exists (that's Phase 4 below). Stated explicitly in the module
  docstring so it isn't mistaken for a working feature.
- **Passes.** `src/roboweaver/ir/passes.py`:
  - `RoboIRVerificationPass` — genuinely new logic (nothing in the codebase checked
    RoboIR's own structural invariants before this): unique object ids, valid object
    roles, `execution.dof`/`execution.robot_id` matching the target robot, non-negative
    payload, known `safety_checks` names, well-formed `ir_version`. Reports `RW401`.
    Silent on every real `build_ir()` output today — it's a regression guard for
    future IR-producing/mutating passes, proven by feeding it a deliberately malformed
    IR in `tests/test_pass_manager.py`.
  - `CapabilityPass` / `SafetyPass` — thin wraps of the pre-existing
    `check_required_capabilities()` (`ir/diagnostics.py`) and `check_safety()`
    (`ir/safety.py`). Same diagnostics, same codes (RW102, RW201, RW301–RW306),
    verified identical to the direct function calls in
    `tests/test_pass_manager.py::test_capability_pass_matches_direct_function_call`
    and `..._safety_pass_matches_direct_function_call`.
  - Default order: Verification → Capability → Safety.
- **IR Diff.** `src/roboweaver/ir/diff.py` — `IRDiff`, `diff_ir()`, `diff_trace()`.
  Diffs the RoboIR schema fields that exist today (objects, capabilities, constraints,
  execution/verification config), with `skill_id` excluded by default (random per
  compile, pure noise). **Does not** produce a task/motion-level diff ("Removed MOVE
  MOVE, Merged GRASP, Inserted WAIT") — see "Deferred" below.
- **Wired into `compiler.py`.** `SkillCompiler.compile_with_diagnostics()` now builds
  the IR, runs it through `PassManager([RoboIRVerificationPass(), CapabilityPass(),
  SafetyPass()])`, and keeps the exact same error-raising logic (raise
  `SkillCompilationError` on any `severity == "error"` diagnostic). `CompilationResult`
  gained one additive field, `pipeline: PipelineTrace | None` — every existing
  consumer (`cli/main.py`, `dashboard/server.py`, the frontend, and every pre-existing
  test) reads `.skill`/`.ir`/`.diagnostics` by name and is unaffected;
  `test_pass_manager.py::test_compile_with_diagnostics_still_raises_rw102_first_for_temi_tighten`
  regression-checks this directly.
- **CLI.** `src/roboweaver/cli/main.py`:
  - `roboweaver compile --opt-level {O0,O1,O2,O3,Os,Oenergy,Osafe} --explain-passes`
    — the latter prints the real per-pass timing/diagnostic table.
  - New `roboweaver diff INSTRUCTION --robot ROBOT [--robot2 ROBOT2]` — cross-robot
    IR diff with `--robot2`, or a diff of the compile pipeline's own trace without it
    (honestly reports "no IR-mutating passes registered yet" today, since
    Verification/Capability/Safety are diagnostics-only).
- **Tests.** `tests/test_pass_manager.py` — 11 tests, added to the suite (157/157
  passing as of this write, `python -m pytest tests/ -q`).

**Deferred within Phase 2** (i.e. not silently claimed done):

- `IntentValidationPass`, `MotionPlanningPass`, `BTGenerationPass`,
  `BackendLoweringPass`, `PackagingPass` — these need RoboIR to absorb task/motion/
  behavior-tree data first (today that data lives separately on `CompiledSkill`).
  That's a bigger schema migration than adding a pass manager, and the honest
  precondition for the roadmap's literal MOVE/GRASP/WAIT-level diff mockup to become
  real instead of fabricated.
- Real optimization passes (waypoint merge, trajectory smoothing, redundant-motion
  removal, ...) — Phase 4 below. `OptimizationLevel` is plumbing, not yet gating
  anything.
- Dashboard/frontend exposure of `CompilationResult.pipeline` — not touched this
  round, to keep the change scoped; a natural, low-effort follow-up
  (`dashboard/server.py`'s `/api/compile` already has `result` in scope).

## Phase 3 — Static Analysis — **Done** (2026-08-04, jointly with Phase 4)

**Architectural finding that shaped both phases:** RoboIR still has no task/motion/
behavior-tree fields (Phase 2's own deferred list), so any check touching tasks,
waypoints, or timing has to operate on `CompiledSkill`, not `RoboIR`. Rather than
genericize `ir/pass_manager.py::PassManager` (which would mean renaming already-
shipped, already-tested API — `PassRecord.ir_before/ir_after`,
`PipelineTrace.initial_ir/final_ir`, `CompilationResult.ir` — across `compiler.py`,
`cli/main.py`, `ir/diff.py`, `tests/test_pass_manager.py` — for a mostly-cosmetic
genericity benefit), a second, small, symmetric Pass Manager was built for
`CompiledSkill`: `src/roboweaver/optimize/pass_manager.py` (`SkillPass`,
`SkillPassContext`, `SkillPassResult`, `SkillPassRecord`, `SkillPipelineTrace`,
`SkillPassManager` — identical shape to `ir/pass_manager.py`, deliberately not shared
code). Phase 3's static-analysis passes and Phase 4's optimization passes both run
through it, which is why they shipped together.

Also found: **the task graph is a flat list, not a graph** (`TaskGraph.tasks:
list[Task]`, no dependency edges) — cycle/deadlock/resource-conflict detection don't
structurally apply to a single skill. They do apply, for real, to
`fleet/choreographer.py::WorkcellSchedule` (a genuine multi-robot DAG with
`depends_on` edges), which is where those checks actually landed.

**Real, cited by file:**

- **`CompiledSkillVerificationPass`** (`src/roboweaver/optimize/passes.py`) —
  `RW501` (error): empty `task_graph.tasks`. `RW502` (warning): a `MOVE_TO` task whose
  description matches no key in `motion_plan.trajectories`/`ik_results` — surfaced a
  real, pervasive, pre-existing bug: `compiler.py::_plan_motion` only ever plans the
  fixed 3-pose pick/place motion regardless of skill category, so most non-pick/place
  templates' `MOVE_TO` tasks (and even `PICK_AND_PLACE`'s own "Transfer to dropoff
  location") have no matching motion data — `runtime/engine.py::execute()` silently
  no-ops for them today. Warning, not error, for the same reason `RW201` (missing
  perception) is a warning: making a pervasive, disclosed, not-yet-fixed gap a
  blocking error would refuse to compile nearly the whole registry. `RW505` (warning):
  a trajectory segment consuming >60% of the real, computed total cycle time — a
  genuine timing-analysis signal, not estimated. Runs both before and after Phase 4's
  optimization passes (regression guard + proof-of-no-breakage), same pattern as
  `ir/passes.py::RoboIRVerificationPass`.
- **Choreography DAG static analysis** (`src/roboweaver/fleet/choreography_verification.py`,
  new — reuses the existing `CompilerDiagnostic` type, no new diagnostic type needed):
  `RW605` (error) dangling `depends_on` reference; `RW601` (error) cyclic dependency,
  with the actual cyclic step ids in `reason` (a structured version of
  `WorkcellSchedule.get_execution_tiers()`'s pre-existing bare `raise ValueError`,
  which is untouched — this is additive); `RW602` (error) the same `robot_id`
  assigned to more than one step within a concurrent execution tier — a real
  correctness bug (a robot can't run two steps at once) nothing checked before.
  Wired into `MultiRobotChoreographer.compile_workcell()`, raising the existing
  `SkillCompilationError` on any error-severity finding.
  **Not checked, and why:** `handover_target` (`WorkcellTaskStep`) turned out, on
  inspection, to be write-only everywhere it's touched (`dashboard/server.py`,
  `fleet/prompt_builder.py`) — set but never read or acted on by any real logic. Its
  one concrete usage (`tests/test_multi_robot_choreography.py`) sets it to a
  *robot_id*, not a step_id, contradicting the "target step" semantics a validator
  would have assumed. Validating a field no consuming code has pinned down would be
  guessing, not checking — deferred until `handover_target` is actually consumed by
  something.
  **Also not checked:** collision proof, cable/tool collision, battery/thermal
  estimation — no geometry or dynamics model exists (unchanged since `ir/safety.py`'s
  own docstring ruled these out).
- **Tests.** `tests/test_choreography_verification.py` — 6 tests (clean DAG, cycle,
  resource conflict, conflict-resolved-by-dependency, dangling reference, end-to-end
  `compile_workcell()` refusal).

## Phase 4 — Compiler Optimizations — **Done** (2026-08-04, jointly with Phase 3)

**Real, cited by file** (`src/roboweaver/optimize/passes.py` unless noted):

- **`WaypointDecimationPass`** — real trajectory compression: for each segment,
  finds the largest *uniform* stride (keep every Nth waypoint) that (a) evenly
  divides the segment's waypoint-count-minus-one, so the true final waypoint always
  lands exactly on-stride and every kept interval spans an identical amount of time —
  keeping `ir/safety.py::_check_velocity_limits`'s uniform-time-stepping assumption
  valid on the decimated result, which is exactly why this rules out non-uniform
  methods like Ramer-Douglas-Peucker here — (b) leaves at least 10 waypoints, and (c)
  keeps every joint's finite-difference velocity within
  `robot_spec.get_max_velocities()`, computed in-pass with the same formula RW304
  uses, so the choice is self-verifying. Reports real `waypoints_before`/
  `waypoints_after`/`pct_reduction` metrics — 82.9% (193→33 waypoints) on the
  standard Franka pick/place demo. `tests/test_optimize_passes.py` re-runs
  `ir/safety.py::check_safety()` on the decimated result and asserts RW304 stays
  clean — proof, not assumption. Gated by `OptimizationLevel`: a no-op at O0, the
  **first pass that gives Phase 2's `OptimizationLevel` plumbing something real to
  gate.**
- **`RedundantSegmentElisionPass`** — collapses a trajectory segment to its two
  endpoints (zero duration) when `start_pose`≈`end_pose`. Doesn't fire on today's
  standard demo poses (real, non-trivial deltas) — proven with a synthetic
  near-zero-delta segment in tests, not assumed to fire "by luck". Also gated by
  `OptimizationLevel`.
- **Motion-plan cache** (`src/roboweaver/optimize/motion_cache.py`, new) — every
  compile today plans against the same 3 fixed Cartesian poses (no perception system
  derives a real per-object pose yet), so the IK+trajectory computation is, honestly,
  a pure function of `robot_spec.id` alone right now. `compute_pick_place_primitives()`
  memoizes it per robot; `compiler.py::_plan_motion` became a thin wrapper (labels the
  cached primitives with the object name, unchanged verbose output plus a
  `(cached)` note). Measured effect: the full test suite (containing many repeated
  compiles per robot) dropped from ~25s to ~14s. **Documented limitation, not
  hidden:** the cache key must include the target pose, not just `robot_spec.id`,
  once perception is ever wired in — it will silently serve a stale plan otherwise.
- **Pipeline ordering fix.** `compiler.py::compile_with_diagnostics()` now runs the
  optimization pipeline (`SkillPassManager`) *before* `build_ir()`/the RoboIR pipeline,
  so `SafetyPass` verifies the final, optimized trajectories — not pre-optimization
  ones. `CompilationResult` gained one more additive field, `skill_pipeline:
  SkillPipelineTrace | None` (same backward-compatible pattern as Phase 2's
  `pipeline`). Duplicate diagnostics from `CompiledSkillVerificationPass` running
  twice are deduped in the final `.diagnostics` list; the raw two-run trace is still
  available via `.skill_pipeline` for inspection.
- **CLI.** `roboweaver compile --explain-passes` now prints both pipelines
  (optimization, then RoboIR); `--opt-level O0` visibly shows the two optimization
  passes as `[skipped]`.
- **Tests.** `tests/test_optimize_passes.py` — 9 tests.

**Deferred, and why (not fabricated):**

- **Joint-energy reduction / payload-aware optimization** — need a dynamics/mass
  model RoboWeaver doesn't have (the same gap `ir/safety.py` already documents for
  torque limits).
- **"Trajectory smoothing"** — nothing to smooth: `compiler.py` already generates
  min-jerk (quintic) trajectories, which are smooth by construction.
- **Gripper-delay elimination** — would mean shortening a `WAIT` task's duration with
  no real data to justify the new number; the same class of fabrication this
  codebase's existing passes refuse to produce.
- **The roadmap's literal MOVE/GRASP/WAIT-level diff mockup** — still blocked on
  RoboIR absorbing task/motion data (Phase 2's deferred list), unchanged.

## v2 Vision (replaces Phase 5–14) — **Done** (2026-08-04)

The original Phase 5–14 outline above (backend architecture, runtime improvements,
execution memory, knowledge graph, cost model, compiler reports, benchmark suite,
formal verification, plugin system, research features) was replaced, before any of
it was built, by a 14-item vision the user proposed: RoboIR unification, a
capability ontology, a richer plugin contract, a digital twin interface, episodic
execution memory, case-based recovery, multi-objective optimization, a "safety
kernel," bounded formal verification, a benchmark suite, a self-improving-compiler
mechanism, industrial deployment packaging, and research extensions. Kept here as a
map from the old numbering (some items reused directly) plus what's genuinely new.
Every item below follows the same discipline as Phase 2/3/4: real, tested,
cited-by-file work, gaps stated honestly rather than stubbed silently or faked.

**1 — RoboIR stabilization (Stage 1, not the full migration).**
`ir/schema.py`: `TaskSummary`, `MotionSummary` (frozen), `RoboIR` gains
`task_summary`/`motion_summary: ... | None = None` (additive). `ir/builder.py::
build_ir()` gains an optional `skill: CompiledSkill | None = None` param that
populates real summaries from the real task graph/motion plan when passed;
`compiler.py::compile_with_diagnostics()` passes the optimized skill.
**Explicitly not done:** full raw-waypoint/BT absorption into RoboIR — still lives
on `CompiledSkill`; the roadmap's literal MOVE/GRASP/WAIT-level IR diff still isn't
real for the same reason it wasn't after Phase 2.

**2 — Capability ontology.** `ir/schema.py::CapabilityClaim(name, confidence,
verified, source)`. `ir/builder.py` constructs real claims: manipulation
capabilities always `verified=True/confidence=1.0` (every `RobotSpec` has an IK
solver by construction); `sensing.force_torque`'s `confidence`/`verified` come
directly from the real `robot_spec.has_force_torque_sensor` field (confirmed
identical on both a robot that has one and one that doesn't,
`tests/test_roboir_v2.py`); `perception.*` stays honestly `verified=False/
confidence=0.5` — formalizes the RW102/RW201 distinction that already existed
ad hoc, doesn't invent a new one.

**3 — Plugin framework.** `plugins/registry.py::PluginRegistry` (generic, name-keyed,
`register()`/`get()`/`names()`) is the shared primitive. First consumer:
`hardware/universal_driver.py::UniversalRobotDriver.connect_robot()`'s old if/elif
bridge dispatch, refactored to registry lookup with zero behavior change (same
substring-alias matching, same ROS2 default — regression-checked per-protocol-string
in `tests/test_plugin_registry.py`). Second, richer consumer:
`plugins/backend.py::RobotBackend` ABC (`metadata()`, `capabilities()`, `validate()`,
`compile()`, `deploy()`) with two real implementations — `Ros2Backend` (wraps the
unmodified `generate_ros2_package()`) and `UrScriptBackend`
(`codegen/urscript_gen.py`, new — real, syntactically valid URScript `movej()`/
`sleep()`/`set_digital_out()` from the compiled skill's real task graph and
trajectories, same integrity level as `urdf_gen.py`'s real-geometry generation).
`roboweaver export --backend {ros2,urscript}` — also fixed `cmd_export` to route
through `compile_with_diagnostics()` instead of bare `compile()`, the same
"don't validate on only one front-end" gap `cmd_compile` already had fixed.
**Explicitly not built:** MoveIt/Isaac/Drake/Webots/CuRobo/BehaviorTree.CPP/ABB
RAPID/KUKA KRL/Fanuc TP backends — unverifiable against real controllers/engines
here; adding one later is a registry entry, not a rewrite.

**4 — Digital twin interface.** `simulation_backends/twin.py::DigitalTwin` ABC.
`NativeTwin` is real — wraps the already-working `runtime.engine.SkillRuntime`
(real kinematics, grasp physics, telemetry). `RemoteTwin` wraps the existing,
already-honest `SimulationHardwareBridge` (TCP-reachability probe only) and
`execute()` returns `success=False` with a message stating plainly that no real
physics ran — never fabricates an Isaac/Gazebo/Webots outcome for engines this
environment can't reach. Both registered in a `PluginRegistry[type[DigitalTwin]]`
(classes, not instances — each twin holds mutable per-use state from `load_robot()`).

**5 — Simulation validation.** `runtime/validation.py::validate_in_simulation()`
defaults to `NativeTwin`. Wired as the second step of `RobotBackend.deploy()`
(item 3): raises `DeploymentRefused` (carrying the real `ExecutionResult`) if the
real simulation run didn't succeed, before any bridge connect is attempted. Proven
against a **real, naturally-occurring failure** — compiling `"Tighten the M8 bolt"`
for `franka_panda` genuinely fails in `NativeTwin` today (item 1's/Phase 3's RW502
gap: `_plan_motion` never produces a trajectory for TIGHTEN's task descriptions, so
the arm never moves toward the target and the grasp genuinely fails) — not a
constructed scenario. `skip_simulation_check` is an explicit, visible opt-out for
this one step (e.g. tests exercising just the connect/send path).

**6 — Execution memory.** `runtime/memory.py::ExecutionMemoryStore` — real,
persisted (JSONL, one file per robot, `registry/repository.py`'s existing
local-file convention). `record()`/`query()`/`success_rate()` (returns `None`, never
a fabricated `0.0`, with no history). `SkillRuntime.__init__` gains
`memory_store: ExecutionMemoryStore | None = None` — **opt-in**, confirmed the
232-test suite creates no `.execution_memory` directory by default
(`tests/test_execution_memory.py`).

**7 — Failure intelligence (case-based recovery).** `runtime/recovery.py` v3:
`RecoveryCandidate(action, estimated_success_probability, cost_s, safety_score,
offset_m, reason)` — declared priors, stated as authored estimates, not learned.
`RecoveryEngine.plan()` scores candidates by `probability * safety_score / cost_s`,
excludes already-attempted actions (auto-derived from `retry_count` for backward
compatibility), and boosts a candidate's probability with a **real** historical rate
from `ExecutionMemoryStore.recovery_action_success_rate()` when real records exist
— `RecoveryPlan.used_historical_data` tells a caller which happened.
`RecoveryEngine.diagnose()` is now a thin, signature-preserving wrapper around
`plan()`; both of `runtime/engine.py`'s call sites are unaffected (regression-checked
against the pre-existing `test_ir.py::test_telemetry_and_recovery_are_wired...`).

**8 — Optimization engine.** `ir/safety.py::compute_manipulability()` extracted
from `_check_manipulability` (one implementation, shared). `optimize/cost_model.py`:
`CompiledSkillCost` (cycle time, payload margin, total joint travel, manipulability
margin, optional real historical success rate) — every field computed from data
already in scope. `pareto_front()` — a real dominated-solution filter (standard
Pareto-dominance definition), explicitly not a continuous-frontier solver.
`compare_robots()` ranks by a weighted sum (default equal weights) and reports the
real Pareto subset; a robot that genuinely can't compile the instruction (e.g.
missing a declared capability) is reported in `skipped` with the real blocking
reason, never silently dropped. `roboweaver compare INSTRUCTION --robots ...`.

**9 — Safety kernel.** `plugins/safety_kernel.py::SafetyKernel.enforce()` raises the
existing `SkillCompilationError` on any error-severity diagnostic — mandatory,
non-bypassable at `RobotBackend.deploy()` (brand-new code, breaks nothing existing).
**Documented honestly:** `compile_with_diagnostics()` already refuses to return a
`CompilationResult` with an error diagnostic, so on the normal path `enforce()` can
never actually fire — its real value is defense in depth against a `CompilationResult`
that reached `deploy()` some other way (proven in tests via a manually-tampered
result). **Not** made mandatory on `SkillRuntime.execute()` — pure simulation, called
directly with a bare `CompiledSkill` throughout the existing CLI/fleet/test suite,
never the real hardware boundary; forcing that path through the compile pipeline
would be an unrelated breaking change. Stated plainly, not silently scoped down.

**10 — Formal verification, bounded.** `optimize/passes.py`: `RW506` (warning) —
an empty composite BT node or an unnamed leaf; deliberately not a "reachability"
check, since every node in a real tree is reachable from the root by construction
(that would be a vacuous, always-passing check). `optimize/formal.py::
check_forbidden_zone_violations()` — real, bounded: every compiled waypoint checked
against a **declared** forbidden joint-range zone, `[]` honestly returned if none is
declared. **Explicitly not attempted:** an SMT/temporal-logic proof of a
continuous-time property — needs a new solver dependency (e.g. `z3-solver`, not
added here without an explicit decision) and nonlinear real arithmetic over
trigonometric forward kinematics, genuinely research-grade work. Cycle detection /
"no deadlock" over the real multi-robot DAG was already delivered in Phase 3
(`RW601`/`RW602`/`RW605`) and isn't redone here.

**11 — Multi-robot benchmark ("RoboBench").** `benchmark/robobench.py::
run_benchmark()` — real compile-pipeline measurement (latency, success/failure,
diagnostic counts, waypoint `pct_reduction`) over every distinct registered robot ×
every skill category the compiler's NL pipeline can actually reach. **Discovered,
not assumed:** of the 17 `IndustrialSkillCategory` templates with real,
hand-authored task graphs, only **13** are reachable through `SkillCompiler.compile()`
at all — `PALLETIZING`, `POLISHING`, `DISASSEMBLY`, and `MOBILE_NAV` have no entry in
`compiler.py::ACTION_CATEGORY_MAP`, so no natural-language instruction can ever route
to them through the real pipeline (only reachable by calling
`skills.taxonomy.get_industrial_skill_template()` directly — dead code from the
compiler's perspective). This benchmark only exercises the 13 reachable ones; the
other 4 are a discovered gap, not silently routed around. `roboweaver benchmark
[--json] [--output FILE]`. Explicitly scoped down from "100 skills × 20 robots × 5
simulators" (no simulators exist here) — stated in the report's own `scope` field.

**12 — Self-learning compiler mechanism.** `optimize/learning.py::
suggest_parameter_adjustments()` — real analysis (low success rate, frequent
recovery-action pattern, frequent joint-limit violations) over real
`ExecutionMemoryStore` records, `None` below `min_samples=5`. **Stated plainly:**
this repo has zero accumulated real execution history right now, so every real
caller gets `None` today — proven with real records a test writes itself, not a
fabricated "10,000 execution" history. This is the mechanism, not a claim that
self-improvement has happened.

**13 — Industrial deployment.** `plugins/safety_kernel.py::
SafetyKernel.build_deployment_manifest(result, backend_name)` — real manifest
(robot id, backend, the Safety Kernel's actual diagnostic counts, item 2's real
capability claims). `registry/package.py::SkillPackage.export_archive()` gained an
additive, optional `deployment_manifest` param that bundles it into the existing
`.rwsp` archive alongside `metadata.json`/`package_data.json`/`behavior_tree.xml`;
`cmd_export` wires it through. Confirmed round-trips exactly through a real tarball
(`tests/test_deployment_manifest.py`).

**14 — Research extensions — deferred, and why.** SMT/constraint-solver integration
and symbolic execution (no solver dependency exists or is added here); continuous-
time/nonlinear kinematic reachability proofs (same reason, item 10); a formal
versioned RoboIR language spec (a documentation deliverable, not code); incremental
compilation (needs a real dependency/cache-invalidation graph over IR generations
that doesn't exist yet); profile-guided optimization (needs item 6's history to
accumulate over real usage first — the mechanism exists, the data doesn't yet);
deterministic replay from telemetry (needs persisted frames, not just outcome
summaries — a natural item-6 follow-up); live Isaac/Gazebo/Webots digital-twin
execution (needs those engines reachable, which they aren't here — item 4's
`RemoteTwin` is the honest placeholder for when they are).

**Tests added across all 14 items:** `test_roboir_v2.py` (4), `test_plugin_registry.py`
(10), `test_backend.py` (6), `test_digital_twin.py` (4), `test_simulation_validation.py`
(3), `test_execution_memory.py` (4), `test_recovery_planning.py` (6),
`test_cost_model.py` (5), `test_safety_kernel.py` (3), plus RW506/RW507 additions to
`test_optimize_passes.py`/new `test_formal_verification.py` (2+3), `test_robobench.py`
(3), `test_learning.py` (4), `test_deployment_manifest.py` (3) — 232/232 passing
(`python -m pytest tests/ -q`).

**Also noted, not fixed (same treatment as the `_plan_motion`/`handover_target`
findings above):** `fleet/orchestrator.py::deploy_skill_to_fleet()` has a fake
unconditional-success path when `skill_package.skill is None`
(`orchestrator.py:65-67`) — every node gets marked `"EXECUTING"` regardless. Not
touched this round.
