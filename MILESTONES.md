# RoboWeaver Milestones and Future Plan

**Last updated:** 2026-08-07
**Current release:** 0.1.0
**RoboIR version:** 0.2.0
**Status:** active development; compiler and generated artifacts are tested, physical
robot certification is not claimed.

This is the single live status document for RoboWeaver. It records what is real now,
the evidence behind each claim, current limitations, recent changes, and future work.
Historical design detail remains in `docs/`, but milestone status should be updated
here first whenever implementation or verification changes.

## Status Rules

| Label | Meaning |
|---|---|
| **Verified** | Implemented and covered by an automated test, build, or measured runtime check. |
| **Implemented** | Present in code, but its full external environment is not available in local CI. |
| **Partial** | A bounded subset works and the unsupported portion is stated explicitly. |
| **Planned** | No production claim; implementation and acceptance evidence are still required. |
| **Blocked externally** | Code may exist, but hardware, credentials, simulator, or another external dependency is unavailable. |

No item should be marked **Verified** merely because code exists or a README says it
works. Record the test, build, hardware log, or other reproducible evidence.

## Current Verified Snapshot

Measured on Python 3.12.13 and Node.js 22 tooling on 2026-08-07:

- **450 tests passed, 1 skipped, and 5 subtests passed.**
- **78.57% branch-aware Python coverage**, with a **75% CI floor**.
- Ruff/Pyflakes, Python compilation, dependency consistency, and CI YAML checks pass.
- Frontend ESLint, strict TypeScript checking, and the Next.js production build pass.
- `pip-audit` and `npm audit` report no known dependency vulnerabilities.
- Bandit reports no medium/high-severity Python findings.
- The Python source distribution and wheel build successfully.
- Generated ROS 2 packages are wheel-built in tests.
- CI contains a ROS 2 Humble job that generates a package and runs `colcon build`.
  This Linux/ROS job is configured for GitHub CI; it was not locally executed on the
  macOS development machine.
- Production Chromium acceptance passes at 1440×900 (13-inch MacBook class),
  2560×1440 (32-inch QHD), and 3840×2160 (32-inch 4K). It visits 12 workspaces,
  rejects horizontal overflow/browser exceptions, starts the real Python backend,
  compiles through the UI, creates a bounded climbing-monkey research package with AI
  disabled, and records per-view/result screenshots at every profile.
- The isolated research image built and ran locally with no network, read-only root,
  all capabilities dropped, no devices, and PID/memory/CPU limits. It validated a
  9-link/8-joint URDF plus Python scaffold and explicitly reported that physics did not run.
- Research evaluation v1 passed 6/6 metrics locally: 4/4 expected compile outcomes,
  exact RW102 precision/recall, one IR digest across three runs, three accepted arm
  targets from one source, NativeTwin lift success, and 78.43% O1 waypoint reduction.
- CI now contains a ROS 2 Jazzy/Gazebo Harmonic headless spawn-and-inspect job and a
  machine-readable research-evaluation artifact job. Neither is public evidence until
  the worktree is pushed and the GitHub-hosted jobs complete.
- A live production LAN-mode run returned compiler access, blocked hardware control,
  completed a real compile, denied discovery with HTTP 403, and denied an untrusted
  Host header with HTTP 421.
- Native `mlir-opt` is not installed on the local macOS machine. CI now installs
  Ubuntu's `mlir-18-tools` and requires a real upstream canonicalize/CSE run before
  containers can publish; that CI result becomes public evidence only after push.

Primary verification commands:

```bash
python -m pytest tests/ -q \
  --cov=roboweaver --cov-branch --cov-report=term-missing --cov-fail-under=75
python -m ruff check src tests scripts --select C901,F
python -m compileall -q src tests scripts
python -m pip check
python -m build --no-isolation

cd frontend
npm run lint
npm run typecheck
npm run build
ROBOWEAVER_VISUAL_REQUIRE_COMPILER=1 npm run test:visual  # backend must be running
npm audit --audit-level=high
```

## Capability Matrix: What Is Real Now

