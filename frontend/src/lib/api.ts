import {
  RobotProfile,
  NexusPackage,
  NexusRecommendation,
  WorkcellBuildResult,
  CompiledSkillResult,
  UniversalCompileMatrix,
  SimObjectProfile,
  SimulateResult,
  CompilationFailedError,
  RobotModel,
  RobotFKResult,
  DiscoveryResult,
  ConnectionResult,
  ConnectionCodeResult,
  NetworkInfo,
  ConnectionAdvice,
  DiscoveredRobot,
  VersionInfo,
  CompiledSkillCostResult,
  RobotComparisonResult,
  BenchmarkReportResult,
  KnowledgeGraphResult,
  GraphPathResult,
  IRDiffResult,
  AIStatusResult,
  AIExplanationResult,
  AIDiagnoseResult,
  AIComposeResult,
  AIChatResult,
  AIModelsResult,
  AIEnrichmentResult,
  AIModelMutationResult,
  AccessInfo,
  ExperimentPlanResult,
  ObservabilityResult,
  ResearchStatusResult,
  ResearchEvaluationResult,
} from '../types';

// Same-origin by default: the Next.js server route attaches the backend token,
// so it is never compiled into browser JavaScript. Direct API access remains an
// explicit local-development override only.
const API_BASE = process.env.NEXT_PUBLIC_ROBOWEAVER_API ?? '/api/roboweaver';

// Every call site below picks one of these explicitly rather than relying on a
// single default: a LAN sweep or an LLM call legitimately takes far longer than
// a registry lookup, and a client that gives up too early or waits forever are
// both wrong. Before this existed, no fetch() in the app had ANY timeout --
// if the backend ever hung, the UI spun forever with no way out.
const TIMEOUT_FAST_MS = 8_000; // registry lookups, simple queries
const TIMEOUT_SCAN_MS = 30_000; // LAN subnet sweep (backend caps at 1024 hosts)
const TIMEOUT_LLM_MS = 60_000; // must exceed the backend's own 45s provider timeout
const TIMEOUT_CODEGEN_MS = 70_000; // one bounded provider review plus adapter generation
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

async function fetchWithTimeout(
  path: string,
  timeoutMs: number,
  init: RequestInit = {}
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(`${API_BASE}${path}`, { ...init, signal: controller.signal });
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
  const body = await res.json();
  if (!res.ok) {
    const diagnostics = Array.isArray(body?.diagnostics)
      ? body.diagnostics.map((item: { code?: string; message?: string }) =>
          `${item.code ?? 'error'}: ${item.message ?? 'Compilation failed'}`).join(' ')
      : null;
    throw new Error(diagnostics ?? body?.error ?? `RoboWeaver API ${path} responded ${res.status}`);
  }
  return body as T;
}

async function compileJSON(path: string, timeoutMs: number = TIMEOUT_FAST_MS): Promise<CompiledSkillResult> {
  const res = await fetchWithTimeout(path, timeoutMs);
  const body = await res.json();
  if (!res.ok) {
    if (body && body.error === 'compilation_failed') {
      throw new CompilationFailedError(body.diagnostics);
    }
    throw new Error(`RoboWeaver API ${path} responded ${res.status}`);
  }
  return body as CompiledSkillResult;
}

async function postJSON<T>(path: string, payload: Record<string, unknown>, timeoutMs = TIMEOUT_FAST_MS): Promise<T> {
  const res = await fetchWithTimeout(path, timeoutMs, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body?.error ?? body?.message ?? `RoboWeaver API ${path} responded ${res.status}`);
  }
  return body as T;
}

