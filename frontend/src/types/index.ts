export type TabType =
  | 'dashboard'
  | 'compiler'
  | 'builder'
  | 'nexus'
  | 'graph'
  | 'fleet'
  | 'connect'
  | 'simulation'
  | 'activity'
  | 'settings';

export interface RobotProfile {
  id: string;
  name: string;
  manufacturer: string;
  dof: number;
  payload_capacity_kg: number;
  max_reach_m: number;
  gripper_type: string;
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

export interface RoboIR {
  ir_version: string;
  skill: { id: string; version: string };
  source: { raw_instruction: string; parser: string };
  intent: { action: string };
  objects: RoboIRObject[];
  constraints: { payload_kg: number | null; precision_mm: number | null };
  required_capabilities: { perception: string[]; manipulation: string[]; sensing: string[] };
  execution: { robot_id: string; dof: number; planner: string; controller: string };
  verification: { collision_check: boolean; simulation_required: boolean; safety_checks: string[] };
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
  };
  tasks: { type: string; description: string }[];
  behavior_tree_xml: string;
  ir: RoboIR;
  diagnostics: CompilerDiagnostic[];
  /** Only present when compiled with `?explain_passes=1`. */
  pipeline?: PipelineTraceResult;
  /** Only present when compiled with `?explain_passes=1`. */
  skill_pipeline?: PipelineTraceResult;
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
  anthropic_configured: boolean;
  anthropic_model: string;
  openai_configured: boolean;
  openai_model: string;
  max_output_tokens: number;
  /** Providers that cost nothing to call. */
  free_providers: string[];
  supported_protocols: string[];
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
 * Outcome of `GET /api/connect`. The backend answers 400 with
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
