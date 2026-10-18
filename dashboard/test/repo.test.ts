import { test } from 'node:test';
import assert from 'node:assert/strict';
import { countBrain, parseFrontmatter, parseRuns, isSkillId } from '../lib/repo.ts';

const runRow = (tool: string, exit_code=0) => JSON.stringify({ts:'2026-10-14T00:00:00Z',tool,
  skill:'context-guardian',exit_code,duration_ms:1,source:'cli'});

test('countBrain counts backlog items, entries, and only open challenges', () => {
  const c = countBrain({
    ROADMAP_TODO: '- [ ] a\n- [x] b\n- [ ] c',
    COMPLETED: '### 2026-01-01 — x\n### 2026-01-02 — y',
    CHALLENGES: '### 2026-01-01 — a\n- الحالة: مفتوح\n### 2026-01-02 — b\n- Status: resolved (2026-01-03)',
  });
  assert.deepEqual(c, { openTasks: 2, doneEntries: 2, openChallenges: 1, ideas: 0 });
});

test('placeholder brain files count as zero', () => {
  assert.equal(countBrain({ CHALLENGES: '# Challenges\n\nNo local incidents have been recorded.' }).openChallenges, 0);
});

test('compact memory entries are counted without counting metadata sub-bullets', () => {
  assert.deepEqual(countBrain({
    COMPLETED: '### 2026-10-01 — shipped\n- Evidence: tests\n- 2026-10-02 | Fixed parser',
    IDEAS_VAULT: '- 2026-10-02 | Try a bounded cache',
    CHALLENGES: '- 2026-10-02 | Status: open; interrupted task\n- 2026-10-03 | Status: resolved; older issue',
  }), { openTasks: 0, doneEntries: 2, openChallenges: 1, ideas: 1 });
});

test('a malformed JSON record does not erase valid run history', () => {
  const runs = parseRuns(`${runRow('a')}\nnull\n[]\n3\n${runRow('b',1)}\n`);
  assert.deepEqual(runs.map((run) => run.tool), ['a', 'b']);
});

test('malformed display fields cannot reach role health or the rendered run list', () => {
  const valid = {ts:'2026-10-14T00:00:00Z',tool:'a',skill:'context-guardian',exit_code:0,duration_ms:1,source:'cli'};
  const bad = [
    {...valid,source:{label:'cli'}}, {...valid,ts:null}, {...valid,ts:'invalid date'},
    {...valid,skill:[]}, {...valid,duration_ms:{}}, {...valid,duration_ms:-1},
    {...valid,output:{text:'bad'}}, {...valid,project_root:[]}, {...valid,tool:''},
  ];
  const runs = parseRuns([valid,...bad,valid].map((row)=>JSON.stringify(row)).join('\n'));
  assert.equal(runs.length,2);
  assert.ok(runs.every((row)=>row.source==='cli' && row.tool==='a'));
});

test('compact OPEN markers count without inventing status for unmarked history', () => {
  assert.equal(countBrain({CHALLENGES:'- 2026-10-13 | OPEN: failing import\n- 2026-10-14 | Cause: older failure; fixed'}).openChallenges,1);
});

test('untested installation templates stay idle', async () => {
  const { listSkills } = await import('../lib/repo.ts');
  const roles = await listSkills();
  assert.ok(roles.length > 0);
  assert.ok(roles.filter((role) => role.runs === 0 && role.openChallenges === 0).every((role) => role.status === 'idle'));
});

test('parseRuns skips torn lines', () => {
  const runs = parseRuns(`${runRow('a')}\n{"tool":\n${runRow('b',1)}\n`);
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
    await modules[0].appendRun({ ts: '2026-10-14T00:00:00Z', tool: 'workflow-contract', skill: 'automation-ops-engineer', exit_code: 0, duration_ms: 1, source: 'dashboard' });
    await modules[0].appendRun({ ts: '2026-10-14T00:00:00Z', tool: 'check', skill: 'context-guardian', exit_code: 2, duration_ms: 3, source: 'dashboard' });
    writeFileSync(modules[0].RUN_LOG, readFileSync(modules[0].RUN_LOG, 'utf8') + JSON.stringify({ project_root: modules[1].PROJECT, skill: 'foreign', exit_code: 0 }) + '\n');
    assert.equal((await modules[0].readRuns()).length, 2);
    assert.equal((await modules[0].readRuns()).some((r: { skill: string }) => r.skill === 'foreign'), false);
    assert.equal((await modules[1].readRuns()).length, 0);
    const escape = await modules[0].runTool('seo-packet', ['--packet=../two/workflow.json']);
    assert.notEqual(escape.exit_code, 0);
  } finally {
    if (oldProject === undefined) delete process.env.CREWLOOM_PROJECT; else process.env.CREWLOOM_PROJECT = oldProject;
    rmSync(folder, { recursive: true, force: true });
  }
});
