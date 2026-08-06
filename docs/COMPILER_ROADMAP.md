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
bounded payload today, not the full capability as originally described; **updated
again 2026-08-04** for the gap-fix batch — see "Gap fixes + Knowledge Graph +
Dashboard API + Frontend IDE Shell" below — which closed the 4 issues the v2 Vision
section flagged but didn't fix (`_plan_motion` not category-specific, 4 unreachable
skill templates, `fleet/orchestrator.py`'s fake-success path, unvalidated
`handover_target`), replaced the ~13-node demo knowledge graph with real registry
ingestion plus Obsidian export, wired the v2 Vision's backend-only features (pass
traces, cost model, compare, benchmark, knowledge graph) into the dashboard API, and
rebuilt the frontend as a VSCode/Antigravity-style IDE shell. A future session should
treat every "not started"/"deferred" item as a starting brief, not a fixed spec, and
re-verify the codebase state before resuming (this file decays like any other design
doc).

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
| Knowledge layer | 7.5/10 → 8.5/10: real registry-ingested graph (39 nodes/213 edges) replaces the old ~13-node demo graph, plus real multi-hop path + Obsidian export |
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

## Gap fixes + Knowledge Graph + Dashboard API + Frontend IDE Shell — **Done** (2026-08-04)

Closes the 4 issues the v2 Vision section above flagged and explicitly deferred,
replaces the knowledge graph's hand-seeded demo data with real registry ingestion
plus Obsidian export, wires the v2 Vision's backend-only features into the dashboard
API, and rebuilds the frontend shell around them. Same discipline as every phase
above: real, tested, cited-by-file; gaps stated honestly.

**1a — Generalized `_plan_motion` (closes the RW502 finding from Phase 3).**
`optimize/motion_cache.py` rewritten: `compute_motion_primitives(robot_spec,
n_targets)` interpolates `n_targets` real Cartesian waypoints across a fixed
two-phase `APPROACH → WORK → RETRACT` path (renamed from the old fixed 3-pose
scheme for generality), IK-solves each with warm-starting (`seed_q` chained
target-to-target), memoized by `(robot_spec.id, n_targets)`.
`compiler.py::_plan_motion` now iterates every real `TaskType.MOVE_TO` task in the
task graph, calls `compute_motion_primitives(self.robot_spec, len(move_to_tasks))`,
and keys `trajectories`/`ik_results` by each task's real `description` — every
`MOVE_TO` task across every category gets a real entry; RW502 no longer fires
anywhere (`tests/test_plan_motion_generalization.py`, 4 tests). **Same documented
limitation as before, unchanged:** targets are still assumed poses along a fixed
path, not perception-derived — no perception system exists yet (RW201 stays a
warning for the same reason it always has).

**1b — 4 new actions make PALLETIZING/POLISHING/DISASSEMBLY/MOBILE_NAV reachable
(closes the RoboBench finding from v2 item 11).** `types.py::Action` gains
`PALLETIZE`, `POLISH`, `DISASSEMBLE`, `NAVIGATE`; `compiler.py` gains matching
`_ACTION_KEYWORDS`/`_ACTION_DEFAULT_PARAMS`/`_ACTION_DEFAULT_OBJ`/
`ACTION_CATEGORY_MAP` entries; `ir/builder.py` gains matching capability inference
(POLISH → force/torque + compliant control, DISASSEMBLE → force/torque). The
templates themselves (`skills/taxonomy.py`) needed no change — they were real,
just unreachable via natural language. `benchmark/robobench.py`'s docstring and
`_CANONICAL_INSTRUCTIONS` updated to match: **all 17** `IndustrialSkillCategory`
templates are now NL-reachable, not 13 (`tests/test_new_actions_routing.py`, 4
tests; `tests/test_knowledge_graph.py` independently confirms 17 real `SKILL`
graph nodes).

**1c — `fleet/orchestrator.py::deploy_skill_to_fleet()` fake-success path fixed.**
The `else` branch that unconditionally marked every node `"EXECUTING"`/`True` when
there was no compiled skill to retarget now reports the honest outcome:
`status="ERROR"`, `active_skill_id=None`, `results[node.node_id]=False` — same
shape the real branch already used for a genuine `retarget_res.success` failure
(`tests/test_orchestrator.py`, 3 tests).

