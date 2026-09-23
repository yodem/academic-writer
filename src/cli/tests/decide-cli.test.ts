import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runDecideCli, __setJev, __setMode } from '../src/decide.ts';
import { setPathArguments } from '../src/paths.ts';

function setup(): { root: string; contextFile: string } {
  const root = mkdtempSync(join(tmpdir(), 'aw-decide-cli-'));
  setPathArguments(['--data-dir', join(root, 'data'), '--project-dir', join(root, 'project')]);
  const contextFile = join(root, 'context.txt');
  writeFileSync(contextFile, 'claim: the text supports this reading.', 'utf8');
  return { root, contextFile };
}

test('aw decide outline.support: valid call returns fallback and logs to the run ledger', async () => {
  const { root, contextFile } = setup();
  __setMode('outline.support', 'off');
  __setJev(undefined);
  try {
    const args = ['decide', 'outline.support', '--question', 'Does this claim follow from the evidence?',
      '--options', 'supported,unsupported', '--context-file', contextFile,
      '--fallback', 'supported', '--run', 'run-1', '--label', 'approved'];
    const result = await runDecideCli(args);
    assert.deepEqual(result, { answer: 'supported', by: 'model', confidence: null });
    const ledger = readFileSync(join(root, 'project', '.academic-helper', 'runs', 'run-1', 'jev.jsonl'), 'utf8').trim();
    const row = JSON.parse(ledger) as { point: string; label: string | null; decidedBy: string };
    assert.equal(row.point, 'outline.support');
    assert.equal(row.label, 'approved');
    assert.equal(row.decidedBy, 'model');
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test('aw decide: rejects a fallback that is not one of --options', async () => {
  const { root, contextFile } = setup();
  try {
    const args = ['decide', 'outline.support', '--question', 'q', '--options', 'supported,unsupported',
      '--context-file', contextFile, '--fallback', 'maybe', '--run', 'run-2'];
    await assert.rejects(() => runDecideCli(args), /--fallback must match one of --options/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test('aw decide: rejects an unknown point', async () => {
  const { root, contextFile } = setup();
  try {
    const args = ['decide', 'not.a.real.point', '--question', 'q', '--options', 'a,b',
      '--context-file', contextFile, '--fallback', 'a', '--run', 'run-3'];
    await assert.rejects(() => runDecideCli(args), /expected aw decide <point>/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test('aw decide: accepts proofread.risk (regression: main.ts once hand-copied the point list and omitted it)', async () => {
  const { root, contextFile } = setup();
  __setMode('proofread.risk', 'off');
  __setJev(undefined);
  try {
    const args = ['decide', 'proofread.risk', '--question', 'q', '--options', 'low,high',
      '--context-file', contextFile, '--fallback', 'low', '--run', 'run-4'];
    const result = await runDecideCli(args);
    assert.equal(result.answer, 'low');
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test('aw decide: missing required flag is a clear error, not a crash', async () => {
  const { root, contextFile } = setup();
  try {
    const args = ['decide', 'outline.support', '--question', 'q', '--options', 'a,b', '--context-file', contextFile];
    await assert.rejects(() => runDecideCli(args), /expected aw decide <point>/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