async function streamAIChat(
  message: string,
  onToken: (token: string) => void,
): Promise<AIChatResult> {
  const path = `/api/ai/chat?stream=1&message=${encodeURIComponent(message)}`;
  const res = await fetchWithTimeout(path, TIMEOUT_LLM_MS);
  if (!res.ok || !res.body) {
    throw new Error(`RoboWeaver API ${path} responded ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let response = '';
  let model = '';
  let latency_s = 0;
  let error: string | null = null;

  const consume = (line: string) => {
    if (!line.trim()) return;
    const chunk = JSON.parse(line) as {
      token?: string; done?: boolean; model?: string; latency_s?: number; error?: string | null;
    };
    if (chunk.token) {
      response += chunk.token;
      onToken(chunk.token);
    }
    if (chunk.model) model = chunk.model;
    if (chunk.latency_s != null) latency_s = chunk.latency_s;
    if (chunk.error) error = chunk.error;
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) consume(line);
    if (done) break;
  }
  consume(buffer);
  return { message, response: response || null, model, latency_s, error };
}

/**
 * `/api/connect` reports a failed bridge as HTTP 400 with a real explanation in
 * the body (`{ error, is_connected: false }`). Surfacing that message is the
 * whole point of the honest-hardware path, so a 400 is parsed and returned
 * rather than collapsed into a generic "responded 400" throw. Only a genuine
 * transport failure (backend down, or timeout) rejects.
 */
async function connectJSON(payload: {
  robot: string;
  protocol: string;
  uri: string;
}): Promise<ConnectionResult> {
  const res = await fetchWithTimeout('/api/connect', TIMEOUT_CONNECT_MS, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const body = (await res.json()) as ConnectionResult;
  if (!res.ok && body && typeof body.is_connected === 'boolean') {
    return body;
  }
  if (!res.ok) {
    throw new Error(`RoboWeaver API /api/connect responded ${res.status}`);
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
  compile: (
    instruction: string,
    robot: string = 'franka_panda',
    explainPasses: boolean = false,
    explainAI: boolean = false,
  ) =>
    compileJSON(
      `/api/compile?instruction=${encodeURIComponent(instruction)}&robot=${encodeURIComponent(robot)}` +
        (explainPasses ? '&explain_passes=1' : '') +
        (explainAI ? '&explain=1' : ''),
      explainAI ? TIMEOUT_LLM_MS : TIMEOUT_FAST_MS,
    ),
  compileMatrix: (instruction: string, robots?: string[]) =>
    getJSON<UniversalCompileMatrix>(
      `/api/compile-matrix?instruction=${encodeURIComponent(instruction)}` +
        (robots && robots.length ? `&robots=${encodeURIComponent(robots.join(','))}` : ''),
      TIMEOUT_SCAN_MS,
    ),
  /** Compile and download a real backend artifact derived from verified RoboIR. */
  artifact: async (
    instruction: string,
    robot: string,
    backend: 'ros2' | 'urscript' | 'abb_rapid',
  ): Promise<{ blob: Blob; filename: string }> => {
    const path = `/api/artifact?instruction=${encodeURIComponent(instruction)}` +
      `&robot=${encodeURIComponent(robot)}&backend=${encodeURIComponent(backend)}`;
    const res = await fetchWithTimeout(path, TIMEOUT_SCAN_MS);
    if (!res.ok) {
      const body = await res.json().catch(() => null) as { reason?: string; error?: string } | null;
      throw new Error(body?.reason ?? body?.error ?? `RoboWeaver API ${path} responded ${res.status}`);
    }
    const disposition = res.headers.get('content-disposition') ?? '';
    const match = /filename="?([^";]+)"?/i.exec(disposition);
    const extension = backend === 'ros2' ? 'zip' : backend === 'abb_rapid' ? 'mod' : 'script';
    return {
      blob: await res.blob(),
      filename: match?.[1] ?? `roboweaver-${robot}.${extension}`,
    };
  },
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
  researchStatus: () => getJSON<ResearchStatusResult>('/api/research/status'),
  observability: () => getJSON<ObservabilityResult>('/api/observability'),
  researchEvaluation: () => getJSON<ResearchEvaluationResult>('/api/research/benchmark', TIMEOUT_SCAN_MS),
  planExperiment: (objective: string, useAI: boolean = true) =>
    postJSON<ExperimentPlanResult>(
      '/api/research/plan',
      { objective, use_ai: useAI },
      TIMEOUT_LLM_MS,
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
  /** Real cross-robot RoboIR diff (ir/diff.py::diff_ir()) -- the same comparison
   * `roboweaver diff INSTRUCTION --robot X --robot2 Y` produces on the CLI. Throws
   * with the real diagnostics when either robot genuinely can't compile the
   * instruction, rather than returning a fabricated/empty diff. */
  diff: async (
    instruction: string, robot: string, robot2: string, explainAI: boolean = false,
  ): Promise<IRDiffResult> => {
    const path = `/api/diff?instruction=${encodeURIComponent(instruction)}&robot=${encodeURIComponent(robot)}&robot2=${encodeURIComponent(robot2)}` +
      (explainAI ? '&explain=1' : '');
    const res = await fetchWithTimeout(path, explainAI ? TIMEOUT_LLM_MS : TIMEOUT_FAST_MS);
    const body = await res.json();
    if (!res.ok) {
      if (body && body.error === 'compilation_failed') {
        throw new CompilationFailedError(body.diagnostics);
      }
      throw new Error(`RoboWeaver API ${path} responded ${res.status}`);
    }
    return body as IRDiffResult;
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
  access: async (): Promise<AccessInfo> => {
    const res = await fetch('/api/access', { cache: 'no-store' });
    const body = await res.json();
    if (!res.ok) throw new Error(body?.error ?? `Access policy responded ${res.status}`);
    return body as AccessInfo;
  },
  /** Ask an LLM to map a discovered endpoint onto a registry robot + protocol. */
  adviseConnection: (robot: DiscoveredRobot, provider: 'ollama' | 'openrouter', model?: string) =>
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
    connectJSON({ robot, protocol, uri }),
  /** Generate a deterministic no-motion connection adapter plus an optional AI review. */
  generateConnectionCode: (
    robot: string,
    protocol: 'ros2' | 'sim',
    uri: string,
    provider: 'none' | 'ollama' | 'openrouter',
    aiReview: boolean,
  ) => postJSON<ConnectionCodeResult>(
    '/api/connect/codegen',
    { robot, protocol, uri, provider, ai_review: aiReview },
    aiReview ? TIMEOUT_CODEGEN_MS : TIMEOUT_FAST_MS,
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

  // ── AI / Ollama Endpoints ──────────────────────────────────────
  /** Full Ollama server status: availability, pulled models, per-feature config. */
  aiStatus: () => getJSON<AIStatusResult>('/api/ai/status', TIMEOUT_FAST_MS),
  /** List locally pulled Ollama models. */
  aiModels: () => getJSON<AIModelsResult>('/api/ai/models', TIMEOUT_FAST_MS),
  aiPullModel: (model: string) =>
    postJSON<AIModelMutationResult>('/api/ai/pull', { model }, 5 * 60_000),
  aiConfigureModel: (feature: string, model: string) =>
    postJSON<AIModelMutationResult>('/api/ai/config', { feature, model }),
  /** AI explanation of a compiled skill — additive, never replaces the real compile. */
  aiExplain: (instruction: string, robot: string = 'franka_panda') =>
    getJSON<AIExplanationResult>(
      `/api/ai/explain?instruction=${encodeURIComponent(instruction)}&robot=${encodeURIComponent(robot)}`,
      TIMEOUT_LLM_MS
    ),
  /** AI-enriched recovery advice for a failure mode. */
  aiDiagnose: (failure: string, robot: string = 'franka_panda', action: string = 'PICK') =>
    getJSON<AIDiagnoseResult>(
      `/api/ai/diagnose?failure=${encodeURIComponent(failure)}&robot=${encodeURIComponent(robot)}&action=${encodeURIComponent(action)}`,
      TIMEOUT_LLM_MS
    ),
  /** Decompose a complex instruction into atomic compilable steps. */
  aiCompose: (instruction: string) =>
    getJSON<AIComposeResult>(
      `/api/ai/compose?instruction=${encodeURIComponent(instruction)}`,
      TIMEOUT_LLM_MS
    ),
  /** Suggest graph edges or an annotation; suggestions are never auto-applied. */
  aiEnrich: (mode: 'edges' | 'pairings' | 'describe' | 'summary' = 'edges', id?: string) =>
    getJSON<AIEnrichmentResult>(
      `/api/ai/enrich?mode=${encodeURIComponent(mode)}` +
        (mode === 'describe' && id ? `&robot=${encodeURIComponent(id)}` : '') +
        (mode === 'summary' && id ? `&node=${encodeURIComponent(id)}` : ''),
      TIMEOUT_LLM_MS,
    ),
  /** General-purpose AI chat about the RoboWeaver platform. */
  aiChat: (message: string) =>
    getJSON<AIChatResult>(
      `/api/ai/chat?message=${encodeURIComponent(message)}`,
      TIMEOUT_LLM_MS
    ),
  aiChatStream: streamAIChat,
};
