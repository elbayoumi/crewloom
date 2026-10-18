import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseToolArguments} from '../lib/tool-arguments.ts';
import {readTools, runTool} from '../lib/repo.ts';

test('arguments preserve quoted paths, empty values and literal shell syntax', () => {
  assert.deepEqual(parseToolArguments('--input "files/my report.md" --label \'Arabic text\' ""'),
    ['--input','files/my report.md','--label','Arabic text','']);
  assert.deepEqual(parseToolArguments('"$(echo secret)" `literal` $HOME'), ['$(echo secret)','`literal`','$HOME']);
  assert.deepEqual(parseToolArguments('["--input","files/my report.md"]'), ['--input','files/my report.md']);
});

test('invalid or oversized argument data fails before execution', () => {
  for (const value of ['"unterminated','trailing\\','[1]','[null]','a\0b']) {
    assert.throws(()=>parseToolArguments(value));
  }
  assert.throws(()=>parseToolArguments('x'.repeat(16385)));
  assert.throws(()=>parseToolArguments(Array(65).fill('x').join(' ')));
});

test('runnable catalog defaults respect dashboard paths; cross-project tools require CLI', async () => {
  const tools = await readTools();
  for (const tool of tools.filter(tool=>tool.dashboard !== 'cli')) {
    const args=parseToolArguments(tool.example_args);
    assert.ok(args.every(arg=>!arg.startsWith('/')),tool.id);
  }
  assert.equal(tools.find(tool=>tool.id==='context')?.example_args,'--skill context-guardian --out context.md');
  const result=await runTool('agency-readiness',[]);
  assert.match(result.error ?? '',/CLI/);
});
