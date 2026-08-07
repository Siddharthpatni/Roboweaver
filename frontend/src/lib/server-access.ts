import type { NextRequest } from 'next/server';

const SAFE_LAN_PATHS = new Set([
  '/api/artifact',
  '/api/benchmark',
  '/api/build',
  '/api/compare',
  '/api/compile',
  '/api/compile-matrix',
  '/api/cost',
  '/api/diff',
  '/api/graph',
  '/api/graph/export-obsidian',
  '/api/graph/path',
  '/api/knowledge',
  '/api/nexus/packages',
  '/api/nexus/recommend',
  '/api/observability',
  '/api/research/status',
  '/api/research/benchmark',
  '/api/robots',
  '/api/skills',
  '/api/version',
]);

function enabled(name: string): boolean {
  return /^(1|true|yes|on)$/i.test(process.env[name] ?? '');
}

function hostWithoutPort(host: string): string {
  const normalized = host.trim().toLowerCase();
  if (normalized.startsWith('[')) return normalized.slice(1, normalized.indexOf(']'));
  return normalized.replace(/:\d+$/, '');
}

function isPrivateHost(hostHeader: string): boolean {
  const host = hostWithoutPort(hostHeader);
  if (host === 'localhost' || host === '::1') return true;
  if (/^(fc|fd)[0-9a-f:]+$/.test(host) || /^fe[89ab][0-9a-f:]+$/.test(host)) return true;
  const parts = host.split('.').map(Number);
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
    return false;
  }
  return parts[0] === 10 || parts[0] === 127 ||
    (parts[0] === 169 && parts[1] === 254) ||
    (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) ||
    (parts[0] === 192 && parts[1] === 168);
}

function isLoopbackHost(hostHeader: string): boolean {
  const host = hostWithoutPort(hostHeader);
  return host === 'localhost' || host === '::1' || host.startsWith('127.');
}

function publicBindConfigured(): boolean {
  const bind = (process.env.ROBOWEAVER_FRONTEND_BIND ?? '').trim().toLowerCase();
  return Boolean(bind) && !['127.0.0.1', '::1', 'localhost'].includes(bind);
}

function hostAllowed(host: string): boolean {
  if (isPrivateHost(host)) return true;
  const allowed = (process.env.ROBOWEAVER_LAN_ALLOWED_HOSTS ?? '')
    .split(',').map((item) => item.trim().toLowerCase()).filter(Boolean);
  return allowed.includes(host.toLowerCase()) || allowed.includes(hostWithoutPort(host));
}

function isSameOrigin(request: NextRequest): boolean {
  const host = request.headers.get('host') ?? '';
  const origin = request.headers.get('origin');
  if (origin) {
    try {
      return new URL(origin).host.toLowerCase() === host.toLowerCase();
    } catch {
      return false;
    }
  }
  return request.headers.get('sec-fetch-site') === 'same-origin';
}

export interface AccessPolicy {
  lanMode: boolean;
  controlEnabled: boolean;
  hostAllowed: boolean;
  permitted: boolean;
  reason: string | null;
}

export function accessPolicy(request: NextRequest, upstreamPath?: string): AccessPolicy {
  const host = request.headers.get('host') ?? '';
  const lanMode = enabled('ROBOWEAVER_LAN_MODE') || publicBindConfigured() ||
    (isPrivateHost(host) && !isLoopbackHost(host));
  const controlEnabled = enabled('ROBOWEAVER_LAN_ALLOW_CONTROL');
  const validHost = !lanMode || hostAllowed(host);
  if (!validHost) return { lanMode, controlEnabled, hostAllowed: false, permitted: false, reason: 'host_not_allowed' };
  if (!upstreamPath) {
    return { lanMode, controlEnabled, hostAllowed: true, permitted: true, reason: null };
  }
  const compilerRoute = SAFE_LAN_PATHS.has(upstreamPath) ||
    /^\/api\/robots\/[A-Za-z0-9._~-]+\/(model|fk|urdf)$/.test(upstreamPath);
  if (compilerRoute && request.method === 'GET') {
    return { lanMode, controlEnabled, hostAllowed: true, permitted: true, reason: null };
  }
  if (lanMode && !controlEnabled) {
    return { lanMode, controlEnabled, hostAllowed: true, permitted: false, reason: 'lan_compiler_only' };
  }
  if (!isSameOrigin(request)) {
    return { lanMode, controlEnabled, hostAllowed: true, permitted: false, reason: 'same_origin_required' };
  }
  return { lanMode, controlEnabled, hostAllowed: true, permitted: true, reason: null };
}

export function accessHeaders(policy: AccessPolicy): Record<string, string> {
  return {
    'X-RoboWeaver-Access-Mode': policy.lanMode ? 'lan' : 'local',
    'X-RoboWeaver-Control': policy.controlEnabled ? 'enabled' : 'compiler-only',
  };
}
