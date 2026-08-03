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
decision — see Phase 3's writeup). Phases 5–14 are recorded as they were scoped on
2026-08-03 and haven't been started — a future session should treat each phase's
description as a starting brief, not a fixed spec, and re-verify the codebase state
before resuming (this file decays like any other design doc, see top-level
`CLAUDE.md`/session norms on trusting current code over stale memory).

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
| Optimization framework | 4/10 → 6/10: 2 real optimization passes + a motion-plan cache, gated by `OptimizationLevel` for the first time |
| Static analysis | (new row) 5/10: 2 real CompiledSkill checks (RW501/502/505) + 3 real choreography DAG checks (RW601/602/605); collision/dynamics-dependent checks still deferred |
| Formal verification | 3/10 |
| Benchmarking | 2/10 |
| Plugin ecosystem | 3/10 |

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

## Phase 5 — Backend Architecture — Not started

Generalize beyond ROS 2 + simulation: MoveIt, Isaac, Drake, Webots, MuJoCo, CuRobo,
BehaviorTree.CPP, and industrial controller dialects (ABB RAPID, KUKA KRL, URScript,
Fanuc TP) as pluggable lowering targets from RoboIR/CompiledSkill.

## Phase 6 — Runtime Improvements — Not started

Replace `runtime/recovery.py`'s retry-branch model with a recovery *tree*: evaluate
candidate recovery actions by probability of success, cost, and safety, then choose
the best one — recovery becomes planning, not branching. Overlaps with
`docs/REDESIGN.md`'s own Phase 2 (deployment/runtime) — reconcile scope with that doc
before starting.

## Phase 7 — Execution Memory — Not started

Turn `runtime/telemetry.py`'s frame-by-frame logs into queryable experience: skill →
robot → environment → failure → recovery → outcome → confidence. Only after this
exists should the compiler start citing historical success rates as a hint — and only
if genuinely computed from recorded outcomes, never fabricated.

## Phase 8 — Knowledge Graph — Not started

Extend `knowledge/graph.py`/`ontology.py`/`package_nexus.py` from lookup tables toward
a real traversable graph: robot → capabilities → tools → controllers → sensors →
objects → tasks → failures → recoveries → optimizations → benchmarks.

## Phase 9 — Cost Model — Not started

Every compiled plan reports execution time, energy, joint wear, collision risk,
accuracy, payload margin, success probability, manipulator utilization — computed from
real data (trajectories, dynamics where available), enabling multi-objective planning.
Depends on Phase 4 (optimizations) and Phase 7 (execution memory) for real numbers to
report rather than placeholders.

## Phase 10 — Compiler Reports — Not started

A structured compile report per skill: robot, compiler version, IR version, compile
time, safety score, optimization score, simulation result, recovery score, warnings,
diagnostics, certificates. Natural home: `PipelineTrace.to_dict()` (Phase 2) extended
with the cost-model fields from Phase 9 once those exist.

## Phase 11 — Benchmark Suite ("RoboBench") — Not started

The single biggest missing piece per the original assessment: N skills × M robots ×
K simulators, measuring compile/planning/execution latency, optimization gain,
recovery success, collision rate, energy, trajectory quality, determinism, memory.
Without this, every performance claim in this project remains anecdotal.

## Phase 12 — Formal Verification — Not started

Behavior Tree → finite state machine → model checker → proof (no deadlock, no
unreachable state, guaranteed completion, safety invariant holds). Research-grade;
depends on Phase 3's execution-graph validation as a prerequisite.

## Phase 13 — Plugin System — Not started

Discoverable planner/verifier/recovery/backend/knowledge/optimizer/NLU plugins, so
third parties can extend RoboWeaver without modifying the compiler core. Natural to
build once Phase 5 (backend architecture) has more than one or two real backends to
generalize the plugin interface from.

## Phase 14 — Research Features — Not started

SMT/constraint-solver integration for planning under complex constraints, symbolic
execution of RoboIR, multi-objective Pareto-front optimization (needs Phase 9's cost
model), a formal versioned RoboIR language reference, incremental compilation,
profile-guided optimization (needs Phase 7), cross-robot binary compatibility via a
truly embodiment-independent RoboIR, and deterministic replay from telemetry.
