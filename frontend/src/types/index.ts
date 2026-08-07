/** Compiler Studio navigation destinations -- pipeline-stage-shaped, not a file
 * explorer's tab-open model. Exactly one is active at a time. */
export type ViewType =
  | 'overview'
  | 'compile'
  | 'compare'
  | 'workcell'
  | 'robots'
  | 'twin'
  | 'graph'
  | 'packages'
  | 'connect'
  | 'benchmark'
  | 'research'
  | 'settings';

export interface RobotProfile {
  id: string;
  name: string;
  manufacturer: string;
  dof: number;
  payload_capacity_kg: number;
  max_reach_m: number;
  gripper_type: string;
  motion_model: 'serial_arm' | 'holonomic_base' | 'differential_drive' | 'branched_humanoid' | 'multi_finger_hand';
  description: string;
}

export interface WorkcellStep {
  step_id: string;
  robot_id: string;
  instruction: string;
  depends_on: string[];
  handover_target: string | null;
  action: string | null;
}

export interface WorkcellBuildResult {
  prompt: string;
  workcell_name: string;
  robots: string[];
  warnings: string[];
  tiers: WorkcellStep[][];
  behavior_tree_xml: string;
}

export interface NexusPackage {
  id: string;
  name: string;
  category: string;
  description: string;
  compatible_robots: string[];
  ros2_dependencies: string[];
  default_topics: string[];
  default_actions: string[];
  version: string;
}

export interface NexusRecommendation {
  matched_robots: string[];
  package_ids: string[];
  recommended_packages: string[];
  ros2_topics: string[];
  ros2_actions: string[];
  package_xml_dependencies: string[];
}

export interface RoboIRObject {
  id: string;
  name: string;
  object_class: string;
  role: 'source' | 'destination' | 'tool' | 'obstacle';
  color: string | null;
  pose_source: 'assumed_default' | 'perception' | 'user_specified';
}

export interface CapabilityClaim {
  name: string;
  confidence: number;
  verified: boolean;
  source: 'declared' | 'unimplemented';
}

export interface RoboIR {
  ir_version: string;
  skill: { id: string; version: string };
  source: { raw_instruction: string; parser: string };
  intent: { action: string };
  objects: RoboIRObject[];
  constraints: { payload_kg: number | null; precision_mm: number | null };
  required_capabilities: {
    perception: string[];
    manipulation: string[];
    sensing: string[];
    claims: CapabilityClaim[];
  };
  execution: { robot_id: string; dof: number; planner: string; controller: string };
  verification: { collision_check: boolean; simulation_required: boolean; safety_checks: string[] };
  program: {
    object_name: string;
    parameters: Record<string, unknown>;
    confidence: number;
    parse_warnings: string[];
    tasks: { type: string; description: string; parameters: Record<string, unknown> }[];
    behavior_tree: { type: string; name: string; children: unknown[] };
  } | null;
  lowering: {
    robot_id: string;
    joint_names: string[];
    ik_solutions: {
      task_description: string;
      joint_angles: number[];
      target_position: number[];
      residual_m: number;
      iterations: number;
      success: boolean;
    }[];
    trajectories: {
      task_description: string;
      start_pose: number[];
      end_pose: number[];
      waypoints: number[][];
      duration_s: number;
    }[];
    motion_model: string;
    scene_digest: string | null;
    legalization_trace: string[];
  } | null;
}

export interface NativeMLIREvidence {
  status: 'succeeded' | 'unavailable' | 'disabled';
  executable: string | null;
  version: string | null;
  pass_pipeline: string[];
  input_sha256: string;
  output_sha256: string | null;
  detail: string | null;
}

/**
 * Real cross-robot RoboIR diff -- mirrors `ir/diff.py::IRDiff`. `field_changes`
 * values are always `[before, after]` pairs. Per-pass diffing (comparing a single
 * compile's own pipeline trace) is deliberately not exposed this way: the three
 * registered RoboIR passes are diagnostics-only today, so that comparison would
 * show "no differences" for almost every real compile -- this type only ever
 * backs the honest, substantive cross-robot comparison (`GET /api/diff`).
 */
export interface IRDiffResult {
  instruction: string;
  from_robot: string;
  to_robot: string;
  field_changes: Record<string, [unknown, unknown]>;
  objects_added: RoboIRObject[];
  objects_removed: RoboIRObject[];
  objects_changed: { before: RoboIRObject; after: RoboIRObject }[];
  explanation?: string | null;
  explanation_model?: string;
  explanation_latency_s?: number;
  explanation_error?: string | null;
}

