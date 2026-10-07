/** Server-approved references to existing project roots. Consumer state never moves into the toolkit. */
import { readFileSync, realpathSync, existsSync, lstatSync } from 'node:fs';
import path from 'node:path';
import { PROJECT, ROOT } from './repo.ts';
import { privateHeaders } from './auth.ts';

export type ProjectReference = { id: string; root: string };
const ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const contains = (parent: string, child: string) => {
  const rel = path.relative(parent, child);
  return rel === '' || (!path.isAbsolute(rel) && rel !== '..' && !rel.startsWith(`..${path.sep}`));
};

export function projectReferences(): ProjectReference[] {
  const configured = process.env.CREWLOOM_PROJECTS;
  if (!configured) return [{ id: 'current-project', root: realpathSync(process.env.CREWLOOM_PROJECT ?? PROJECT) }];
  const value: unknown = JSON.parse(configured);
  if (!Array.isArray(value) || value.length < 1 || value.length > 32) throw new Error('Project references must contain 1..32 approved entries');
  const found: ProjectReference[] = [];
  for (const entry of value) {
    if (!entry || typeof entry !== 'object' || Object.keys(entry).some((key) => !['id', 'root'].includes(key))) throw new Error('Invalid project reference');
    const { id, root } = entry;
    if (typeof id !== 'string' || !ID.test(id) || typeof root !== 'string' || !path.isAbsolute(root)) throw new Error('Project references need a stable ID and absolute root');
    const canonical = realpathSync(root);
    if (canonical !== path.resolve(root) || !lstatSync(root).isDirectory()) throw new Error('Project roots must be canonical directories without aliases');
    if (contains(realpathSync(ROOT), canonical) || contains(canonical, realpathSync(ROOT))) throw new Error('Consumer projects must remain separate from the toolkit root');
    const configPath = path.join(canonical, 'crewloom.project.json');
    const configStat = lstatSync(configPath);
    if (!configStat.isFile() || configStat.nlink !== 1 || configStat.size > 65536) throw new Error('Project configuration is not a bounded regular file');
    const config = JSON.parse(readFileSync(configPath, 'utf8'));
    if (config.schema_version !== 1 || config.project_id !== id) throw new Error('Project reference does not match existing project identity');
    const bindingPath = path.join(canonical, '.crewloom', 'binding.json');
    if (existsSync(bindingPath)) {
      const bindingStat = lstatSync(bindingPath);
      if (realpathSync(bindingPath) !== bindingPath || !bindingStat.isFile() || bindingStat.nlink !== 1 || bindingStat.size > 65536) throw new Error('Project binding path is not canonical');
      const binding = JSON.parse(readFileSync(bindingPath, 'utf8'));
      if (binding.project_id !== id || binding.project_root !== canonical) throw new Error('Project binding disagrees with selected root');
    }
    if (found.some((item) => item.id === id || contains(item.root, canonical) || contains(canonical, item.root))) throw new Error('Duplicate or overlapping project references');
    found.push({ id, root: canonical });
  }
  return found;
}

export function selectedProject(req: Request): ProjectReference {
  const projects = projectReferences();
  const requested = new URL(req.url).searchParams.get('project');
  const chosenId = requested || (projects.length === 1 ? projects[0].id : null);
  const selected = projects.find((item) => item.id === chosenId);
  if (!selected) throw new Error('Choose one approved project ID; arbitrary request paths are refused');
  for (const relative of ['.crewloom', '.agents', '.claude']) {
    const candidate = path.join(selected.root, relative);
    if (existsSync(candidate) && lstatSync(candidate).isSymbolicLink()) throw new Error('Project runtime/role roots may not be aliases');
  }
  return selected;
}

export async function inSelectedProject(req: Request, action: (project: ProjectReference) => Promise<Response>): Promise<Response> {
  let project: ProjectReference;
  try { project = selectedProject(req); }
  catch { return Response.json({ error: 'Invalid or ambiguous project selection/configuration' }, { status: 400, headers: { ...privateHeaders } }); }
  return action(project);
}
