# Research Positioning

## Contributions

RoboIR as a versioned, embodiment-independent intermediate representation carrying
required capabilities, provenance-tagged capability claims, and safety/verification
state, not just geometry; a real LLVM/MLIR-style pass manager over frozen, SSA-style IR
generations with per-pass timing and a full inspectable trace; a Robot Backend
interface, backed by a generic plugin registry, that keeps the compiler proper
independent of any one middleware; an honesty-by-construction pattern applied
consistently across hardware bridges, digital twins, execution memory, and case-based
recovery (attempt/measure the real thing, report a typed truthful status, `None` rather
than a fabricated number when there's no data); a Compiler Debugger that turns
capability mismatches into structured, fixable diagnostics instead of silent failures;
a real, registry-ingested knowledge graph with multi-hop pathfinding, a genuine
Obsidian export, and — as of the most recent deepening — a real role in a compiler
decision (candidate-robot selection for `compare_robots()`), not only documentation.

## Honest positioning against prior work

This is integration and a compiler-shaped architecture applied to robotics skill
generation, not a claim of new algorithms in motion planning, formal methods, or IR
theory. Said plainly, not implied away:

- **Vs. LLVM/MLIR**: RoboIR borrows the pass-manager shape (ordered, timed, diagnostic-
  emitting transformations over immutable generations) but is a single-level IR today,
  not a multi-dialect, progressively-lowered one. MLIR's dialect system — Task/Motion/
  Manipulation/Navigation/Safety dialects lowering into each other — is a real,
  substantially larger redesign this project has not attempted.
- **Vs. MoveIt / Tesseract / OMPL**: RoboWeaver does not implement a competing motion
  planner. Its IK/trajectory generation is a real damped-pseudoinverse solver with
  min-jerk trajectory generation — adequate for the compiler's own verification and
  demo purposes, not a research contribution in planning algorithms, and not benchmarked
  against these libraries' planning quality (see [`BENCHMARKS.md`](BENCHMARKS.md) for
  why a fair comparison would look different from what exists today).
- **Vs. BehaviorTree.CPP / Task Constructor**: RoboWeaver generates Behavior Trees as a
  compilation target (Groot2-compatible XML) rather than providing a BT authoring/
  runtime environment. It's a producer of BT artifacts, not an alternative to the BT
  runtime ecosystem.
- **Vs. ROS 2 itself**: RoboWeaver targets `rclpy`/URScript as backends; it is not a
  replacement for ROS 2's own tooling, and every generated package still depends on the
  real ROS 2 ecosystem to run.

## Where the genuine novelty claim is narrower, and sharper for it

Not "a compiler for robotics" (explored territory) but the specific combination of:
capability-aware compilation that fails closed at compile time rather than at runtime
(the Compiler Debugger); a knowledge graph that gates candidate selection on the same
real declared hardware capabilities it uses for documentation, rather than maintaining
two separate, driftable notions of "what a robot can do"; and an honesty-by-construction
discipline enforced consistently enough across hardware bridges, digital twins,
execution memory, and now knowledge-graph-driven decisions that "this returns `None`
because there's no data" is a load-bearing design pattern, not an incidental one.

## What would sharpen this further (real, deferred, not started)

- **Multi-robot SSA** — versioned RoboIR values across a choreographed multi-robot plan,
  so a handoff is a real value-passing edge, not just a validated string reference
  (`handover_target`).
- **Safety-preserving optimization** — a pass that can prove (not just re-verify after
  the fact) that its transformation cannot introduce a safety violation, rather than
  running the safety checker again after every pass as a regression guard.
- **Compiler-driven task decomposition** — today's task decomposition comes from a
  hand-authored template per skill category (`skills/taxonomy.py`); a pass that derives
  task structure from the knowledge graph and declared capabilities, rather than a
  fixed template lookup, would be a real step toward "the graph as another compiler
  pass" rather than "the graph as an input to one existing pass's candidate list."

None of these are claimed as done. They're the honest next layer if the goal is a
sharper research contribution rather than a broader one.
