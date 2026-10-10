import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runMetrics } from '../lib/run-metrics.ts';
import type { Run } from '../lib/repo.ts';

test('metrics preserve role separation, UTC buckets and actual failures', () => {
  const now = Date.parse('2026-10-10T12:00:00Z');
  const run = (skill: string, exit_code: number, duration_ms: number): Run =>
    ({ skill, exit_code, duration_ms, ts: '2026-10-09T23:00:00Z', tool: 'check', source: 'cli' });
  const result = runMetrics([run('a', 0, 100), run('a', 2, 300), run('b', 0, 10),
    { ...run('a', 0, 10), ts: 'invalid' }, run('a', 0, NaN)], now);
  assert.equal(result.window, 3);
  assert.deepEqual(result.roles[0], { role: 'a', total: 2, failed: 1, average_ms: 200 });
  assert.deepEqual(result.days[5], { date: '2026-10-09', total: 3, failed: 1 });
  assert.equal(result.days[6].total, 0);
});
