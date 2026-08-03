# LinkedIn post — RoboWeaver

## Images (post in this order as a carousel)
1. `01_overview.png` — dashboard / hero shot
2. `02_compiler_debugger.png` — Compiler Debugger catching a real capability gap
3. `03_inspire_hand_grasp.png` — Inspire Hand digital twin, real actuator telemetry
4. `04_franka_cad_model.png` — real Franka arm CAD model, posed by real kinematics
5. `05_fleet_registry.png` — 11-robot hardware abstraction layer
6. `06_knowledge_nexus.png` — ROS 2 package catalog

Optional: attach `docs/media/demo.gif` as a native LinkedIn video/gif for extra reach — carousels + video both get an algorithmic boost over a single static image.

---

## Post copy (primary version)

I've been building RoboWeaver: an LLVM-inspired compiler for robot skills — you describe a task in plain English, and it compiles through a typed intermediate representation into a verified, deployable ROS 2 behavior tree.

The idea: robotics software keeps re-solving the same problem per robot, per skill, with no shared representation a planner, a simulator, and a code generator can all agree on. RoboWeaver's answer is RoboIR — every skill compiles: intent → RoboIR → motion plan → behavior tree → ROS 2 package, the same pipeline shape as source → IR → machine code.

A few pieces I'm most glad I built for real instead of faking:

→ A Compiler Debugger. If a skill needs a capability the target robot doesn't have — say, force-torque sensing for a "tighten the bolt" instruction on a robot with no F/T sensor — compilation fails loudly with a structured, fixable diagnostic instead of silently producing a bad plan. (Screenshot 2.)

→ A real digital twin, not a placeholder. The Franka arm in the 3D viewer is the actual Apache-2.0 CAD mesh, posed through its real published DH kinematic chain — not a generic capsule-and-sphere stand-in. (Screenshot 4.)

→ Hardware-honest bridges. The Inspire Hand driver speaks real RS485 with a real CRC-16/MODBUS checksum, proven against a virtual serial loopback test — and when no physical hand answers, it says so and falls back to a software grasp-physics model instead of pretending a connection exists.

→ 11 robots in the hardware abstraction layer, from 3-DOF service AMRs to a 20-DOF dexterous hand, each with its own real N-DOF kinematic chain and joint limits — not one hardcoded robot with everything else as a fake.

Everything ships with CI (Python 3.10/3.12 backend, TypeScript/Next.js frontend), a real test suite, and honest labeling everywhere a feature is real vs. still on the roadmap.

Built with Python, Next.js, Three.js, and a healthy amount of "does this actually work or does it just look like it works."

#Robotics #ROS2 #SoftwareEngineering #CompilerDesign #OpenSource

---

## Shorter version (if you want a tighter post)

RoboWeaver: an LLVM-style compiler for robot skills. Describe a task in English, it compiles through a typed IR (RoboIR) into a verified ROS 2 behavior tree — checked against the target robot's real capabilities before it's allowed to run.

Highlights:
• Compiler Debugger — capability mismatches fail loudly with a fixable diagnostic, never a silent bad plan
• Real CAD-based 3D digital twin, posed by the arm's actual DH kinematics
• Hardware-honest drivers — real RS485/CRC-16, honest fallback when nothing's physically connected
• 11 robots in the registry, from service AMRs to a 20-DOF dexterous hand
• Full CI across backend + frontend

#Robotics #ROS2 #OpenSource
