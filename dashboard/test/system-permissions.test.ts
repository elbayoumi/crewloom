import { test } from 'node:test';
import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { probeAccessibility, probeScreenRecording, openPreferencePane, COMMAND_TIMEOUT_MS } from '../lib/permissions.ts';

test('accessibility is unknown without a native controller trust measurement', async () => {
  assert.equal((await probeAccessibility()).granted, null);
});
test('capture is noninteractive, passes argv directly, and rejects absent or fake files', async () => {
  const noFile = await probeScreenRecording(async (file, args) => {
    assert.equal(file, 'screencapture'); assert.equal(args[0], '-x'); return { ok: true };
  });
  assert.equal(noFile.granted, false);
  assert.equal((await probeScreenRecording(async (_, args) => { await writeFile(args[1], 'not a png'); return { ok: true }; })).granted, false);
  const valid = await probeScreenRecording(async (_, args) => {
    await writeFile(args[1], Buffer.from([137,80,78,71,13,10,26,10,1])); return { ok: true };
  });
  assert.equal(valid.granted, true);
});
test('capture failure remains explicit and commands have a timeout', async () => {
  assert.deepEqual(await probeScreenRecording(async () => ({ ok: false, error: 'timeout' })), { granted: false, error: 'timeout' });
  assert.equal(COMMAND_TIMEOUT_MS, 5000);
});
test('preference pane uses fixed allowlist and shell-free argv', async () => {
  let calls = 0;
  const run = async (file: string, args: string[]) => { calls++; assert.equal(file, 'open'); assert.deepEqual(args, ['x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture']); return { ok: true }; };
  for (const pane of ['Privacy_Anything','../../etc','Privacy_Accessibility;id']) assert.equal((await openPreferencePane(pane, run)).ok, false);
  assert.equal(calls, 0); assert.equal((await openPreferencePane('Privacy_ScreenCapture', run)).ok, true);
});

test('new routes refuse unauthorized and foreign-origin requests before OS actions', async () => {
  const env = { CREWLOOM_DASHBOARD_TOKEN: 'z'.repeat(43), CREWLOOM_DASHBOARD_HOST: '127.0.0.1', CREWLOOM_DASHBOARD_PORT: '4317', CREWLOOM_DASHBOARD_LOCAL_ACCESS: undefined };
  const before = new Map(Object.keys(env).map(key => [key, process.env[key]]));
  Object.entries(env).forEach(([key, value]) => { if (value === undefined) delete process.env[key]; else process.env[key] = value; });
  try {
    const extension = await import('../app/api/extension/route.ts');
    const permissions = await import('../app/api/system-permissions/route.ts');
    for (const module of [extension, permissions]) {
      assert.equal((await module.GET(new Request('http://127.0.0.1:4317/api/test'))).status, 401);
      assert.equal((await module.POST(new Request('http://127.0.0.1:4317/api/test', { method: 'POST', headers: { Origin: 'https://foreign.example' }, body: '{}' }))).status, 401);
    }
    const { SESSION_COOKIE, issueSession } = await import('../lib/auth.ts');
    const cookie = `${SESSION_COOKIE}=${issueSession(env.CREWLOOM_DASHBOARD_TOKEN).value}`;
    const foreign = new Request('http://127.0.0.1:4317/api/test', { method: 'POST', headers: { Origin: 'https://foreign.example', Cookie: cookie }, body: '{}' });
    assert.equal((await permissions.POST(foreign)).status, 403);
    const good = new Request('http://127.0.0.1:4317/api/extension', { headers: { authorization: `Bearer ${env.CREWLOOM_DASHBOARD_TOKEN}` } });
    const result = await extension.GET(good); assert.equal(result.status, 200);
    const body = await result.json(); assert.equal(body.computerUseActive, null); assert.equal(body.connection, 'unverified');
    const post = await extension.POST(new Request(good, { method: 'POST', body: '{}' })); assert.equal(post.status, 405);
  } finally { before.forEach((value, key) => { if (value === undefined) delete process.env[key]; else process.env[key] = value; }); }
});
