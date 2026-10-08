import { inSelectedProject, projectReferences } from '../../../lib/projects.ts';
import { guard, privateHeaders } from '../../../lib/auth.ts';
import { listSkills, readRuns, readTools, readTasks } from '../../../lib/repo.ts';

export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  return inSelectedProject(req, async (project) => {
  const [skills, tools, runs, taskView] = await Promise.all([listSkills(project.root), readTools(), readRuns(50, project.root), readTasks(project.root)]);
  const failed = runs.filter((r) => r.exit_code !== 0).length;
  return Response.json({
    projectRoot: project.root, projectId: project.id, projects: projectReferences(),
    generatedAt: new Date().toISOString(),
    totals: {
      skills: skills.length, tools: tools.length, runs: runs.length, failedRuns: failed,
      attention: skills.filter((s) => s.status === 'attention').length,
      openTasks: skills.reduce((n, s) => n + s.openTasks, 0),
      openChallenges: skills.reduce((n, s) => n + s.openChallenges, 0),
      unknownChallenges: skills.reduce((n, s) => n + s.unknownChallenges, 0),
      verified: skills.filter((s) => s.status === 'verified').length,
    },
    skills, tools, runs, tasks: taskView.tasks, taskDiagnostics: taskView.diagnostics,
  }, { headers: { ...privateHeaders } });
  });
}