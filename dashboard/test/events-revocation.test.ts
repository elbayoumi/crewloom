import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { SESSION_COOKIE, issueSession, revokeSession } from '../lib/auth.ts';

const TOKEN = 'r'.repeat(43);
const ENV = { CREWLOOM_DASHBOARD_TOKEN: TOKEN, CREWLOOM_DASHBOARD_HOST: '127.0.0.1',
  CREWLOOM_DASHBOARD_PORT: '4317' };

/** Run a body with the server environment this route reads, then restore it exactly. */
async function withServerEnv<T>(values: Record<string, string | undefined>, body: () => Promise<T>): Promise<T> {
  const saved = new Map<string, string | undefined>();
  for (const [key, value] of Object.entries(values)) {
    saved.set(key, process.env[key]);
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  }
  try { return await body(); } finally {
    for (const [key, value] of saved) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
  }
}

/**
 * A disposable watched project, so the stream watches throwaway directories instead of this
 * repository. The environment has to be in place before the route is imported: the watched roots
 * are resolved once, when `lib/repo.ts` is first loaded.
 */
function withProject<T>(body: (project: string) => Promise<T>): Promise<T> {
  const project = mkdtempSync(path.join(os.tmpdir(), 'crewloom-events-'));
  for (const dir of ['.crewloom', '.agents/skills', '.claude/skills', 'Brain']) {
    mkdirSync(path.join(project, dir), { recursive: true });
  }
  return withServerEnv({ ...ENV, CREWLOOM_PROJECT: project }, async () => {
    try { return await body(project); } finally { rmSync(project, { recursive: true, force: true }); }
  });
}

const loadStream = () => import(pathToFileURL(path.resolve('app', 'api', 'events', 'route.ts')).href);

const open = async (headers: Record<string, string>) => {
  const { GET } = await loadStream();
  const res = await GET(new Request('http://127.0.0.1:4317/api/events', { headers }));
  assert.equal(res.status, 200);
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  const frames: string[] = [];
  // The stream opens with a ping and then the ready frame; both are written before this returns.
  for (const _ of [0, 1]) frames.push(decoder.decode((await reader.read()).value));
  return { reader, frames };
};

/** Whether a pending read has already settled, after one real turn of the event loop. */
async function settled(read: Promise<unknown>): Promise<boolean> {
  let done = false;
  void read.then(() => { done = true; }, () => { done = true; });
  await new Promise((resolve) => setImmediate(resolve));
  return done;
}

test('an open session stream ends when its session is revoked, and not before', { timeout: 10000 }, async (t) => {
  await withProject(async () => {
    t.mock.timers.enable({ apis: ['setInterval'] });
    const cookie = `${SESSION_COOKIE}=${issueSession(TOKEN).value}`;
    const { reader, frames } = await open({ cookie });
    assert.match(frames.join(''), /event: ready/);
    // A session that is still live keeps streaming across a re-check.
    t.mock.timers.tick(5000);
    assert.equal(await settled(reader.read()), false, 'a live session stream was closed early');
    // Logging out revokes the session server-side; the cookie itself is unchanged.
    assert.equal(revokeSession(cookie), true);
    t.mock.timers.tick(5000);
    assert.deepEqual(await reader.read(), { done: true, value: undefined });
  });
});

test('a bearer stream carries no session and is not closed by an interval', async (t) => {
  await withProject(async () => {
    t.mock.timers.enable({ apis: ['setInterval'] });
    const { reader } = await open({ authorization: `Bearer ${TOKEN}` });
    t.mock.timers.tick(15000);
    assert.equal(await settled(reader.read()), false, 'a bearer stream was closed by the re-check');
    // Cancelling the request is what ends a bearer stream, and it clears every timer.
    await reader.cancel();
  });
});