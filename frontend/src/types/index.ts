export type TabType = 'dashboard' | 'incidents' | 'nexus' | 'simulation' | 'activity' | 'settings';

export interface WorkflowStep {
  id: number;
  label: string;
  status: 'completed' | 'running' | 'approved' | 'rejected' | 'pending';
  timestamp?: string;
  detail?: string;
}

export interface Incident {
  id: string;
  title: string;
  service: string;
  rootCause: string;
  timestamp: string;
  status: 'pending_review' | 'approved' | 'rejected' | 'escalated';
  baseCode: string;
  proposedCode: string;
  filePath: string;
  tokenCount: number;
  processingTime: string;
  riskScore: string;
  riskLevel: 'Low' | 'Medium' | 'High';
  steps: WorkflowStep[];
}

export interface RoboticsPackage {
  id: string;
  name: string;
  repo: string;
  category: 'Navigation' | 'Manipulation' | 'Perception' | 'Fleet Control' | 'Hardware Driver';
  rosDistro: string;
  description: string;
  topics: string[];
  dependencies: string[];
  status: 'Ready' | 'Active' | 'Optimizing' | 'Warning';
  stars: number;
}

export interface SimHandFinger {
  name: string;
  angleDeg: number;
  forceN: number;
  targetN: number;
  contact: boolean;
}

export interface SimRobotState {
  id: string;
  name: string;
  model: string;
  bus: string;
  protocol: string;
  graspState: 'Open' | 'Precision Grip' | 'Pinch' | 'Power Grasp';
  slipRiskPercentage: number;
  fingers: SimHandFinger[];
  jointAngles: number[];
  temperature: number;
  voltage: number;
}
