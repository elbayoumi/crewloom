/** Concurrent requests bind existing approved roots without a mutable global project selection. */
import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync, symlinkSync, realpathSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { projectReferences, selectedProject } from '../lib/projects.ts';
import { appendRun, skillDetail, readRuns, readTasks } from '../lib/repo.ts';
function fixture() {
  const root = realpathSync(mkdtempSync(path.join(tmpdir(), 'crewloom-dashboard-multi-')));
  const saved = process.env.CREWLOOM_PROJECTS;
  const projects = ['project-one', 'project-two'].map((id) => {
    const project = path.join(root, id);
    const brain = path.join(project, '.agents', 'skills', 'context-guardian', 'brain');
    mkdirSync(brain, { recursive: true });
    writeFileSync(path.join(project, 'crewloom.project.json'), JSON.stringify({ schema_version: 1, project_id: id }));
    writeFileSync(path.join(brain, 'ARCHITECTURE.md'), id);
    writeFileSync(path.join(brain, '..', 'SKILL.md'), 'local role');
    return { id, root: project };
  });
  process.env.CREWLOOM_PROJECTS = JSON.stringify(projects);
  return { root, projects, cleanup() { if (saved === undefined) delete process.env.CREWLOOM_PROJECTS; else process.env.CREWLOOM_PROJECTS = saved; rmSync(root, { recursive: true, force: true }); } };
}
const request = (id?: string) => new Request('http://127.0.0.1:4317/api/overview' + (id ? '?project=' + encodeURIComponent(id) : ''));
test('concurrent projects keep brain reads and run writes separate', async () => {
  const f = fixture();
  try {
    await Promise.all(f.projects.map(async (item, i) => {
      const selected = selectedProject(request(item.id));
      await new Promise((resolve) => setTimeout(resolve, i ? 1 : 20));
      assert.equal((await skillDetail('context-guardian', selected.root))?.brain.ARCHITECTURE, item.id);
      await appendRun({ ts: 'synthetic', tool: item.id, skill: 'context-guardian', exit_code: 0, duration_ms: 1, source: 'dashboard' }, selected.root);
      assert.deepEqual((await readRuns(10, selected.root)).map((run) => run.tool), [item.id]);
    }));
    for (const item of f.projects) assert.equal(JSON.parse(readFileSync(path.join(item.root, '.crewloom', 'runs.jsonl'), 'utf8')).project_root, item.root);
  } finally { f.cleanup(); }
});
test('ambiguous, arbitrary, duplicate and mismatched selections refuse without writes', () => {
  const f = fixture();
  try {
    assert.throws(() => selectedProject(request()));
    assert.throws(() => selectedProject(request('../project-one')));
    process.env.CREWLOOM_PROJECTS = JSON.stringify([f.projects[0], f.projects[0]]);
    assert.throws(() => projectReferences(), /Duplicate/);
    process.env.CREWLOOM_PROJECTS = JSON.stringify([{ ...f.projects[0], id: 'wrong-id' }]);
    assert.throws(() => projectReferences(), /identity/);
    assert.equal(existsSync(path.join(f.projects[1].root, '.crewloom')), false);
  } finally { f.cleanup(); }
});
test('project aliases and runtime symlinks cannot redirect selection', () => {
  const f = fixture();
  try {
    const alias = path.join(f.root, 'alias'); symlinkSync(f.projects[0].root, alias, 'dir');
    process.env.CREWLOOM_PROJECTS = JSON.stringify([{ ...f.projects[0], root: alias }]);
    assert.throws(() => projectReferences(), /canonical/);
    process.env.CREWLOOM_PROJECTS = JSON.stringify(f.projects);
    symlinkSync(f.projects[1].root, path.join(f.projects[0].root, '.crewloom'), 'dir');
    assert.throws(() => selectedProject(request('project-one')), /aliases/);
  } finally { f.cleanup(); }
});

test('task summaries show scoped status without exposing task payloads or accepting foreign state', async () => {
  const f = fixture();
  try {
    const project = f.projects[0];
    const tasks = path.join(project.root, '.crewloom', 'tasks');
    mkdirSync(path.join(tasks, 'task-one'), { recursive: true });
    mkdirSync(path.join(tasks, 'foreign-task'), { recursive: true });
    const binding = { project_id: project.id, project_root: project.root, checkout_id: 'synthetic-checkout' };
    writeFileSync(path.join(project.root, '.crewloom', 'binding.json'), JSON.stringify(binding));
    const record = { ...binding, schema_version: 1, task_id: 'task-one', role: 'context-guardian', status: 'complete', verified: false, prompt: 'private synthetic payload' };
    writeFileSync(path.join(tasks, 'task-one', 'state.json'), JSON.stringify(record));
    writeFileSync(path.join(tasks, 'foreign-task', 'state.json'), JSON.stringify({ ...record, task_id: 'foreign-task', project_root: f.projects[1].root }));
    const view = await readTasks(project.root);
    assert.deepEqual(view.tasks.map((task) => task.id), ['task-one']);
    assert.equal(view.tasks[0].verified, false, 'completion alone is not acceptance');
    assert.equal(JSON.stringify(view).includes('private synthetic payload'), false);
    assert.equal(view.diagnostics.length, 1);
  } finally { f.cleanup(); }
});
