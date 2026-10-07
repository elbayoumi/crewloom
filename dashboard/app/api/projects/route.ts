import { guard, privateHeaders } from '../../../lib/auth.ts';
import { projectReferences } from '../../../lib/projects.ts';
export const dynamic = 'force-dynamic';
export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  try { return Response.json({ projects: projectReferences() }, { headers: { ...privateHeaders } }); }
  catch { return Response.json({ error: 'Invalid approved project configuration' }, { status: 400, headers: { ...privateHeaders } }); }
}
