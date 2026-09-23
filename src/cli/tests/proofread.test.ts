import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runProofread, __stubs } from '../src/proofread.js';
import { setPathArguments } from '../src/paths.js';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

function paths(): string { const base = mkdtempSync(join(tmpdir(), 'aw-proofread-')); setPathArguments(['--data-dir', base, '--project-dir', base]); return base; }

test('one find + one verify call per chunk; refute downgrades, never drops; must-catch never sent to verify', async () => {
  const calls: string[] = [];
  __stubs({
    find: async (chunk) => { calls.push('find'); return [{ id: `f${chunk.index}`, line: chunk.startLine, before: 'x', after: 'y', class: 'typo', meaningRisk: 'low' }]; },
    verify: async (changes) => { calls.push('verify'); assert.ok(changes.every((change) => !change.mustCatch)); return changes.map((change) => ({ id: change.id, verdict: change.id === 'f1' ? 'refute' : 'uphold' })); },
    mustCatch: async () => [{ id: 'm1', mustCatch: true, class: 'names_terms', before: 'a', after: 'b', line: 1, meaningRisk: 'low' }],
    memo: async () => 'Memo',
  });
  const chunks = Array.from({ length: 3 }, (_, index) => ({ id: `c${index}`, index, startLine: index + 1, endLine: index + 1, text: 'x' }));
  const result = await runProofread({ chunks, runId: 't', out: paths() });
  assert.equal(calls.filter((call) => call === 'find').length, 3);
  assert.equal(calls.filter((call) => call === 'verify').length, 3);
  assert.equal(result.changes.find((change) => change.id === 'f1')?.status, 'refuted');
  assert.ok(result.changes.find((change) => change.id === 'm1'));
});

test('cascade Jev confidence can skip a model verify fallback', async () => {
  const { __setJev, __setMode } = await import('../src/decide.js');
  __setJev(async () => ({ answer: 'uphold', confidence: 0.99 }));
  __setMode('proofread.verify', 'cascade');
  let verified = false;
  __stubs({ find: async (chunk) => [{ id: `z${chunk.index}`, line: chunk.startLine, before: 'x', after: 'y', class: 'typo', meaningRisk: 'low' }], verify: async (items) => { verified = true; return items.map((item) => ({ id: item.id, verdict: 'refute' })); }, mustCatch: async () => [], memo: async () => '' });
  const result = await runProofread({ chunks: [{ id: 'c', index: 0, startLine: 1, endLine: 1, text: 'x' }], runId: 't-cascade', out: paths() });
  assert.equal(verified, false);
  assert.equal(result.changes[0]?.status, 'verified');
  __setJev(undefined);
  __setMode('proofread.verify', 'shadow');
});
