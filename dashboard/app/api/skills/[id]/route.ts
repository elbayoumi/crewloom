import { skillDetail } from '@/lib/repo.ts';

export const dynamic = 'force-dynamic';

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const detail = await skillDetail(id);
  return detail ? Response.json(detail) : Response.json({ error: 'Unknown skill' }, { status: 404 });
}
