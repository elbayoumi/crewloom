import { test } from 'node:test';
import assert from 'node:assert/strict';
import { countBrain, parseFrontmatter, parseRuns, isSkillId } from '../lib/repo.ts';

test('countBrain counts backlog items, entries, and only open challenges', () => {
  const c = countBrain({
    ROADMAP_TODO: '- [ ] a\n- [x] b\n- [ ] c',
    COMPLETED: '### 2026-01-01 — x\n### 2026-01-02 — y',
    CHALLENGES: '### 2026-01-01 — a\n- الحالة: مفتوح\n### 2026-01-02 — b\n- Status: resolved (2026-01-03)',
  });
  assert.deepEqual(c, { openTasks: 2, doneEntries: 2, openChallenges: 1, resolvedChallenges: 1, unknownChallenges: 0, ideas: 0 });
});

test('placeholder brain files count as zero', () => {
  assert.equal(countBrain({ CHALLENGES: '# Challenges\n\nNo local incidents have been recorded.' }).openChallenges, 0);
});

test('parseRuns skips torn lines', () => {
  const runs = parseRuns('{"tool":"a","exit_code":0}\n{"tool":\n{"tool":"b","exit_code":1}\n');
  assert.deepEqual(runs.map((r) => r.tool), ['a', 'b']);
});

test('frontmatter and skill id validation', () => {
  assert.equal(parseFrontmatter('---\nname: x\ndescription: hello: world\n---\nbody').description, 'hello: world');
  assert.equal(isSkillId('../etc'), false);
  assert.equal(isSkillId('seo-growth-engineer'), true);
});

test('dashboard project memory, relative tool inputs, and run history stay isolated', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const path = await import('node:path');
  const { pathToFileURL } = await import('node:url');
  const folder = mkdtempSync(path.join(tmpdir(), 'crewloom-projects-'));
  const oldProject = process.env.CREWLOOM_PROJECT;
  try {
    const modules = [];
    for (const name of ['one', 'two']) {
      const project = path.join(folder, name);
      const role = path.join(project, '.agents', 'skills', 'context-guardian');
      mkdirSync(path.join(role, 'brain'), { recursive: true });
      writeFileSync(path.join(role, 'SKILL.md'), 'role');
      writeFileSync(path.join(role, 'brain', 'ARCHITECTURE.md'), name);
      writeFileSync(path.join(project, 'workflow.json'), name === 'one' ? readFileSync('../examples/workflows/valid.json') : '[]');
      process.env.CREWLOOM_PROJECT = project;
      const url = pathToFileURL(path.resolve('lib/repo.ts')); url.searchParams.set('project-test', name);
      modules.push(await import(url.href));
    }
    assert.equal((await modules[0].skillDetail('context-guardian')).brain.ARCHITECTURE, 'one');
    assert.equal((await modules[1].skillDetail('context-guardian')).brain.ARCHITECTURE, 'two');
    const result = await modules[0].runTool('workflow-contract', ['workflow.json']);
    assert.equal(result.exit_code, 0, result.output);
    await modules[0].appendRun({ ts: 'now', tool: 'workflow-contract', skill: 'automation-ops-engineer', exit_code: 0, duration_ms: 1, source: 'dashboard' });
    assert.equal((await modules[0].readRuns()).length, 1);
    assert.equal((await modules[1].readRuns()).length, 0);
    const escape = await modules[0].runTool('seo-packet', ['--packet=../two/workflow.json']);
    assert.notEqual(escape.exit_code, 0);
  } finally {
    if (oldProject === undefined) delete process.env.CREWLOOM_PROJECT; else process.env.CREWLOOM_PROJECT = oldProject;
    rmSync(folder, { recursive: true, force: true });
  }
});
