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
