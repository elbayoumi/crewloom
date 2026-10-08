import { guard, privateHeaders } from '../../../lib/auth.ts';
import { catalogRequest, projectCatalog } from '../../../lib/projects.ts';
export const dynamic = 'force-dynamic';
export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  return Response.json(await projectCatalog(), { headers: privateHeaders });
}

export async function POST(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  let body;
  try { body = await req.json(); } catch { return Response.json({ error: 'Invalid JSON' }, { status: 400 }); }
  if (!body || Object.keys(body).some((key) => !['action', 'project_id', 'task_id'].includes(key))
      || body.action !== 'cancel-task' || typeof body.project_id !== 'string' || typeof body.task_id !== 'string'
      || !/^[a-z0-9][a-z0-9._-]{2,63}$/.test(body.project_id) || !/^[a-z0-9][a-z0-9._-]{2,63}$/.test(body.task_id)) {
    return Response.json({ error: 'Expected registered project_id and task_id for cancel-task' }, { status: 400 });
  }
  const result = await catalogRequest('cancel-task', body.project_id, body.task_id);
  return Response.json(result, { status: result.error ? 409 : 200, headers: privateHeaders });
}
