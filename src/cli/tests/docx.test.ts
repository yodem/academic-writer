import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { assembleArticle } from '../src/docx.js';

function project(): string {
  const root = mkdtempSync(join(tmpdir(), 'aw-docx-'));
  mkdirSync(join(root, '.academic-helper', 'drafts'), { recursive: true });
  return root;
}

test('converts markers, removes definitions and extends repeated 12-character anchors', () => {
  const root = project();
  try {
    writeFileSync(join(root, '.academic-helper/drafts/U.md'), 'prefix SAME-TAIL12[^a] middle SAME-TAIL12[^b]\n\n[^a]: Note A\n[^b]: Note B\n');
    const result = assembleArticle({ sections: [{ title: 'A', units: [{ id: 'U' }] }] }, root, 'r', {});
    const p = (result.article.sections as { paragraphs: { text: string; footnotes: { after: string; text: string }[] }[] }[])[0]!.paragraphs[0]!;
    assert.equal(p.text, 'prefix SAME-TAIL12 middle SAME-TAIL12');
    assert.deepEqual(p.footnotes.map((f) => f.text), ['Note A', 'Note B']);
    assert.notEqual(p.footnotes[0]!.after, 'SAME-TAIL12');
    assert.notEqual(p.footnotes[0]!.after, p.footnotes[1]!.after);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('uses outline section/unit order with intro first and conclusion last', () => {
  const root = project();
  try {
    for (const id of ['intro', 'zeta', 'alpha', 'conclusion']) writeFileSync(join(root, `.academic-helper/drafts/${id}.md`), `${id} text`);
    const result = assembleArticle({ sections: [{ title: 'First', units: [{ id: 'intro' }, { id: 'zeta' }, { id: 'alpha' }, { id: 'conclusion' }] }] }, root, 'r', {});
    const paragraphs = (result.article.sections as { paragraphs: { text: string }[] }[]).flatMap((s) => s.paragraphs.map((p) => p.text));
    assert.deepEqual(paragraphs, ['intro text', 'zeta text', 'alpha text', 'conclusion text']);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('reports missing drafts and unmatched markers by name', () => {
  const root = project();
  try {
    assert.throws(() => assembleArticle({ sections: [{ title: 'A', units: [{ id: 'missing' }] }] }, root, 'r', {}), /ERROR docx: missing draft missing/);
    writeFileSync(join(root, '.academic-helper/drafts/U.md'), 'text[^nope]');
    assert.throws(() => assembleArticle({ sections: [{ title: 'A', units: [{ id: 'U' }] }] }, root, 'r', {}), /ERROR docx: footnote nope has no definition/);
  } finally { rmSync(root, { recursive: true, force: true }); }
});
