import { promises as fs, existsSync, realpathSync } from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { childEnvironment, redactOutput } from './child-env.ts';

export const ROOT = path.resolve(process.env.CREWLOOM_ROOT ?? path.join(process.cwd(), '..'));
export const SKILLS = path.join(ROOT, '.agents', 'skills');
export const PROJECT = path.resolve(process.env.CREWLOOM_PROJECT ?? ROOT);
export const RUN_LOG = path.join(PROJECT, '.crewloom', 'runs.jsonl');
export const BRAIN_FILES = ['ARCHITECTURE', 'COMPLETED', 'CHALLENGES', 'IDEAS_VAULT', 'ROADMAP_TODO'] as const;
const SKILL_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export type Tool = { id: string; skill: string; path: string; description: string; example_args: string; effect: string; dashboard?: 'cli' | 'project' };
export type Run = { ts: string; tool: string; skill: string; exit_code: number; duration_ms: number; source: 'cli' | 'dashboard'; project_root?: string; output?: string };
export type SkillSummary = {
  id: string; description: string; lastActivity: string | null;
  openTasks: number; doneEntries: number; openChallenges: number; ideas: number; tools: string[];
  runs: number; failedRuns: number; status: 'healthy' | 'attention' | 'idle';
};

export const isSkillId = (value: string) => SKILL_ID.test(value);

