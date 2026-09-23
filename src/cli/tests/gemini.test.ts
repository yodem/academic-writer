import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { callGemini, __setTransport } from '../src/gemini.ts';
import { setPathArguments } from '../src/paths.ts';

const cliTemp = mkdtempSync(join(tmpdir(), 'aw-cli-ledger-'));
setPathArguments(['--data-dir', cliTemp, '--project-dir', cliTemp]);

test('truncated reply is ERROR, never partial JSON', async () => {
  __setTransport(async () => ({ text: '{"a":', finishReason: 'MAX_TOKENS', usage: { in: 10, out: 5 } }));
  await assert.rejects(callGemini({ step: 'proofread.find', system: '', parts: ['x'], runId: 't' }),
    (e: unknown) => e instanceof Error && /ERROR.*proofread\.find.*MAX_TOKENS/.test(e.message));
});

test('schema-valid reply parses', async () => {
  process.env.GOOGLE_API_KEY = 'test-key';
  __setTransport(async () => ({ text: '{"ok":true}', finishReason: 'STOP', usage: { in: 10, out: 5 } }));
  const r = await callGemini({ step: 'proofread.find', system: '', parts: ['x'], runId: 't', responseSchema: { type: 'object' } });
  assert.deepEqual(r.json, { ok: true });
});

test('schema parse failures have the specified error', async () => {
  process.env.GOOGLE_API_KEY = 'test-key';
  __setTransport(async () => ({ text: '{bad', finishReason: 'STOP', usage: { in: 1, out: 1 } }));
  await assert.rejects(callGemini({ step: 'proofread.find', system: '', parts: [], runId: 'parse', responseSchema: {} }), /ERROR proofread.find: invalid JSON/);
});

test('plaintext secrets.json is not an API key source', async () => {
  const oldKey = process.env.GOOGLE_API_KEY;
  const oldProject = process.env.CLAUDE_PROJECT_DIR;
  const project = mkdtempSync(join(tmpdir(), 'aw-cli-test-'));
  delete process.env.GOOGLE_API_KEY;
  mkdirSync(join(project, '.academic-helper'), { recursive: true });
  writeFileSync(join(project, '.academic-helper', 'secrets.json'), JSON.stringify({ GOOGLE_API_KEY: 'planted-secret' }));
  setPathArguments(['--data-dir', project, '--project-dir', project]);
  try {
    await assert.rejects(callGemini({ step: 'proofread.find', system: '', parts: ['x'], runId: 't' }), /ERROR.*proofread\.find.*key/i);
  } finally {
    rmSync(project, { recursive: true, force: true });
    if (oldKey === undefined) delete process.env.GOOGLE_API_KEY;
    else process.env.GOOGLE_API_KEY = oldKey;
    if (oldProject === undefined) delete process.env.CLAUDE_PROJECT_DIR;
    else process.env.CLAUDE_PROJECT_DIR = oldProject;
  }
});
