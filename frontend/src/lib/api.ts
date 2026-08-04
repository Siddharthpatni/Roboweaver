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
  DiscoveryResult,
  ConnectionResult,
  NetworkInfo,
  ConnectionAdvice,
  DiscoveredRobot,
  VersionInfo,
  CompiledSkillCostResult,
  RobotComparisonResult,
  BenchmarkReportResult,
  KnowledgeGraphResult,
  GraphPathResult,
} from '../types';

const API_BASE = process.env.NEXT_PUBLIC_ROBOWEAVER_API ?? 'http://localhost:8080';

// Every call site below picks one of these explicitly rather than relying on a
// single default: a LAN sweep or an LLM call legitimately takes far longer than
// a registry lookup, and a client that gives up too early or waits forever are
// both wrong. Before this existed, no fetch() in the app had ANY timeout --
// if the backend ever hung, the UI spun forever with no way out.
const TIMEOUT_FAST_MS = 8_000; // registry lookups, simple queries
const TIMEOUT_SCAN_MS = 30_000; // LAN subnet sweep (backend caps at 1024 hosts)
const TIMEOUT_LLM_MS = 60_000; // must exceed the backend's own 45s provider timeout
const TIMEOUT_CONNECT_MS = 15_000; // TCP/ROS2 bridge probes

/** Raised when the client gives up before the server responds. Distinguished
 * from a generic network error so the UI can say "took too long", not just
 * "failed" -- those need different next steps for the user. */
export class TimeoutError extends Error {
  constructor(path: string, ms: number) {
    super(`RoboWeaver API ${path} did not respond within ${Math.round(ms / 1000)}s.`);
    this.name = 'TimeoutError';
  }
}

