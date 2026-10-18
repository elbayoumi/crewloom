import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {guard, privateHeaders} from '../../../../lib/auth.ts';
import {ROOT} from '../../../../lib/repo.ts';

export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  try {
    const bytes = await readFile(path.join(ROOT,'assets','crewloom-chrome-extension.zip'));
    return new Response(new Uint8Array(bytes), {headers:{...privateHeaders,
      'Content-Type':'application/zip',
      'Content-Disposition':'attachment; filename="crewloom-chrome-extension.zip"'}});
  } catch {
    return Response.json({error:'Browser extension package is unavailable'}, {status:503,headers:privateHeaders});
  }
}
