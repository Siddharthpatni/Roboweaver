# Benchmarks

**RoboBench** (`benchmark/robobench.py`) is a real compile-pipeline measurement —
latency, success/failure, diagnostic counts, waypoint reduction — over every distinct
registered robot × every skill category the compiler's NL pipeline can actually reach
(all 17). Explicitly scoped as compile-time measurement, not simulator-execution
benchmarking (no simulators are integrated here yet — stated in the report's own
`scope` field, never silently implied to be more).

```bash
roboweaver benchmark --output report.json
```

Sample real output — `roboweaver benchmark` with no `--robots` filter, which runs
every distinct registered robot (11) × all 17 skill categories (187 cells):

```
132/187 cells compiled successfully, total 24.3s
```

The 55 real failures aren't noise: they're mostly end-effector-only embodiments
(`shadow_hand`, `robotiq_hand`) genuinely failing to compile `MOBILE_NAV` and similar
categories their kinematics can't reach — a real, honest signal about embodiment fit,
not something the report hides or averages away. Every cell reports real compile time,
error/warning counts, and — where `WaypointDecimationPass` fired — the real
waypoint-reduction percentage (typically ~78–83% on the standard demo trajectories,
self-verified against the real velocity-limit safety check each run, not a fixed
claimed number).

## What this is not

RoboBench does not compare against MoveIt, BehaviorTree.CPP, Task Constructor,
OpenRAVE, or Tesseract, and this doc won't pretend that gap is closed. Those projects
solve a different problem — continuous motion planning, a production BT runtime — than
what RoboWeaver's own compile pipeline measures. A fair head-to-head would mean routing
RoboWeaver's compiled output *through* one of them (e.g. lowering to a MoveIt
`MotionPlanRequest` and comparing planning quality/time against RoboWeaver's own IK
solver) rather than inventing a benchmark number against a library doing an unrelated
job. That's real, scoped, deferred work — tracked in [`ROADMAP.md`](ROADMAP.md), not
claimed here.

## Reproducing

```bash
git clone https://github.com/Siddharthpatni/Roboweaver.git
cd Roboweaver && pip install -e .
roboweaver benchmark --robots franka_panda,ur5e,kuka_iiwa,kinova_gen3,abb_irb120 --output report.json
```

Or the dashboard API: `GET /api/benchmark?robots=franka_panda,ur5e` (small default
subset server-side to keep a live dashboard call fast — the CLI is where the full
matrix runs).