async function fetchWithTimeout(path: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(`${API_BASE}${path}`, { signal: controller.signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new TimeoutError(path, timeoutMs);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

async function getJSON<T>(path: string, timeoutMs: number = TIMEOUT_FAST_MS): Promise<T> {
  const res = await fetchWithTimeout(path, timeoutMs);
  if (!res.ok) {
    throw new Error(`RoboWeaver API ${path} responded ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function compileJSON(path: string): Promise<CompiledSkillResult> {
  const res = await fetchWithTimeout(path, TIMEOUT_FAST_MS);
  const body = await res.json();
  if (!res.ok) {
    if (body && body.error === 'compilation_failed') {
      throw new CompilationFailedError(body.diagnostics);
    }
    throw new Error(`RoboWeaver API ${path} responded ${res.status}`);
  }
  return body as CompiledSkillResult;
}

/**
 * `/api/connect` reports a failed bridge as HTTP 400 with a real explanation in
 * the body (`{ error, is_connected: false }`). Surfacing that message is the
 * whole point of the honest-hardware path, so a 400 is parsed and returned
 * rather than collapsed into a generic "responded 400" throw. Only a genuine
 * transport failure (backend down, or timeout) rejects.
 */
async function connectJSON(path: string): Promise<ConnectionResult> {
  const res = await fetchWithTimeout(path, TIMEOUT_CONNECT_MS);
  const body = (await res.json()) as ConnectionResult;
  if (!res.ok && body && typeof body.is_connected === 'boolean') {
    return body;
  }
  if (!res.ok) {
    throw new Error(`RoboWeaver API ${path} responded ${res.status}`);
  }
  return body;
}

export const RoboWeaverAPI = {
  baseUrl: API_BASE,
  robots: () => getJSON<RobotProfile[]>('/api/robots'),
  nexusPackages: () => getJSON<NexusPackage[]>('/api/nexus/packages'),
  nexusRecommend: (prompt: string) =>
    getJSON<NexusRecommendation>(`/api/nexus/recommend?prompt=${encodeURIComponent(prompt)}`),
  build: (prompt: string) =>
    getJSON<WorkcellBuildResult>(`/api/build?prompt=${encodeURIComponent(prompt)}`),
  compile: (instruction: string, robot: string = 'franka_panda', explainPasses: boolean = false) =>
    compileJSON(
      `/api/compile?instruction=${encodeURIComponent(instruction)}&robot=${encodeURIComponent(robot)}` +
        (explainPasses ? '&explain_passes=1' : '')
    ),
  /** Real cost figures for one instruction on one robot (optimize/cost_model.py). */
  cost: (instruction: string, robot: string = 'franka_panda') =>
    getJSON<CompiledSkillCostResult>(
      `/api/cost?instruction=${encodeURIComponent(instruction)}&robot=${encodeURIComponent(robot)}`
    ),
  /** Compiles the same instruction across multiple robots and ranks them by real
   * cost (optimize/cost_model.py::compare_robots()). Omit `robots` (or pass an
   * empty array) to let the real knowledge graph suggest candidates instead --
   * the response's `candidate_source` says which happened. */
  compare: (instruction: string, robots?: string[]) =>
    getJSON<RobotComparisonResult>(
      `/api/compare?instruction=${encodeURIComponent(instruction)}` +
        (robots && robots.length ? `&robots=${encodeURIComponent(robots.join(','))}` : ''),
      TIMEOUT_SCAN_MS
    ),
  /** Real compile-time benchmark (benchmark/robobench.py::run_benchmark()) --
   * defaults to a small robot subset server-side to keep a live call fast. */
  benchmark: (robots?: string[]) =>
    getJSON<BenchmarkReportResult>(
      `/api/benchmark${robots && robots.length ? `?robots=${encodeURIComponent(robots.join(','))}` : ''}`,
      TIMEOUT_SCAN_MS
    ),
  /** Real knowledge graph built from the live registries (knowledge/ingest_registry.py). */
  graph: () => getJSON<KnowledgeGraphResult>('/api/graph'),
  /** Real BFS shortest path between two graph node ids; `path` is null when
   * genuinely unreachable within max_hops. */
  graphPath: (from: string, to: string) =>
    getJSON<GraphPathResult>(`/api/graph/path?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),
  /** Downloads the same real Obsidian vault `roboweaver graph export-obsidian`
   * produces on the CLI -- one .md file per real node, cross-linked with
   * real [[wikilinks]] -- as a zip, generated server-side into a temp dir. */
  graphExportObsidian: async (): Promise<Blob> => {
    const res = await fetchWithTimeout('/api/graph/export-obsidian', TIMEOUT_SCAN_MS);
    if (!res.ok) {
      throw new Error(`RoboWeaver API /api/graph/export-obsidian responded ${res.status}`);
    }
    return res.blob();
  },
  simulateGestures: () => getJSON<string[]>('/api/simulate/gestures'),
  simulateObjects: () => getJSON<SimObjectProfile[]>('/api/simulate/objects'),
  simulate: (gesture: string, object: string) =>
    getJSON<SimulateResult>(`/api/simulate?gesture=${encodeURIComponent(gesture)}&object=${encodeURIComponent(object)}`),
  discover: (host?: string) =>
    getJSON<DiscoveryResult>(`/api/discover${host ? `?host=${encodeURIComponent(host)}` : ''}`),
  /** Sweep an entire CIDR range. The backend refuses ranges above its host cap. */
  discoverSubnet: (subnet: string) =>
    getJSON<DiscoveryResult>(`/api/discover?subnet=${encodeURIComponent(subnet)}`, TIMEOUT_SCAN_MS),
  network: () => getJSON<NetworkInfo>('/api/network'),
  version: () => getJSON<VersionInfo>('/api/version'),
  /** Ask an LLM to map a discovered endpoint onto a registry robot + protocol. */
  adviseConnection: (robot: DiscoveredRobot, provider: string, model?: string) =>
    getJSON<ConnectionAdvice>(
      `/api/connect/advise?host=${encodeURIComponent(robot.host)}` +
        `&port=${robot.port}` +
        `&banner=${encodeURIComponent(robot.banner ?? '')}` +
        `&hostname=${encodeURIComponent(robot.hostname ?? '')}` +
        `&guess=${encodeURIComponent(robot.robot_type_guess ?? '')}` +
        `&latency=${robot.latency_ms}` +
        `&provider=${encodeURIComponent(provider)}` +
        (model ? `&model=${encodeURIComponent(model)}` : ''),
      TIMEOUT_LLM_MS
    ),
  connectRobot: (robot: string, protocol: string, uri: string) =>
    connectJSON(
      `/api/connect?robot=${encodeURIComponent(robot)}&protocol=${encodeURIComponent(
        protocol
      )}&uri=${encodeURIComponent(uri)}`
    ),
  robotModel: (id: string) => getJSON<RobotModel>(`/api/robots/${encodeURIComponent(id)}/model`),
  /** Downloads the URDF text derived from the robot's real kinematic spec — not
   * an LLM-generated mesh; see codegen/urdf_gen.py for why. */
  robotUrdf: async (id: string): Promise<string> => {
    const res = await fetchWithTimeout(`/api/robots/${encodeURIComponent(id)}/urdf`, TIMEOUT_FAST_MS);
    if (!res.ok) {
      throw new Error(`RoboWeaver API /api/robots/${id}/urdf responded ${res.status}`);
    }
    return res.text();
  },
  robotFK: (id: string, q: number[]) =>
    getJSON<RobotFKResult>(`/api/robots/${encodeURIComponent(id)}/fk?q=${q.join(',')}`),
};
