import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setPathArguments } from '../src/paths.ts';
import { __setTransport } from '../src/gemini.ts';
import { ocrDocument, exitCodeFor } from '../src/ocr.ts';

const root = mkdtempSync(join(tmpdir(), 'aw-ocr-gate-'));
setPathArguments(['--data-dir', root, '--project-dir', root]);
process.env.GOOGLE_API_KEY = 'test-key';

function scans(name: string, n: number): string {
  const dir = join(root, name); mkdirSync(dir, { recursive: true });
  for (let i = 1; i <= n; i++) writeFileSync(join(dir, `p${String(i).padStart(2, '0')}.png`), Buffer.from('image'));
  return dir;
}
function stub(): { calls: number } {
  const state = { calls: 0 };
  __setTransport(async () => { state.calls += 1; return { text: JSON.stringify([{ page_number: 1, text: 'text', is_born_digital: false, confidence: 'high' }]), finishReason: 'STOP', usage: { in: 1, out: 1 } }; });
  return state;
}

test('ocr gate stops Gemini past the cap and exits 4', async () => {
  process.env.AW_OCR_GEMINI_CAP = '2';
  try {
    const state = stub();
    const out = await ocrDocument({ input: scans('cap', 5), language: 'en', runId: 'gate-cap', engine: 'gemini' });
    assert.equal(state.calls, 2);
    assert.deepEqual(out.pages.map((p) => p.text), ['text', 'text', '', '', '']);
    assert.match(out.pages[2].notes ?? '', /^needs approval: Gemini, 3 pages, est\. \$0\.01; rerun with --confirm-cost$/);
    assert.equal(out.pages[2].confidence, 'low');
    assert.deepEqual(out.summary.needs_approval, [3, 4, 5]);
    assert.equal(exitCodeFor(out), 4);
    // --confirm-cost lifts the cap
    const again = stub();
    const all = await ocrDocument({ input: scans('cap', 5), language: 'en', runId: 'gate-cap-confirm', engine: 'gemini', confirmCost: true });
    assert.equal(again.calls, 5);
    assert.equal(exitCodeFor(all), 0);
  } finally { delete process.env.AW_OCR_GEMINI_CAP; }
});

test('ocr gate counts earlier calls in the same run', async () => {
  process.env.AW_OCR_GEMINI_CAP = '3';
  try {
    const dir = join(root, '.academic-helper', 'runs', 'gate-run'); mkdirSync(dir, { recursive: true });
    const row = (step: string, provider: string) => JSON.stringify({ run_id: 'gate-run', step, provider, model: 'm', input_tokens: 1, output_tokens: 1, cost_usd: null, latency_ms: 1, exit: 'OK', same_family: false });
    writeFileSync(join(dir, 'usage.jsonl'), [row('ocr', 'gemini'), row('ocr', 'gemini'), row('write.draft', 'gemini'), row('ocr', 'code')].join('\n') + '\n');
    const state = stub();
    const out = await ocrDocument({ input: scans('prior', 3), language: 'en', runId: 'gate-run', engine: 'gemini' });
    assert.equal(state.calls, 1);
    assert.deepEqual(out.summary.needs_approval, [2, 3]);
    assert.match(out.pages[1].notes ?? '', /needs approval: Gemini, 2 pages, est\. \$0\.01; rerun/);
  } finally { delete process.env.AW_OCR_GEMINI_CAP; }
});

test('ocr model override requires confirm-cost', async () => {
  const state = stub();
  const input = scans('override', 1);
  await assert.rejects(ocrDocument({ input, language: 'en', runId: 'ov', engine: 'gemini', geminiModel: 'gemini-2.5-pro' }), /needs the author's approval.*--confirm-cost/);
  await assert.rejects(ocrDocument({ input, language: 'en', runId: 'ov', engine: 'claude', claudeModel: 'claude-opus-5-5' }), /--confirm-cost/);
  assert.equal(state.calls, 0);
  const seen: string[] = [];
  __setTransport(async (r) => { seen.push(r.model); return { text: JSON.stringify([{ page_number: 1, text: 't', is_born_digital: false }]), finishReason: 'STOP', usage: { in: 1, out: 1 } }; });
  await ocrDocument({ input, language: 'en', runId: 'ov2', engine: 'gemini', geminiModel: 'gemini-2.5-pro', confirmCost: true });
  assert.deepEqual(seen, ['gemini-2.5-pro']);
});
