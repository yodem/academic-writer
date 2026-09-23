import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runProofread, __stubs, __setWrongWordPass } from '../src/proofread.js';
import { setPathArguments } from '../src/paths.js';
import { mkdtempSync, readFileSync } from 'node:fs';
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

test('hspell null-after candidate merges with finder correction as must-catch', async () => {
  const verified: string[] = [];
  __stubs({
    find: async (chunk) => [{ id: 'finder', line: chunk.startLine, before: 'ההיתיחסות', after: 'ההתייחסות', class: 'typo', meaningRisk: 'low' }],
    mustCatch: async () => [{ id: 'spell', line: 1, before: 'ההיתיחסות', after: null, class: 'typo', meaningRisk: 'low', mustCatch: true }],
    verify: async (changes) => { verified.push(...changes.map((change) => change.id)); return changes.map((change) => ({ id: change.id, verdict: 'uphold' })); },
    memo: async () => '',
  });
  const result = await runProofread({ chunks: [{ id: 'c', index: 0, startLine: 1, endLine: 1, text: 'ההיתיחסות' }], runId: 't-hspell', out: paths() });
  assert.deepEqual(verified, []);
  assert.equal(result.changes.find((change) => change.id === 'spell')?.after, 'ההתייחסות');
  assert.equal(result.changes.find((change) => change.id === 'spell')?.status, 'must-catch+finder');
});

test('overlapping must-catch correction supersedes finder candidate', async () => {
  let verifyCalls = 0;
  __stubs({
    find: async (chunk) => [{ id: 'finder-name', line: chunk.startLine, before: 'רש\'', after: 'רש\u05F4י', class: 'wrong_word', meaningRisk: 'low' }],
    mustCatch: async () => [{ id: 'term-name', line: 1, before: 'רש\'', after: 'רש\u05F4י', class: 'names_terms', meaningRisk: 'low', mustCatch: true }],
    verify: async (changes) => { verifyCalls += 1; return changes.map((change) => ({ id: change.id, verdict: 'uphold' })); },
    memo: async () => '',
  });
  const result = await runProofread({ chunks: [{ id: 'c', index: 0, startLine: 1, endLine: 1, text: 'רש\'' }], runId: 't-overlap', out: paths() });
  assert.equal(verifyCalls, 0);
  assert.equal(result.changes.find((change) => change.id === 'term-name')?.status, 'must-catch');
  assert.equal(result.changes.find((change) => change.id === 'finder-name')?.skipReason, 'superseded-by-must-catch');
});

test('find candidates retain the wrong_word class for contextual real-word errors', async () => {
  let verifyClass = '';
  __stubs({
    find: async (chunk) => [{ id: 'wrong', line: chunk.startLine, before: 'להתפשר אם', after: 'להתפשר עם', class: 'wrong_word', meaningRisk: 'medium' }],
    mustCatch: async () => [],
    verify: async (changes) => { verifyClass = changes[0]?.class ?? ''; return changes.map((change) => ({ id: change.id, verdict: 'uphold' })); },
    memo: async () => '',
  });
  await runProofread({ chunks: [{ id: 'c', index: 0, startLine: 1, endLine: 1, text: 'להתפשר אם' }], runId: 't-wrong-word', out: paths() });
  assert.equal(verifyClass, 'wrong_word');
});

test('wrong-word second pass stays off by default: no extra find call', async () => {
  __setWrongWordPass(undefined); // the default that ships (thresholds.json > proofread.wrongWordPass.enabled: false)
  let wrongWordCalls = 0;
  __stubs({
    find: async () => [],
    findWrongWord: async () => { wrongWordCalls += 1; return []; },
    mustCatch: async () => [],
    verify: async () => [],
    memo: async () => '',
  });
  await runProofread({ chunks: [{ id: 'c', index: 0, startLine: 1, endLine: 1, text: 'x' }], runId: 't-ww-off', out: paths() });
  assert.equal(wrongWordCalls, 0);
});

