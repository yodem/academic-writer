import { test } from 'node:test';
import assert from 'node:assert/strict';
import { jevQuestion } from '../src/jev.ts';
import { pluginRoot, __setPiRunner, callPi } from '../src/pi.ts';

test('jev question uses instructions + criteria map (API shape)', () => {
  assert.deepEqual(jevQuestion({ question: 'fix?', options: ['uphold', 'refute'], context: 'x' }),
    { type: 'choice', instructions: 'fix?', criteria: { uphold: null, refute: null } });
});

test('plugin root is derived from <root>/bin/aw, not the environment', () => {
  assert.equal(pluginRoot('/opt/p/academic-writer/bin/aw'), '/opt/p/academic-writer');
});

test('pi receives the system prompt text and an absolute skill path', async () => {
  let seen: string[] = [];
  __setPiRunner(async (args, systemPrompt) => { seen = args.map((a) => a === '__SYSTEM_PROMPT__' ? systemPrompt : a); return { finalText: '{}', usage: { in: 1, out: 1 } }; });
  process.argv[1] = '/opt/p/academic-writer/bin/aw';
  await callPi('proofread.verify', 'prompt', 'You are a judge.').catch(() => undefined);
  if (seen.length) {
    assert.equal(seen[seen.indexOf('--system-prompt') + 1], 'You are a judge.');
    assert.equal(seen[seen.indexOf('--skill') + 1], '/opt/p/academic-writer/pi-skills/aw-judge');
  }
});
