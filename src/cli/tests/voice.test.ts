import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { voiceBundle, __setDataDir } from '../src/voice.js';

test('no store → exit 3 with pull hint', async () => {
  __setDataDir(mkdtempSync(join(tmpdir(), 'aw-')));
  await assert.rejects(voiceBundle({ n: 6, pairs: 2, runId: 't' }), /exit 3.*aw voice pull/);
});

test('bundle takes at most one exemplar per source paper', async () => {
  const d = mkdtempSync(join(tmpdir(), 'aw-'));
  mkdirSync(join(d, 'voice'));
  const ex = Array.from({ length: 12 }, (_, i) => JSON.stringify({ id: `e${i}`, source: `paper${i % 3}`, text: 'x' })).join('\n');
  writeFileSync(join(d, 'voice/exemplars.jsonl'), ex);
  writeFileSync(join(d, 'voice/profile.json'), '{"schemaVersion":1,"voiceVersion":"v"}');
  writeFileSync(join(d, 'voice/rules.md'), '');
  writeFileSync(join(d, 'voice/style-words.json'), '{"banned":[],"capped":[],"filler":[]}');
  writeFileSync(join(d, 'voice/pairs.jsonl'), '');
  __setDataDir(d);
  const b = await voiceBundle({ n: 6, pairs: 2, runId: 't' });
  assert.equal(new Set(b.exemplars.map(e => e.source)).size, b.exemplars.length);
});