/** Count `- [ ]` backlog items, dated `###` entries, and unresolved challenges. */
export function countBrain(files: Partial<Record<(typeof BRAIN_FILES)[number], string>>) {
  const count = (text: string | undefined, re: RegExp) => (text?.match(re) ?? []).length;
  const records = (text = '') => text.split(/(?=^### |^\s*- \d{4}-\d{2}-\d{2}\b)/m)
    .filter((record) => /^(### |\s*- \d{4}-\d{2}-\d{2}\b)/.test(record));
  const entries = records(files.CHALLENGES);
  const statusLine = (entry: string) => entry.split('\n').find((line) =>
    /(الحالة|status|(?:^|\|)\s*(?:open|مفتوح)\s*:)/i.test(line)) ?? '';
  const openChallenges = entries.filter((entry) => /(مفتوح|\bopen\b)/i.test(statusLine(entry)) &&
    !/(resolved|closed|مغلق|محلول)/i.test(statusLine(entry))).length;
  return {
    openTasks: count(files.ROADMAP_TODO, /^\s*- \[ \]/gm),
    doneEntries: records(files.COMPLETED).length,
    openChallenges,
    ideas: records(files.IDEAS_VAULT).length,
  };
}

export function parseFrontmatter(text: string): { name?: string; description?: string } {
  const match = text.match(/^---\n([\s\S]*?)\n---/);
  const out: Record<string, string> = {};
  for (const line of match?.[1].split('\n') ?? []) {
    const i = line.indexOf(':');
    if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return out;
}

export function parseRuns(text: string): Run[] {
  const runs: Run[] = [];
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try {
      const value = JSON.parse(line);
      if (value && typeof value === 'object' && !Array.isArray(value) &&
          typeof value.tool === 'string' && value.tool.trim() &&
          typeof value.skill === 'string' && value.skill.trim() &&
          typeof value.ts === 'string' && Number.isFinite(Date.parse(value.ts)) &&
          Number.isInteger(value.exit_code) &&
          typeof value.duration_ms === 'number' && Number.isFinite(value.duration_ms) && value.duration_ms >= 0 &&
          (value.source === 'cli' || value.source === 'dashboard') &&
          (value.output === undefined || typeof value.output === 'string') &&
          (value.project_root === undefined || (typeof value.project_root === 'string' && value.project_root.trim()))) runs.push(value as Run);
    } catch { /* skip this malformed record only */ }
  }
  return runs;
}

function assertProjectLog() {
  const folder = path.dirname(RUN_LOG);
  for (const candidate of [folder, RUN_LOG]) {
    if (!existsSync(candidate)) continue;
    const relative = path.relative(realpathSync(PROJECT), realpathSync(candidate));
    if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) throw new Error('Run history escapes selected project');
  }
}

export async function readRuns(limit = 200): Promise<Run[]> {
  assertProjectLog();
  try {
    const file = await fs.open(RUN_LOG, 'r');
    try {
      const info = await file.stat();
      const bytes = Math.min(info.size, 1024 * 1024);
      const buffer = Buffer.alloc(bytes);
      const { bytesRead } = await file.read(buffer, 0, bytes, info.size - bytes);
      let text = buffer.subarray(0, bytesRead).toString('utf8');
      if (info.size > bytes) text = text.slice(text.indexOf('\n') + 1);
      return parseRuns(text).filter((r) => !r.project_root || r.project_root === PROJECT).slice(-limit).reverse();
    } finally { await file.close(); }
  } catch { return []; }
}

export async function appendRun(run: Run) {
  assertProjectLog();
  await fs.mkdir(path.dirname(RUN_LOG), { recursive: true });
  await fs.appendFile(RUN_LOG, JSON.stringify({ ...run, project_root: PROJECT }) + '\n', 'utf8');
}

export async function readTools(): Promise<Tool[]> {
  const raw = await fs.readFile(path.join(ROOT, 'documentation', 'TOOLS.json'), 'utf8');
  return (JSON.parse(raw) as { tools: Tool[] }).tools;
}

async function readBrain(id: string) {
  const agentDir = path.join(PROJECT, '.agents', 'skills', id);
  const claudeDir = path.join(PROJECT, '.claude', 'skills', id);
  const dirs = [agentDir, claudeDir].filter((dir) => existsSync(path.join(dir, 'SKILL.md')));
  if (dirs.length > 1) throw new Error('Ambiguous project role: choose one host installation');
  const dir = path.join(dirs[0] ?? agentDir, 'brain');
  const within = (file: string) => { const rel = path.relative(realpathSync(PROJECT), realpathSync(file)); return rel !== '..' && !rel.startsWith(`..${path.sep}`) && !path.isAbsolute(rel); };
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

export async function listSkills(): Promise<SkillSummary[]> {
  const [ids, tools, runs] = await Promise.all([fs.readdir(SKILLS), readTools(), readRuns(1000)]);
  const out: SkillSummary[] = [];
  for (const id of ids.sort()) {
    const skillFile = path.join(SKILLS, id, 'SKILL.md');
    if (!isSkillId(id) || !existsSync(skillFile)) continue;
    const { files, latest } = await readBrain(id);
    const meta = parseFrontmatter(await fs.readFile(skillFile, 'utf8'));
    const mine = runs.filter((r) => r.skill === id);
    const failedRuns = mine.filter((r) => r.exit_code !== 0).length;
    const counts = countBrain(files);
    const status = failedRuns > 0 || counts.openChallenges > 0 ? 'attention' : mine.length ? 'healthy' : 'idle';
    out.push({
      id, description: meta.description ?? '', lastActivity: latest ? new Date(latest).toISOString() : null,
      ...counts, tools: tools.filter((t) => t.skill === id).map((t) => t.id), runs: mine.length, failedRuns, status,
    });
  }
  return out;
}

export async function skillDetail(id: string) {
  if (!isSkillId(id) || !existsSync(path.join(SKILLS, id, 'SKILL.md'))) return null;
  const { files } = await readBrain(id);
  return { id, skill: await fs.readFile(path.join(SKILLS, id, 'SKILL.md'), 'utf8'), brain: files };
}

export type ExecResult = { exit_code: number; output: string; duration_ms: number };

function exec(args: string[], timeoutMs: number, cwd = PROJECT): Promise<ExecResult> {
  return new Promise((resolve) => {
    const started = Date.now();
    const child = spawn('python3', args, { cwd, env: childEnvironment({ CREWLOOM_NO_LOG: '1' }) });
    let output = '';
    const cap = (d: Buffer) => { if (output.length < 20000) output += d.toString(); };
    child.stdout.on('data', cap);
    child.stderr.on('data', cap);
    const timer = setTimeout(() => { child.kill('SIGKILL'); output += '\n[timeout]'; }, timeoutMs);
    child.on('error', (e) => { clearTimeout(timer); resolve({ exit_code: 127, output: String(e), duration_ms: Date.now() - started }); });
    child.on('close', (code) => { clearTimeout(timer); resolve({ exit_code: code ?? 1, output: redactOutput(output), duration_ms: Date.now() - started }); });
  });
}

/** Run a registered tool only; arguments must be plain strings and use project-relative paths. */
export async function runTool(toolId: string, args: string[]): Promise<ExecResult & { error?: string }> {
  const tool = (await readTools()).find((t) => t.id === toolId);
  if (!tool) return { exit_code: 2, output: '', duration_ms: 0, error: 'Unknown tool' };
  if (tool.dashboard === 'cli') return { exit_code: 2, output: '', duration_ms: 0,
    error: 'This tool needs explicit CLI project/account inputs; use its documented CLI command' };
  for (const arg of args) {
    if (arg.includes('\0') || (!arg.startsWith('-') && /(^|\/)\.\.(\/|$)/.test(arg)) || path.isAbsolute(arg)) {
      return { exit_code: 2, output: '', duration_ms: 0, error: `Rejected argument: ${arg}` };
    }
  }
  const result = await exec([path.join(ROOT, 'scripts/crewloom.py'), 'run', '--project', PROJECT, tool.id, '--', ...args], 60000);
  return result;
}

export async function runChecks(): Promise<ExecResult> {
  return exec([path.join(ROOT, 'scripts/check_repository.py')], 180000, ROOT);
}
