import { mkdirSync, watch, type FSWatcher } from 'node:fs';
import { RUN_LOG, PROJECT, SKILLS } from '@/lib/repo.ts';
import path from 'node:path';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

/** Server-sent events: one `change` event per debounced filesystem change under skills/brain or the run log. */
export async function GET(req: Request) {
  const encoder = new TextEncoder();
  const watchers: FSWatcher[] = [];
  let timer: ReturnType<typeof setTimeout> | undefined;
  let beat: ReturnType<typeof setInterval> | undefined;
  const stream = new ReadableStream({
    start(controller) {
      const send = (event: string, data: object) => controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      const notify = (file: string | null) => {
        clearTimeout(timer);
        timer = setTimeout(() => send('change', { file, ts: Date.now() }), 150);
      };
      mkdirSync(path.join(PROJECT, '.crewloom'), { recursive: true });
      for (const dir of [SKILLS, path.join(PROJECT, '.agents', 'skills'), path.join(PROJECT, '.claude', 'skills'), path.join(PROJECT, '.crewloom'), path.join(PROJECT, 'Brain')]) {
        try { watchers.push(watch(dir, { recursive: true }, (_e, f) => notify(f ? String(f) : null))); } catch { /* dir absent */ }
      }
      beat = setInterval(() => controller.enqueue(encoder.encode(': ping\n\n')), 15000);
      send('ready', { watching: watchers.length, runLog: path.relative(PROJECT, RUN_LOG) });
      req.signal.addEventListener('abort', () => {
        watchers.forEach((w) => w.close());
        clearTimeout(timer); clearInterval(beat);
        try { controller.close(); } catch { /* already closed */ }
      });
    },
  });
  return new Response(stream, { headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache, no-transform', Connection: 'keep-alive' } });
}
