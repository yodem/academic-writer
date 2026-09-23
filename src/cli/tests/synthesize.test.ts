import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { synthesizeAll, __stubs } from '../src/synthesize.js';
import { setPathArguments } from '../src/paths.js';

function freshProject(prefix: string, drafts: Record<string, string>): string {
  const root = mkdtempSync(join(tmpdir(), prefix));
  setPathArguments(['--data-dir', join(root, 'data'), '--project-dir', join(root, 'proj')]);
  const dir = join(root, 'proj', '.academic-helper', 'drafts');
  mkdirSync(dir, { recursive: true });
  for (const [id, text] of Object.entries(drafts)) writeFileSync(join(dir, `${id}.md`), text, 'utf8');
  return root;
}

test('an exact-match edit is applied to the drafts on disk', async () => {
  const root = freshProject('aw-synth-apply-', { U1: 'פסקה ראשונה.\n\nפסקה שנייה.' });
  __stubs({ gen: async () => [{ unitId: 'U1', paragraphIndex: 1, before: 'פסקה שנייה.', after: 'פסקה שנייה, מחוברת יותר.', reason: 'bridge' }] });
  const r = await synthesizeAll({ runId: 'apply' });
  assert.equal(r.applied, 1);
  assert.equal(r.edits.length, 1);
  const text = readFileSync(join(root, 'proj', '.academic-helper', 'drafts', 'U1.md'), 'utf8');
  assert.match(text, /פסקה שנייה, מחוברת יותר\./);
});

test('an edit whose "before" does not match exactly is skipped, never applied', async () => {
  const root = freshProject('aw-synth-mismatch-', { U1: 'פסקה ראשונה.\n\nפסקה שנייה.' });
  __stubs({ gen: async () => [{ unitId: 'U1', paragraphIndex: 1, before: 'טקסט שלא קיים בפסקה', after: 'צריך היה להיכשל', reason: 'bridge' }] });
  const r = await synthesizeAll({ runId: 'mismatch' });
  assert.equal(r.applied, 0);
  const text = readFileSync(join(root, 'proj', '.academic-helper', 'drafts', 'U1.md'), 'utf8');
  assert.doesNotMatch(text, /צריך היה להיכשל/);
  assert.match(text, /פסקה שנייה\./);
});

test('never rewrites the whole article — every other paragraph is untouched', async () => {
  const root = freshProject('aw-synth-scope-', { U1: 'א.\n\nב.\n\nג.' });
  __stubs({ gen: async () => [{ unitId: 'U1', paragraphIndex: 1, before: 'ב.', after: 'ב, מתוקן.', reason: 'bridge' }] });
  await synthesizeAll({ runId: 'scope' });
  const text = readFileSync(join(root, 'proj', '.academic-helper', 'drafts', 'U1.md'), 'utf8');
  assert.match(text, /^א\./m);
  assert.match(text, /^ג\./m);
  assert.match(text, /ב, מתוקן\./);
});

test('missing drafts directory is a named ERROR', async () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-synth-missing-'));
  setPathArguments(['--data-dir', join(root, 'data'), '--project-dir', join(root, 'proj')]);
  __stubs({ gen: async () => [] });
  await assert.rejects(synthesizeAll({ runId: 'missing' }), /ERROR write\.synthesize/);
});

test('repeated paragraph openers are detected across units', async () => {
  const { repeatedOpeners } = await import('../src/synthesize.ts');
  const units = [{ id: 'A', paragraphs: ['אני טוען כי א', 'משהו אחר'] }, { id: 'B', paragraphs: ['אני טוען כי ב'] }, { id: 'C', paragraphs: ['אני טוען כי ג'] }];
  const r = repeatedOpeners(units, 3, 3);
  assert.equal(r.length, 1); assert.equal(r[0]?.opener, 'אני טוען כי'); assert.equal(r[0]?.at.length, 3);
});
