import { test } from 'node:test';
import assert from 'node:assert/strict';
import { childEnvironment, redactOutput } from '../lib/child-env.ts';

const TOKEN = 'a'.repeat(43);
const source = {
  PATH: '/usr/bin', HOME: '/home/u', CREWLOOM_PROJECT: '/p', CREWLOOM_CATALOG: '/c',
  CREWLOOM_DASHBOARD_TOKEN: TOKEN, GITHUB_TOKEN: 'gh' + 'p_' + 'b'.repeat(36), AWS_SECRET_ACCESS_KEY: 'c'.repeat(40),
  OPENAI_API_KEY: 's' + 'k-' + 'd'.repeat(30), DB_PASSWORD: 'hunter2hunter2', TOKENIZERS_PARALLELISM: 'false',
};

test('children do not inherit the dashboard credential or secret-named variables', () => {
  const env = childEnvironment({ CREWLOOM_NO_LOG: '1' }, source);
  for (const name of ['CREWLOOM_DASHBOARD_TOKEN', 'GITHUB_TOKEN', 'AWS_SECRET_ACCESS_KEY', 'OPENAI_API_KEY', 'DB_PASSWORD']) {
    assert.equal(name in env, false, name);
  }
  assert.deepEqual(env, { PATH: '/usr/bin', HOME: '/home/u', CREWLOOM_PROJECT: '/p', CREWLOOM_CATALOG: '/c',
    TOKENIZERS_PARALLELISM: 'false', CREWLOOM_NO_LOG: '1' });
});

test('explicit extra values win over the inherited environment', () => {
  assert.equal(childEnvironment({ PATH: '/x' }, source).PATH, '/x');
});

test('stored output hides exact secret values and common credential shapes', () => {
  const pem = ['-----BEGIN RSA', 'PRIVATE KEY-----'].join(' ');
  const output = `token=${TOKEN}\nkey ${source.GITHUB_TOKEN}\nnormal line\n${pem}\nabc\n${pem.replace('BEGIN', 'END')}`;
  const redacted = redactOutput(output, source);
  assert.equal(redacted.includes(TOKEN), false);
  assert.equal(redacted.includes('ghp_'), false);
  assert.equal(redacted.includes('PRIVATE KEY'), false);
  assert.match(redacted, /normal line/);
});
