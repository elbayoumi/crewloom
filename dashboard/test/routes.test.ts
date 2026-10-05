import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const TOKEN = 'z'.repeat(43);
const ORIGIN = 'http://127.0.0.1:4317';
const ENV = { CREWLOOM_DASHBOARD_TOKEN: TOKEN, CREWLOOM_DASHBOARD_HOST: '127.0.0.1', CREWLOOM_DASHBOARD_PORT: '4317' };

/**
 * Route-level acceptance: these call the real handlers with real `Request` objects, so a
 * route that forgets its guard fails here rather than only in a browser.
 */
function withServerEnv<T>(values: Record<string, string | undefined>, body: () => T | Promise<T>): Promise<T> {
  const saved = new Map<string, string | undefined>();
  for (const [key, value] of Object.entries(values)) {
    saved.set(key, process.env[key]);
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  }
  return (async () => {
    try { return await body(); } finally {
      for (const [key, value] of saved) {
        if (value === undefined) delete process.env[key]; else process.env[key] = value;
      }
    }
  })();
}

const load = (relative: string) => import(pathToFileURL(path.resolve('app', relative)).href);

const request = (route: string, options: RequestInit & { cookie?: string } = {}) => {
  const { cookie, ...init } = options;
  const headers = new Headers(init.headers);
  if (cookie) headers.set('cookie', cookie);
  return new Request(`http://127.0.0.1:4317${route}`, { ...init, headers });
};

const login = async (origin: string | null = ORIGIN) => {
  const { POST } = await load('api/auth/login/route.ts');
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (origin) headers.Origin = origin;
  const res = await POST(request('/api/auth/login', {
    method: 'POST', headers, body: JSON.stringify({ token: TOKEN }),
  }));
  const cookie = (res.headers.get('set-cookie') ?? '').split(';')[0];
  return { res, cookie };
};

test('a valid login issues a session cookie and a real logout revokes it', async () => {
  await withServerEnv(ENV, async () => {
    const { cookie } = await login();
    assert.match(cookie, /^crewloom_session=/);
    const { GET: session } = await load('api/auth/session/route.ts');
    const active = await session(request('/api/auth/session', { cookie }));
    const activeBody = await active.json();
    assert.equal(activeBody.authenticated, true);
    assert.equal(activeBody.method, 'session');
    assert.equal(activeBody.expires_at > Math.floor(Date.now() / 1000), true);
    const { DELETE } = await load('api/auth/login/route.ts');
    const out = await DELETE(request('/api/auth/login', { method: 'DELETE', cookie, headers: { origin: ORIGIN } }));
    assert.equal(out.status, 200);
    assert.match(out.headers.get('set-cookie') ?? '', /crewloom_session=;.*Max-Age=0/);
    assert.equal((await DELETE(request('/api/auth/login', { method: 'DELETE', cookie }))).status, 403);
    // The server revoked the issued session, not merely the browser's copy of the cookie.
    assert.equal((await session(request('/api/auth/session', { cookie }))).status, 200);
    const after = await session(request('/api/auth/session', { cookie }));
    assert.equal((await after.json()).authenticated, false);
  });
});

test('login itself refuses a missing or foreign origin even with a correct credential', async () => {
  await withServerEnv(ENV, async () => {
    assert.equal((await login(null)).res.status, 403);
    assert.equal((await login('http://attacker.invalid')).res.status, 403);
    assert.equal((await login(ORIGIN)).res.status, 200);
  });
});

test('a wrong or malformed login token is refused without echoing anything', async () => {
  await withServerEnv(ENV, async () => {
    const { POST } = await load('api/auth/login/route.ts');
    for (const body of [{ token: 'wrong' }, {}, { token: 5 }, JSON.stringify('nope')]) {
      const res = await POST(request('/api/auth/login', { method: 'POST', headers: { origin: ORIGIN }, body: typeof body === 'string' ? body : JSON.stringify(body) }));
      assert.equal(res.status, 401);
      const text = JSON.stringify(await res.json());
      assert.equal(text.includes(TOKEN), false);
      assert.equal(res.headers.get('set-cookie'), null);
    }
    const garbage = await POST(request('/api/auth/login', { method: 'POST', headers: { origin: ORIGIN }, body: 'not json' }));
    assert.equal(garbage.status, 400);
  });
});

test('every read and write route refuses unauthenticated and cross-origin callers', async () => {
  await withServerEnv(ENV, async () => {
    const { cookie } = await login();
    const { GET: overview } = await load('api/overview/route.ts');
    const { GET: skill } = await load('api/skills/[id]/route.ts');
    const { GET: events } = await load('api/events/route.ts');
    const { POST: run } = await load('api/run/route.ts');
    const { POST: check } = await load('api/check/route.ts');
    const ctx = { params: Promise.resolve({ id: 'context-guardian' }) };
    const bare = request('/api/overview');
    for (const [name, call] of [
      ['overview', () => overview(bare)],
      ['skill', () => skill(bare, ctx)],
      ['events', () => events(bare)],
      ['run', () => run(request('/api/run', { method: 'POST', body: '{"tool":"x","args":[]}' }))],
      ['check', () => check(request('/api/check', { method: 'POST' }))],
    ] as const) {
      const res = await call();
      assert.equal(res.status, 401, name);
      assert.equal(res.headers.get('content-type'), 'application/json', name);
      assert.equal(JSON.stringify(await res.clone().json()).includes(TOKEN), false, name);
    }
    // An authenticated session cookie is accepted on reads, and refused cross-origin on writes.
    assert.equal((await overview(request('/api/overview', { cookie }))).status, 200);
    const forgedOrigin = request('/api/run', { method: 'POST', cookie, headers: { origin: 'http://evil.example' }, body: '{"tool":"x","args":[]}' });
    const refused = await run(forgedOrigin);
    assert.equal(refused.status, 403);
    assert.equal((await check(request('/api/check', { method: 'POST', cookie }))).status, 403);
// Bearer automation is an explicit, documented alternative to the browser session.
assert.equal((await overview(request('/api/overview', { headers: { authorization: `Bearer ${TOKEN}` } }))).status, 200);
assert.equal((await run(request('/api/run', { method: 'POST', headers: { authorization: 'Bearer nope' }, body: '{"tool":"x","args":[]}' }))).status, 401);
// An authorized write reaches its own validation rather than the guard.
const allowed = await run(request('/api/run', {
  method: 'POST', cookie, headers: { origin: ORIGIN }, body: '{"tool":"unknown-tool","args":[]}',
}));
assert.equal(allowed.status, 400);
assert.equal((await allowed.json()).error, 'Unknown tool');
  });
});

test('an unconfigured dashboard server exposes nothing', async () => {
  await withServerEnv({ ...ENV, CREWLOOM_DASHBOARD_TOKEN: undefined }, async () => {
    const { GET: overview } = await load('api/overview/route.ts');
    const { GET: session } = await load('api/auth/session/route.ts');
    const { GET: events } = await load('api/events/route.ts');
    for (const call of [() => overview(request('/api/overview')), () => session(request('/api/auth/session')),
      () => events(request('/api/events'))]) {
      assert.equal((await call()).status, 503);
    }
  });
});