export interface CompilerDiagnostic {
  code: string;
  severity: 'error' | 'warning';
  message: string;
  reason: string;
  required_capability: string | null;
  fixes: string[];
}

export interface CompiledSkillResult {
  instruction: string;
  robot: string;
  intent: {
    action: string;
    object_name: string;
    parameters: Record<string, unknown>;
    confidence: number;
  };
  tasks: { type: string; description: string }[];
  behavior_tree_xml: string;
  ir: RoboIR;
  diagnostics: CompilerDiagnostic[];
  native_mlir: NativeMLIREvidence | null;
  /** Only present when compiled with `?explain_passes=1`. */
  pipeline?: PipelineTraceResult;
  /** Only present when compiled with `?explain_passes=1`. */
  skill_pipeline?: PipelineTraceResult;
  /** Present only when compiled with `?explain=1`; null means Ollama was unavailable. */
  explanation?: string | null;
  explanation_model?: string;
  explanation_latency_s?: number;
  explanation_error?: string | null;
  /** Present only when compiled with `?explain_mlir=1` and native_mlir evidence
   * exists; cascade-backed (Ollama -> Gemini -> OpenRouter), read-only summary
   * of the real emitted MLIR text and recorded mlir-opt evidence. */
  mlir_explanation?: string | null;
  mlir_explanation_provider?: string;
  mlir_explanation_model?: string;
  mlir_explanation_error?: string | null;
  mlir_explanation_cache_hit?: boolean;
}

export interface UniversalCompileMatrix {
  instruction: string;
  source_digest: string;
  portable: {
    action: string;
    object_name: string;
    parameters: Record<string, unknown>;
    confidence: number;
    warnings: string[];
    tasks: { type: string; description: string; parameters: Record<string, unknown> }[];
  };
  targets: Record<string, CompiledSkillResult>;
  failures: Record<string, CompilerDiagnostic[]>;
}

export class CompilationFailedError extends Error {
  diagnostics: CompilerDiagnostic[];
  constructor(diagnostics: CompilerDiagnostic[]) {
    super(diagnostics.map((d) => d.message).join('; '));
    this.diagnostics = diagnostics;
  }
}

export interface RobotJointSpec {
  name: string;
  type: string;
  axis: [number, number, number];
  lower_limit: number;
  upper_limit: number;
}

export interface RobotLinkSpec {
  name: string;
  length: number;
  mass: number;
}

export interface RobotModel {
  id: string;
  name: string;
  dof: number;
  base_height_m: number;
  max_reach_m: number;
  motion_model: RobotProfile['motion_model'];
  kinematic_chains: Record<string, number[]>;
  collision_radius_m: number;
  joints: RobotJointSpec[];
  links: RobotLinkSpec[];
}

export interface RobotFKResult {
  id: string;
  q: number[];
  positions: [number, number, number][];
}

/**
 * A robot or simulator endpoint found by a real TCP probe from
 * `RobotDiscoveryService` (src/roboweaver/hardware/discovery.py).
 * Every entry corresponds to a socket that actually answered — nothing here
 * is fabricated, so an empty `discovered` list genuinely means nothing is
 * listening, not that the scan failed.
 */
export interface DiscoveredRobot {
  name: string;
  host: string;
  port: number;
  protocol: string;
  description: string;
  reachable: boolean;
  latency_ms: number;
  robot_type_guess: string;
  /** 0-1. Low when the port is one ordinary desktop software commonly holds. */
  confidence: number;
  /** Non-empty when identification is unreliable; explains why. */
  caveat: string;
  /** Bytes the service volunteered on connect — real evidence of what is there. */
  banner: string;
  /** Reverse-DNS name, when the resolver returns one. */
  hostname: string;
}

/**
 * A local, non-IP path to a robot — serial/RS-485, SocketCAN, or a Unix domain
 * socket. These are what exist when the machine has no TCP route to the robot
 * at all.
 */
export interface LocalTransport {
  kind: 'serial' | 'can' | 'unix_socket';
  device: string;
  description: string;
  available: boolean;
  readable: boolean;
  detail: string;
}

export interface DiscoveryResult {
  discovered: DiscoveredRobot[];
  scan_duration_ms: number;
  hosts_scanned: number;
  ports_scanned: number;
  local_transports: LocalTransport[];
  platform_name: string;
  /** Transport kinds this OS can actually be scanned for (CAN is Linux-only). */
  supported_transports: string[];
  /** CIDR actually swept, or '' when only this machine was checked. */
  scanned_range: string;
}

