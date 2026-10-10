import type { Run } from './repo.ts';

/** Bounded project-owned run window; invalid/torn entries never invent successes. */
export function runMetrics(runs: Run[], now = Date.now()) {
  const valid = runs.filter((r) => typeof r.skill === 'string' && Number.isInteger(r.exit_code)
    && Number.isFinite(r.duration_ms) && r.duration_ms >= 0 && Number.isFinite(Date.parse(r.ts)));
  const byRole = new Map<string, { role: string; total: number; failed: number; duration: number }>();
  for (const run of valid) {
    const role = byRole.get(run.skill) ?? { role: run.skill, total: 0, failed: 0, duration: 0 };
    role.total++; role.failed += run.exit_code === 0 ? 0 : 1; role.duration += run.duration_ms;
    byRole.set(run.skill, role);
  }
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(now - (6 - index) * 86400000).toISOString().slice(0, 10);
    const mine = valid.filter((r) => new Date(r.ts).toISOString().slice(0, 10) === date);
    return { date, total: mine.length, failed: mine.filter((r) => r.exit_code !== 0).length };
  });
  return { window: valid.length, days, roles: [...byRole.values()].map((r) => ({ role: r.role,
    total: r.total, failed: r.failed, average_ms: Math.round(r.duration / r.total) }))
    .sort((a, b) => b.total - a.total || a.role.localeCompare(b.role)) };
}
