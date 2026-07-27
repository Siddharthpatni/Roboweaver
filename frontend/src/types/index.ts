export type TabType = 'dashboard' | 'compiler' | 'builder' | 'nexus' | 'fleet' | 'simulation' | 'activity' | 'settings';

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
