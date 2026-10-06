import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgv } from '../lib/argv.ts';
import { challengeStatus, countBrain, currentFailures, parseFrontmatter, roleStatus, validateArgs } from '../lib/repo.ts';
import type { Evidence, Run } from '../lib/repo.ts';

const evidence = (over: Partial<Evidence> = {}): Evidence => ({ documented: true, configured: false, exercised: false, verified: false, acceptance: 'none-recorded', ...over });
const none = { currentFailures: [] as string[], openChallenges: 0, unknownChallenges: 0 };
const run = (tool: string, exit_code: number): Run => ({ ts: 't', tool, skill: 's', exit_code, duration_ms: 1, source: 'cli' });

// R10
test('a challenge without a recognised status is unknown, never closed (English and Arabic)', () => {
  assert.equal(challengeStatus('2026-01-01 — a\n- Cause: x\n- Fix: y'), 'unknown');
  assert.equal(challengeStatus('a\n- الحالة: قيد المراجعة'), 'unknown');
  assert.equal(challengeStatus('a\n- Status: pending'), 'unknown');
  for (const line of ['- الحالة: مفتوح', '- Status: Open', '**Status:** open (2026-10-01)', 'State: ongoing', '- الحالة: مفتوحة']) assert.equal(challengeStatus('a\n' + line), 'open', line);
  for (const line of ['- الحالة: محلول (2026-10-03)', '- Status: resolved', '- Status: Closed 2026-10-06', '- الحالة: مغلق', 'Status: fixed']) assert.equal(challengeStatus('a\n' + line), 'resolved', line);
  const counts = countBrain({ CHALLENGES: '### one\n- Status: open\n### two\nno status here\n### three\n- الحالة: محلول' });
  assert.deepEqual([counts.openChallenges, counts.unknownChallenges, counts.resolvedChallenges], [1, 1, 1]);
});

test('unknown challenge status makes a role need attention', () => {
  assert.equal(roleStatus({ ...none, evidence: evidence({ exercised: true }), unknownChallenges: 1 }), 'attention');
});

// R09
test('documentation alone never creates a success verdict', () => {
  assert.equal(roleStatus({ ...none, evidence: evidence() }), 'documented');
  assert.equal(roleStatus({ ...none, evidence: evidence({ configured: true }) }), 'configured');
  assert.notEqual(roleStatus({ ...none, evidence: evidence({ configured: true }) }), 'verified');
});

test('a successful tool exit is exercised, not accepted; only an acceptance record verifies', () => {
  assert.equal(roleStatus({ ...none, evidence: evidence({ configured: true, exercised: true }) }), 'exercised');
  assert.equal(roleStatus({ ...none, evidence: evidence({ configured: true, exercised: true, verified: true, acceptance: 'recorded' }) }), 'verified');
});

test('a failing current run stays visible even after earlier passes; a later pass clears it', () => {
  assert.deepEqual(currentFailures([run('a', 1), run('a', 0), run('b', 0)]), ['a']);
  assert.deepEqual(currentFailures([run('a', 0), run('a', 1)]), []);
  assert.equal(roleStatus({ ...none, evidence: evidence({ exercised: true, verified: true }), currentFailures: ['a'] }), 'attention');
});

test('listSkills over a real project: no role is healthy without evidence; acceptance and failures are read from the project', async () => {
  const folder = mkdtempSync(path.join(tmpdir(), 'crewloom-evidence-'));
  const old = process.env.CREWLOOM_PROJECT;
  try {
    process.env.CREWLOOM_PROJECT = folder;
    const url = pathToFileURL(path.resolve('lib/repo.ts')); url.searchParams.set('evidence', String(Date.now()));
    const repo = await import(url.href);
    const first = await repo.listSkills();
    assert.ok(first.length >= 40);
    assert.deepEqual([...new Set(first.map((s: { status: string }) => s.status))], ['documented'], 'zero runs, nothing installed: documented only');
    assert.ok(first.every((s: { evidence: Evidence }) => !s.evidence.exercised && !s.evidence.verified));
    mkdirSync(path.join(folder, '.crewloom', 'acceptance'), { recursive: true });
    writeFileSync(path.join(folder, '.crewloom', 'acceptance', 'context-guardian.json'), JSON.stringify({ schema_version: 1, passed: true, exit_code: 0, command: 'python3 -m unittest' }));
    writeFileSync(path.join(folder, '.crewloom', 'acceptance', 'seo-growth-engineer.json'), JSON.stringify({ passed: true }));
    const registered = JSON.parse(readFileSync(path.resolve('../documentation/TOOLS.json'), 'utf8')).tools[0];
    writeFileSync(path.join(folder, '.crewloom', 'runs.jsonl'), JSON.stringify({ ts: 't', tool: registered.id, skill: registered.skill, exit_code: 1, duration_ms: 1, source: 'cli' }) + '\n');
    const second = await repo.listSkills();
    const by = (id: string) => second.find((s: { id: string }) => s.id === id);
    assert.equal(by('context-guardian').status === 'verified' || by('context-guardian').currentFailures.length > 0, true);
    assert.equal(by('seo-growth-engineer').evidence.verified, false, 'an incomplete acceptance record does not verify');
    assert.equal(by(registered.skill).status, 'attention');
    assert.deepEqual(by(registered.skill).currentFailures, [registered.id]);
  } finally { process.env.CREWLOOM_PROJECT = old; rmSync(folder, { recursive: true, force: true }); }
});

