/** Independent supervisor acceptance: preserve these security assertions. */
import assert from 'node:assert/strict';
import test from 'node:test';
import { authorize, issueSession, originTrusted, readCookie, sessionCookie, sessionState } from '../lib/auth.ts';
import { POST as login, DELETE as logout } from '../app/api/auth/login/route.ts';

function fixture() {
  const keys = ['CREWLOOM_DASHBOARD_TOKEN', 'CREWLOOM_DASHBOARD_HOST',
    'CREWLOOM_DASHBOARD_PORT', 'CREWLOOM_DASHBOARD_SCHEME', 'CREWLOOM_DASHBOARD_ORIGINS'];
  const saved = Object.fromEntries(keys.map(key => [key, process.env[key]]));
  process.env.CREWLOOM_DASHBOARD_TOKEN = 'synthetic-fixture-token-012345678901234567890123456789';
  process.env.CREWLOOM_DASHBOARD_HOST = '127.0.0.1';
  process.env.CREWLOOM_DASHBOARD_PORT = '4317';
  delete process.env.CREWLOOM_DASHBOARD_SCHEME;
  delete process.env.CREWLOOM_DASHBOARD_ORIGINS;
  return () => {
    for (const key of keys) {
      if (saved[key] === undefined) delete process.env[key];
      else process.env[key] = saved[key];
    }
  };
}

function configured(run: () => void) {
  const restore = fixture();
  try { run(); } finally { restore(); }
}

async function configuredAsync(run: () => Promise<void>) {
  const restore = fixture();
  try { await run(); } finally { restore(); }
}

test('the actual Set-Cookie value establishes a verifiable browser session', () => configured(() => {
  const token = process.env.CREWLOOM_DASHBOARD_TOKEN!;
  const issued = issueSession(token);
  const cookie = sessionCookie(issued.value).split(';')[0];
  assert.equal(readCookie(cookie), issued.value);
  const result = authorize(new Request('http://127.0.0.1:4317/api/overview', { headers: { Cookie: cookie } }));
  assert.equal(result.ok, true);
}));

test('successful session authentication retains its expiry for event-stream closure', () => configured(() => {
  const token = process.env.CREWLOOM_DASHBOARD_TOKEN!;
  const issued = issueSession(token);
  const result = sessionState('crewloom_session=' + issued.value, token);
  assert.equal(result.ok, true);
  assert.equal(result.expiresAt, issued.expiresAt);
}));

test('Origin accepts only an exact serialized trusted origin', () => configured(() => {
  assert.equal(originTrusted('http://127.0.0.1:4317'), true);
  for (const origin of ['http://attacker.invalid', 'http://127.0.0.1:4317/foreign',
    'http://127.0.0.1:4317?foreign=1', 'http://user@127.0.0.1:4317',
    'http://127.0.0.1:4317#foreign', 'null']) {
    assert.equal(originTrusted(origin), false, origin);
  }
}));

test('expired and altered cookies cannot authorize protected reads', () => configured(() => {
  const token = process.env.CREWLOOM_DASHBOARD_TOKEN!;
  const expired = issueSession(token, Date.now() - 24 * 60 * 60 * 1000);
  assert.equal(sessionState('crewloom_session=' + expired.value, token).ok, false);
  const fresh = issueSession(token);
  const changed = fresh.value.slice(0, -1) + (fresh.value.endsWith('0') ? '1' : '0');
  assert.equal(sessionState('crewloom_session=' + changed, token).ok, false);
}));

test('a weak configured bearer secret fails closed', () => configured(() => {
  process.env.CREWLOOM_DASHBOARD_TOKEN = 'weak';
  const result = authorize(new Request('http://127.0.0.1:4317/api/overview', {
    headers: { Authorization: 'Bearer weak' },
  }));
  assert.equal(result.ok, false);
}));

