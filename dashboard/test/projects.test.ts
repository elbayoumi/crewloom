import { test } from 'node:test';
import assert from 'node:assert/strict';
import { projectCommand, type ProjectRecord } from '../lib/project-commands.ts';
const project: ProjectRecord = { project_id: 'project-a', project_root: "/tmp/owner's project", checkout_id: 'a'.repeat(32),
  available: true, tasks: [{ task_id: 'task-one', role: 'context-guardian', status: 'active' }], workflows: [], batches: [] };
test('commands preserve explicit identity and quote roots for shell display', () => {
  const command = projectCommand(project, 'status', 'task-one');
  assert.match(command, /--project-id 'project-a'/);
  assert.ok(command.includes("'/tmp/owner'\\''s project'"));
  assert.match(command, /--task-id 'task-one'/);
});
test('resume includes the owning role and cancellation names an explicit reason', () => {
  assert.match(projectCommand(project, 'enter', 'task-one'), /--role 'context-guardian'/);
  assert.match(projectCommand(project, 'cancel', 'task-one'), /--reason 'operator request'/);
});
test('all project API methods authenticate before reading or mutating', async () => {
  const { readFileSync } = await import('node:fs');
  const source = readFileSync(new URL('../app/api/projects/route.ts', import.meta.url), 'utf8');
  for (const action of ['GET', 'POST']) {
    const section = source.split(`export async function ${action}`)[1];
    assert.ok(section.indexOf('guard(req)') < section.indexOf(action === 'GET' ? 'await projectCatalog' : 'await catalogRequest'));
  }
  assert.match(source, /Object.keys\(body\).some/);
});

test('separate auth module copies share issuance and revocation within the server process', async () => {
  const first = await import('../lib/auth.ts');
  const second = await import(new URL('../lib/auth.ts?catalog-copy', import.meta.url).href);
  const token = 'catalog-test-only-secret-value-32-characters';
  const issued = first.issueSession(token);
  const cookie = first.SESSION_COOKIE + '=' + issued.value;
  assert.equal(second.sessionState(cookie, token).ok, true);
  second.revokeSession(cookie);
  assert.equal(first.sessionState(cookie, token).ok, false);
});

test('project routes refuse anonymous callers and browser-supplied paths', async () => {
  const routes = await import('../app/api/projects/route.ts');
  const previous = process.env.CREWLOOM_DASHBOARD_TOKEN;
  process.env.CREWLOOM_DASHBOARD_TOKEN = 'catalog-test-only-secret-value-32-characters';
  try {
    for (const method of ['GET', 'POST']) {
      const response = await routes[method as 'GET' | 'POST'](new Request('http://127.0.0.1:4317/api/projects', { method }));
      assert.equal(response.status, 401);
    }
    const injected = await routes.POST(new Request('http://127.0.0.1:4317/api/projects', {
      method: 'POST', headers: { authorization: 'Bearer ' + process.env.CREWLOOM_DASHBOARD_TOKEN, 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'cancel-task', project_id: 'project-a', task_id: 'task-one', project_root: '/other' }),
    }));
    assert.equal(injected.status, 400);
  } finally {
    if (previous === undefined) delete process.env.CREWLOOM_DASHBOARD_TOKEN;
    else process.env.CREWLOOM_DASHBOARD_TOKEN = previous;
  }
});
