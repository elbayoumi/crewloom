import { test } from 'node:test';
import assert from 'node:assert/strict';
import { countBrain, parseFrontmatter, parseRuns, isSkillId } from '../lib/repo.ts';

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

test('parseRuns skips torn lines', () => {
  const runs = parseRuns('{"tool":"a","exit_code":0}\n{"tool":\n{"tool":"b","exit_code":1}\n');
  assert.deepEqual(runs.map((r) => r.tool), ['a', 'b']);
});

test('frontmatter and skill id validation', () => {
  assert.equal(parseFrontmatter('---\nname: x\ndescription: hello: world\n---\nbody').description, 'hello: world');
  assert.equal(isSkillId('../etc'), false);
  assert.equal(isSkillId('seo-growth-engineer'), true);
});
