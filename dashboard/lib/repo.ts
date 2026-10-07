import { promises as fs, existsSync, realpathSync } from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

export const ROOT = path.resolve(process.env.CREWLOOM_ROOT ?? path.join(process.cwd(), '..'));
export const SKILLS = path.join(ROOT, '.agents', 'skills');
export const PROJECT = path.resolve(process.env.CREWLOOM_PROJECT ?? ROOT);
export const RUN_LOG = path.join(PROJECT, '.crewloom', 'runs.jsonl');
export const BRAIN_FILES = ['ARCHITECTURE', 'COMPLETED', 'CHALLENGES', 'IDEAS_VAULT', 'ROADMAP_TODO'] as const;
const SKILL_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export type Tool = { id: string; skill: string; path: string; description: string; example_args: string; effect: string };
export type Run = { ts: string; tool: string; skill: string; exit_code: number; duration_ms: number; source: 'cli' | 'dashboard'; project_root?: string; output?: string };
/** What is actually known about a role. `verified` needs an explicit acceptance record, never a tool exit code alone. */
export type Evidence = { documented: boolean; configured: boolean; exercised: boolean; verified: boolean; acceptance: 'recorded' | 'none-recorded' | 'unverified' };
export type RoleStatus = 'attention' | 'verified' | 'exercised' | 'configured' | 'documented';
export type SkillSummary = {
  id: string; description: string; lastActivity: string | null;
  openTasks: number; doneEntries: number; openChallenges: number; resolvedChallenges: number; unknownChallenges: number; ideas: number; tools: string[];
  runs: number; failedRuns: number; currentFailures: string[]; evidence: Evidence; status: RoleStatus;
};

export const isSkillId = (value: string) => SKILL_ID.test(value);

export type ChallengeStatus = 'open' | 'resolved' | 'unknown';
const STATUS_LINE = /^\s*(?:[-*]\s*)?(?:\*\*)?(الحالة|status|state)\s*(?:\*\*)?\s*[:：]\s*(?:\*\*)?\s*(.+)$/iu;
const OPEN_VALUE = /^(?:مفتوح|مفتوحة|open|ongoing|in progress)(?![\p{L}\p{N}_])/iu;
const RESOLVED_VALUE = /^(?:محلول|محلولة|مغلق|مغلقة|resolved|closed|fixed|done|solved)(?![\p{L}\p{N}_])/iu;

