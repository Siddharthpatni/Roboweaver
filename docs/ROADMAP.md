# What's Real, and What's Still Open

The condensed version. For file-and-test-cited detail behind every line here, see
[`COMPILER_ROADMAP.md`](COMPILER_ROADMAP.md) (the living source of truth this file
summarizes) and [`REDESIGN.md`](REDESIGN.md) (the original Phase 1 build record).

## What's Real Today

**The MVP core (single robot, nine stages) — done:**

```
01 Knowledge → 02 Task Understanding → 03 RoboIR → 04 Skill Compiler
→ 05 Motion Planner → 06 Behavior Tree → 07 Simulation → 08 Package → 09 Dashboard
```

```bash
roboweaver compile "Pick the red cube and place it into the blue bin" --verbose
```

RoboIR → Behavior Tree → trajectory → native/MuJoCo simulation (real telemetry
recording and failure recovery) → `.rwsp` skill package. Full account, cited by file:
[`REDESIGN.md` §11](REDESIGN.md#11-what-actually-got-built-phase-1).

**Everything built on top of that core** — every item below is real, tested, and cited
by file in [`COMPILER_ROADMAP.md`](COMPILER_ROADMAP.md); only the headline is repeated
here:

- **A real Pass Manager** (`ir/pass_manager.py`, `optimize/pass_manager.py`) — LLVM/MLIR-
  style: an ordered list of passes over immutable, frozen (SSA-style) IR/skill
  generations, each pass timed by the manager itself (not self-reported), producing a
  full `PipelineTrace` inspectable via `roboweaver compile --explain-passes` or
  `/api/compile?explain_passes=1`.
- **Real static analysis and optimization passes** — `CompiledSkillVerificationPass`
  (RW501/RW502/RW505), choreography DAG checks (RW601–RW605, cycle detection, resource
  conflicts, dangling/unreachable handoffs), `WaypointDecimationPass` (up to ~83%
  trajectory compression, self-verified against the real velocity-limit safety check),
  `RedundantSegmentElisionPass`.
- **A real plugin/backend framework** — `PluginRegistry`, `RobotBackend` ABC,
  `Ros2Backend`/`UrScriptBackend`.
- **A real digital twin interface** — `DigitalTwin` ABC; `NativeTwin` wraps the real
  `SkillRuntime` (kinematics, grasp physics, telemetry); `RemoteTwin` is an honest
  TCP-reachability probe that explicitly reports "no real physics ran" rather than
  fabricating an Isaac/Gazebo/Webots result.
- **Real execution memory and case-based recovery** — `ExecutionMemoryStore` (opt-in,
  JSONL-persisted, `None` — never a fabricated `0.0` — when no history exists);
  `RecoveryEngine` scores declared-prior recovery candidates and boosts them with real
  historical success rates once real data accumulates.
- **A real multi-objective cost model, now graph-aware** — `CompiledSkillCost` (cycle
  time, payload margin, joint travel, manipulability margin), a real Pareto-dominance
  filter, `roboweaver compare INSTRUCTION [--robots a,b,c]` / `/api/compare` — omit
  `--robots` and the real knowledge graph supplies candidates instead.
- **A real (mandatory, defense-in-depth) safety kernel** at the `RobotBackend.deploy()`
  boundary, and **real bounded formal verification** — BT well-formedness (RW506) and a
  declared-forbidden-joint-zone check (RW507) — explicitly not an SMT/temporal-logic
  proof, stated as such.
- **RoboBench** — a real compile-pipeline benchmark (latency, diagnostics, waypoint
  reduction) over every distinct registered robot × all 17 NL-reachable skill
  categories. `roboweaver benchmark` / `/api/benchmark`.
- **A real, generalized motion planner** — every `MOVE_TO` task in every skill category
  gets a real, IK-solved trajectory keyed by its own task description (previously only
  the pick/place category did; RW502 no longer fires anywhere).
- **All 17 industrial/service skill categories are NL-reachable** — PALLETIZING,
  POLISHING, DISASSEMBLY, and MOBILE_NAV were real templates with no route from natural
  language until this batch; now they are.
- **A real knowledge graph that influences compilation** — registry-ingested (not
  seeded demo data), real multi-hop BFS pathfinding, real Obsidian markdown export, a
  real force-directed graph view in the frontend, and a real input to candidate-robot
  selection in `compare_robots()` (see `ARCHITECTURE.md`).
- **A hardened, localhost-only dashboard API** — binds `127.0.0.1` by default, a real
  Origin allow-list (not wildcard CORS), a socket timeout, capped input sizes.
- **A pipeline-first Compiler Studio frontend** — real per-pass flow visualization
  (`/api/compile?explain_passes=1` rendered as a real flow, not a text feed), a real
  cross-robot RoboIR diff view (`/api/diff`), and a real three.js digital twin.
  Replaced an earlier VSCode/Antigravity-style IDE shell (Activity Bar/Explorer
  tree/tab strip/Terminal drawer) that read as a generic file-navigation tool rather
  than a compiler.

## Genuinely Still Open

In the order it makes sense to tackle them:

1. **Perception.** No perception system exists; every object pose is a disclosed,
   assumed default (`RW201`). This is the single biggest gap standing between today's
   compiler and a skill that runs on a real, unstructured scene.
2. **RoboIR as a computational graph, not just a job description.** `task_summary`/
   `motion_summary` are real but read-only reflections of the task graph; the graph
   itself still lives on `CompiledSkill`, not inside RoboIR. Folding it in — so
   optimization passes rewrite RoboIR directly — is real architectural work, not done.
3. **Motion planning as a real pass.** Currently a distinct call from `compiler.py`
   before the Pass Manager runs, not an `IKPass`/`TrajectoryPass` inside it — real
   either way, but not yet inspectable via `--explain-passes` like the rest of the
   pipeline.
4. **More genuine optimization passes**, not just validators/compressors — a
   motion-fusion pass and a nearest-neighbor task-reordering pass are the two most
   concretely scoped candidates.
5. **Multi-robot scheduling.** Choreography *validation* (cycle detection, resource
   conflicts) is real; there's no scheduler that actively chooses tiering/ordering to
   optimize a multi-robot plan, only one that checks a given plan is valid.
6. **Research-grade verification.** An SMT/temporal-logic proof of a continuous-time
   safety property — needs a solver dependency (e.g. `z3-solver`) not added here
   without a deliberate decision, and nonlinear real arithmetic over trigonometric
   forward kinematics. Today's formal verification is real but bounded/discrete.
7. **Live simulator integration.** `RemoteTwin` is the honest placeholder for
   Isaac/Gazebo/Webots — real when those engines are reachable, which they aren't in
   this environment. This is the honest path to real robot/simulator experiments, not
   claiming ones that didn't happen.
8. **Profile-guided optimization and deterministic replay**, once real execution
   history (execution memory, above) has actually accumulated from real usage — the
   mechanism exists, the data doesn't yet.
9. **An LLM-backed Task Understanding backend**, strictly additive to the deterministic
   default, never a silent replacement for it.

Multi-tenant auth, a skill marketplace, and mobile clients remain explicitly out of
scope — see [`REDESIGN.md` §9](REDESIGN.md#9-roadmap).

**Explicitly not planned as "credibility fixes":** buying physical robot hardware or
running a project comparison against MoveIt/BT.CPP/Task Constructor/OpenRAVE/Tesseract
purely to look more established. RoboBench measures RoboWeaver's own compile pipeline
and doesn't attempt those libraries' job (continuous motion planning, a mature BT
runtime) — a fair comparison would need to run this project's compiler output *through*
some of them, which is closer to item 7 above than a new benchmark. See
[`BENCHMARKS.md`](BENCHMARKS.md).
