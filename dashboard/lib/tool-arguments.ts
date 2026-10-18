/** Parse argument data only; never invoke a shell or expand variables/commands. */
export function parseToolArguments(input: string): string[] {
  if (input.length > 16384) throw new Error('Arguments exceed 16 KiB');
  if (input.trimStart().startsWith('[')) {
    const value: unknown = JSON.parse(input);
    if (!Array.isArray(value) || value.some((item) => typeof item !== 'string' || item.includes('\0')) || value.length > 64) {
      throw new Error('Use a JSON array of at most 64 strings');
    }
    return value;
  }
  const args: string[] = [];
  let word = '', quote = '', escaped = false, started = false;
  for (const char of input) {
    if (char === '\0') throw new Error('Arguments may not contain NUL');
    if (escaped) { word += char; escaped = false; started = true; continue; }
    if (char === '\\' && quote !== "'") { escaped = true; started = true; continue; }
    if (quote) {
      if (char === quote) quote = ''; else word += char;
      continue;
    }
    if (char === '"' || char === "'") { quote = char; started = true; }
    else if (/\s/.test(char)) { if (started) { args.push(word); word = ''; started = false; } }
    else { word += char; started = true; }
  }
  if (quote || escaped) throw new Error('Unclosed quote or trailing escape in arguments');
  if (started) args.push(word);
  if (args.length > 64) throw new Error('Use at most 64 arguments');
  return args;
}