| Area | Status | Current implementation and boundary |
|---|---|---|
| Target-independent frontend | **Verified** | Natural-language source is parsed once into a portable semantic program without reading a target `RobotSpec`. The deterministic scored parser is the default; Ollama is opt-in. |
| Robot profile contracts | **Verified, bounded** | 12 distinct built-in profiles plus validated caller-provided `RobotSpec` instances. Profiles declare one of five validated motion models, optional kinematic chains, motion parameters, collision radius, and legal operation sets. |
| Language/task coverage | **Verified, bounded** | 18 natural-language actions route into 17 industrial/service categories. Complete keyword boundaries prevent substring matches, and unknown source actions fail closed as RW101. This is deterministic taxonomy routing, not unrestricted language understanding. |
| Complete RoboIR | **Verified** | Frozen RoboIR 0.2.0 contains source provenance, objects, capabilities, constraints, complete `ProgramSpec`, recursive behavior, exact target `LoweringSpec`, IK evidence, joints, trajectories, and summaries. |
| Deep IR immutability | **Verified** | Top-level and nested sequences/mappings reject mutation. Passes must produce new generations. |
| Multi-target compilation | **Verified** | One portable source program is independently planned and verified against each concrete target. One target failure does not invalidate accepted lowerings. |
| Motion planning | **Verified, bounded** | A real full-conversion engine declares legal/illegal operations, applies ordered rewrite patterns, fails unresolved operations, and dispatches discoverable serial-arm, holonomic-base, differential-drive, branched-humanoid, and multi-finger plugins. Plans/IR record every legalization rewrite; orientation and dynamics remain open. |
| Pass infrastructure | **Verified** | Ordered RoboIR and `CompiledSkill` pass managers record timing, metrics, diagnostics, snapshots, and optimization levels. RoboIR passes now use lazy analysis caching plus explicit preserved-analysis declarations and invalidation, adapted from LLVM's new pass-manager semantics. |
| Upstream compiler execution | **Implemented; CI gate configured** | RoboIR emits valid unregistered-dialect MLIR. In auto/required mode a bounded subprocess executes upstream `mlir-opt` canonicalize+CSE with a minimal environment and records executable, version, pipeline, and input/output SHA-256. Local status truthfully says unavailable; Ubuntu CI installs `mlir-18-tools` and requires success. This is not LLVM machine-code generation. |
| Compiler plugins | **Verified** | The active target-lowering dispatcher uses a typed Input/Transformation/Output phase registry with deterministic priority and `roboweaver.motion_lowerers` entry-point discovery, adapting RoboticsLanguage's composition model without vendoring or claiming source-level integration. |
| Optimization | **Verified, bounded** | Waypoint decimation and redundant-segment elision run with verify-before/after checks. This is not a broad LLVM optimization catalog. |
| Capability diagnostics | **Verified** | RW1xx–RW6xx diagnostics reject unsupported capabilities and malformed or unsafe programs. Perception gaps are warnings; safety and required sensing failures are blocking. |
| Perception provenance | **Verified, bounded** | Assumed, user-specified, and measured poses are distinguished. Typed external observations validate object id/class, frame, timestamp freshness, confidence, finite XYZ, provider, and calibration before compilation; invalid configured input fails closed. A camera detector is not bundled. |
| Safety kernel | **Verified, bounded** | Deployment revalidates the exact RoboIR, target profile, capability contract, joint/workspace/floor/payload/velocity checks, and generated manifest hash. This is not safety certification. |
| Collision and formal checks | **Verified, bounded** | Behavior-tree/forbidden-range checks run automatically. With a typed Scene, the final pass checks every emitted waypoint using sampled link capsules or inflated mobile footprints, performs deterministic bounded replanning, records the scene digest, and fails as RW307 when no verified route exists. No self-collision, SMT, temporal-logic, or continuous-time proof is claimed. |
| Native simulation | **Verified, bounded** | Complete RoboIR is adapted into the legacy runtime view and executed through the native twin. PICK has a modeled process outcome; other processes report unsupported status rather than false success. |
| External simulation | **Partial / blocked externally** | Remote twin connectivity is truthful, but Isaac, Gazebo, Webots, and similar physics engines are not integrated or exercised here. |
| Research experiment sandbox | **Verified, bounded** | Open-ended prompts become a validated connected-tree morphology, deterministic URDF, and deterministic training-adapter scaffold. A hardened no-network/no-device Docker run passed locally. Model-authored code is never executed; no Gazebo/MuJoCo physics or training outcome is claimed. |
| Model cascade and observability | **Verified, bounded** | At most three explicit attempts route Ollama → configured Gemini → configured OpenRouter. Exact TTL cache hits re-run validation. Sentinel-inspired traces retain provider/model/latency/token/error metadata but no prompts, responses, keys, or target addresses. This is an original in-process implementation, not Sentinel's complete gateway. |
| Research evaluation | **Verified locally; CI artifact configured** | Versioned harness measures expected compilation outcomes, diagnostic precision/recall, three-run IR determinism, target portability, modeled NativeTwin correctness, and an internal O0/O1 planning baseline. External MoveIt/baseline comparison and independent reproduction remain open. |
| Gazebo acceptance | **Implemented; public CI pending** | Jazzy/Harmonic CI generates a compiler-derived URDF, validates it with `check_urdf`, starts headless Gazebo, spawns the model through `ros_gz_sim`, and inspects its joints with `gz model`. Gazebo is unavailable on this macOS workspace, so no local simulator result is claimed. |
| ROS 2 backend | **Verified** | RoboIR-only generation of a complete `ament_python` package with exact joints, waypoints, controller client, launch/config files, BehaviorTree XML, and manifest. Generated packages are wheel-tested and CI is configured for Humble `colcon`. |
| URScript backend | **Verified, target-gated** | RoboIR-only URScript generation is available only for validated Universal Robots profiles. Other profiles are rejected instead of receiving misleading output. |
| BehaviorTree XML | **Verified** | Production dashboard and `.rwsp` export paths generate XML from complete RoboIR. Legacy `CompiledSkill` export remains only for backward-compatible callers without RoboIR. |
| Downloadable artifacts | **Verified** | The dashboard API returns reproducible ROS package ZIPs or target-gated URScript files. |
| Connection adapter generation | **Verified** | The dashboard generates a deterministic Python no-motion connection probe from a validated registry profile and real bridge protocol. Target URI is supplied at runtime and is not embedded in model review prompts. |
| Ollama connection assistance | **Verified, optional** | Local endpoint identification and additive adapter review use the centralized Ollama manager. Provider failure never removes deterministic generated code. |
| OpenRouter connection assistance | **Verified, optional** | Explicit opt-in OpenRouter client, code-focused free primary with free-router fallback, bounded responses, server-only key, cloud privacy notice, model-output validation, deterministic fakes, and a live container request are verified. |
| Deployment manifests | **Verified** | Manifests include canonical RoboIR, SHA-256 digest, robot/backend identity, capability claims, diagnostics, and explicit collision/safety status. |
| Physical deployment/HIL gate | **Verified in software; hardware blocked** | Physical protocols cannot bypass simulation. The guarded HIL runner rejects simulation bridges, requires explicit operator confirmation and live safety I/O, validates limits, acknowledgement, changed/tracking feedback, and emits hash-linked evidence only after success. No physical run or certification evidence exists. |
| Responsive dashboard | **Verified at representative viewports** | Fluid layouts, mobile navigation, compiler stages, target matrix, artifact controls, and evidence ledger pass production Chromium at 1440×900, 2560×1440, and 3840×2160. The browser also completes a real compile through the Python backend at every profile. |
| Security/operations | **Verified in CI/local checks** | Loopback/private backend, token-required remote bind, Origin allow-list, bounded requests, constant-time token comparison, private-IP/Host validation, compiler-only LAN policy, server-only token, non-root hardened containers, audits, Bandit, and CodeQL coverage. |

