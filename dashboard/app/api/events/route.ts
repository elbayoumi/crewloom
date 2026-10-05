import { mkdirSync, watch, type FSWatcher } from 'node:fs';
import path from 'node:path';
import { authorize, privateHeaders } from '../../../lib/auth.ts';
import { RUN_LOG, PROJECT, SKILLS } from '../../../lib/repo.ts';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

/** How often an open session stream re-proves that its session is still live. */
const SESSION_RECHECK_MS = 5000;

/** Server-sent events: one `change` event per debounced filesystem change under skills/brain or the run log. */
export async function GET(req: Request) {
  const decision = authorize(req);
  if (!decision.ok) {
    const headers: Record<string, string> = { ...privateHeaders };
    if (decision.status === 401) headers['WWW-Authenticate'] = 'Bearer realm="crewloom-dashboard"';
    return Response.json({ error: decision.error }, { status: decision.status, headers });
  }
  const encoder = new TextEncoder();
  const watchers: FSWatcher[] = [];
  let timer: ReturnType<typeof setTimeout> | undefined;
  let beat: ReturnType<typeof setInterval> | undefined;
  let expiry: ReturnType<typeof setTimeout> | undefined;
  let recheck: ReturnType<typeof setInterval> | undefined;
  const close = () => {
    watchers.forEach((w) => w.close());
    clearTimeout(timer); clearInterval(beat); clearTimeout(expiry); clearInterval(recheck);
  };
  const stream = new ReadableStream({
    start(controller) {
      let open = true;
      const end = () => {
        if (!open) return;
        open = false;
        close();
        try { controller.close(); } catch { /* already closed */ }
      };
      const send = (event: string, data: object) => {
        if (!open) return;
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      };
      const notify = (file: string | null) => {
        clearTimeout(timer);
        timer = setTimeout(() => send('change', { file, ts: Date.now() }), 150);
      };
      mkdirSync(path.join(PROJECT, '.crewloom'), { recursive: true });
      for (const dir of [SKILLS, path.join(PROJECT, '.agents', 'skills'), path.join(PROJECT, '.claude', 'skills'), path.join(PROJECT, '.crewloom'), path.join(PROJECT, 'Brain')]) {
        try { watchers.push(watch(dir, { recursive: true }, (_e, f) => notify(f ? String(f) : null))); } catch { /* dir absent */ }
      }
      if (open) controller.enqueue(encoder.encode(': ping\n\n'));
      // A session stream must not outlive its session: an expired or revoked cookie stops
      // the flow instead of leaving an authenticated channel open. Cookie expiry alone is not
      // enough, because a logout revokes a session long before its expiry; the decision is
      // therefore re-proved against the server's live sessions every few seconds. Bearer
      // automation carries no session to lose, so its stream runs until the request ends.
      if (decision.ok && decision.method === 'session' && decision.expiresAt) {
        expiry = setTimeout(end, Math.max(0, decision.expiresAt * 1000 - Date.now()));
        recheck = setInterval(() => { if (!authorize(req).ok) end(); }, SESSION_RECHECK_MS);
      }
      send('ready', { watching: watchers.length, runLog: path.relative(PROJECT, RUN_LOG), expires_at: decision.ok ? decision.expiresAt : null });
      req.signal.addEventListener('abort', end);
    },
    cancel() { close(); },
  });
  return new Response(stream, {
    headers: {
      ...privateHeaders,
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    },
  });
}