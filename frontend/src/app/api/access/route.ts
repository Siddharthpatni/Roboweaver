import type { NextRequest } from 'next/server';
import { accessHeaders, accessPolicy } from '../../../lib/server-access';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest): Promise<Response> {
  const policy = accessPolicy(request);
  if (!policy.permitted) {
    return Response.json({ error: policy.reason }, { status: 421, headers: accessHeaders(policy) });
  }
  return Response.json({
    mode: policy.lanMode ? 'lan' : 'local',
    compiler_access: true,
    hardware_control: policy.controlEnabled,
    backend_token_exposed: false,
    host_validated: policy.hostAllowed,
  }, { headers: { ...accessHeaders(policy), 'Cache-Control': 'no-store' } });
}
