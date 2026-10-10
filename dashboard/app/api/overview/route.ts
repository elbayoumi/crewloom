import { runMetrics } from '../../../lib/run-metrics.ts';
import { controlStatus } from '../../../lib/control-status.ts';
import { guard, privateHeaders } from '../../../lib/auth.ts';
import { PROJECT, listSkills, readRuns, readTools } from '../../../lib/repo.ts';

export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const [skills, tools, history, queue, budget] = await Promise.all([listSkills(), readTools(), readRuns(1000), controlStatus('queue'), controlStatus('budget')]);
  const runs = history.slice(0, 50);
  const failed = runs.filter((r) => r.exit_code !== 0).length;
  return Response.json({
    projectRoot: PROJECT,
    generatedAt: new Date().toISOString(),
    totals: {
      skills: skills.length, tools: tools.length, runs: runs.length, failedRuns: failed,
      attention: skills.filter((s) => s.status === 'attention').length,
      openTasks: skills.reduce((n, s) => n + s.openTasks, 0),
      openChallenges: skills.reduce((n, s) => n + s.openChallenges, 0),
    },
    skills, tools, runs, activity: runMetrics(history), controls: { queue, budget },
  }, { headers: { ...privateHeaders } });
}