export interface NetworkRange {
  cidr: string;
  interface_ip: string;
  interface_name: string;
  /** 'interface' when read from the OS, 'assumed_/24' when inferred. */
  netmask_source: string;
  host_count: number;
}

export interface AdvisorStatus {
  ollama_available: boolean;
  ollama_host: string;
  ollama_model: string;
  openrouter_configured: boolean;
  openrouter_model: string;
  openrouter_codegen_model: string;
  providers: string[];
  supported_protocols: string[];
  remote_privacy_notice: string;
}

/**
 * Real process facts from the running backend — `roboweaver_version` is read
 * straight off `roboweaver.__version__` (in sync with pyproject.toml) and
 * `ir_version` off RoboIR's own dataclass field, not duplicated literals that
 * could drift. `uptime_seconds` resets on every self-healing restart, since
 * that's a fresh server instance, not the same one that's been up forever.
 */
export interface VersionInfo {
  roboweaver_version: string;
  ir_version: string;
  python_version: string;
  platform: string;
  self_healing_active: boolean;
  uptime_seconds: number | null;
  registered_robots: number;
  native_mlir: {
    mode: string;
    available: boolean;
    executable: string | null;
    version: string | null;
  };
}

export interface AccessInfo {
  mode: 'local' | 'lan';
  compiler_access: boolean;
  hardware_control: boolean;
  backend_token_exposed: false;
  host_validated: boolean;
}

export interface NetworkInfo {
  ranges: NetworkRange[];
  max_scan_hosts: number;
  advisor: AdvisorStatus;
}

/**
 * An LLM's suggested driver binding. `robot_id` is null whenever the advice was
 * rejected — the backend validates against the real registry, so a hallucinated
 * id never reaches here as a suggestion.
 */
export interface ConnectionAdvice {
  robot_id: string | null;
  protocol: string | null;
  uri: string | null;
  reasoning: string;
  confidence: number;
  provider: string;
  model: string;
  error: string | null;
}

/**
 * Outcome of `POST /api/connect`. The backend answers 400 with
 * `{ error, is_connected: false }` when the bridge can't be established, so
 * `error` and `is_connected` are the two fields worth branching on.
 */
export interface ConnectionResult {
  robot_id?: string;
  is_connected: boolean;
  protocol?: string;
  dof?: number;
  active_controllers?: string[];
  latency_ms?: number;
  message?: string;
  error?: string;
}

export interface ConnectionCodeResult {
  robot_id: string;
  protocol: string;
  filename: string;
  /** Deterministic adapter. This is always the authoritative generated source. */
  code: string;
  environment: Record<string, string>;
  safety_notes: string[];
  /** Optional model annotation; never replaces `code`. */
  annotated_code: string | null;
  issues: string[];
  suggestions: string[];
  provider: 'none' | 'ollama' | 'openrouter';
  model: string;
  latency_s: number;
  ai_error: string | null;
}

export interface SimObjectProfile {
  id: string;
  name: string;
  diameter_mm: number;
  compatible_gestures: string[];
  min_hold_force_n: number;
  max_safe_force_n: number;
}

export interface SimulateResult {
  gesture: string;
  object: string;
  is_simulated: boolean;
  connect_fallback_reason: string | null;
  actuator_positions: number[];
  actuator_currents_ma: number[];
  actuator_forces_n: number[];
  total_force_n: number;
  object_name: string | null;
  object_status: string;
  stability_score: number;
  slip_risk: number;
}

/**
 * One row of a pass-manager trace: what one real compiler pass did.
 * `timing_s` is measured by the PassManager around the pass's `run()` call, not
 * self-reported, mirroring `ir/pass_manager.py::PassRecord.to_dict()` and
 * `optimize/pass_manager.py::SkillPassRecord.to_dict()` (identical shape).
 */
export interface PassRecordResult {
  pass_name: string;
  generation: number;
  modified: boolean;
  skipped: boolean;
  timing_s: number;
  diagnostic_count: number;
  diagnostics: CompilerDiagnostic[];
  metrics: Record<string, number>;
}

/**
 * A full PassManager.run() trace -- generation 0 is the IR/skill before any pass
 * ran. Mirrors `PipelineTrace.to_dict()` (RoboIR passes) and
 * `SkillPipelineTrace.to_dict()` (CompiledSkill passes); both produce this same shape.
 */
export interface PipelineTraceResult {
  generations: number;
  total_timing_s: number;
  diagnostic_count: number;
  passes: PassRecordResult[];
}

