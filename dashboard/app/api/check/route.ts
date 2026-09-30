import { runChecks } from '@/lib/repo.ts';

export const dynamic = 'force-dynamic';

export async function POST() {
  return Response.json(await runChecks());
}