## Completed Milestones

### M0 — Deterministic Compiler Foundation — Verified

- Deterministic intent parser with confidence and explicit fallback warnings.
- Industrial task templates and behavior programs.
- N-DOF robot specification, serial-chain kinematics/IK, trajectories, and runtime execution.
- Local AI remains an optional sidecar and never a required compile dependency.

Evidence: `src/roboweaver/compiler.py`, `src/roboweaver/types.py`,
`src/roboweaver/skills/taxonomy.py`, and compiler/routing tests.

### M1 — Complete RoboIR and Compiler Passes — Verified

- RoboIR upgraded from summaries to a complete semantic and lowered representation.
- `ProgramSpec` stores parameters, ordered tasks, warnings, confidence, and behavior.
- `LoweringSpec` stores target identity, joint names, IK solutions, and trajectories.
- Deeply immutable nested IR values and generation-based pass execution.
- Structural verification checks program/lowering consistency and finite dimensions.

Evidence: `src/roboweaver/ir/schema.py`, `builder.py`, `passes.py`,
`tests/test_pass_manager.py`, and `tests/test_roboir_v2.py`.

### M2 — Universal Target-Independent Compilation — Verified

- Portable frontend executes once without target-specific semantics.
- The same source digest and semantic program are reused across concrete targets.
- Every target performs independent IK, trajectory generation, capability checks,
  safety checks, and artifact lowering.
- Valid custom `RobotSpec` instances work without registry or vendor-specific code.
- Invalid external specifications fail at the compiler boundary.

Evidence: `tests/test_universal_compilation.py`, `tests/test_motion_semantics.py`,
and the `/api/compile-matrix` route.

### M3 — RoboIR-Only Runtime and Backends — Verified

- Safety, simulation validation, ROS 2, URScript, BehaviorTree XML, downloadable
  artifacts, deployment manifests, and production `.rwsp` export consume RoboIR.
- Compatibility adapters can reconstruct the legacy runtime view without reparsing
  source or consulting task templates.
- Changing a retained `CompiledSkill` cannot change verified generated artifacts.

Evidence: `src/roboweaver/ir/adapters.py`, backend/codegen modules,
`tests/test_backend.py`, and `tests/test_generated_output_security.py`.

### M4 — Truthful Safety, Perception, and Simulation Status — Verified, bounded

- Assumed, user-specified, and future perception-derived pose provenance are typed.
- A supplied PICK pose removes stale perception operations from both tasks and behavior.
- Richer perception contracts cannot be erased by one coordinate triple.
- Collision verification remains `false` without a supplied typed Scene. With one,
  sampled link/footprint checks, bounded replanning, and a scene digest are mandatory.
- Physical deployment refuses assumptions and cannot bypass simulation validation.
- Only modeled process outcomes can be reported as validated.

Evidence: `tests/test_motion_semantics.py`, `tests/test_simulation_validation.py`,
`tests/test_safety_kernel.py`, and `tests/test_deployment_manifest.py`.

### M5 — Faithful Buildable Artifacts — Verified

- ROS 2 package generation includes complete source/manifest/config/launch data.
- Generic ROS output uses a `FollowJointTrajectory` client rather than falsely calling
  itself an action server.
- URScript is emitted only for compatible Universal Robots targets.
- Artifact API outputs are deterministic and downloadable.
- Generated package wheel build is part of the test suite; Humble `colcon` is a CI gate.

Evidence: `src/roboweaver/codegen/ros2_gen.py`, `urscript_gen.py`,
`scripts/generate_ros2_ci_package.py`, and generated-package/artifact tests.

### M6 — Compiler Studio and Responsive Workspace — Verified at representative viewports

- The default Compiler Studio experience is beginner-first: describe the job, choose
  one or many robot targets, compile, then review plain-language result cards.
- Technical compiler details use progressive disclosure. Users can open all six real
  stages without making IR, pass-manager, or lowering terminology the entry point.
- The simple result states what was understood, what was planned, which targets were
  accepted or rejected, what can be downloaded, and what remains unverified.
- Compiler UI shows source parsing, task decomposition, complete RoboIR, pass traces,
  per-target lowering, and generated artifacts instead of only rendering trees.
- Universal mode compiles a real target matrix; rejected targets show diagnostics.
- Evidence ledger distinguishes recorded, assumed, computed, declared, and unavailable.
- Navigation and major workspace introductions now use task-oriented language. The
  Inspire Hand simulator is labeled as a bounded hand-specific model rather than a
  universal digital twin.
- Page-level fixed-width caps were removed across all major workspaces.
- 13-inch layouts collapse to one-column working surfaces; large displays use fluid
  multi-column grids and available width.

