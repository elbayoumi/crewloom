import { guard, privateHeaders } from '../../../lib/auth.ts';
import { probeAccessibility, probeScreenRecording, openPreferencePane, validPane } from '../../../lib/permissions.ts';
export const dynamic = 'force-dynamic';
export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const mac = process.platform === 'darwin';
  const [accessibility, screen] = await Promise.all([
    probeAccessibility(), mac ? probeScreenRecording() : Promise.resolve({ granted: null, error: 'macOS probe unavailable' })
  ]);
  return Response.json({ platform: process.platform, permissions: [
    { id: 'accessibility', ...accessibility }, { id: 'screen_recording', ...screen },
    { id: 'browser_extension', granted: null, error: 'Use browser companion handshake' }
  ] }, { headers: privateHeaders });
}
export async function POST(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  let body;
  try { body = await req.json(); } catch { return Response.json({ error: 'Invalid JSON' }, { status: 400, headers: privateHeaders }); }
  if (!body || Object.keys(body).length !== 1 || !validPane(body.pane)) return Response.json({ error: 'Invalid preference pane' }, { status: 400, headers: privateHeaders });
  if (process.platform !== 'darwin') return Response.json({ error: 'macOS only' }, { status: 400, headers: privateHeaders });
  const result = await openPreferencePane(body.pane);
  return Response.json(result, { status: result.ok ? 200 : 500, headers: privateHeaders });
}