// R19
test('folded, literal, quoted and multi-line descriptions parse to their text', () => {
  const doc = (body: string) => `---\nname: x\n${body}\n---\nbody`;
  assert.equal(parseFrontmatter(doc('description: >-\n  First line\n  second line\n')).description, 'First line second line');
  assert.equal(parseFrontmatter(doc('description: >\n  Folded one\n  still one\n\n  new paragraph\n')).description, 'Folded one still one\nnew paragraph');
  assert.equal(parseFrontmatter(doc('description: |\n  line one\n  line two\n')).description, 'line one\nline two');
  assert.equal(parseFrontmatter(doc('description: "He said \\"hi\\": ok"')).description, 'He said "hi": ok');
  assert.equal(parseFrontmatter(doc("description: 'it''s: fine'")).description, "it's: fine");
  assert.equal(parseFrontmatter(doc('description: plain start\n  and a continuation')).description, 'plain start and a continuation');
  assert.equal(parseFrontmatter(doc('description: يصف دورًا\n  بالعربية')).description, 'يصف دورًا بالعربية');
  const flow = parseFrontmatter(doc('description: [a, b]'));
  assert.equal(flow.description, undefined);
  assert.match(String(flow.warnings), /Unsupported YAML value for description/);
  assert.equal(parseFrontmatter(doc('description: hello: world')).description, 'hello: world');
});

test('every shipped role parses to a real description and the frontmatter bound holds', () => {
  const roles = path.resolve('../.agents/skills');
  const ids = readdirSync(roles).filter((id) => /^[a-z0-9-]+$/.test(id));
  assert.ok(ids.length >= 40);
  for (const id of ids) {
    const description = parseFrontmatter(readFileSync(path.join(roles, id, 'SKILL.md'), 'utf8')).description ?? '';
    assert.ok(description.length > 10 && !/^[>|]/.test(description), id);
  }
  const huge = `---\nname: x\ndescription: ok\n${'k: v\n'.repeat(100000)}---\n`;
  const bounded = parseFrontmatter(huge);
  assert.equal(bounded.description, undefined, 'unterminated frontmatter beyond the bound is not guessed');
  assert.match(String(bounded.warnings), /not closed within/);
  const longBody = parseFrontmatter(`---\nname: x\ndescription: ok\n---\n${'body\n'.repeat(100000)}`);
  assert.equal(longBody.description, 'ok');
});

// R18
test('quoted arguments stay single arguments, including spaces, Arabic and special characters', () => {
  assert.deepEqual(parseArgv('--project "/p/My Project" --input "docs/ملف عربي.md"').argv, ['--project', '/p/My Project', '--input', 'docs/ملف عربي.md']);
  assert.deepEqual(parseArgv("'a b' c\\ d \"q\\\"uote\" it's".replace("it's", "x")).argv, ['a b', 'c d', 'q"uote', 'x']);
  assert.deepEqual(parseArgv('--note="a & b; $HOME `x`"').argv, ['--note=a & b; $HOME `x`']);
  assert.deepEqual(parseArgv('   ').argv, []);
  assert.deepEqual(parseArgv('a "" b').argv, ['a', '', 'b']);
  assert.deepEqual(parseArgv('src/*.py').argv, ['src/*.py'], 'no glob or shell expansion');
});

test('malformed or oversized argument text is an error, not a guess', () => {
  for (const bad of ['"open', "'open", 'trailing\\']) assert.ok(parseArgv(bad).error, bad);
  assert.ok(parseArgv(Array(65).fill('a').join(' ')).error);
  assert.ok(parseArgv('x'.repeat(4097)).error);
  assert.equal(parseArgv('ok').error, undefined);
});

test('the server still refuses traversal, absolute paths and NUL while accepting spaced Arabic paths', () => {
  assert.equal(validateArgs(['docs/ملف عربي.md', '--root', 'a b/c']), null);
  for (const bad of ['../outside', 'a/../../b', '/etc/passwd', 'x\0y', '..\\win']) assert.match(String(validateArgs([bad])), /Rejected argument/, bad);
  assert.equal(validateArgs(['--flag=../x']), null, 'an option value is the tool\'s own business');
});