Evidence: frontend ESLint, TypeScript, production build, and production Chromium
screenshots/overflow/runtime checks at 1440×900, 2560×1440, and 3840×2160.

### M7 — CI, Security, and Release Evidence — Verified

- Exact Python CI/test dependency lock and pinned build tooling.
- Python 3.10/3.12 test matrix, branch coverage floor, Ruff, compile/import checks.
- npm audit, pip-audit, Bandit, CodeQL, frontend type/lint/build checks.
- Distribution build/install smoke test, generated ROS package build, and container
  stack health/authentication smoke tests.
- Full Apache License 2.0 text and documentation claims reconciled with implementation.

Evidence: `.github/workflows/ci.yml`, `requirements-ci.lock`, `pyproject.toml`, and
the latest verified snapshot above.

### M8 — Provider-Safe Connection Code Generation — Verified locally

- Connect Hardware offers an explicit local Ollama or remote OpenRouter selector.
- Endpoint advice defaults to the official `openrouter/free` router. Connection review
  prefers the free code-focused `cohere/north-mini-code:free` and uses that router as
  an automatic availability fallback; the actual responding model is recorded.
- API keys remain server-side and are read only from process configuration or the
  ignored local `.env` file.
- Generated Python adapters come from validated robot profiles and the implemented
  `ros2` or `sim` bridge registry. They verify connectivity and send no trajectory.
- Target host and port are supplied through `ROBOWEAVER_TARGET_URI`; connection-code
  review does not send that URI to OpenRouter.
- Model annotations, issues, and suggestions remain separate from authoritative source.
- Endpoint identification with OpenRouter is explicit and displays the exact cloud-data
  boundary before host, port, banner, hostname, guess, and latency leave the machine.

Evidence: `src/roboweaver/codegen/connection_gen.py`,
`src/roboweaver/nlu/openrouter_manager.py`, `tests/test_connection_codegen.py`,
`tests/test_openrouter_manager.py`, live dashboard route tests, and a successful live
Ollama review through the Docker-served frontend proxy using `llama3.1:8b`. A live
OpenRouter request also succeeded through the same proxy: the named free coding primary
used its configured fallback and reported `poolside/laguna-s-2.1:free` as the actual
model. The deterministic source remained intact and excluded the endpoint URI.

### M9 — Universal Target Dialects and Physical-Evidence Boundaries — Verified, bounded

- Added explicit target legality and dedicated lowering for serial arms, holonomic
  bases, differential bases, branched humanoids, and multi-finger hands.
- Added validated external perception observations with frozen RoboIR provenance.
- Added typed sphere/AABB scenes, deterministic bounded environment replanning, a
  final post-optimization collision pass, scene digest, and structured RW307 refusal.
- Added a guarded hardware-in-the-loop acceptance runner and tamper-evident evidence
  schema; no physical evidence file is created unless live safety and feedback pass.
- Refactored the dashboard dispatcher and every default Ruff complexity violation;
  `ruff check src tests scripts --select C901,F` now passes with zero violations.
- Added production browser acceptance for every workspace and real compiler execution
  at MacBook, 32-inch QHD, and 32-inch 4K viewport profiles.

Evidence: `tests/test_target_dialects.py`, `tests/test_perception_pipeline.py`,
`tests/test_collision_planner.py`, `tests/test_hil_evidence.py`,
`frontend/scripts/visual-qa.mjs`, and the fresh verification snapshot above.

### M10 — Upstream Compiler Core and Hardened LAN Workbench — Verified locally; native CI pending push

- Replaced the name-only conversion check with a bounded full-conversion engine:
  declarative legal/illegal operation sets, ordered-benefit rewrite patterns,
  convergence bounds, exact rewrite traces, and failure when any illegal op remains.
- Replaced the hard-coded lowerer lookup with a phase-aware registry that resolves
  built-ins and external `roboweaver.motion_lowerers` entry points by deterministic
  priority. This uses RoboticsLanguage's composition idea; RoboticsLanguage itself is
  not a vendored library or runtime dependency.
- Added LLVM new-pass-manager core behavior to the active RoboIR pipeline: lazy
  analyses, cache hits/misses, preserved-analysis declarations, and invalidation after
  changing passes. The frontend displays the measured cache metrics.
- Added a real upstream MLIR bridge. It emits generic `roboweaver.*` operations,
  invokes `mlir-opt --allow-unregistered-dialect --canonicalize --cse`, strips API keys
  from the child environment, bounds execution/output, and records version plus hashes.
- Added an Ubuntu 24.04 CI job installing `mlir-18-tools`; native success is required
  before container publication. Local macOS verification reports `unavailable` because
  no `mlir-opt` executable is installed here; it does not fabricate native evidence.
- Added a LAN gateway mode that binds only the Next.js frontend publicly while keeping
  the authenticated Python API private. Compiler/read-only routes remain available;
  discovery, connection, AI, simulator mutation, model mutation, and control are denied
  unless a separate control flag is enabled. Private-host and same-origin checks prevent
  DNS rebinding and browser CSRF across the gateway. A public bind/private-IP request
  automatically enters LAN policy even when an operator forgets the explicit mode flag.
- Settings now shows local/LAN mode, physical-control state, and native MLIR tool status.
  Compiler details show legalization rewrites and native-tool evidence.

Evidence: `tests/test_upstream_compiler_core.py`, `scripts/verify_native_mlir.py`,
`.github/workflows/ci.yml`, `frontend/src/lib/server-access.ts`, live HTTP 200/403/421
checks, and the production three-viewport Chromium acceptance run.

