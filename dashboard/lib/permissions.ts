import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const execute = promisify(execFile);
export const COMMAND_TIMEOUT_MS = 5000;
export type CommandRunner = (file: string, args: string[]) => Promise<{ ok: boolean; error?: string }>;
export type ProbeResult = { granted: boolean | null; error?: string };
export const runCommand: CommandRunner = async (file, args) => {
  try { await execute(file, args, { timeout: COMMAND_TIMEOUT_MS, maxBuffer: 65536 }); return { ok: true }; }
  catch { return { ok: false, error: 'System command failed or timed out' }; }
};
// No native desktop controller is implemented here; browser DOM actions need no AX grant.
export async function probeAccessibility(): Promise<ProbeResult> {
  return { granted: null, error: 'Native controller accessibility trust is not measured' };
}
export async function probeScreenRecording(run: CommandRunner = runCommand): Promise<ProbeResult> {
  const folder = await mkdtemp(join(tmpdir(), 'crewloom-perm-'));
  try {
    const target = join(folder, 'probe.png');
    const result = await run('screencapture', ['-x', target]);
    if (!result.ok) return { granted: false, error: result.error };
    const bytes = await readFile(target);
    const png = Buffer.from([137,80,78,71,13,10,26,10]);
    return bytes.length > 8 && bytes.subarray(0,8).equals(png)
      ? { granted: true } : { granted: false, error: 'No PNG capture produced' };
  } catch { return { granted: false, error: 'No readable capture produced' }; }
  finally { await rm(folder, { recursive: true, force: true }); }
}
const PANES = new Set(['Privacy_Accessibility', 'Privacy_ScreenCapture']);
export function validPane(pane: unknown): pane is string { return typeof pane === 'string' && PANES.has(pane); }
export async function openPreferencePane(pane: string, run: CommandRunner = runCommand) {
  if (!validPane(pane)) return { ok: false, error: 'Invalid preference pane' };
  const url = `x-apple.systempreferences:com.apple.preference.security?${pane}`;
  return { ...await run('open', [url]), url };
}
