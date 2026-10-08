import { inSelectedProject } from '../../../lib/projects.ts';
import { appendRun, readTools, runTool } from '../../../lib/repo.ts';
import { guard } from '../../../lib/auth.ts';

export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  return inSelectedProject(req, async (project) => {
  let body: { tool?: unknown; args?: unknown };
  try { body = await req.json(); } catch { return Response.json({ error: 'Invalid JSON' }, { status: 400 }); }
  if (typeof body.tool !== 'string' || !Array.isArray(body.args) || !body.args.every((a) => typeof a === 'string')) {
    return Response.json({ error: 'Expected { tool: string, args: string[] }' }, { status: 400 });
  }
  const tool = (await readTools()).find((t) => t.id === body.tool);
  const result = await runTool(body.tool, body.args as string[], project.root);
  if (result.error) return Response.json({ error: result.error }, { status: 400 });
  await appendRun({
    ts: new Date().toISOString().replace(/\.\d+Z$/, '+00:00'), tool: body.tool, skill: tool?.skill ?? '',
    exit_code: result.exit_code, duration_ms: result.duration_ms, source: 'dashboard', output: result.output.slice(-2000),
  }, project.root);
  return Response.json(result);
  });
}