### M11 — Isolated Research Lab, Provider Cascade, and Reproducible Evaluation — Verified locally; Gazebo CI pending push

- Added a maximum-three-attempt cascade over local Ollama, Gemini Flash-Lite, and
  OpenRouter, with explicit provider/model provenance for every attempt.
- Added bounded exact-result caching and a thread-safe trace registry adapted from
  Sentinel's operational ideas. Traces deliberately exclude prompts, responses, API
  keys, connection URIs, and target addresses; cache hits re-run deterministic gates.
- Added a strict embodiment schema: 24-link/32-joint ceilings, connected acyclic tree,
  finite geometry/dynamics limits, allow-listed sensors/training algorithms, and a
  deterministic AST-checked training scaffold. AI emits data only, never executable code.
- Added a deterministic climbing-monkey fallback with 9 links, 8 joints, contact/IMU/
  camera observations, PPO reward/termination contracts, URDF, JSON, and Python artifacts.
- Added a research Docker profile with no network or devices, read-only root, dropped
  capabilities, no-new-privileges, and PID/memory/CPU bounds. A local hardened run passed
  artifact validation and truthfully reported `not_run_no_simulator_adapter` for physics.
- Added a responsive Research Lab frontend with a rotatable 3D morphology preview,
  cascade readiness, cache/failure/latency metrics, attempt table, downloadable artifacts,
  isolation contract, and one-click six-metric evaluation.
- Added research evaluation v1 and CI artifact publication. Local evidence: 6/6 metrics,
  one IR SHA-256 across three runs, 3/3 arm targets accepted from one source, exact RW102,
  0.179824 m NativeTwin lift, and median waypoints reduced from 204 (O0) to 44 (O1).
- Added a ROS 2 Jazzy/Gazebo Harmonic CI gate following the official `ros_gz_sim` path:
  parse URDF, launch a headless empty world, spawn the compiler-derived robot, list the
  entity, and inspect its joints. It is configured but has not run on GitHub yet.

Evidence: `tests/test_model_cascade.py`, `tests/test_gemini_manager.py`,
`tests/test_research_experiments.py`, `tests/test_research_evaluation.py`, the local
hardened Docker report, `frontend/scripts/visual-qa.mjs`, and `.github/workflows/ci.yml`.

## Latest Change Log

### 2026-08-07 — Isolated Research Lab and Measurable Evaluation

- Status: locally verified; Gazebo and public CI evidence pending push.
- Added the bounded Ollama/Gemini/OpenRouter cascade, exact cache, privacy-preserving
  model-attempt traces, open-ended embodiment schema, deterministic research artifacts,
  and hardened no-network/no-device Docker sandbox.
- Added the responsive Research Lab and verified both its empty state and generated
  climbing-monkey result at 1440×900, 2560×1440, and 3840×2160.
- Added six reproducible metrics plus Jazzy/Harmonic headless-spawn CI. The local harness
  passed 6/6; Gazebo is not installed locally and the configured CI job is not yet public.
- Fresh verification: 450 tests passed, 1 skipped, 5 subtests, 78.57% branch coverage,
  zero C901/F findings, production frontend type/lint/build, no npm/pip audit findings,
  no Bandit medium/high findings, successful wheel/sdist build, and hardened Docker run.

### 2026-08-07 — Real Compiler-Core Integration and LAN Hardening

- Brutal before-state: neither LLVM/MLIR nor RoboticsLanguage was executed or imported;
  the project had custom classes with similar names and a hard-coded lowerer map.
- Current state: RoboWeaver executes a real internal full-conversion/plugin/analysis
  architecture on every compile and executes upstream `mlir-opt` whenever available.
- Upstream boundary: LLVM source is not copied or linked, RoboticsLanguage source is not
  copied or imported, and no machine-code backend is claimed. Their documented core
  mechanisms are adapted; the separately installed MLIR executable is the native link.
- Added native-tool evidence to API/UI, an upstream acceptance CI gate, a compiler-only
  same-network mode, Host rebinding protection, same-origin control policy, and visible
  runtime access status.
- Fresh verification: 441 tests passed, 1 skipped, 5 subtests passed; coverage rounds to
  79%; Ruff C901/F, TypeScript, ESLint, production build, live LAN policy checks, and all
  three responsive Chromium profiles pass.

### 2026-08-07 — Universal Compiler Architecture and Acceptance Closure

- Initially adapted the vocabulary and broad architecture from LLVM/MLIR conversion
  targets and RoboticsLanguage phases. M10 supersedes this with executable conversion,
  analysis invalidation, plugin discovery, and native `mlir-opt` evidence.
- Closed the perception, environment-collision, non-serial lowering, HIL harness,
  responsive QA, and default-complexity findings with bounded implementations.
- Added browser-to-real-compiler CI: the production UI now has to return a real
  compilation result and render it at all three requested display profiles.
- Verified 433 tests, 1 skip, 5 subtests, 78.48% branch coverage, zero C901/F Ruff
  violations, Python compilation/dependency consistency, frontend lint/typecheck/build,
  and the three-profile production Chromium acceptance run.
- Physical robot execution remains externally blocked and is not represented as done.

### 2026-08-07 — Evidence-First Credibility Audit

- Verified the local repository is a full, non-shallow clone with 93 commits; GitHub's
  public API reports creation on 2026-07-26, one star, one fork, and no open issues.
  The public `main` commit still matches local `HEAD`; the much larger current
  credibility/redesign worktree is uncommitted and therefore not yet public evidence.
- Measured 17,440 Python source lines and 6,345 Python test lines before this audit.
  These size figures establish scope, not correctness.
