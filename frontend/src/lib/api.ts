import {
  RobotProfile,
  NexusPackage,
  NexusRecommendation,
  WorkcellBuildResult,
  CompiledSkillResult,
  SimObjectProfile,
  SimulateResult,
  CompilationFailedError,
  RobotModel,
  RobotFKResult,
} from '../types';

const API_BASE = process.env.NEXT_PUBLIC_ROBOWEAVER_API ?? 'http://localhost:8080';

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`RoboWeaver API ${path} responded ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function compileJSON(path: string): Promise<CompiledSkillResult> {
  const res = await fetch(`${API_BASE}${path}`);
  const body = await res.json();
  if (!res.ok) {
    if (body && body.error === 'compilation_failed') {
      throw new CompilationFailedError(body.diagnostics);
    }
    throw new Error(`RoboWeaver API ${path} responded ${res.status}`);
  }
  return body as CompiledSkillResult;
}

export const RoboWeaverAPI = {
  baseUrl: API_BASE,
  robots: () => getJSON<RobotProfile[]>('/api/robots'),
  nexusPackages: () => getJSON<NexusPackage[]>('/api/nexus/packages'),
  nexusRecommend: (prompt: string) =>
    getJSON<NexusRecommendation>(`/api/nexus/recommend?prompt=${encodeURIComponent(prompt)}`),
  build: (prompt: string) =>
    getJSON<WorkcellBuildResult>(`/api/build?prompt=${encodeURIComponent(prompt)}`),
  compile: (instruction: string, robot: string = 'franka_panda') =>
    compileJSON(`/api/compile?instruction=${encodeURIComponent(instruction)}&robot=${encodeURIComponent(robot)}`),
  simulateGestures: () => getJSON<string[]>('/api/simulate/gestures'),
  simulateObjects: () => getJSON<SimObjectProfile[]>('/api/simulate/objects'),
  simulate: (gesture: string, object: string) =>
    getJSON<SimulateResult>(`/api/simulate?gesture=${encodeURIComponent(gesture)}&object=${encodeURIComponent(object)}`),
  robotModel: (id: string) => getJSON<RobotModel>(`/api/robots/${encodeURIComponent(id)}/model`),
  robotFK: (id: string, q: number[]) =>
    getJSON<RobotFKResult>(`/api/robots/${encodeURIComponent(id)}/fk?q=${q.join(',')}`),
};
