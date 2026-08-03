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

**Written 2026-08-03**, when Phase 2 below was completed. Phases 3–14 are recorded as
they were scoped that day and haven't been started — a future session should treat
each phase's description as a starting brief, not a fixed spec, and re-verify the
codebase state before resuming (this file decays like any other design doc, see
top-level `CLAUDE.md`/session norms on trusting current code over stale memory).

## Maturity scorecard (baseline, 2026-08-03)

Self-assessed against LLVM/MLIR/TVM/TensorRT as a reference point, before Phase 2's
work landed. Re-score after each phase rather than trusting this snapshot.

| Area | Maturity (baseline) |
|---|---|
| Compiler pipeline | 8.5/10 |
| RoboIR | 8/10 → improved by Phase 2 (frozen, pass-managed, diffable) |
| Safety verification | 8.5/10 |
| Runtime execution | 8/10 |
| Runtime recovery | 8.5/10 |
| Multi-robot support | 7.5/10 |
| Backend abstraction | 8/10 |
| Code generation | 8/10 |
| Knowledge layer | 7.5/10 |
| Optimization framework | 4/10 → plumbing added by Phase 2 (OptimizationLevel), zero real passes yet |
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

## Phase 3 — Static Analysis — Not started

Expand `ir/safety.py` beyond its current 6 checks (reachability, workspace/floor,
joint limits, payload, velocity, manipulability/singularity) toward: collision proof,
cycle/deadlock detection over the task graph, execution-graph validation, resource
conflicts, timing analysis, and reachability certificates. Explicitly not:
battery/thermal estimation or cable/tool collision without a real geometry/dynamics
model to back them — this codebase's stated ethos (see `ir/safety.py`'s own
docstring) refuses to check a fabricated value against a real limit.

## Phase 4 — Compiler Optimizations — Not started

The first *real* optimization passes: waypoint merge, trajectory smoothing,
redundant-motion removal, gripper-delay elimination, joint-energy reduction,
payload-aware optimization, motion-cache reuse. Each should report real
before/after metrics (moves removed, time saved, path/energy/joint-travel reduction)
computed from the actual trajectories, not estimated. This is what finally gives
`OptimizationLevel` (Phase 2) something to gate, and `ir/diff.py`'s `diff_trace()`
its first genuinely non-empty diffs.

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