- Historical audit result (subsequently closed in M9): 16 functions exceeded C901=10.
  `dashboard/server.py::_route` is the largest hotspot at complexity 117, and the
  server, CLI, compiler, taxonomy, and several runtime modules remain too monolithic.
- Inspected the repository's `.agents` content; it contains architecture metadata,
  not an executable hidden agent workflow.
- Integrated target-declared forbidden joint ranges into the mandatory compiler pass
  pipeline before and after optimization. Invalid declarations fail as RW508 and
  sampled violations block compilation as RW507.
- Added a human-accountability and AI-assistance contribution policy plus a pull-request
  evidence template to reduce low-context, unverifiable contribution load.
- Marked dashboard images as historical captures instead of implying that they prove
  the current sidebar/provider redesign or requested laptop/desktop viewports.
- Replaced substring action matching with complete word/phrase boundaries and made
  unknown actions fail closed as RW101 before portable IR or artifacts are produced.
- Replaced process-global random IK seeds with reproducible, well-spaced seeds so the
  same source/profile/settings cannot drift between success and failure across runs.
- Removed the workcell parser's fabricated PICK fallback. Unsupported clauses are
  disclosed, empty executable plans fail RW101, and API/frontend errors retain the
  real compiler diagnostic.
- Re-ran the complete branch-aware suite after these changes: 420 tests passed with
  78.59% coverage; frontend lint, strict TypeScript, and production build also pass.

### 2026-08-07 — Ollama/OpenRouter Connection Code Workflow

- Added an optional OpenRouter provider using the official chat-completions endpoint
  and `openrouter/free` router, with bounded inputs/responses and safe error handling.
- Added deterministic, downloadable robot connection adapters that send no motion.
- Added optional Ollama/OpenRouter annotations and issue reports without replacing the
  generated source.
- Added explicit cloud privacy messaging and kept API credentials out of browser code.
- Added provider status and selection to Connect Hardware.
- Verified one-call Ollama review through the running frontend and API containers.
- Added a code-focused free OpenRouter primary with an official free-router fallback,
  then verified that fallback and actual-model reporting through the running containers.
- Raised the verified suite to 398 passing tests with 78.31% branch coverage.

### 2026-08-07 — Beginner-First Frontend Redesign

- Rebuilt the local Docker API and frontend images after discovering port 3000 was
  serving a stale container build. Replaced the rejected example API token in the
  ignored local `.env`; both containers and the authenticated frontend proxy are healthy.
- Reorganized navigation into a plain-language main workflow and supporting tools.
- Rewrote the start page around the four actions a user needs to understand:
  describe a job, make a plan, check each robot, and prepare a download.
- Made simple Compiler Studio mode the default and retained a full technical mode for
  inspecting the real frontend, task plan, portable IR, compiler passes, target
  lowering, and emitted artifacts.
- Added result cards for interpretation, task planning, target acceptance, and runtime
  downloads, plus an explicit hardware-readiness limitations panel.
- Added responsive simple-result grids that expand on large displays and collapse to a
  single readable column on laptop/mobile widths.
- Reworded Compare, Workcell, Benchmark, Robot Library, Connections, Hand Simulator,
  Capability Evidence, Package Library, and Settings entry points.
- Frontend lint, strict TypeScript, and production build pass after the redesign.
- Attempted browser viewport QA through the required in-app browser workflow; no
  browser instance was available, so screenshot acceptance remains open and unclaimed.

### 2026-08-07 — Universal Compiler Credibility Pass

- Made complete RoboIR 0.2.0 the post-frontend source of truth.
- Added target-independent portable compilation and independently verified target matrix.
- Added exact action-specific Cartesian inputs and pose-aware cache keys.
- Migrated built-in safety, native simulation, ROS 2, URScript, dashboard XML, and
  production `.rwsp` behavior export to RoboIR.
- Added reproducible downloadable artifacts and ROS Humble `colcon` CI.
- Strengthened Safety Kernel revalidation and deployment manifests.
- Added deep nested IR immutability and consistency verification.
- Added validated custom/unregistered `RobotSpec` support.
- Corrected perception semantics for supplied poses and richer perception tasks.
- Rebuilt Compiler Studio around six visible compiler stages and an evidence ledger.
- Removed page-level fixed-width caps throughout the frontend.
- Raised the earlier credibility-pass test count to 386 and measured branch coverage to 78.21%.
- Reconciled README and architecture/roadmap documentation with tested behavior.

## Current Limitations and Non-Claims

These are not hidden defects; they define the current product boundary:

1. **External perception input, not a bundled vision stack.** The provider contract,
   validation, provenance, and JSON/static adapters are real; camera detection,
   segmentation, depth estimation, and ROS image transport remain integrations.
2. **Bounded environment collision planning.** Sphere/AABB environment checks and
   replanning are real when a Scene is supplied. Self-collision, mesh geometry,
   continuous swept-volume proof, and dynamic obstacles remain open.
3. **Position-only IK objective.** Orientation, dynamics, torque, singularity-aware
   global planning, and mature planning-framework integration remain open.
4. **Limited process simulation.** PICK has a native outcome model. Other tasks can
   execute trajectories but cannot claim validated process outcomes.
5. **No physical HIL evidence yet.** The acceptance runner and evidence hash are tested
   with a feedback bridge, but real robot logs, calibrated transforms, safety-I/O test
   records, risk assessment, and certification evidence are absent.
6. **Bounded formal verification only.** No continuous-time or theorem-prover claim.
7. **Two pass-manager working types remain.** Optimization still operates on a
  `CompiledSkill` compatibility view before final RoboIR construction.
