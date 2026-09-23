import { test } from 'node:test';
import assert from 'node:assert/strict';
import { decide, __setJev, __setMode } from '../src/decide.js';
import { setPathArguments } from '../src/paths.js';
setPathArguments(['--data-dir', '/tmp/aw-t6-data', '--project-dir', '/tmp/aw-t6-project']);

test('shadow: model decides, jev logged', async () => {
  __setMode('proofread.verify', 'shadow');
  __setJev(async () => ({ answer: 'refute', confidence: 0.9 }));
  const r = await decide({ point: 'proofread.verify', question: 'q', options: ['uphold', 'refute'], context: 'c', runId: 't', fallback: async () => 'uphold' });
  assert.deepEqual([r.answer, r.by], ['uphold', 'model']);
});

test('cascade: confident jev decides, unsure escalates', async () => {
  __setMode('proofread.verify', 'cascade');
  __setJev(async () => ({ answer: 'refute', confidence: 0.9 }));
  assert.equal((await decide({ point: 'proofread.verify', question: 'q', options: ['uphold', 'refute'], context: 'c', runId: 't', fallback: async () => 'uphold' })).by, 'jev');
  __setJev(async () => ({ answer: 'refute', confidence: 0.5 }));
  assert.equal((await decide({ point: 'proofread.verify', question: 'q', options: ['uphold', 'refute'], context: 'c', runId: 't', fallback: async () => 'uphold' })).by, 'model');
});

test('no key behaves as off: jev never called', async () => {
  __setMode('proofread.verify', 'cascade');
  __setJev(undefined);
  const r = await decide({ point: 'proofread.verify', question: 'q', options: ['uphold', 'refute'], context: 'c', runId: 't', fallback: async () => 'uphold' });
  assert.equal(r.by, 'model');
});

test('shadow: a failing Jev never breaks the model path', async () => {
  __setMode('proofread.verify', 'shadow');
  __setJev(async () => { throw new Error('HTTP 500'); });
  const r = await decide({ point: 'proofread.verify', question: 'q', options: ['uphold', 'refute'], context: 'c', runId: 't', fallback: async () => 'uphold' });
  assert.deepEqual([r.answer, r.by], ['uphold', 'model']);
});
