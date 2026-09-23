import { test } from 'node:test';
import assert from 'node:assert/strict';
import { judge, __setPiRunner, __setPiReady } from '../src/judge.js';
import { __setTransport } from '../src/gemini.js';
import { setPathArguments } from '../src/paths.js';
setPathArguments(['--data-dir', '/tmp/aw-t6-data', '--project-dir', '/tmp/aw-t6-project']);

test('pi unavailable → gemini, same_family when finder is gemini', async () => {
  __setPiReady(false);
  __setTransport(async () => ({ text: '{"v":[]}', finishReason: 'STOP', usage: { in: 1, out: 1 } }));
  const r = await judge({ step: 'proofread.verify', prompt: 'p', schema: { type: 'object' }, runId: 't', finderProvider: 'gemini' });
  assert.equal(r.sameFamily, true);
});

test('pi runs isolated and invalid JSON is retried once', async () => {
  process.argv[1] = '/opt/p/academic-writer/bin/aw'; // aw derives the plugin root from its own path
  __setPiReady(true);
  const argsSeen: string[][] = [];
  let n = 0;
  __setPiRunner(async (args) => { argsSeen.push(args); n++; return { finalText: n === 1 ? 'not json' : '{"v":[]}', usage: { in: 1, out: 1 } }; });
  const r = await judge({ step: 'proofread.verify', prompt: 'p', schema: { type: 'object' }, runId: 't', finderProvider: 'gemini' });
  assert.equal(r.sameFamily, false);
  assert.equal(n, 2);
  for (const f of ['--no-session', '--no-extensions', '--no-skills', '--no-context-files', '--no-tools']) assert.ok(argsSeen[0].includes(f), f);
});
