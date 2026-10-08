import { spawn } from 'node:child_process';
import path from 'node:path';
import { ROOT } from './repo.ts';

import type { ProjectCatalog } from './project-commands.ts';

/** Server-selected catalog only. No request can supply a filesystem path. */
export async function catalogRequest(action: 'list' | 'cancel-task', projectId?: string, taskId?: string): Promise<ProjectCatalog | { status?: string; error?: string }> {
  const catalog = process.env.CREWLOOM_CATALOG;
  if (!catalog) return action === 'list' ? { configured: false, projects: [] } : { error: 'No project catalog configured' };
  return new Promise((resolve) => {
    const child = spawn(process.env.PYTHON ?? 'python3', [path.join(ROOT, 'scripts/crewloom.py'),
      'projects', action, '--catalog', catalog,
      ...(action === 'cancel-task' ? ['--project-id', projectId ?? '', '--task-id', taskId ?? ''] : [])], { cwd: ROOT, shell: false });
    let output = ''; let size = 0; let refused = false;
    const timer = setTimeout(() => { refused = true; child.kill(); }, 15000);
    child.stdout.on('data', (chunk: Buffer) => {
      size += chunk.length;
      if (size > 2 * 1024 * 1024) { refused = true; child.kill(); } else output += chunk.toString();
    });
    child.stderr.resume();
    child.on('error', () => { clearTimeout(timer); resolve({ configured: true, projects: [], error: 'Project catalog process unavailable' }); });
    child.on('close', (code) => {
      clearTimeout(timer);
      try {
        const result = JSON.parse(output);
        if (refused || code !== 0 || (action === 'list' && !Array.isArray(result.projects))) throw new Error(result.error ?? 'Catalog read refused');
        resolve(action === 'list' ? { configured: true, projects: result.projects } : result);
      } catch (error) { resolve({ configured: true, projects: [], error: String(error) }); }
    });
  });
}


export async function projectCatalog(): Promise<ProjectCatalog> {
  return await catalogRequest('list') as ProjectCatalog;
}