test('login rejects a missing or foreign Origin even with a correct credential', async () => configuredAsync(async () => {
  const token = process.env.CREWLOOM_DASHBOARD_TOKEN!;
  for (const origin of [undefined, 'http://attacker.invalid']) {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (origin) headers.Origin = origin;
    const response = await login(new Request('http://127.0.0.1:4317/api/auth/login',
      { method: 'POST', headers, body: JSON.stringify({ token }) }));
    assert.equal(response.status, 403, origin ?? 'missing Origin');
  }
}));

test('forging Host cannot authorize login from a foreign Origin', async () => configuredAsync(async () => {
  const response = await login(new Request('http://127.0.0.1:4317/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json', Host: 'attacker.invalid',
      Origin: 'http://attacker.invalid' },
    body: JSON.stringify({ token: process.env.CREWLOOM_DASHBOARD_TOKEN! }),
  }));
  assert.equal(response.status, 403);
}));

test('valid JSON with the wrong shape is refused without an uncaught server error', async () => configuredAsync(async () => {
  for (const body of [null, [], 17, 'credential', { token: null }]) {
    const response = await login(new Request('http://127.0.0.1:4317/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Origin: 'http://127.0.0.1:4317' },
      body: JSON.stringify(body),
    }));
    assert.ok(response.status >= 400 && response.status < 500, JSON.stringify(body));
    assert.equal(response.headers.get('set-cookie'), null);
  }
}));

test('logout invalidates the actual issued session rather than clearing only a browser cookie', async () => configuredAsync(async () => {
  const origin = 'http://127.0.0.1:4317';
  const response = await login(new Request(origin + '/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json', Origin: origin },
    body: JSON.stringify({ token: process.env.CREWLOOM_DASHBOARD_TOKEN! }),
  }));
  assert.equal(response.status, 200);
  const cookie = response.headers.get('set-cookie')!.split(';')[0];
  const authenticated = () => authorize(new Request(origin + '/api/overview', { headers: { Cookie: cookie } }));
  assert.equal(authenticated().ok, true);
  const result = await logout(new Request(origin + '/api/auth/login', {
    method: 'DELETE', headers: { Cookie: cookie, Origin: origin },
  }));
  assert.equal(result.status, 200);
  assert.equal(authenticated().ok, false);
}));

test('password-free local mode allows direct access but refuses foreign origins and remote binds', async () => {
  const auth = await import('../lib/auth.ts');
  const oldLocal = process.env.CREWLOOM_DASHBOARD_LOCAL;
  const oldHost = process.env.CREWLOOM_DASHBOARD_HOST;
  const oldPort = process.env.CREWLOOM_DASHBOARD_PORT;
  process.env.CREWLOOM_DASHBOARD_LOCAL = '1'; process.env.CREWLOOM_DASHBOARD_HOST = '127.0.0.1';
  process.env.CREWLOOM_DASHBOARD_PORT = '4317';
  try {
    const url = 'http://127.0.0.1:4317/api/overview';
    const direct = auth.authorize(new Request(url));
    assert.equal(direct.ok, true);
    if (direct.ok) assert.equal(direct.method, 'local');
    assert.equal(auth.authorize(new Request(url, { method: 'POST', headers: { Origin: 'http://127.0.0.1:4317' } })).ok, true);
    for (const req of [new Request('http://attacker.example:4317/api/overview'), new Request(url, { headers: { Origin:'https://attacker.example' } }), new Request(url,{method:'POST'})]) {
      assert.equal(auth.authorize(req).ok, false);
    }
    const session = await import('../app/api/auth/session/route.ts');
    const response = await session.GET(new Request(url));
    assert.equal((await response.json()).method, 'local');
    process.env.CREWLOOM_DASHBOARD_HOST = '0.0.0.0';
    assert.equal(auth.localAccess(),false);
  } finally {
    for (const [key, value] of Object.entries({ CREWLOOM_DASHBOARD_LOCAL:oldLocal, CREWLOOM_DASHBOARD_HOST:oldHost, CREWLOOM_DASHBOARD_PORT:oldPort })) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
  }
});
