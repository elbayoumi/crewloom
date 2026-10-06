/** Exact argv for a tool launch: quotes group words, nothing is split inside a quoted path. */
export type ArgvResult = { argv: string[]; error?: string };
export const MAX_ARGS = 64;
export const MAX_ARG_LENGTH = 4096;

/** POSIX-style words: whitespace separates; 'literal'; "double" with \" and \\ escapes; \x escapes outside quotes. */
export function parseArgv(text: string): ArgvResult {
  const argv: string[] = [];
  let current = '';
  let started = false;
  let quote: '"' | "'" | null = null;
  const push = () => { if (started) { argv.push(current); current = ''; started = false; } };
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (quote === "'") { if (char === "'") quote = null; else current += char; continue; }
    if (quote === '"') {
      if (char === '"') quote = null;
      else if (char === '\\' && (text[i + 1] === '"' || text[i + 1] === '\\')) { current += text[i + 1]; i += 1; }
      else current += char;
      continue;
    }
    if (char === '"' || char === "'") { quote = char; started = true; continue; }
    if (char === '\\') {
      if (i + 1 >= text.length) return { argv: [], error: 'Trailing backslash' };
      current += text[i + 1]; started = true; i += 1; continue;
    }
    if (/\s/u.test(char)) { push(); continue; }
    current += char; started = true;
  }
  if (quote) return { argv: [], error: `Unterminated ${quote === '"' ? 'double' : 'single'} quote` };
  push();
  if (argv.length > MAX_ARGS) return { argv: [], error: `At most ${MAX_ARGS} arguments` };
  const tooLong = argv.find((a) => a.length > MAX_ARG_LENGTH);
  if (tooLong !== undefined) return { argv: [], error: `Argument longer than ${MAX_ARG_LENGTH} characters` };
  return { argv };
}