test('wrong-word second pass, when flagged on, adds one call per chunk and its low-risk candidate reaches verified', async () => {
  __setWrongWordPass(true);
  try {
    let wrongWordCalls = 0;
    __stubs({
      find: async () => [],
      findWrongWord: async (chunk) => { wrongWordCalls += 1; return [{ id: 'w1', line: chunk.startLine, before: 'לארוס', after: 'להרוס', class: 'wrong_word', meaningRisk: 'low' }]; },
      mustCatch: async () => [],
      verify: async (changes) => changes.map((change) => ({ id: change.id, verdict: 'uphold' })),
      memo: async () => '',
    });
    const result = await runProofread({ chunks: [{ id: 'c', index: 0, startLine: 1, endLine: 1, text: 'לארוס' }], runId: 't-ww-on', out: paths() });
    assert.equal(wrongWordCalls, 1);
    const merged = result.changes.find((change) => change.before === 'לארוס');
    assert.equal(merged?.status, 'verified');
    assert.equal(merged?.class, 'wrong_word');
  } finally {
    __setWrongWordPass(undefined);
  }
});

test('wrong-word second-pass ids never collide with the primary pass ids from the same chunk', async () => {
  __setWrongWordPass(true);
  try {
    __stubs({
      find: async (chunk) => [{ id: 'c1', line: chunk.startLine, before: 'alpha', after: 'ALPHA', class: 'typo', meaningRisk: 'low' }],
      findWrongWord: async (chunk) => [{ id: 'c1', line: chunk.startLine, before: 'beta', after: 'BETA', class: 'wrong_word', meaningRisk: 'low' }],
      mustCatch: async () => [],
      verify: async (changes) => changes.map((change) => ({ id: change.id, verdict: 'uphold' })),
      memo: async () => '',
    });
    const result = await runProofread({ chunks: [{ id: 'c', index: 0, startLine: 1, endLine: 1, text: 'alpha beta' }], runId: 't-ww-collide', out: paths() });
    const ids = result.changes.map((change) => change.id);
    assert.equal(new Set(ids).size, ids.length, 'ids from the two passes must not collide');
    assert.equal(result.changes.find((change) => change.before === 'alpha')?.status, 'verified');
    assert.equal(result.changes.find((change) => change.before === 'beta')?.status, 'verified');
  } finally {
    __setWrongWordPass(undefined);
  }
});

test('wrong-word second-pass candidate duplicating a primary-pass hit on the same span is dropped before verify', async () => {
  __setWrongWordPass(true);
  try {
    let verifiedIds: string[] = [];
    __stubs({
      find: async (chunk) => [{ id: 'primary', line: chunk.startLine, before: 'לארוס', after: 'להרוס', class: 'wrong_word', meaningRisk: 'low' }],
      findWrongWord: async (chunk) => [{ id: 'dup', line: chunk.startLine, before: 'לארוס', after: 'להרוס', class: 'wrong_word', meaningRisk: 'low' }],
      mustCatch: async () => [],
      verify: async (changes) => { verifiedIds = changes.map((change) => change.id); return changes.map((change) => ({ id: change.id, verdict: 'uphold' })); },
      memo: async () => '',
    });
    await runProofread({ chunks: [{ id: 'c', index: 0, startLine: 1, endLine: 1, text: 'לארוס' }], runId: 't-ww-dup', out: paths() });
    assert.equal(verifiedIds.length, 1);
  } finally {
    __setWrongWordPass(undefined);
  }
});

test('a must-catch occurrence index survives contractChange into changes.json', async () => {
  const outDir = paths();
  __stubs({
    find: async () => [],
    mustCatch: async () => [{ id: 'cap1', line: 1, before: 'כמו כן', after: 'נוסף על כך', class: 'style_words', meaningRisk: 'low', mustCatch: true, occurrence: 2 }],
    verify: async () => [],
    memo: async () => '',
  });
  await runProofread({ chunks: [{ id: 'c', index: 0, startLine: 1, endLine: 1, text: 'כמו כן x כמו כן' }], runId: 't-occurrence', out: outDir });
  const written = JSON.parse(readFileSync(join(outDir, 'changes.json'), 'utf8')) as { changes: Array<{ before: string; occurrence?: number }> };
  const capped = written.changes.find((change) => change.before === 'כמו כן');
  assert.equal(capped?.occurrence, 2);
});
