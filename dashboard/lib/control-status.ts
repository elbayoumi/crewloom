import { spawn } from 'node:child_process';
import path from 'node:path';
import { ROOT } from './repo.ts';

/** Read-only controls selected by server configuration. Never accept browser paths. */
export async function controlStatus(kind: 'queue' | 'budget') {
  const directory = process.env[kind === 'queue' ? 'CREWLOOM_QUEUE' : 'CREWLOOM_USAGE_BUDGET'];
  if (!directory) return { configured: false };
  return new Promise<Record<string, unknown>>((resolve) => {
    const child = spawn(process.env.PYTHON ?? 'python3', [path.join(ROOT, 'scripts/crewloom.py'),
      kind, 'status', '--directory', directory], { cwd: ROOT, shell: false });
    let output = ''; let size = 0; let refused = false;
    const timer = setTimeout(() => { refused = true; child.kill(); }, 10000);
    child.stdout.on('data', (chunk: Buffer) => {
      size += chunk.length;
      if (size > 4 * 1024 * 1024) { refused = true; child.kill(); } else output += chunk.toString();
    });
    child.stderr.resume();
    child.on('error', () => { clearTimeout(timer); resolve({ configured: true, error: 'Control process unavailable' }); });
    child.on('close', (code) => {
      clearTimeout(timer);
      try {
        const result = JSON.parse(output);
        if (refused || code !== 0 || result.error) throw new Error(result.error ?? 'Control status refused');
        if (kind === 'queue') {
          if (!Array.isArray(result.jobs)) throw new Error('Malformed queue status');
          // Do not expose shared filesystem paths or manifests to the browser.
          resolve({ configured: true, jobs: result.jobs.slice(-100).map((j: Record<string, unknown>) =>
            ({ id: j.id, project_id: j.project_id, priority: j.priority, status: j.status, error: j.error, waiting_for: j.waiting_for })) });
        } else resolve({ configured: true, ...result });
      } catch (error) { resolve({ configured: true, error: String(error) }); }
    });
  });
}
