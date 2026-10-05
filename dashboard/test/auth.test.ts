import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MIN_TOKEN_LENGTH,
  SESSION_COOKIE,
  accessToken,
  authorize,
  clearedSessionCookie,
  expectedOrigins,
  guard,
  issueSession,
  originTrusted,
  readCookie,
  secretEquals,
  sessionCookie,
  sessionState,
} from '../lib/auth.ts';

const TOKEN = 'a'.repeat(43);
const ORIGIN = 'http://127.0.0.1:4317';

/** Run a body with the server environment this module reads, then restore it exactly. */
async function withServerEnv<T>(values: Record<string, string | undefined>, body: () => T | Promise<T>): Promise<T> {
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

const server = { CREWLOOM_DASHBOARD_TOKEN: TOKEN, CREWLOOM_DASHBOARD_HOST: '127.0.0.1', CREWLOOM_DASHBOARD_PORT: '4317' };
const get = (headers: Record<string, string> = {}, method = 'GET') => new Request('http://127.0.0.1:4317/api/overview', { method, headers });

function sessionCookieHeader(): string {
  return `${SESSION_COOKIE}=${issueSession(TOKEN).value}`;
}

test('every API route refuses an unauthenticated read before touching project data', async () => {
  await withServerEnv(server, () => {
    const decision = authorize(get());
    assert.equal(decision.ok, false);
    assert.equal(decision.ok === false && decision.status, 401);
  });
});

test('a wrong or empty credential is refused identically', async () => {
  await withServerEnv(server, () => {
    const cases: Record<string, string>[] = [
      { authorization: 'Bearer wrong-token' }, { cookie: `${SESSION_COOKIE}=deadbeef` }, { cookie: '' },
    ];
    for (const header of cases) {
      const decision = authorize(get(header));
      assert.equal(decision.ok, false);
      assert.equal(decision.ok === false && decision.status, 401);
    }
  });
});

test('secret comparison is length independent and rejects non-strings', () => {
  assert.equal(secretEquals(TOKEN, TOKEN), true);
  assert.equal(secretEquals(TOKEN.slice(1), TOKEN), false);
  assert.equal(secretEquals(undefined, TOKEN), false);
  assert.equal(secretEquals(null, TOKEN), false);
  assert.equal(secretEquals(TOKEN, ''), false);
});

test('a session cookie is HttpOnly, SameSite, expiring, and never carries the token', async () => {
  await withServerEnv(server, () => {
    const session = issueSession(TOKEN);
    const cookie = sessionCookie(session.value);
    assert.match(cookie, /HttpOnly/);
    assert.match(cookie, /SameSite=Strict/);
    assert.match(cookie, /Max-Age=3600/);
    assert.equal(cookie.includes(TOKEN), false);
    assert.equal(sessionState(`${SESSION_COOKIE}=${session.value}`, TOKEN).ok, true);
    assert.equal(sessionState(`${SESSION_COOKIE}=${session.value}`, TOKEN).expiresAt, session.expiresAt);
    assert.match(clearedSessionCookie(), /Max-Age=0/);
  });
});

test('an expired, edited, or cross-token session stops authorizing', async () => {
  await withServerEnv(server, () => {
    const session = issueSession(TOKEN);
    const later = Date.now() + 3600 * 1000 + 1000;
    assert.equal(sessionState(`${SESSION_COOKIE}=${session.value}`, TOKEN, later).ok, false);
    const edited = `${session.value.slice(0, -1)}${session.value.endsWith('a') ? 'b' : 'a'}`;
    assert.equal(sessionState(`${SESSION_COOKIE}=${edited}`, TOKEN).ok, false);
    assert.equal(sessionState(`${SESSION_COOKIE}=${session.value}`, 'b'.repeat(43)).ok, false);
    assert.equal(sessionState(null, TOKEN).ok, false);
    assert.equal(sessionState('garbage', TOKEN).ok, false);
  });
});

test('mutating requests need an exact trusted origin; bearer automation does not', async () => {
  await withServerEnv(server, () => {
    const cookie = { cookie: sessionCookieHeader() };
    assert.equal(authorize(get({ ...cookie, origin: ORIGIN }, 'POST')).ok, true);
    for (const headers of [{ ...cookie }, { ...cookie, origin: 'http://evil.example' },
      { ...cookie, origin: 'http://127.0.0.1:4318' }, { ...cookie, origin: 'https://127.0.0.1:4317' },
      { ...cookie, referer: ORIGIN }]) {
      const decision = authorize(get(headers, 'POST'));
      assert.equal(decision.ok, false, JSON.stringify(headers));
      assert.equal(decision.ok === false && decision.status, 403);
    }
    // A forged Host moves the request URL; it must not become the trusted origin.
    const forged = new Request('http://attacker.invalid:4317/api/run', { method: 'POST', headers: cookie });
    assert.equal(authorize(forged).ok, false);
// Authentication is decided before provenance: anonymous callers are told 401, not 403.
const anonymous = authorize(get({}, 'POST'));
assert.equal(anonymous.ok === false && anonymous.status, 401);
    const bearer = authorize(get({ authorization: `Bearer ${TOKEN}` }, 'POST'));
    assert.deepEqual(bearer, { ok: true, method: 'bearer', expiresAt: null });
    assert.equal(authorize(get({ authorization: `Bearer ${TOKEN}` })).ok, true);
  });
});

test('the origin allowlist comes from server configuration, never from the request', async () => {
  await withServerEnv({ ...server, CREWLOOM_DASHBOARD_HOST: 'dashboard.internal', CREWLOOM_DASHBOARD_PORT: '9000',
    CREWLOOM_DASHBOARD_SCHEME: 'https', CREWLOOM_DASHBOARD_ORIGINS: 'https://ops.example.com' }, () => {
    assert.deepEqual(expectedOrigins(), ['https://dashboard.internal:9000', 'https://ops.example.com']);
    assert.equal(originTrusted('http://127.0.0.1:4317'), false);
    assert.equal(originTrusted('https://ops.example.com'), true);
    assert.equal(originTrusted('https://ops.example.com.evil.test'), false);
    assert.equal(originTrusted('null'), false);
    assert.equal(originTrusted(''), false);
    // An https deployment marks its session cookie Secure.
    assert.match(sessionCookie('v'), /; Secure$/);
  });
  await withServerEnv(server, () => {
    assert.equal(sessionCookie('v').includes('Secure'), false);
    for (const host of ['127.0.0.1', 'localhost', '[::1]']) assert.equal(expectedOrigins().includes(`http://${host}:4317`), true);
    assert.equal(originTrusted('http://localhost:4317'), true);
    // A bare serialized origin only: a path, query, fragment, or userinfo is malformed.
    for (const malformed of ['http://127.0.0.1:4317/evil', 'http://127.0.0.1:4317/', 'http://127.0.0.1:4317?x=1',
      'http://127.0.0.1:4317#x', 'http://user@127.0.0.1:4317', 'null', 'file:///etc/passwd']) {
      assert.equal(originTrusted(malformed), false, malformed);
    }
  });
});

test('an unconfigured server fails closed instead of serving project data', async () => {
  await withServerEnv({ ...server, CREWLOOM_DASHBOARD_TOKEN: undefined }, () => {
    const decision = authorize(get({ authorization: 'Bearer anything' }));
    assert.equal(decision.ok, false);
    assert.equal(decision.ok === false && decision.status, 503);
    const denied = guard(get());
    assert.equal(denied?.status, 503);
    assert.equal(denied?.headers.get('WWW-Authenticate'), null);
  });
});

test('a credential too short to be a secret is refused like a missing one', async () => {
  await withServerEnv({ ...server, CREWLOOM_DASHBOARD_TOKEN: 'weak' }, () => {
    assert.equal(accessToken(), null);
    const decision = authorize(get({ authorization: 'Bearer weak' }));
    assert.equal(decision.ok === false && decision.status, 503);
    assert.match(decision.ok === false ? decision.error : '', /at least 32 characters/);
  });
  await withServerEnv({ ...server, CREWLOOM_DASHBOARD_TOKEN: 'k'.repeat(MIN_TOKEN_LENGTH) }, () => {
    assert.equal(accessToken(), 'k'.repeat(MIN_TOKEN_LENGTH));
    assert.equal(authorize(get({ authorization: `Bearer ${'k'.repeat(MIN_TOKEN_LENGTH)}` })).ok, true);
  });
});

test('the refusal response carries no secret and asks for bearer automation', async () => {
  await withServerEnv(server, async () => {
    const denied = guard(get());
    assert.equal(denied?.status, 401);
    assert.match(denied?.headers.get('WWW-Authenticate') ?? '', /Bearer/);
    assert.equal(denied?.headers.get('Cache-Control'), 'no-store');
    assert.equal(denied?.headers.get('Vary'), 'Cookie');
    const body = await denied?.json();
    assert.equal(JSON.stringify(body).includes(TOKEN), false);
    assert.equal(guard(get({ cookie: sessionCookieHeader() })), null);
  });
});

test('readCookie parses a cookie header without trusting its ordering', () => {
  assert.equal(readCookie(`other=1; ${SESSION_COOKIE}=value; last=2`), 'value');
  assert.equal(readCookie(`${SESSION_COOKIE}= value `), 'value');
  assert.equal(readCookie('nonsense'), null);
  assert.equal(readCookie(null), null);
});