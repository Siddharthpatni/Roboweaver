# RoboWeaver Architecture Map

Quick-reference index for every module. Use this to locate the right file without re-reading the entire codebase.

## Backend (Python) — `src/roboweaver/`

### Core Pipeline
| File | Key Classes/Functions | Purpose |
|---|---|---|
| `compiler.py` | `SkillCompiler`, `CompilationResult`, `ACTION_CATEGORY_MAP` | 4-stage pipeline: intent parse → task decompose → motion plan → BT compile |
| `types.py` | `Action` (enum, 16 values), `SkillIntent`, `TaskGraph`, `CompiledSkill`, `ExecutionResult`, `BTNode`, `MotionPlan`, `IKResult` | All core data types |
| `math3d.py` | `Vec3`, `Mat3`, `Transform3D` | Pure-Python 3D math |

### Intermediate Representation (`ir/`)
| File | Key Classes/Functions | Purpose |
|---|---|---|
| `schema.py` | `RoboIR`, `ObjectRef`, `RequiredCapabilities`, `Constraints`, `ExecutionSpec`, `VerificationSpec` | IR data model |
| `builder.py` | `build_ir()` | Constructs RoboIR from SkillIntent + RobotSpec |
| `diagnostics.py` | `CompilerDiagnostic`, `SkillCompilationError`, `check_required_capabilities()` | Capability checking (force/torque, perception) |
| `safety.py` | `check_safety()`, `_check_reachability`, `_check_joint_limits`, `_check_velocity_limits`, `_check_manipulability`, `_check_payload`, `_check_workspace_and_floor` | 6 safety verification passes |

### Hardware Abstraction (`hardware/`)
| File | Key Classes/Functions | Purpose |
|---|---|---|
| `robot_spec.py` | `RobotSpec`, `JointSpec`, `LinkSpec` | Data model for any robot |
| `registry_robots.py` | `ROBOT_REGISTRY` (dict), `get_robot_spec()`, `get_franka_panda_spec()`, `get_ur5e_spec()`, etc. | 15+ robot profiles |
| `kinematics_ndof.py` | `NDOFIKSolver`, `forward_kinematics_ndof()`, `forward_kinematics_chain_ndof()` | N-DOF FK/IK engine |
| `universal_driver.py` | `UniversalRobotDriver`, `ROS2HardwareBridge`, `SimulationHardwareBridge`, `RobotConnectionStatus` | Robot connection middleware |
| `safety_guard.py` | `WorkspaceSafetyGuard`, `SafetyCheckResult` | Workspace/joint/payload validation |
| `inspire_hand_rs485.py` | `InspireHandRS485Driver`, `InspireHandState` | Inspire RH56F1-E2 dexterous hand driver |
| `discovery.py` | `RobotDiscoveryService`, `DiscoveredRobot` | **[NEW]** Network robot scanner |

### NLU (`nlu/`)
| File | Key Classes/Functions | Purpose |
|---|---|---|
| `ollama_parser.py` | `OllamaIntentParser`, `OllamaParseResult` | Optional local LLM intent parsing via Ollama |

### Runtime (`runtime/`)
| File | Key Classes/Functions | Purpose |
|---|---|---|
| `engine.py` | `SkillRuntime` | Executes compiled skills in simulation |
| `recovery.py` | `RecoveryEngine`, `FailureMode`, `RecoveryAction`, `RecoveryPlan` | Failure diagnosis & recovery |
| `telemetry.py` | `TelemetryRecorder` | Frame-by-frame execution recording |

### Fleet / Multi-Robot (`fleet/`)
| File | Key Classes/Functions | Purpose |
|---|---|---|
| `choreographer.py` | `MultiRobotChoreographer` | DAG-based multi-robot task scheduling |
| `orchestrator.py` | Orchestration utilities | Fleet orchestration |
| `prompt_builder.py` | `SystemPromptParser`, `MultiRobotChoreographer` | NL prompt → multi-robot workcell |
| `retargeter.py` | Cross-embodiment retargeting | Retargets skills across robot types |

### Code Generation (`codegen/`)
| File | Key Classes/Functions | Purpose |
|---|---|---|
| `ros2_gen.py` | ROS 2 package generation | Generates ROS 2 packages from compiled skills |
| `groot2.py` | `export_groot2_xml()` | Groot2-compatible BehaviorTree XML |
| `inspire_ros2_gen.py` | `generate_inspire_hand_ros2_package()` | Inspire Hand ROS 2 package |

### Skills (`skills/`)
| File | Key Classes/Functions | Purpose |
|---|---|---|
| `taxonomy.py` | `IndustrialSkillCategory` (enum), `get_industrial_skill_template()` | 14 industrial skill templates with task graphs & BT trees |

### Knowledge (`knowledge/`)
| File | Purpose |
|---|---|
| `graph.py` | Robotics knowledge graph |
| `package_nexus.py` | `RoboticsPackageNexus` — ROS 2 package catalog & recommendation engine |
| `ontology.py` | Robotics ontology |
| `ingest.py` | Knowledge ingestion |

### Other
| File | Purpose |
|---|---|
| `dashboard/server.py` | HTTP API server (stdlib `http.server`), all `/api/*` endpoints |
| `cli/main.py` | CLI entry point (`roboweaver compile`, `dashboard`, etc.) |
| `registry/repository.py` | `SkillRepository` — compiled skill storage |
| `registry/package.py` | Skill package model |

---

## Frontend (Next.js/TypeScript) — `frontend/src/`

### App
| File | Purpose |
|---|---|
| `app/page.tsx` | Main page — tab routing, dashboard, settings, activity |
| `app/globals.css` | Global theme (color palette, cards, animations) |
| `app/layout.tsx` | Root layout with fonts |

### Components
| File | Purpose |
|---|---|
| `components/Sidebar.tsx` | Navigation sidebar with logo, nav items, connection status |
| `components/TopBar.tsx` | Header bar with search, status pill, new-workcell button |
| `components/CompilerView.tsx` | Skill compiler UI — instruction input, robot selector, RoboIR display, BT XML viewer |
| `components/WorkcellBuilderView.tsx` | Multi-robot workcell builder |
| `components/KnowledgeNexusView.tsx` | ROS 2 package catalog browser |
| `components/FleetRegistryView.tsx` | Robot fleet registry |
| `components/LiveSimulationView.tsx` | Inspire Hand simulation UI |
| `components/RobotConnectView.tsx` | **[NEW]** Robot discovery & connection panel |
| `components/Robotic3DViewport.tsx` | Three.js 3D robot viewer |
| `components/Robot3DModel.tsx` | 3D robot model rendering |

### Data & Config
| File | Purpose |
|---|---|
| `lib/api.ts` | `RoboWeaverAPI` — all fetch wrappers to backend |
| `types/index.ts` | All TypeScript interfaces and types |

### Key Tab Types
`'dashboard' | 'compiler' | 'builder' | 'nexus' | 'fleet' | 'simulation' | 'activity' | 'settings' | 'connect'`
