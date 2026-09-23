import { test } from 'node:test';
import assert from 'node:assert/strict';
import { applyPlan, __setDataDir, __confirm } from '../src/revise.js';
import { mkdtempSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
test('plugin_defect goes to the ledger; voice_signal needs confirmation', async () => {
  const d = mkdtempSync(join(tmpdir(), 'aw-')); mkdirSync(join(d, 'voice')); writeFileSync(join(d, 'voice/pairs.jsonl'), '');
  __setDataDir(d); __confirm(async () => false);
  await applyPlan({ runId: 't', pluginVersion: '0.13.0', items: [
    { id: 'a', category: 'plugin_defect', proposal: { step: 'evidence.extract', authorWords: 'used the Ibn Tibbon translation, not Makbili' } },
    { id: 'b', category: 'voice_signal', proposal: { before: 'יתרה מזאת', after: 'זאת ועוד' } } ] });
  assert.match(readFileSync(join(d, 'feedback/ledger.jsonl'), 'utf8'), /Makbili/);
  assert.equal(readFileSync(join(d, 'voice/pairs.jsonl'), 'utf8'), '');
});
