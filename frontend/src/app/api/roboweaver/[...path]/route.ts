import { randomUUID } from 'node:crypto';
import type { NextRequest } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const MAX_PROXY_BODY_BYTES = 4_096;
const SAFE_SEGMENT = /^[A-Za-z0-9._~-]+$/;
const SAFE_REQUEST_ID = /^[A-Za-z0-9._-]{1,64}$/;
const RESPONSE_HEADERS = new Set([
  'cache-control',
  'content-disposition',
  'content-length',
  'content-type',
  'retry-after',
  'x-request-id',
]);

type RouteContext = { params: Promise<{ path: string[] }> };

function jsonError(error: string, status: number, requestId: string): Response {
  return Response.json(
    { error, request_id: requestId },
    {
      status,
      headers: {
        'Cache-Control': 'no-store',
        'X-Request-ID': requestId,
      },
    },
  );
}

function upstreamBase(): URL {
  const value = process.env.ROBOWEAVER_INTERNAL_API ?? 'http://127.0.0.1:8080';
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
    throw new Error('ROBOWEAVER_INTERNAL_API must be an HTTP(S) origin without credentials.');
  }
  if (url.pathname !== '/' || url.search || url.hash) {
    throw new Error('ROBOWEAVER_INTERNAL_API must be an origin without a path, query, or fragment.');
  }
  return url;
}

function timeoutFor(path: string, method: string): number {
  if (method === 'POST' && path === '/api/ai/pull') return 5 * 60_000;
  if (path.startsWith('/api/ai/') || path === '/api/connect/advise') return 70_000;
  if (path === '/api/discover' || path === '/api/benchmark') return 35_000;
  return 20_000;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const suppliedRequestId = request.headers.get('x-request-id') ?? '';
  const requestId = SAFE_REQUEST_ID.test(suppliedRequestId) ? suppliedRequestId : randomUUID();
  const { path: segments } = await context.params;
  if (!segments.length || segments.length > 16 || segments.some((segment) => !SAFE_SEGMENT.test(segment))) {
    return jsonError('invalid_upstream_path', 400, requestId);
  }

  const upstreamPath = `/${segments.map(encodeURIComponent).join('/')}`;
  let upstream: URL;
  try {
    upstream = upstreamBase();
  } catch {
    return jsonError('upstream_configuration_error', 503, requestId);
  }
  upstream.pathname = upstreamPath;
  upstream.search = request.nextUrl.search;

  const headers = new Headers({
    Accept: request.headers.get('accept') ?? 'application/json',
    'X-Request-ID': requestId,
  });
  const token = process.env.ROBOWEAVER_API_TOKEN;
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let body: ArrayBuffer | undefined;
  if (request.method === 'POST') {
    const contentType = request.headers.get('content-type') ?? '';
    if (contentType.split(';', 1)[0].trim().toLowerCase() !== 'application/json') {
      return jsonError('content_type_must_be_application_json', 415, requestId);
    }
    const declaredLength = Number(request.headers.get('content-length') ?? '0');
    if (!Number.isSafeInteger(declaredLength) || declaredLength < 0 || declaredLength > MAX_PROXY_BODY_BYTES) {
      return jsonError('request_body_too_large', 413, requestId);
    }
    body = await request.arrayBuffer();
    if (body.byteLength === 0 || body.byteLength > MAX_PROXY_BODY_BYTES) {
      return jsonError(body.byteLength ? 'request_body_too_large' : 'request_body_required', body.byteLength ? 413 : 400, requestId);
    }
    headers.set('Content-Type', 'application/json');
  }

  try {
    const response = await fetch(upstream, {
      method: request.method,
      headers,
      body,
      cache: 'no-store',
      redirect: 'manual',
      signal: AbortSignal.timeout(timeoutFor(upstreamPath, request.method)),
    });
    const responseHeaders = new Headers();
    for (const [name, value] of response.headers) {
      if (RESPONSE_HEADERS.has(name.toLowerCase())) responseHeaders.set(name, value);
    }
    responseHeaders.set('Cache-Control', 'no-store');
    responseHeaders.set('X-Request-ID', response.headers.get('x-request-id') ?? requestId);
    return new Response(response.body, { status: response.status, headers: responseHeaders });
  } catch {
    return jsonError('upstream_unavailable', 502, requestId);
  }
}

export async function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, context);
}

export async function POST(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, context);
}