8. **The default language frontend is bounded.** It is deterministic and inspectable,
   but taxonomy/keyword routing is not open-ended understanding.
9. **Viewport evidence is pixel-profile evidence.** The requested representative
   resolutions are verified, but browser automation cannot certify a monitor's physical
   inches, operating-system scaling, color calibration, or assistive-technology setup.
10. **Large modules remain.** Default C901 is clean and the dispatcher is decomposed,
    but `dashboard/server.py` remains a large route module that should be split by domain.
11. **Embodiment lowerers are bounded.** All five motion models have dedicated command
    semantics, but Pepper lacks whole-body/base coupling, standalone hand collision needs
    a parent-arm transform, and vendor-controller/HIL conformance remains external.
12. **Native LLVM/MLIR is a validation bridge, not a full backend.** The emitted module
    runs canonicalize/CSE in `mlir-opt`; RoboWeaver does not lower robotics operations to
    LLVM IR, object files, or machine code and does not link the LLVM libraries.
13. **RoboticsLanguage is architecture influence, not a dependency.** Its phased plugin
    composition is implemented in RoboWeaver's registry, but its Python/XML AST, ROS C++
    generators, and source tree are not imported or vendored.
14. **LAN mode is intentionally compiler-only by default.** Anonymous same-network users
    cannot scan networks, connect robots, consume AI providers, mutate simulator/model
    state, or issue physical control through the frontend unless an operator explicitly
    enables the separate control flag. Network isolation is not a safety certification.
15. **Research morphology is not a robot design certificate.** Generated primitive URDF
    geometry is a bounded hypothesis. It has not passed dynamics, torque, singularity,
    continuous-time collision, manufacturability, or physical validation.
16. **The training artifact is an adapter scaffold, not a trained brain.** It defines a
    bounded rollout/reward contract but requires a real simulator adapter and learning
    implementation. The isolated run validates artifacts; it does not train a policy.
17. **Observability is intentionally in-process.** It adapts Sentinel's bounded fallback,
    provenance, cache, and control-room ideas, but does not include Sentinel's durable
    database, semantic cache, alerts, authentication, or distributed evaluation workers.

## Future Planning

### P0A — Code Structure and Reviewability — Partially verified

Goal: make the implementation reviewable without relying on one maintainer's memory or
aggregate coverage.

Deliverables:

- Split `dashboard/server.py` into bounded route modules with explicit request/response
  schemas and a small dispatcher.
- Separate CLI argument construction from command execution and extract compiler parser,
  portable frontend, lowering, and verification orchestration boundaries.
- Replace the taxonomy's long conditional constructor with declarative validated data
  or small category builders.
- Add a staged C901 quality gate, ratcheting the maximum down as hotspots are removed.
- Add architecture-boundary tests so refactors cannot introduce circular domain imports.

Current result: the dispatcher and all 16 reported hotspots were decomposed and the
repository passes default C901 with no suppressions. Remaining work is physical route
module separation and an architecture-boundary import test.

### P0 — Visual Responsive Acceptance — Verified locally; CI gate configured

Goal: prove the dashboard on the two requested display classes.

Deliverables:

- Automated browser coverage at representative laptop and desktop viewports, such as
  1280×800, 1440×900, 2560×1440, and 3840×2160.
- Screenshots for every major view, not only Compiler Studio.
- Assertions for no horizontal page overflow, reachable navigation, non-overlapping
  dialogs, readable compiler stages, and usable artifact controls.
- Keyboard navigation and reduced-motion checks.

Current result: 12 workspaces, a real compiler result, and a generated bounded research
result pass at 1440×900, 2560×1440, and 3840×2160; CI installs Chromium and uploads the captures. GitHub-hosted execution
will become public evidence after this worktree is committed and CI completes.

### P0B — Native Compiler and LAN Production Closure — Partially verified

Goal: deepen the new bridge and shared-workbench layer without inflating their claims.

Deliverables:

- Register a versioned RoboWeaver MLIR dialect instead of relying only on generic
  unregistered operations; add dialect verification, typed robotics operations, and
  source locations connected back to RoboIR diagnostics.
- Add a real conversion from that dialect into one executable middleware/controller
  representation. LLVM IR/object-code lowering is only appropriate for CPU-side runtime
  components, not as a false replacement for robot controller semantics.
- Publish and test an external lowerer package through the entry-point boundary; add
  signed plugin provenance and an operator allow-list before loading third-party code in
  production deployments.
- Add optional authenticated LAN identities/roles for teams that need more than
  anonymous compiler-only access, TLS termination guidance, and reverse-proxy tests.
- Run the native MLIR job and LAN container acceptance on public GitHub CI after this
  worktree is committed. Preserve the logs/artifacts as public evidence.

Current result: internal full conversion, analysis invalidation, phase plugins, native
`mlir-opt` invocation/CI configuration, compiler-only LAN access, Host validation, and
  same-origin control gates are implemented. Registered MLIR dialect libraries, signed
third-party plugins, user identities, TLS, and a public completed CI run remain open.

### P0C — Simulator and Research Baseline Closure — Partially implemented

Goal: convert the new safe experiment artifacts and local evaluation into defensible
external simulator and paper-quality evidence.

Deliverables:

- Implement a versioned `SimulatorAdapter` for Gazebo Harmonic or MuJoCo that loads the
  exact generated embodiment, executes bounded rollouts, and returns physics metrics.
- Bridge compiler trajectories to `ros2_control` in Gazebo and verify joint-state,
  controller acknowledgement, collision/contact, timeout, and deterministic reset.
