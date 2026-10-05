import { guard } from '../../../lib/auth.ts';
import { runChecks } from '../../../lib/repo.ts';

export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  return Response.json(await runChecks());
}