**1d — Real `handover_target` validation.** Phase 3 found `handover_target` was
write-only and deferred validating it. `fleet/choreography_verification.py` now
checks it for real: `RW603` (error) — `handover_target` names no `robot_id` present
anywhere in the schedule (a genuine typo, not a same-robot edge case). `RW604`
(warning) — `handover_target` names a real robot in the schedule, but no step
assigned to that robot is reachable (via real BFS over `depends_on` edges, same
pattern as the existing cycle-detection) from the handing-off step, i.e. the
handoff has no real downstream continuation. Verified against the pre-existing
`tests/test_multi_robot_choreography.py` pepper→pepper fixture: not RW603 (pepper
is a real robot in that schedule) and not RW604 (a later pepper step genuinely
depends on it) — no regression, plus 4 new cases in
`tests/test_choreography_verification.py`.

**Regression fallout from 1a, fixed honestly, not by weakening assertions:**
`test_verification_pass_flags_dangling_move_to_as_warning` tested the old bug
directly — renamed to `test_verification_pass_no_longer_flags_dangling_move_to`,
now asserts RW502 is empty. `test_deploy_refuses_when_simulation_genuinely_fails`
previously relied on TIGHTEN naturally failing in simulation as a side effect of
the RW502 bug; now that every category compiles and simulates cleanly, the test
constructs a deliberate joint-limit violation (mutates the last trajectory
segment's final waypoint) and its docstring says so plainly instead of implying
the failure is still coincidental. Full suite: 248/248 passing after this batch.

**2 — Knowledge graph: real ingestion + multi-hop path + Obsidian export.**
`knowledge/graph.py` gains `find_path(start_id, end_id, max_hops=6)` — real BFS,
undirected. `knowledge/ingest_registry.py` (new): `build_graph_from_registry()`
replaces the old ~13-node hand-seeded demo graph
(`create_default_robotics_knowledge_graph`) with real nodes/edges from the live
registries — one `ROBOT` node per distinct `RobotSpec` in `ROBOT_REGISTRY` (11),
one `PACKAGE` node per `RoboticsPackageNexus.PACKAGE_CATALOG` entry (11) with real
`COMPATIBLE_WITH` edges to the robots its own `compatible_robots` list actually
names, one `SKILL` node per NL-reachable `IndustrialSkillCategory` (17, after 1b)
with a `SUITABLE_FOR` edge gated on `has_force_torque_sensor` for skills that
really need it (verified: `TIGHTEN_BOLT` connects to every force/torque-capable
robot and explicitly not to `temi`, which has none) — 39 nodes, 213 edges total,
verified live. `knowledge/obsidian_export.py` (new): `export_to_obsidian()` writes
one real `.md` file per node with a properties table and a `## Links` section using
Obsidian `[[wikilink|display name]]` syntax for every real outgoing edge — every
link resolves to a real other file in the output directory (verified by regex-
scanning every exported file's links against the real file list, not just spot-
checked). CLI: `roboweaver graph build|path|export-obsidian`. Tests:
`tests/test_knowledge_graph.py`, 6 tests.

**3 — Dashboard API extensions (`dashboard/server.py`).** Wires the v2 Vision's
backend-only features into the dashboard, additive-only (no existing response
shape changed): `GET /api/compile?explain_passes=1` adds the real
`pipeline`/`skill_pipeline` traces (`PipelineTrace.to_dict()`/
`SkillPipelineTrace.to_dict()`, both real since Phase 2/4) to the existing
response. `GET /api/cost?instruction=&robot=` → `optimize/cost_model.py::
compute_cost()`'s real `CompiledSkillCost`. `GET /api/compare?instruction=&robots=`
→ `compare_robots()`'s real weighted ranking + Pareto-optimal subset + honest
`skipped` reasons. `GET /api/benchmark?robots=` → `run_benchmark()`'s real report
(small default subset — `franka_panda`/`ur5e`/`kuka_iiwa` — to keep a live
dashboard call fast; the CLI's `roboweaver benchmark` is where the full matrix
runs). `GET /api/graph` and `GET /api/graph/path?from=&to=` → the real ingested
knowledge graph and BFS path from item 2 (replaces the old demo-graph response the
`/api/knowledge` route served). Verified live: server started, every new route
curled against the real running process — real 39-node/213-edge graph, a real
3-hop path, real cost/compare/benchmark numbers, `explain_passes=1` returning real
pass records. `frontend/src/types/index.ts` gained matching TypeScript types
(`PipelineTraceResult`, `CompiledSkillCostResult`, `RobotComparisonResult`,
`BenchmarkReportResult`, `KnowledgeGraphResult`, `GraphPathResult`) mirroring the
real Python response shapes field-for-field; `frontend/src/lib/api.ts` gained
matching fetch methods (`cost`, `compare`, `benchmark`, `graph`, `graphPath`, and
`compile(...)` gained an `explainPasses` flag) using the same
timeout/error-handling conventions as the existing ones. `npx tsc --noEmit` clean.

**4 — Frontend IDE-shell rebuild.** Restructures the app's layout around a
VSCode/Antigravity-style shell; the established "Cyberpunk-Neon" visual identity
and the separate Iron-Man 3D-model palette are both left untouched — this is a
structural change, not a re-theme. New `frontend/src/components/ide/`:
`TabsContext.tsx` (a `TabType`-keyed open/active-tab model — each view is a
singleton tab, opening an already-open one just focuses it, since the views
re-fetch their own data on mount and have no per-instance identity to multiplex);
`tabMeta.ts` (single source of truth for tab icon/label, replacing the old
`Sidebar.tsx`'s own hardcoded copy); `ActivityBar.tsx` (the old `Sidebar.tsx`'s nine
real nav destinations narrowed to an icon-only strip, plus an Explorer-visibility
toggle); `ExplorerPanel.tsx` (a file-tree-style browser over the exact same real
data the full-page views already fetch — Robots from `/api/robots`, Skills from the
new `/api/graph`'s real `SKILL` nodes, Knowledge from `/api/nexus/packages`,
Discovered from `/api/discover` — grouped as collapsible sections instead of a
page-sized grid; clicking a leaf opens the corresponding tab); `TabStrip.tsx`
(closable VSCode-style tab pills, at least one always stays open);
`TerminalPanel.tsx` (the one genuinely new interaction: a collapsible,
drag-resizable bottom panel with three buttons — compile trace, compare, benchmark
— each triggering one real call to item 3's dashboard endpoints and rendering the
real response as a monospace, severity-colored feed; explicitly **not** a PTY or an
interactive shell, stated in its own file comment, no arbitrary command input
exists); `StatusBar.tsx` (real connection status, real registered-robot count,
real open-tab count). `app/page.tsx` restructured to compose
`ActivityBar + ExplorerPanel + (TabStrip + main + TerminalPanel) + StatusBar`
instead of the old `Sidebar + TopBar + single active view`; every existing view
(`CompilerView`, `WorkcellBuilderView`, `KnowledgeNexusView`, `FleetRegistryView`,
`RobotConnectView`, `LiveSimulationView`) is reused unchanged as tab content — none
of them were rewritten. `Sidebar.tsx`/`TopBar.tsx` deleted (confirmed unreferenced
by `grep` before removal) rather than left as dead code.
**Verified in a real browser, not just typechecked:** `npm run dev` +
`roboweaver dashboard --port 8080` started for real; driven end-to-end with
Playwright (already a devDependency, previously unused) against a real Chromium —
opened 4 tabs simultaneously (Overview, Compiler, Fleet Registry, Knowledge Nexus),
triggered a real `explain_passes=1` compile and a real benchmark from the Terminal
panel and confirmed the real pass records / RW201 warnings / `51/51 cells compiled
clean` benchmark line rendered with correct severity coloring, closed a tab,
collapsed the Explorer panel, and opened the Digital Twin tab to confirm the
three.js viewport still renders unchanged inside the new tab context — zero
console/page errors across the whole run. `npx tsc --noEmit` and `npm run lint`
both clean.

**Tests added:** `tests/test_plan_motion_generalization.py` (4),
`tests/test_new_actions_routing.py` (4), `tests/test_orchestrator.py` (3),
`tests/test_knowledge_graph.py` (6), plus 4 new cases in
`tests/test_choreography_verification.py` and regression fixes across
`tests/test_optimize_passes.py`/`tests/test_simulation_validation.py` — 254/254
passing (`python -m pytest tests/ -q`). No new automated frontend tests (matches
the existing project convention — Playwright was used here as a one-off manual-
verification driver, not wired into CI).

## UI fidelity fixes, dashboard hardening, Obsidian graph frontend, graph-driven compilation — **Done** (2026-08-04)

Four follow-up batches, each triggered by direct user feedback rather than
self-scoped, and each verified live (real browser via Playwright, real curl
against a live server, or both) rather than by inspection alone.

**1 — UI fidelity ("why does everything look fake").** The IDE shell's default
views were empty until a user acted (`CompilerView`/`WorkcellBuilderView` now
auto-run their default example on mount); the Terminal panel defaulted open
and empty, eating ~240px on every tab (now defaults collapsed); the Overview
KPI card hardcoded the literal string `'RH56F1-E2'` and visibly clipped (now
matches the other cards' real `apiOnline`-derived Ready/Offline state); and
the Digital Twin's Inspire Hand/TurtleBot 4 viewport was a hand-rolled
canvas-2D perspective projection (`Robotic3DViewport.tsx`, deleted) whose
"Wireframe" toggle set state nobody read. Replaced with real three.js
(`DigitalTwinViewport.tsx`, `robot3d/InspireHandMesh.tsx`,
`robot3d/TurtleBotMesh.tsx`) using the same OrbitControls/lighting/auto-fit
rig already proven for the Franka CAD mesh — segment lengths from each
robot's real `RobotSpec.links`, finger bend still driven by real
`InspireHandSimulator` telemetry, Wireframe now a real per-mesh material
property threaded through every part.

**2 — Dashboard hardening.** The API bound to all interfaces
(`server_address = ("", port)`) with a wildcard `Access-Control-Allow-Origin:
*`. Bound to `127.0.0.1` by default now (`--host 0.0.0.0` is the explicit,
warned opt-in); an Origin allow-list (`_ALLOWED_ORIGIN_RE`, any
`http(s)://localhost|127.0.0.1|[::1]` port) rejects a disallowed request with
`403` in `do_GET()` *before* any handler runs — real, because CORS response
headers alone don't stop a cross-origin `fetch()` from firing, only from
being *read*, so the old wildcard let any open webpage silently trigger a
real side effect like `POST /api/connect`. `DashboardHTTPRequestHandler.timeout =
60` bounds a stalled socket; instruction/prompt params capped at 2000 chars,
robot-list params at 20. `tests/test_dashboard_hardening.py` (8 tests) spins
up the real server on an ephemeral port.

**3 — Real Obsidian knowledge graph, in the frontend.** The graph existed but
had no frontend consumer. `GET /api/graph/export-obsidian` streams the same
real vault `roboweaver graph export-obsidian` writes to disk, zipped
server-side into a temp dir. `KnowledgeGraphView.tsx` (new `graph` tab) is a
real `d3-force` simulation over `/api/graph`'s real response — drag, zoom,
search-highlight, click a node for its real properties, or run the real
`/api/graph/path` BFS between two clicked nodes. Node/edge counts (39/213)
and the force layout were verified live; labels are hidden below a zoom/hover/
selection threshold specifically because a 39-node, 213-edge hub-heavy graph
(a no-sensor-requirement skill connects to all 11 robots) turned out
genuinely illegible with every label always on — a real, empirically-found
UX bug, not a design guess.

**4 — The knowledge graph actually influencing compilation.** Direct response
to review feedback that the graph "acts more like documentation" — it should
"actively influence... capability selection." `SkillCompiler.classify_category()`
(new, public) exposes the exact real classification `compile()` itself routes
through (`_parse_intent()` + `ACTION_CATEGORY_MAP`), robot-independent, without
duplicating the keyword-scoring logic or requiring a full compile.
`knowledge/ingest_registry.py::suggest_robots_for_instruction()` uses it to
look up the instruction's real skill node and return every robot id the
graph's own `SUITABLE_FOR` edges connect to it — the same real force/torque
gate the graph already enforces elsewhere, read, not re-derived.
`optimize/cost_model.py::compare_robots()`'s `robot_ids` is now `| None`:
omitted, it calls the graph lookup instead of requiring the caller to already
know which robots are candidates, and `RobotComparison.candidate_source`
(`"explicit"` vs `"knowledge_graph"`) reports which happened so no caller can
present a graph-derived guess as a user choice. Wired through
`roboweaver compare INSTRUCTION` (`--robots` now optional) and
`GET /api/compare` (`robots` param now optional) — both verified live.
**A real, non-obvious result surfaced immediately**: for `"Tighten the M8
bolt"`, the graph correctly proposes `shadow_hand`/`robotiq_hand` as
candidates (they declare `has_force_torque_sensor=True`), but both genuinely
fail to compile (`skipped`, real IK non-convergence) — the graph narrows
candidates on a coarse, real signal; the compiler's simulation-grounded
compile step remains the actual authority on whether a candidate works. This
is the intended architecture, not a bug: the graph informs, it doesn't
override verification. **Deliberately not touched**: `package_nexus.py::
recommend_stack_for_prompt()` (the Knowledge Nexus "Architecture recommender")
stays keyword-matched — reworking its scenario-specific heuristics
(`"shopmate"`, `"retail"`, ...) onto generic graph traversal is a
larger, separate redesign, and the UI already honestly labels it
"keyword-matched, not ML-based" rather than overclaiming.

**Tests added:** `tests/test_dashboard_hardening.py` (8),
`tests/test_graph_driven_compilation.py` (4), plus 2 new cases in
`tests/test_cost_model.py` — 268/268 passing (`python -m pytest tests/ -q`).

## Compiler Studio: frontend rebuilt around the pipeline, not files — **Done** (2026-08-05)

External review feedback (independent of the graph-driven-compilation ask above)
argued the IDE-shell frontend undermines RoboWeaver's own identity — a robotics
*compiler* presented as a VSCode-style file-navigation tool (Activity Bar, Explorer
tree, multi-tab strip, Terminal drawer). Full detail in
[`ARCHITECTURE.md`](ARCHITECTURE.md)'s "Frontend — Compiler Studio, Not an IDE"
section; summarized here for the change log.

**Deleted:** `frontend/src/components/ide/` in full (`ActivityBar.tsx`,
`ExplorerPanel.tsx`, `StatusBar.tsx`, `TabStrip.tsx`, `TabsContext.tsx`,
`tabMeta.ts`, `TerminalPanel.tsx`) — the shell chrome and its multi-tab-open state
model.

**New navigation:** `components/nav/TopNav.tsx` — a horizontal bar with
Compile/Compare/Workcell/Benchmark rendered as a connected pipeline sequence, plus
Overview/Robots/Digital Twin/Knowledge Graph/Packages/Connect/Settings as a plain
destination list. Single active view (`useState`), no new state-management
dependency — proportionate to 11 views, each already fetching its own data.

**Two genuinely new real features**, grounded by reading `ir/diff.py` directly before
building anything (its own docstring, and `cli/main.py::cmd_diff()`'s, both already
say per-pass diffing shows "no differences" for almost every real compile today,
since the three registered RoboIR passes are diagnostics-only — building the diff
viewer around that would have been honest but empty):

1. **`components/PipelineTraceView.tsx`** — the compile pipeline made visible.
   `/api/compile?explain_passes=1`'s real per-pass timing/modified/skipped/
   diagnostics/metrics (real since Phase 2, previously only a Terminal-panel text
   feed) rendered as a real horizontal flow with timing bars and metric chips.
   Zero new backend work — presentation only.
2. **Real cross-robot RoboIR diff.** New `GET /api/diff?instruction=&robot=&robot2=`
   in `dashboard/server.py`, mirroring `cli/main.py::cmd_diff()`'s `--robot2` path
   exactly (`ir/diff.py::diff_ir()`), same Origin-check/input-cap hardening as every
   other route. `components/RoboIRDiffView.tsx` renders real `field_changes`/
   `objects_added`/`objects_removed` — the godbolt.org-style "one instruction,
   compare targets" moment, e.g. `franka_panda → ur5e` on "Pick up the red cube"
   shows a real `execution.dof: 7 → 6`. New `components/CompareView.tsx` composes
   this with the existing `compare_robots()` ranking (previously only reachable via
   the deleted Terminal panel) as a first-class page.

**New `components/BenchmarkView.tsx`** — RoboBench as a real sortable table
(click any column header) instead of Terminal text; no charting dependency added.

**Reused as-is, re-homed not rewritten** (real, tested, no dependency on the old
shell): `DigitalTwinViewport.tsx`, `robot3d/InspireHandMesh.tsx`,
`robot3d/TurtleBotMesh.tsx`, `Robot3DModel.tsx`, `FrankaMeshModel.tsx`,
`KnowledgeGraphView.tsx`, `FleetRegistryView.tsx`, `RobotConnectView.tsx`,
`WorkcellBuilderView.tsx`, `KnowledgeNexusView.tsx`. `CompilerView.tsx` kept its real
RoboIR/BT-XML rendering; its diagnostics-list-only view is now preceded by
`PipelineTraceView` as the page's centerpiece.

**Explicitly deferred, not built this round** (named, not silently dropped): React
Flow/Cytoscape-based non-linear pipeline visualization (today's pipeline is linear);
Framer Motion transitions; a Monaco editor for instruction/RoboIR editing; ECharts
benchmark history; Zustand/TanStack Query global state; an Execution Memory timeline;
trajectory replay/velocity/acceleration visualization in the Digital Twin.

**Verified live:** `npx tsc --noEmit` and `npm run lint` clean; every nav destination
driven via Playwright against a real `npm run dev` + `roboweaver dashboard` — a real
compile showing real pass cards, a real graph-derived compare (including two robots
that pass the graph's coarse capability gate but genuinely fail to compile,
correctly shown as `skipped`), a real cross-robot diff, Digital Twin/Knowledge
Graph/Fleet/Connect all working unchanged in their new home — zero console errors.
Fresh screenshots and a re-recorded demo GIF against the new UI (`docs/media/`).

**Tests added:** `tests/test_dashboard_diff_route.py` (4, real `/api/diff` against a
live server) — 272/272 passing (`python -m pytest tests/ -q`).