- Add MoveIt 2 or another mature planner baseline over the same scenes and robot models;
  report success, path length, planning time, clearance, and failure diagnostics.
- Add camera/ROS-topic observation ingestion with recorded calibration, timestamps, and
  replayable sensor evidence.
- Publish the benchmark definition, fixed seeds, machine metadata, raw JSON results,
  analysis notebook, and an external reproduction protocol.

Current result: the sandbox contract, artifact generator, local six-metric harness, and
Jazzy/Harmonic spawn CI are implemented. Physics rollout, controller bridge, external
planner baseline, live perception, and independent reproduction are still open.

### P1 — Real Perception Input Contract — Partially verified

Goal: replace assumed scene poses with measured, timestamped observations.

Deliverables:

- Typed observation containing object id/class, pose, frame, timestamp, confidence,
  sensor/provider id, and calibration provenance.
- Provider interface for external ROS 2 perception systems.
- Staleness, frame, confidence, and calibration validation before compilation/deploy.
- Dashboard path for observation inspection and explicit source selection.
- One small real vertical slice using a supported detector/pose provider.

Current result: the typed contract, validation, provenance, fail-closed behavior, and
tests meet the software portion. A recorded live sensor/ROS provider remains open.

### P2 — Collision-Aware Motion Planning — Partially verified

Goal: replace `collision_check: false` with a real modeled result when geometry exists.

Deliverables:

- Versioned workcell/environment geometry in RoboIR.
- Robot link collision geometry and self/environment collision checks.
- Planning backend adapter, initially for one mature planner.
- Collision evidence and failure diagnostics in the pass trace and manifest.

Current result: collision status is true only after every emitted sampled waypoint was
checked against the supplied typed Scene. Mesh/self/dynamic/continuous checks and a
mature external planner adapter remain open.

### P3 — Motion Planning as Explicit RoboIR Passes — Planned

Goal: expose lowering internals as inspectable compiler passes.

Deliverables:

- `IKPass`, `TrajectoryPass`, and target-lowering context operating on RoboIR
  generations.
- Remove duplicated pass-manager infrastructure or unify it behind a typed generic
  core without losing trace compatibility.
- Incremental invalidation keyed by source, target profile, scene, and optimization
  settings.

Definition of done: optimization and lowering no longer require a mutable
`CompiledSkill` working representation.

Current result: lazy RoboIR analysis caching and preserved-analysis invalidation are
real; source/target/scene cache keys and the unification of the second CompiledSkill
pass manager remain open.

### P4 — Additional Real Backend Dialects — Planned

Goal: prove backend extensibility beyond ROS 2 and URScript.

Candidate sequence:

1. ABB RAPID or KUKA KRL with an official syntax/build validation path.
2. A mature simulation/planning bridge such as MoveIt 2 or Gazebo.
3. Vendor-neutral controller conformance tests.

Definition of done: each backend has target-specific validation, syntax/build tests,
failure diagnostics, documentation, and no copied target semantics outside RoboIR.

### P5 — Hardware-in-the-Loop Evidence — Harness verified / hardware-dependent

Goal: turn software deployment readiness into measured hardware evidence.

Deliverables:

- Calibrated robot/tool/workcell manifest.
- Measured joint-state feedback and controller acknowledgement logs.
- Supervised low-speed reference skill on real hardware.
- Emergency-stop, watchdog, timeout, rejection, and recovery test records.
- Signed deployment manifest linked to telemetry and exact RoboIR hash.

Current result: the guarded runner enforces acknowledgement, safety I/O, joint limits,
changed/tracking feedback, and hash-linked evidence in tests. Definition of done still
requires that a reproducible physical run can be traced from source and RoboIR
through artifact, controller acknowledgement, telemetry, and outcome. This still does
not replace a robot-specific risk assessment or safety certification.

### P6 — Research-Grade Verification — Future research

Goal: add stronger proofs only where assumptions can be modeled honestly.

Potential work:

- SMT-backed bounded scheduling/resource proofs.
- Temporal properties over discrete execution traces.
- Continuous-time checks for tractable approximations.
- Counterexample generation linked to compiler diagnostics.

Definition of done: every proof states its model, assumptions, solver, boundedness,
and unsupported physical effects. “Formal verification” must never imply more.

### P7 — Execution-Guided Optimization and Replay — Planned after real data

Goal: use measured execution evidence instead of synthetic improvement claims.

Deliverables:

- Persisted telemetry frames and deterministic replay.
- Profile-guided optimization keyed to exact robot/scene/tool versions.
- Train/validation separation and rollback for learned parameter changes.
- Before/after evidence for safety, success rate, and cycle time.

Definition of done: recommendations are based on sufficient real samples and remain
optional until reverified by the normal compiler and deployment gates.

## Update Protocol

Whenever code changes a capability or milestone:

1. Update **Last updated**, **Current Verified Snapshot**, and the relevant matrix row.
2. Add a dated item under **Latest Change Log**.
3. Change a status only when its definition above is satisfied.
4. Record exact automated tests, external evidence, and unsupported boundaries.
5. Update test count and coverage only from a fresh complete run.
6. If a claim is removed or regresses, record it immediately; do not wait for a release.
7. Keep README concise and link here for full live status.

Suggested entry template:

```markdown
### YYYY-MM-DD — Short change title

- Status: Verified | Implemented | Partial | Planned | Blocked externally
- Changed: concrete implementation summary
- Evidence: tests/build/logs/files
- Limitations: what remains unsupported
- Next: the smallest follow-up with a measurable definition of done
```
