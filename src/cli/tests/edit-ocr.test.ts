import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setPathArguments } from '../src/paths.ts';
import { __setTransport } from '../src/gemini.ts';
import { __setDataDir } from '../src/voice.ts';
import { editText } from '../src/edit.ts';
import { ocrDocument, __setProbe } from '../src/ocr.ts';

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
  __setProbe(() => false); // auto with only a Google key: Gemini reads the page
  const result = await ocrDocument({ input: image, language: 'he', runId: 'ocr-test' });
  __setProbe(() => true);
  assert.equal(result.pages[0]?.text, 'Page text');
  assert.equal(result.pages[0]?.is_born_digital, false);
  assert.equal(result.truncated, false);
});

test.after(() => rmSync(root, { recursive: true, force: true }));

import { chmodSync } from 'node:fs';
import { chooseEngine } from '../src/ocr.ts';

function fakeBin(name: string, script: string): string {
  const dir = mkdtempSync(join(tmpdir(), `aw-fake-${name}-`));
  const file = join(dir, name); writeFileSync(file, `#!/bin/sh\n${script}\n`); chmodSync(file, 0o755);
  return dir;
}

test('a named engine must be available, with a named error', () => {
  const key = process.env.GOOGLE_API_KEY;
  try {
    __setProbe(() => true);
    assert.equal(chooseEngine('gemini').engine, 'gemini');
    assert.equal(chooseEngine('claude').engine, 'claude');
    process.env.GOOGLE_API_KEY = '';
    __setProbe(() => false);
    assert.throws(() => chooseEngine('gemini'), /needs a Google API key/);
    assert.throws(() => chooseEngine('claude'), /needs the claude program/);
    assert.throws(() => chooseEngine('local'), /needs tesseract/);
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

test('a Gemini content refusal becomes a blocked page; other Gemini failures still fail', async () => {
  const image = join(root, 'gemini-refused.png'); writeFileSync(image, Buffer.from('image'));
  __setTransport(async () => ({ text: '', finishReason: 'RECITATION', usage: { in: 2, out: 0 } }));
  const refused = await ocrDocument({ input: image, language: 'en', runId: 'ocr-recitation', engine: 'gemini' });
  assert.equal(refused.pages[0]?.text, '');
  assert.match(refused.pages[0]?.notes ?? '', /blocked: Gemini refused this page \(RECITATION\)/);
  __setTransport(async () => ({ text: '', finishReason: 'MAX_TOKENS', usage: { in: 2, out: 0 } }));
  await assert.rejects(ocrDocument({ input: image, language: 'en', runId: 'ocr-maxtokens', engine: 'gemini' }), /MAX_TOKENS/);
});

test('a Claude error that is not a content refusal fails the run instead of passing as a blocked page', async () => {
  const image = join(root, 'claude-auth.png'); writeFileSync(image, Buffer.from('image'));
  const dir = fakeBin('claude', `cat >/dev/null; echo '{"type":"result","is_error":true,"result":"Invalid API key · Please run /login"}'`);
  const path = process.env.PATH;
  process.env.PATH = `${dir}:${path}`;
  try {
    await assert.rejects(ocrDocument({ input: image, language: 'he', runId: 'ocr-claude-auth', engine: 'claude' }), /claude failed: Invalid API key/);
  } finally { process.env.PATH = path; }
});

test('agreement uses letters only, without vowel points, like the bake-off scorer', async () => {
  const { __test } = await import('../src/ocr.ts');
  assert.equal(__test.lettersOnly('בְּרֵאשִׁית, בָּרָא!'), 'בראשית ברא');
  assert.equal(__test.similarity('abcd', 'abcd'), 1);
  assert.equal(__test.similarity('abcd', 'abxd'), 0.75);
});

const HEBREW = 'אבגד הוזח טיכל מנסע פצקר שת '.repeat(12); // over shortAnswerMinChars letters
function suryaBin(text: string): string {
  return fakeBin('surya_ocr', `mkdir -p "$3/page"; printf '{"page":[{"blocks":[{"html":"<p>%s</p>","reading_order":0}]}]}' '${text}' > "$3/page/results.json"`);
}
async function auto(name: string, bins: string[], have: string[], key: string, out?: string): Promise<Awaited<ReturnType<typeof ocrDocument>>> {
  const image = join(root, `${name}.png`); writeFileSync(image, Buffer.from('image'));
  const path = process.env.PATH; const saved = process.env.GOOGLE_API_KEY;
  process.env.PATH = `${bins.join(':')}:${path}`; process.env.GOOGLE_API_KEY = key;
  __setProbe((cmd) => have.includes(cmd));
  try { return await ocrDocument({ input: image, language: 'he', runId: `ocr-${name}`, engine: 'auto', out }); }
  finally { process.env.PATH = path; process.env.GOOGLE_API_KEY = saved; __setProbe(() => true); }
}
const claudeSays = (text: string) => fakeBin('claude', `cat >/dev/null\ncat <<'EOF'\n${JSON.stringify({ type: 'result', is_error: false, result: text })}\nEOF`);
const ALL = ['surya_ocr', 'tesseract', 'claude'];

test('auto keeps the free reading when Surya and Tesseract agree, and never calls Claude', async () => {
  const marker = join(root, 'claude-called');
  const claude = fakeBin('claude', `touch ${marker}; cat >/dev/null`);
  const r = await auto('agree', [suryaBin(HEBREW), fakeBin('tesseract', `echo '${HEBREW}'`), claude], ALL, '');
  assert.equal(r.engine, 'auto');
  assert.equal(r.pages[0]?.engine, 'surya');
  assert.match(r.pages[0]?.notes ?? '', /Surya and Tesseract agree \(1\.000\)/);
  assert.equal(existsSync(marker), false);
});

test('auto sends the page to Claude when the free readers disagree', async () => {
  const r = await auto('disagree', [suryaBin('שונה לגמרי'), fakeBin('tesseract', `echo '${HEBREW}'`), claudeSays(HEBREW)], ALL, '');
  assert.equal(r.pages[0]?.engine, 'claude');
  assert.equal(r.pages[0]?.text, HEBREW);
});

test('a Claude soft refusal or short answer goes to Gemini when there is a key', async () => {
  __setTransport(async () => ({ text: JSON.stringify([{ page_number: 1, text: 'Gemini text', is_born_digital: false, confidence: 'high', notes: '' }]), finishReason: 'STOP', usage: { in: 2, out: 2 } }));
  const soft = await auto('soft', [fakeBin('tesseract', `echo '${HEBREW}'`), claudeSays("I can't transcribe this page verbatim. Summary follows.")], ['tesseract', 'claude'], 'test-key');
  assert.equal(soft.pages[0]?.engine, 'gemini');
  assert.match(soft.pages[0]?.notes ?? '', /read by Gemini: Claude declined/);
  const short = await auto('short', [fakeBin('tesseract', `echo '${HEBREW}'`), claudeSays('אבגד הוזח')], ['tesseract', 'claude'], 'test-key');
  assert.equal(short.pages[0]?.engine, 'gemini');
  assert.match(short.pages[0]?.notes ?? '', /much shorter than the free reading/);
});

test('a Claude refusal with no Gemini key falls back to the free reading, marked low confidence', async () => {
  const refused = fakeBin('claude', `cat >/dev/null; echo '{"type":"result","is_error":true,"result":"API Error: Output blocked by content filtering policy"}'`);
  const r = await auto('refused-nokey', [fakeBin('tesseract', `echo '${HEBREW}'`), refused], ['tesseract', 'claude'], '');
  assert.equal(r.pages[0]?.engine, 'local');
  assert.equal(r.pages[0]?.confidence, 'low');
  assert.match(r.pages[0]?.notes ?? '', /Claude refused the page; no Google API key/);
  assert.equal(r.pages[0]?.text.trim(), HEBREW.trim());
});

test('two empty free readings are not an agreement: Claude reads the page', async () => {
  const r = await auto('empty', [suryaBin(''), fakeBin('tesseract', `echo ''`), claudeSays(HEBREW)], ALL, '');
  assert.equal(r.pages[0]?.engine, 'claude');
});

test('a failing free reader is skipped, not fatal, and --out names each page\'s reader', async () => {
  const out = join(root, 'auto-out.md');
  const r = await auto('tess-fails', [fakeBin('surya_ocr', 'exit 1'), fakeBin('tesseract', 'echo "no heb data" >&2; exit 1'), claudeSays(HEBREW)], ALL, '', out);
  assert.equal(r.pages[0]?.engine, 'claude');
  assert.match(readFileSync(out, 'utf8'), /^OCR engine: auto \(page 1: claude\)/);
  const s = await auto('surya-fails', [fakeBin('surya_ocr', 'exit 1'), fakeBin('tesseract', `echo '${HEBREW}'`), claudeSays(HEBREW)], ALL, '');
  assert.equal(s.pages[0]?.engine, 'claude');
});