/**
 * Real cost figures computed from an already-compiled skill -- nothing estimated
 * beyond what the compile pipeline produced. `historical_success_rate` is only
 * ever a real number from ExecutionMemoryStore, never fabricated when null.
 * Mirrors `optimize/cost_model.py::CompiledSkillCost`.
 */
export interface CompiledSkillCostResult {
  estimated_cycle_time_s: number;
  payload_margin_kg: number;
  total_joint_travel_rad: number;
  manipulability_margin: number;
  historical_success_rate: number | null;
}

export interface RobotRankingEntry {
  robot: string;
  score: number;
  cost: CompiledSkillCostResult;
}

/**
 * Mirrors `optimize/cost_model.py::compare_robots()`'s real weighted ranking +
 * Pareto-optimal subset. `skipped` reports the real compilation-blocking reason
 * for a robot that genuinely can't run this instruction, never a silent drop.
 */
export interface RobotComparisonResult {
  instruction: string;
  ranked: RobotRankingEntry[];
  pareto_optimal: string[];
  skipped: Record<string, string>;
  /** 'explicit' when the caller named robots; 'knowledge_graph' when they were
   * omitted and the real graph's SUITABLE_FOR edges supplied the candidates. */
  candidate_source: 'explicit' | 'knowledge_graph';
}

export interface BenchmarkCellResult {
  category: string;
  robot_id: string;
  instruction: string;
  success: boolean;
  compile_time_s: number;
  error_count: number;
  warning_count: number;
  waypoint_pct_reduction: number | null;
  failure_reason: string | null;
}

/** Mirrors `benchmark/robobench.py::BenchmarkReport.to_dict()` -- real compile-time
 * measurement across a scope of skill categories x registered robots, not
 * simulator-execution benchmarking. */
export interface BenchmarkReportResult {
  scope: string;
  total_cells: number;
  success_count: number;
  total_compile_time_s: number;
  cells: BenchmarkCellResult[];
}

export interface KnowledgeGraphNode {
  id: string;
  name: string;
  type: string;
  properties: Record<string, unknown>;
}

export interface KnowledgeGraphEdge {
  source_id: string;
  target_id: string;
  relation: string;
  properties: Record<string, unknown>;
}

/** Mirrors `knowledge/graph.py::RoboticsKnowledgeGraph.to_dict()`, built from the
 * live registries (`knowledge/ingest_registry.py`) -- real robots, packages, and
 * NL-reachable skills, not the old hand-seeded demo graph. */
export interface KnowledgeGraphResult {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
}

/** `path` is null when `find_path()` genuinely found no route within max_hops --
 * never a fabricated connection. */
export interface GraphPathResult {
  from: string;
  to: string;
  path: string[] | null;
}

// ── AI / Ollama Types ──────────────────────────────────────────────

export interface AIModelInfo {
  name: string;
  size_bytes: number;
  parameter_size: string;
  quantization: string;
}

/** Full Ollama status from `/api/ai/status`. */
export interface AIStatusResult {
  available: boolean;
  host: string;
  version: string | null;
  default_model: string;
  feature_models: Record<string, string>;
  recommendations: Record<string, string>;
  models: AIModelInfo[];
  avg_latency_s: number | null;
  total_calls: number;
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  error: string | null;
}

/** AI-generated explanation of a compiled skill. */
export interface AIExplanationResult {
  instruction: string;
  robot: string;
  explanation: string | null;
  model: string;
  latency_s: number;
  error: string | null;
}

/** AI-enriched recovery advice for a runtime failure. */
export interface AIDiagnoseResult {
  failure_mode: string;
  robot: string;
  rule_based_action: string;
  rule_based_reason: string;
  ai_explanation: string | null;
  ai_root_cause: string | null;
  fix_description: string | null;
  confidence: number | null;
  suggested_parameter_changes: Record<string, unknown> | null;
  model: string;
  latency_s: number;
  error: string | null;
}

export interface ComposedStepResult {
  step_id: string;
  instruction: string;
  action: string;
  target_object: string;
  suggested_robot: string | null;
  depends_on: string[];
  reasoning: string;
}

/** AI-decomposed skill composition. */
export interface AIComposeResult {
  original_instruction: string;
  steps: ComposedStepResult[];
  suggested_robots: string[];
  choreography_prompt: string;
  model: string;
  latency_s: number;
  error: string | null;
}

/** AI chat response. */
export interface AIChatResult {
  message: string;
  response: string | null;
  model: string;
  latency_s: number;
  error: string | null;
}

export interface AIModelsResult {
  available: boolean;
  models: AIModelInfo[];
}

