import { guard, privateHeaders } from '../../../lib/auth.ts';
export const dynamic = 'force-dynamic';
export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  return Response.json({ daemon: 'crewloom', browserCompanion: 'manual',
    connection: 'unverified', computerUseActive: null }, { headers: privateHeaders });
}
export async function POST(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  return Response.json({ error: 'Registration is not implemented' }, { status: 405, headers: privateHeaders });
}
