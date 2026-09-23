import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildEvidence, __stubs } from '../src/evidence.ts';
import { setPathArguments } from '../src/paths.ts';

test('non-verbatim quotes are dropped; cache hit skips refetch', async () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-evidence-'));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  let fetches = 0;
  __stubs({
    fetchCk: async () => { fetches += 1; return 'הרמב״ם כתב כי הנבואה היא שפע מאת האל.'; },
    extract: async () => ({ passages: [
      { id: 'p1', sourceId: 's1', locator: '1', quote: 'הנבואה היא שפע', gloss: '', relevance: 3 },
      { id: 'p2', sourceId: 's1', locator: '1', quote: 'הנבואה היא אור', gloss: '', relevance: 2 },
    ] }),
  });
  try {
    const first = await buildEvidence({ sources: ['s1'], runId: 't' });
    assert.deepEqual(first.passages.map((passage) => passage.id), ['p1']);
    await buildEvidence({ sources: ['s1'], runId: 't2' });
    assert.equal(fetches, 1);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test('an empty quote is rejected as not verbatim', async () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-evidence-empty-'));
  setPathArguments(['--data-dir', join(root, 'data'), '--project-dir', join(root, 'project')]);
  __stubs({ fetchCk: async () => 'טקסט המקור המלא.', extract: async () => ({ passages: [
    { id: 'e1', sourceId: 's9', locator: '1', quote: '   ', gloss: '', relevance: 1 } ] }) });
  try {
    const r = await buildEvidence({ sources: ['s9'], runId: 'empty' });
    assert.equal(r.passages.length, 0);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('ck metadata: title from the bold line, author from the Author section', async () => {
  const { ckMetadata } = await import('../src/evidence.ts');
  const m = ckMetadata('# איך לקרוא ספר זה\n\n**יוסף בן שלום אשכנזי על קבלה** · Ra\'avad on Kabbalah\n\n## מחבר / Author\n\n- יוסף בן שלום אשכנזי (Yosef ben Sholom Ashkenazi) · RI\n');
  assert.equal(m.title, 'יוסף בן שלום אשכנזי על קבלה');
  assert.equal(m.author, 'יוסף בן שלום אשכנזי');
});

test('the intent core text is marked primary + isCoreText; others follow primarySources', async () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-evidence-core-'));
  setPathArguments(['--data-dir', join(root, 'd'), '--project-dir', join(root, 'p')]);
  const { writeFileSync, mkdirSync } = await import('node:fs'); mkdirSync(join(root, 'p'), { recursive: true });
  const intentPath = join(root, 'p', 'intent.json');
  writeFileSync(intentPath, JSON.stringify({ thesis: 't', coreTextSourceId: 'c1', primarySources: ['p2'] }));
  __stubs({ fetchCk: async (id: string) => `**Book ${id}**\n\nטקסט`, extract: async () => ({ passages: [] }) });
  try {
    const r = await buildEvidence({ sources: ['c1', 'p2', 's3'], intent: intentPath, runId: 'core' });
    assert.deepEqual(r.sources.map((s) => [s.id, s.role, s.isCoreText]), [['c1', 'primary', true], ['p2', 'primary', false], ['s3', 'secondary', false]]);
    assert.equal(r.sources[0]?.title, 'Book c1');
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('title from ck toc: the line before ID', async () => {
  const { titleFromToc } = await import('../src/evidence.ts');
  assert.equal(titleFromToc('============\nSefer Yetzirah\nID: cmtbr5am34 | 6 pages\n====='), 'Sefer Yetzirah');
});