/** One challenge entry's status. A missing or unrecognised status is `unknown`, never closed. */
export function challengeStatus(entry: string): ChallengeStatus {
  for (const line of entry.split('\n')) {
    const match = line.match(STATUS_LINE);
    if (!match) continue;
    const value = match[2].trim().replace(/^[*_`]+/, '');
    if (OPEN_VALUE.test(value)) return 'open';
    if (RESOLVED_VALUE.test(value)) return 'resolved';
    return 'unknown';
  }
  return 'unknown';
}

/** Count `- [ ]` backlog items, dated `###` entries, and challenges by status (open, resolved, unknown). */
export function countBrain(files: Partial<Record<(typeof BRAIN_FILES)[number], string>>) {
  const count = (text: string | undefined, re: RegExp) => (text?.match(re) ?? []).length;
  const entries = (files.CHALLENGES ?? '').split(/^### /m).slice(1);
  const statuses = entries.map(challengeStatus);
  return {
    openTasks: count(files.ROADMAP_TODO, /^\s*- \[ \]/gm),
    doneEntries: count(files.COMPLETED, /^### /gm),
    openChallenges: statuses.filter((s) => s === 'open').length,
    resolvedChallenges: statuses.filter((s) => s === 'resolved').length,
    unknownChallenges: statuses.filter((s) => s === 'unknown').length,
    ideas: count(files.IDEAS_VAULT, /^### /gm),
  };
}

const FRONTMATTER_BYTES = 16 * 1024;
const FRONTMATTER_LINES = 200;
const unquote = (value: string) => {
  const v = value.trim();
  if (v.length >= 2 && v.startsWith("'") && v.endsWith("'")) return v.slice(1, -1).replace(/''/g, "'");
  if (v.length >= 2 && v.startsWith('"') && v.endsWith('"')) return v.slice(1, -1).replace(/\\(["\\])/g, '$1');
  return v;
};

/**
 * A bounded subset of YAML frontmatter: plain and quoted scalars, indented plain continuation,
 * and folded (`>`) / literal (`|`) block scalars with `-`/`+` chomping. Anything else (flow
 * collections, nested maps, anchors) is reported in `warnings` instead of being shown as garbage.
 */
export function parseFrontmatter(text: string): { name?: string; description?: string; warnings?: string[] } {
  const match = text.slice(0, FRONTMATTER_BYTES).match(/^---\r?\n([\s\S]*?)\r?\n---/);
  const out: Record<string, string> = {};
  const warnings: string[] = [];
  if (!match && text.startsWith('---') && text.length > FRONTMATTER_BYTES) warnings.push(`Frontmatter is not closed within ${FRONTMATTER_BYTES} bytes`);
  const lines = (match?.[1] ?? '').split(/\r?\n/).slice(0, FRONTMATTER_LINES);
  for (let i = 0; i < lines.length; i += 1) {
    const head = lines[i].match(/^([A-Za-z_][\w-]*):\s*(.*)$/);
    if (!head) continue;
    const [, key, raw] = head;
    const indented: string[] = [];
    while (i + 1 < lines.length && (/^\s+\S/.test(lines[i + 1]) || (lines[i + 1].trim() === '' && i + 2 < lines.length && /^\s+\S/.test(lines[i + 2])))) {
      indented.push(lines[i + 1]); i += 1;
    }
    const block = raw.match(/^([>|])([+-]?)\s*$/);
    if (block) {
      const indent = Math.min(...indented.filter((l) => l.trim()).map((l) => l.match(/^\s*/)![0].length), Infinity);
      const body = indented.map((l) => (l.trim() ? l.slice(Number.isFinite(indent) ? indent : 0) : ''));
      if (block[1] === '|') out[key] = body.join('\n').replace(/\n+$/, block[2] === '+' ? '\n' : '');
      else {
        const paragraphs = body.join('\n').split(/\n{2,}/).map((p) => p.split('\n').map((s) => s.trim()).filter(Boolean).join(' '));
        out[key] = paragraphs.join('\n').trim();
      }
      continue;
    }
    if (/^[\[{&*!]/.test(raw)) { warnings.push(`Unsupported YAML value for ${key}`); continue; }
    if (raw === '' && indented.some((l) => /^\s+[\w-]+:\s/.test(l))) { warnings.push(`Unsupported nested value for ${key}`); continue; }
    const parts = [raw, ...indented.map((l) => l.trim())].filter((s) => s !== '');
    out[key] = parts.length > 1 && !/^["']/.test(raw) ? parts.join(' ') : unquote(parts.join(' '));
  }
  return warnings.length ? { ...out, warnings } : out;
}

export function parseRuns(text: string): Run[] {
  const runs: Run[] = [];
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try { runs.push(JSON.parse(line) as Run); } catch { /* skip a torn line */ }
  }
  return runs;
}

function assertProjectLog(project = PROJECT) {
  const runLog = path.join(project, '.crewloom', 'runs.jsonl');
  const folder = path.dirname(runLog);
  for (const candidate of [folder, runLog]) {
    if (!existsSync(candidate)) continue;
    const relative = path.relative(realpathSync(project), realpathSync(candidate));
    if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) throw new Error('Run history escapes selected project');
  }
}

export async function readRuns(limit = 200, project = PROJECT): Promise<Run[]> {
  assertProjectLog(project);
  try { return parseRuns(await fs.readFile(path.join(project, '.crewloom', 'runs.jsonl'), 'utf8')).slice(-limit).reverse(); } catch { return []; }
}

export async function appendRun(run: Run, project = PROJECT) {
  assertProjectLog(project);
  await fs.mkdir(path.join(project, '.crewloom'), { recursive: true });
  await fs.appendFile(path.join(project, '.crewloom', 'runs.jsonl'), JSON.stringify({ ...run, project_root: project }) + '\n', 'utf8');
}

export async function readTools(): Promise<Tool[]> {
  const raw = await fs.readFile(path.join(ROOT, 'documentation', 'TOOLS.json'), 'utf8');
  return (JSON.parse(raw) as { tools: Tool[] }).tools;
}

async function readBrain(id: string, project = PROJECT) {
  const agentDir = path.join(project, '.agents', 'skills', id);
  const claudeDir = path.join(project, '.claude', 'skills', id);
  const dirs = [agentDir, claudeDir].filter((dir) => existsSync(path.join(dir, 'SKILL.md')));
  if (dirs.length > 1) throw new Error('Ambiguous project role: choose one host installation');
  const dir = path.join(dirs[0] ?? agentDir, 'brain');
  const within = (file: string) => { const rel = path.relative(realpathSync(project), realpathSync(file)); return rel !== '..' && !rel.startsWith(`..${path.sep}`) && !path.isAbsolute(rel); };
  if (existsSync(dir) && !within(dir)) throw new Error('Project brain escapes through symlink');
  const files: Partial<Record<(typeof BRAIN_FILES)[number], string>> = {};
  let latest = 0;
  for (const name of BRAIN_FILES) {
    const file = path.join(dir, `${name}.md`);
    try {
      if (existsSync(file) && !within(file)) throw new Error('Project brain file escapes through symlink');
      files[name] = await fs.readFile(file, 'utf8');
      latest = Math.max(latest, (await fs.stat(file)).mtimeMs);
    } catch (error) { if (existsSync(file)) throw error; /* absent */ }
  }
  return { files, latest };
}

/** One bounded controller call per request verifies role records against existing executor evidence. */
async function readAcceptances(ids: string[], project: string): Promise<Record<string, boolean>> {
  const directory = path.join(project, '.crewloom', 'acceptance');
  if (!existsSync(directory)) return {};
  if (realpathSync(directory) !== directory) return {};
  const roles = ids.filter(isSkillId).slice(0, 64);
  const program = 'import sys,json;sys.path.insert(0,sys.argv[1]);import project_binding as p;print(json.dumps({role:p.role_acceptance(sys.argv[2],role)["verified"] for role in json.loads(sys.argv[3])}))';
  const result = await exec(['-c', program, path.join(ROOT, 'scripts'), project, JSON.stringify(roles)], 15000, project);
  try { return result.exit_code === 0 ? JSON.parse(result.output) : {}; } catch { return {}; }
}

export async function readAcceptance(id: string, project = PROJECT): Promise<boolean> {
  return (await readAcceptances([id], project))[id] === true;
}

/** The tools whose most recent run failed; `runs` is newest first. */
export function currentFailures(runs: Run[]): string[] {
  const seen = new Set<string>();
  const failing: string[] = [];
  for (const run of runs) {
    if (seen.has(run.tool)) continue;
    seen.add(run.tool);
    if (run.exit_code !== 0) failing.push(run.tool);
  }
  return failing;
}

/** Documented -> configured -> exercised -> verified; a failing current run or an open/unknown challenge needs attention. */
export function roleStatus(input: { evidence: Evidence; currentFailures: string[]; openChallenges: number; unknownChallenges: number }): RoleStatus {
  if (input.evidence.acceptance === 'unverified' || input.currentFailures.length || input.openChallenges || input.unknownChallenges) return 'attention';
  if (input.evidence.verified) return 'verified';
  if (input.evidence.exercised) return 'exercised';
  if (input.evidence.configured) return 'configured';
  return 'documented';
}

export async function listSkills(project = PROJECT): Promise<SkillSummary[]> {
  const [ids, tools, runs] = await Promise.all([fs.readdir(SKILLS), readTools(), readRuns(1000, project)]);
  const out: SkillSummary[] = [];
  const verifiedRoles = await readAcceptances(ids, project);
  for (const id of ids.sort()) {
    const skillFile = path.join(SKILLS, id, 'SKILL.md');
    if (!isSkillId(id) || !existsSync(skillFile)) continue;
    const { files, latest } = await readBrain(id, project);
    const meta = parseFrontmatter(await fs.readFile(skillFile, 'utf8'));
    const mine = runs.filter((r) => r.skill === id);
    const failedRuns = mine.filter((r) => r.exit_code !== 0).length;
    const counts = countBrain(files);
    const failing = currentFailures(mine);
    const configured = ['.agents', '.claude'].some((host) => existsSync(path.join(project, host, 'skills', id, 'SKILL.md')));
    const verified = verifiedRoles[id] === true;
    const evidence: Evidence = { documented: true, configured, exercised: mine.length > 0, verified, acceptance: verified ? 'recorded' : existsSync(path.join(project, '.crewloom', 'acceptance', id + '.json')) ? 'unverified' : 'none-recorded' };
    out.push({
      id, description: meta.description ?? '', lastActivity: latest ? new Date(latest).toISOString() : null,
      ...counts, tools: tools.filter((t) => t.skill === id).map((t) => t.id), runs: mine.length, failedRuns,
      currentFailures: failing, evidence, status: roleStatus({ evidence, currentFailures: failing, openChallenges: counts.openChallenges, unknownChallenges: counts.unknownChallenges }),
    });
  }
  return out;
}

export async function skillDetail(id: string, project = PROJECT) {
  if (!isSkillId(id) || !existsSync(path.join(SKILLS, id, 'SKILL.md'))) return null;
  const { files } = await readBrain(id, project);
  return { id, skill: await fs.readFile(path.join(SKILLS, id, 'SKILL.md'), 'utf8'), brain: files };
}


export type TaskSummary = { id: string; role: string; status: string; verified: boolean; updatedAt: string | null };

/** Read bounded task summaries only; project payloads, prompts and acceptance bodies stay private. */
export async function readTasks(project = PROJECT): Promise<{ tasks: TaskSummary[]; diagnostics: string[] }> {
  const tasks: TaskSummary[] = []; const diagnostics: string[] = [];
  const directory = path.join(project, '.crewloom', 'tasks');
  if (!existsSync(directory)) return { tasks, diagnostics };
  if (realpathSync(directory) !== directory) throw new Error('Task directory is not canonical');
  const configFile = path.join(project, 'crewloom.project.json');
  const bindingFile = path.join(project, '.crewloom', 'binding.json');
  const boundedJSON = async (file: string) => {
    const stat = await fs.lstat(file);
    if (!stat.isFile() || stat.nlink !== 1 || realpathSync(file) !== file || stat.size > 65536) throw new Error('Invalid task metadata file');
    return JSON.parse(await fs.readFile(file, 'utf8'));
  };
  let config; let binding;
  try { [config, binding] = await Promise.all([boundedJSON(configFile), boundedJSON(bindingFile)]); }
  catch { return { tasks, diagnostics: ['Task identity could not be verified'] }; }
  const names = (await fs.readdir(directory)).sort();
  if (names.length > 200) diagnostics.push('Task list limited to 200 entries');
  for (const id of names.slice(0, 200)) {
    if (!isSkillId(id)) { diagnostics.push('Invalid task identifier omitted'); continue; }
    try {
      const record = await boundedJSON(path.join(directory, id, 'state.json'));
      if (record.schema_version !== 1 || record.task_id !== id || record.project_root !== project ||
          record.project_id !== config.project_id || record.checkout_id !== binding.checkout_id ||
          binding.project_root !== project || binding.project_id !== config.project_id ||
          typeof record.status !== 'string' || !isSkillId(record.role)) throw new Error('Mismatched task identity');
      tasks.push({ id, role: record.role, status: record.status.slice(0, 40), verified: false,
                   updatedAt: typeof record.updated_at === 'string' ? record.updated_at.slice(0, 40) : null });
    } catch { diagnostics.push('Unavailable or invalid task record: ' + id); }
  }
  if (tasks.length) {
    const program = 'import sys,json;sys.path.insert(0,sys.argv[1]);import project_binding as p;print(json.dumps({task:p.task_acceptance(sys.argv[2],task)["verified"] for task in json.loads(sys.argv[3])}))';
    const result = await exec(['-c', program, path.join(ROOT, 'scripts'), project, JSON.stringify(tasks.slice(0, 64).map((task) => task.id))], 15000, project);
    if (result.exit_code !== 0) diagnostics.push('Current task acceptance could not be checked');
    try {
      const verified = result.exit_code === 0 ? JSON.parse(result.output) : {};
      for (const task of tasks) task.verified = verified[task.id] === true;
    } catch { diagnostics.push('Current task acceptance could not be checked'); }
  }
  return { tasks, diagnostics };
}


export type ExecResult = { exit_code: number; output: string; duration_ms: number };

function exec(args: string[], timeoutMs: number, cwd = PROJECT): Promise<ExecResult> {
  return new Promise((resolve) => {
    const started = Date.now();
    const child = spawn('python3', args, { cwd, env: { ...process.env, CREWLOOM_NO_LOG: '1' } });
    let output = '';
    const cap = (d: Buffer) => { if (output.length < 20000) output += d.toString(); };
    child.stdout.on('data', cap);
    child.stderr.on('data', cap);
    const timer = setTimeout(() => { child.kill('SIGKILL'); output += '\n[timeout]'; }, timeoutMs);
    child.on('error', (e) => { clearTimeout(timer); resolve({ exit_code: 127, output: String(e), duration_ms: Date.now() - started }); });
    child.on('close', (code) => { clearTimeout(timer); resolve({ exit_code: code ?? 1, output, duration_ms: Date.now() - started }); });
  });
}

/** Refuse NUL, traversal and absolute paths; spaces, Arabic and quotes inside a single argument are fine. */
export function validateArgs(args: string[]): string | null {
  for (const arg of args) {
    if (typeof arg !== 'string' || arg.includes('\0') || (!arg.startsWith('-') && /(^|[\\/])\.\.([\\/]|$)/.test(arg)) || path.isAbsolute(arg)) return `Rejected argument: ${String(arg).replace(/\0/g, '\\0')}`;
  }
  return null;
}

/** Run a registered tool only; arguments must be plain strings and use project-relative paths. */
export async function runTool(toolId: string, args: string[], project = PROJECT): Promise<ExecResult & { error?: string }> {
  const tool = (await readTools()).find((t) => t.id === toolId);
  if (!tool) return { exit_code: 2, output: '', duration_ms: 0, error: 'Unknown tool' };
  const rejected = validateArgs(args);
  if (rejected) return { exit_code: 2, output: '', duration_ms: 0, error: rejected };
  const result = await exec([path.join(ROOT, 'scripts/crewloom.py'), 'run', '--project', project, tool.id, '--', ...args], 60000, project);
  return result;
}

export async function runChecks(): Promise<ExecResult> {
  return exec([path.join(ROOT, 'scripts/check_repository.py')], 180000, ROOT);
}
