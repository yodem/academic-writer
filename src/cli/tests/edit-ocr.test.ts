import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setPathArguments } from '../src/paths.ts';
import { __setTransport } from '../src/gemini.ts';
import { __setDataDir } from '../src/voice.ts';
import { editText } from '../src/edit.ts';
import { ocrDocument } from '../src/ocr.ts';

const root = mkdtempSync(join(tmpdir(), 'aw-edit-ocr-'));
setPathArguments(['--data-dir', root, '--project-dir', root]);
__setDataDir(root);
process.env.GOOGLE_API_KEY = 'test-key';

test('edit uses the model response and writes --out', async () => {
  const voice = join(root, 'voice'); mkdirSync(voice, { recursive: true });
  writeFileSync(join(voice, 'profile.json'), '{}');
  writeFileSync(join(voice, 'exemplars.jsonl'), ''); writeFileSync(join(voice, 'pairs.jsonl'), '');
  writeFileSync(join(voice, 'rules.md'), ''); writeFileSync(join(voice, 'style-words.json'), '{"banned":[],"capped":[],"filler":[]}');
  const source = join(root, 'source.md'); const out = join(root, 'revised.md'); writeFileSync(source, 'Original passage.');
  __setTransport(async () => ({ text: JSON.stringify({ revised_text: 'Revised passage.' }), finishReason: 'STOP', usage: { in: 2, out: 2 } }));
  assert.deepEqual(await editText({ textFile: source, instruction: 'Clarify it', language: 'en', runId: 'edit-test', out }), { revised_text: 'Revised passage.' });
  assert.equal(readFileSync(out, 'utf8'), 'Revised passage.');
});

test('OCR transcribes image input and returns the MCP page shape', async () => {
  const image = join(root, 'scan.png'); writeFileSync(image, Buffer.from('image'));
  __setTransport(async () => ({ text: JSON.stringify([{ page_number: 1, text: 'Page text', is_born_digital: false, confidence: 'high', notes: '' }]), finishReason: 'STOP', usage: { in: 2, out: 2 } }));
  const result = await ocrDocument({ input: image, language: 'he', runId: 'ocr-test' });
  assert.equal(result.pages[0]?.text, 'Page text');
  assert.equal(result.pages[0]?.is_born_digital, false);
  assert.equal(result.truncated, false);
});

test.after(() => rmSync(root, { recursive: true, force: true }));

import { chmodSync } from 'node:fs';
import { chooseEngine, __setProbe } from '../src/ocr.ts';

function fakeBin(name: string, script: string): string {
  const dir = mkdtempSync(join(tmpdir(), `aw-fake-${name}-`));
  const file = join(dir, name); writeFileSync(file, `#!/bin/sh\n${script}\n`); chmodSync(file, 0o755);
  return dir;
}

test('engine tiers: Gemini with a key, else Claude, else local, else a named error', () => {
  const key = process.env.GOOGLE_API_KEY;
  try {
    __setProbe(() => true);
    assert.equal(chooseEngine('auto').engine, 'gemini');
    process.env.GOOGLE_API_KEY = '';
    assert.equal(chooseEngine('auto').engine, 'claude');
    __setProbe((cmd) => cmd === 'tesseract');
    assert.equal(chooseEngine('auto').engine, 'local');
    __setProbe(() => false);
    assert.throws(() => chooseEngine('auto'), /no OCR engine available/);
    assert.throws(() => chooseEngine('gemini'), /needs a Google API key/);
  } finally { process.env.GOOGLE_API_KEY = key; __setProbe(() => true); }
});

test('Claude tier reads each image in an isolated claude call; a filtered page is marked blocked', async () => {
  const image = join(root, 'claude-scan.png'); writeFileSync(image, Buffer.from('image'));
  const ok = fakeBin('claude', `cat >/dev/null; echo '{"type":"result","is_error":false,"result":"שורה ראשונה"}'`);
  const path = process.env.PATH;
  process.env.PATH = `${ok}:${path}`;
  try {
    const result = await ocrDocument({ input: image, language: 'he', runId: 'ocr-claude', engine: 'claude' });
    assert.equal(result.engine, 'claude');
    assert.equal(result.pages[0]?.text, 'שורה ראשונה');
    const blocked = fakeBin('claude', `cat >/dev/null; echo '{"type":"result","is_error":true,"result":"API Error: Output blocked by content filtering policy"}'`);
    process.env.PATH = `${blocked}:${path}`;
    const refused = await ocrDocument({ input: image, language: 'he', runId: 'ocr-claude-2', engine: 'claude' });
    assert.equal(refused.pages[0]?.text, '');
    assert.match(refused.pages[0]?.notes ?? '', /blocked by Claude/);
  } finally { process.env.PATH = path; }
});

test('local tier runs tesseract and marks the text not image-verified', async () => {
  const image = join(root, 'local-scan.png'); writeFileSync(image, Buffer.from('image'));
  const dir = fakeBin('tesseract', `echo "local text"`);
  const path = process.env.PATH;
  process.env.PATH = `${dir}:${path}`;
  try {
    const result = await ocrDocument({ input: image, language: 'en', runId: 'ocr-local', engine: 'local' });
    assert.equal(result.engine, 'local');
    assert.equal(result.pages[0]?.text.trim(), 'local text');
    assert.match(result.pages[0]?.notes ?? '', /not image-verified/);
  } finally { process.env.PATH = path; }
});

test('pages under the low-resolution floor are flagged outside the Gemini tier', async () => {
  const { __test } = await import('../src/ocr.ts');
  assert.match(__test.lowResNote('claude', 74), /low resolution \(74 dpi\)/);
  assert.equal(__test.lowResNote('gemini', 74), '');
  assert.equal(__test.lowResNote('claude', 300), '');
});
