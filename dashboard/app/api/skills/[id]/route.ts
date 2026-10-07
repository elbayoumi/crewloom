import { inSelectedProject } from '../../../../lib/projects.ts';
import { skillDetail } from '../../../../lib/repo.ts';
import { guard, privateHeaders } from '../../../../lib/auth.ts';

export const dynamic = 'force-dynamic';

export async function GET(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const denied = guard(req);
  if (denied) return denied;
  return inSelectedProject(req, async (project) => {
  const { id } = await ctx.params;
  const detail = await skillDetail(id, project.root);
  return detail
    ? Response.json(detail, { headers: { ...privateHeaders } })
    : Response.json({ error: 'Unknown skill' }, { status: 404, headers: { ...privateHeaders } });
  });
}