export interface AIEdgeSuggestion {
  robot_id: string;
  skill_category: string;
  confidence: number;
  reasoning: string;
}

export interface AIEnrichmentResult {
  mode: 'edges' | 'describe' | 'pairings' | 'summary';
  suggestions?: AIEdgeSuggestion[];
  descriptions?: Array<{
    robot_id: string;
    summary: string;
    strengths: string[];
    limitations: string[];
    ideal_tasks: string[];
  }>;
  pairings?: Array<{
    robot_a: string;
    robot_b: string;
    reasoning: string;
    suggested_tasks: string[];
  }>;
  summaries?: Array<{ node_id: string; summary: string }>;
  model: string;
  latency_s: number;
  error: string | null;
}

export interface AIModelMutationResult {
  success: boolean;
  model: string;
  feature?: string;
  message?: string;
}

export interface ResearchProviderStatus {
  configured: boolean;
  available?: boolean;
  model: string;
  experiment_model?: string;
  remote: boolean;
}

export interface ResearchStatusResult {
  providers: Record<'ollama' | 'gemini' | 'openrouter', ResearchProviderStatus>;
  cascade: string[];
  max_attempts: number;
  sandbox: {
    profile: string;
    network: string;
    root_filesystem: string;
    devices: string;
    command: string;
    physics_adapter: string;
    physics_adapter_scope: string;
  };
  boundaries: {
    model_code_execution: boolean;
    physical_hardware: boolean;
    cache_safety_revalidation: boolean;
    prompt_storage: boolean;
  };
}

export interface ExperimentLink {
  name: string;
  shape: 'box' | 'cylinder' | 'sphere' | 'capsule';
  size_m: [number, number, number];
  mass_kg: number;
}

export interface ExperimentJoint {
  name: string;
  parent: string;
  child: string;
  joint_type: 'fixed' | 'revolute' | 'continuous' | 'prismatic';
  axis: [number, number, number];
  lower: number;
  upper: number;
  effort: number;
  velocity: number;
}

export interface ExperimentPlanResult {
  spec: {
    name: string;
    objective: string;
    embodiment_class: string;
    links: ExperimentLink[];
    joints: ExperimentJoint[];
    sensors: string[];
    training: {
      algorithm: string;
      observation_terms: string[];
      reward_terms: string[];
      termination_terms: string[];
      max_steps: number;
    };
  };
  provider: string;
  model: string;
  attempts: number;
  cache_hit: boolean;
  ai_error: string | null;
  artifacts: Record<string, string>;
  artifact_sha256: Record<string, string>;
  safety: {
    schema_validated: boolean;
    python_ast_validated: boolean;
    model_authored_code_executed: boolean;
    physical_hardware_allowed: boolean;
    external_network_allowed: boolean;
    limitations: string[];
  };
  sandbox: {
    runner: string;
    network: string;
    root_filesystem: string;
    capabilities: string;
    devices: string;
    pids_limit: number;
    memory_limit: string;
    cpu_limit: number;
    command: string;
    status: string;
    physics_adapter: string;
  };
}

export interface ModelCallTrace {
  trace_id: string;
  parent_id: string;
  timestamp: number;
  feature: string;
  provider: string;
  requested_model: string;
  actual_model: string;
  attempt: number;
  status: 'succeeded' | 'failed' | 'cache_hit' | 'blocked';
  latency_s: number;
  input_chars: number;
  output_chars: number;
  token_count: number | null;
  error_category: string | null;
  error_message: string | null;
  cache_key: string | null;
}

export interface ObservabilityResult {
  traces: {
    privacy: string;
    totals: {
      traces: number;
      requests: number;
      succeeded: number;
      failed: number;
      blocked: number;
      cache_hits: number;
      tokens: number;
    };
    success_rate: number | null;
    cache_hit_rate: number;
    p95_latency_s: number | null;
    providers: Record<string, number>;
    recent: ModelCallTrace[];
  };
  cache: {
    entries: number;
    max_entries: number;
    ttl_seconds: number;
    hits: number;
    misses: number;
    evictions: number;
  };
  implementation: string;
}

export interface ResearchEvaluationResult {
  benchmark_version: string;
  passed: number;
  total: number;
  elapsed_s: number;
  metrics: Array<{
    name: 'compilation_success' | 'diagnostic_precision' | 'determinism' | 'target_portability' | 'runtime_correctness' | 'planning_performance';
    passed: boolean;
    value: number | string | boolean;
    evidence: Record<string, unknown>;
  }>;
  limitations: string[];
}
