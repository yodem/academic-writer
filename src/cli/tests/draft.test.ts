import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { draftAll, __stubs } from '../src/draft.js';
import { setPathArguments } from '../src/paths.js';

function freshProject(prefix: string): string {
  const root = mkdtempSync(join(tmpdir(), prefix));
  setPathArguments(['--data-dir', join(root, 'data'), '--project-dir', join(root, 'proj')]);
  return root;
}
const noVoice = { exemplars: [] as unknown[], pairs: [] as unknown[], rules: '', styleWords: { banned: [] as { word: string; replacement: string | null }[], capped: [] as { word: string; maxPer: 'paragraph' | 'chapter'; max: number }[], filler: [] as string[] } };

// Step 1: the spec's verbatim test (spec-T15.md Task 15, Step 1).
freshProject('aw-draft-spec-');
test('dependency order, predecessors passed, intro/conclusion last, non-verbatim quote fails the gate', async () => {
  const seen: { unit: string; preds: string[] }[] = [];
  __stubs({ gen: async (u, preds) => { seen.push({ unit: u.id, preds: preds.map(p => p.id) }); return u.id === 'U3' ? 'כתוב ״ציטוט ארוך שאינו מופיע במקור כלל״' : `טקסט ${u.id}`; },
            evidenceQuotes: ['ציטוט מהמקור'], voice: { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } } });
  const outline = { units: [ { id: 'intro', role: 'intro', dependsOn: [] }, { id: 'U1', dependsOn: [] }, { id: 'U2', dependsOn: ['U1'] },
                             { id: 'U3', dependsOn: ['U2'] }, { id: 'conclusion', role: 'conclusion', dependsOn: [] } ] };
  const r = await draftAll(outline, { runId: 't' });
  assert.deepEqual(seen.map(s => s.unit).slice(0, 3), ['U1', 'U2', 'U3']);
  assert.deepEqual(seen.find(s => s.unit === 'U2')?.preds, ['U1']);
  assert.deepEqual(seen.slice(-2).map(s => s.unit).sort(), ['conclusion', 'intro']);
  assert.equal(r.failures[0]?.unit, 'U3'); assert.equal(r.failures[0]?.gate, 'quote-not-in-evidence');
});

// Real (nested) outline.json shape (sections[].units), and a cycle in dependsOn.
test('nested sections[].units outline flattens, and a dependsOn cycle is a named ERROR', async () => {
  freshProject('aw-draft-nested-');
  __stubs({ gen: async (u) => `Body text for ${u.id}.`, evidenceQuotes: [], voice: noVoice });
  const cyclic = { sections: [ { id: 's1', units: [ { id: 'A', dependsOn: ['B'] }, { id: 'B', dependsOn: ['A'] } ] } ] };
  await assert.rejects(draftAll(cyclic, { runId: 'cycle' }), (e: unknown) => e instanceof Error && /cycle detected/.test(e.message));

  const acyclic = { sections: [ { id: 's1', units: [ { id: 'A', dependsOn: [] }, { id: 'B', dependsOn: ['A'] } ] } ] };
  const r = await draftAll(acyclic, { runId: 'nested' });
  assert.deepEqual(r.drafted, ['A', 'B']);
});

// Gate: citation-not-in-sources.
test('gate: citation-not-in-sources rejects a footnote key absent from sources.json', async () => {
  const root = freshProject('aw-draft-citation-');
  mkdirSync(join(root, 'proj', '.academic-helper'), { recursive: true });
  writeFileSync(join(root, 'proj', '.academic-helper', 'sources.json'), JSON.stringify([{ sourceId: 'known1', title: 'T', author: 'A', role: 'secondary', isCoreText: false }]));
  __stubs({ gen: async () => 'טקסט עם ציטוט.[^unknown-source]\n\n[^unknown-source]: עמ׳ 1 — הסבר.', evidenceQuotes: [], voice: noVoice });
  const outline = { units: [{ id: 'U1', dependsOn: [] }] };
  const r = await draftAll(outline, { runId: 'citation' });
  assert.deepEqual(r.failures, [{ unit: 'U1', gate: 'citation-not-in-sources', detail: 'unknown-source' }]);
});

test('gate: a citation key that is in sources.json passes', async () => {
  const root = freshProject('aw-draft-citation-ok-');
  mkdirSync(join(root, 'proj', '.academic-helper'), { recursive: true });
  writeFileSync(join(root, 'proj', '.academic-helper', 'sources.json'), JSON.stringify([{ sourceId: 'known1', title: 'T', author: 'A', role: 'secondary', isCoreText: false }]));
  __stubs({ gen: async () => 'טקסט עם ציטוט.[^known1]\n\n[^known1]: עמ׳ 1 — הסבר.', evidenceQuotes: [], voice: noVoice });
  const outline = { units: [{ id: 'U1', dependsOn: [] }] };
  const r = await draftAll(outline, { runId: 'citation-ok' });
  assert.deepEqual(r.failures, []);
});

// Gate: style-banned.
test('gate: style-banned rejects a unit that uses a banned style word', async () => {
  freshProject('aw-draft-banned-');
  __stubs({ gen: async () => 'זהו טקסט עם מילה_אסורה בתוכו.', evidenceQuotes: [],
            voice: { ...noVoice, styleWords: { banned: [{ word: 'מילה_אסורה', replacement: null }], capped: [], filler: [] } } });
  const outline = { units: [{ id: 'U1', dependsOn: [] }] };
  const r = await draftAll(outline, { runId: 'banned' });
  assert.deepEqual(r.failures, [{ unit: 'U1', gate: 'style-banned', detail: 'מילה_אסורה' }]);
});

// Gate: style-capped.
test('gate: style-capped rejects a capped word used more than its per-paragraph max', async () => {
  freshProject('aw-draft-capped-');
  __stubs({ gen: async () => 'חוזר ושוב חוזר באותה פסקה.', evidenceQuotes: [],
            voice: { ...noVoice, styleWords: { banned: [], capped: [{ word: 'חוזר', maxPer: 'paragraph', max: 1 }], filler: [] } } });
  const outline = { units: [{ id: 'U1', dependsOn: [] }] };
  const r = await draftAll(outline, { runId: 'capped' });
  assert.deepEqual(r.failures, [{ unit: 'U1', gate: 'style-capped', detail: '"חוזר" x2 > 1/paragraph' }]);
});

// Gate: word-bounds — only enforced when the outline unit declares a paragraph plan.
test('gate: word-bounds rejects a unit under thresholds.writerUnit.minWords when the outline specifies paragraphs', async () => {
  freshProject('aw-draft-wordbounds-');
  __stubs({ gen: async () => 'משפט קצר מדי.', evidenceQuotes: [], voice: noVoice });
  const outline = { units: [{ id: 'U1', dependsOn: [], paragraphs: [{ move: 'open', evidenceIds: [], bridgeTo: '' }] }] };
  const r = await draftAll(outline, { runId: 'wordbounds' });
  assert.equal(r.failures[0]?.unit, 'U1');
  assert.equal(r.failures[0]?.gate, 'word-bounds');
});

test('gate: word-bounds is skipped for a unit whose outline entry has no paragraphs array', async () => {
  freshProject('aw-draft-wordbounds-skip-');
  __stubs({ gen: async () => 'משפט קצר מדי.', evidenceQuotes: [], voice: noVoice });
  const outline = { units: [{ id: 'U1', dependsOn: [] }] };
  const r = await draftAll(outline, { runId: 'wordbounds-skip' });
  assert.deepEqual(r.failures, []);
});

// Jev point write.audit_prescreen: logged only; the auditor is always required,
// even in cascade mode with a confident Jev answer.
test('write.audit_prescreen: cascade mode never marks the citation auditor skippable', async () => {
  freshProject('aw-draft-cascade-');
  const { __setJev, __setMode } = await import('../src/decide.js');
  __setMode('write.audit_prescreen', 'cascade');
  __setJev(async () => ({ answer: 'skip-likely', confidence: 0.99 }));
  try {
    __stubs({ gen: async () => 'פסקה ראשונה.\n\nפסקה שנייה.', evidenceQuotes: [], voice: noVoice });
    const outline = { units: [{ id: 'A', dependsOn: [] }] };
    const r = await draftAll(outline, { runId: 'cascade-t' });
    assert.equal(r.audit.length, 2);
    assert.ok(r.audit.every((item) => item.required === true));
  } finally {
    __setMode('write.audit_prescreen', 'shadow');
    __setJev(undefined);
  }
});

// --unit redraft mode: only the named unit is drafted.
test('--unit redraft mode drafts only the named unit', async () => {
  freshProject('aw-draft-unit-');
  const calls: string[] = [];
  __stubs({ gen: async (u) => { calls.push(u.id); return `Body ${u.id}.`; }, evidenceQuotes: [], voice: noVoice });
  const outline = { units: [{ id: 'A', dependsOn: [] }, { id: 'B', dependsOn: ['A'] }] };
  const r = await draftAll(outline, { runId: 'unit-mode', unit: 'B' });
  assert.deepEqual(calls, ['B']);
  assert.deepEqual(r.drafted, ['B']);
});

test('a passage id whose source is known is a valid citation; an unknown one fails the gate', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-cite-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'sources.json'), JSON.stringify([{ id: 's1' }]));
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ passages: [{ id: 'p1', sourceId: 's1', quote: 'ציטוט' }, { id: 'p9', sourceId: 'sX', quote: 'אחר' }] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  __stubs({ gen: async (u) => (u.id === 'U1' ? 'טענה ״ציטוט״.[^p1]' : 'טענה.[^p9]'),
            evidenceQuotes: ['ציטוט'], voice: { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } } });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }, { id: 'U2', dependsOn: ['U1'] }] }, { runId: 'cite' });
  assert.deepEqual(r.failures.map((f) => [f.unit, f.gate]), [['U2', 'citation-not-in-sources']]);
});

test('evidence passages reach the drafter with their ids, sources and locators', async () => {
  const { renderPassages } = await import('../src/draft.ts');
  const out = renderPassages([{ id: 'p1', sourceId: 's1', locator: 'הקדמה', quote: 'ראיתי להעתיק', gloss: 'g' }]);
  assert.match(out, /\[p1\] source=s1 locator=הקדמה/);
  assert.match(out, /quote: ראיתי להעתיק/);
});

test('quote placeholders are replaced by the verbatim evidence quote; unknown ids stay for the gate', async () => {
  const { substituteQuotes } = await import('../src/draft.ts');
  const q = new Map([['p1', 'ראיתי להעתיק הספר'], ['e1', 'the lexicon']]);
  assert.equal(substituteQuotes('כתב ⟦Q:p1⟧ ועוד ⟦Q:e1⟧ ו⟦Q:zz⟧', q), 'כתב "ראיתי להעתיק הספר" ועוד \u201Cthe lexicon\u201D ו⟦Q:zz⟧');
});

test('sources listed in evidence.json count as known sources when sources.json is absent', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-cite2-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [{ id: 'p1', sourceId: 's1', quote: 'ציטוט' }] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  __stubs({ gen: async () => 'טענה.[^p1]', evidenceQuotes: ['ציטוט'], voice: { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } } });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'cite2' });
  assert.deepEqual(r.failures, []);
});

test('quote gate: inserted quotes with inner marks pass; short term quotes pass; a long invented quote fails', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q3-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [{ id: 'p1', sourceId: 's1', quote: 'וצא"ל כי הפילוסופים אומרים' }] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async (u) => (u.id === 'U1' ? 'כתב ⟦Q:p1⟧.[^p1] זהו ״יש מאין״ במובנו.' : 'הוא כתב ״משפט ארוך שלא הופיע בשום מקור בכלל״.[^p1]'), voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }, { id: 'U2', dependsOn: [] }] }, { runId: 'q3' });
  assert.deepEqual(r.failures.map((f) => [f.unit, f.gate]), [['U2', 'quote-not-in-evidence']]);
});

test('inserted quote before sentence punctuation drops the quote\'s own final period', async () => {
  const { substituteQuotes } = await import('../src/draft.ts');
  assert.equal(substituteQuotes('הוא כתב ⟦Q:p1⟧.', new Map([['p1', 'וזהו כפירה בתורה.']])), 'הוא כתב "וזהו כפירה בתורה".');
});

test('footnote definitions for passage keys are rendered from evidence metadata', async () => {
  const { renderFootnotes } = await import('../src/draft.ts');
  const out = renderFootnotes('טקסט.[^p1]\n\n[^p1]: Page 3 — gloss\n[^x]: keep', new Map([['p1', { author: 'יוסף בן שלום אשכנזי', title: 'פירוש לספר יצירה', locator: 'Page 3' }]]));
  assert.match(out, /\[\^p1\]: יוסף בן שלום אשכנזי, פירוש לספר יצירה, עמ׳ 3\./);
  assert.match(out, /\[\^x\]: keep/);
});

test('quote pairing: acronym gershayim are skipped, prefix-attached quotes are delimiters', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q4-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async () => 'הרמב״ם דן במושג ה״יש מאין״ ובמושג ה״אין״ אצל הקב״ה ז״ל, וזו טענה ארוכה מאוד על הדברים.', voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'q4' });
  assert.deepEqual(r.failures, []);
});

test('Hebrew quotations get a straight quote, never gershayim; Latin ones get curly quotes', async () => {
  const { substituteQuotes } = await import('../src/draft.ts');
  const out = substituteQuotes('⟦Q:h⟧ ו⟦Q:l⟧ ו⟦Q:a⟧', new Map([['h', 'הרמב"ם כתב כך'], ['l', 'Shemarya wrote'], ['a', 'תשכ״ב']]));
  assert.equal(out, '"הרמב"ם כתב כך" ו\u201CShemarya wrote\u201D ו"תשכ״ב"');
  assert.ok(!out.includes('\u05F4\u05F4'));
  // the inserted Hebrew quote contains no gershayim as a delimiter: its first and last characters are ASCII
  const hebrew = substituteQuotes('⟦Q:h⟧', new Map([['h', 'שלום עולם']]));
  assert.equal(hebrew[0], '"');
  assert.equal(hebrew[hebrew.length - 1], '"');
});

test('quote pairing: straight-quote acronyms are skipped, prefix-attached straight quotes are delimiters', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q5-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async () => 'הרמב"ם דן במושג ה"יש מאין" ובמושג ה"אין" אצל הקב"ה ז"ל בשנת תשכ"ב, וזו טענה ארוכה מאוד על הדברים.', voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'q5' });
  assert.deepEqual(r.failures, []);
});

test('quote gate: a long invented quote in straight quotes still fails after acronyms are filtered', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q6-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async () => 'הרמב"ם כתב "משפט ארוך שלא הופיע בשום מקור בכלל" בספרו.', voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'q6' });
  assert.deepEqual(r.failures.map((f) => [f.unit, f.gate]), [['U1', 'quote-not-in-evidence']]);
});

test('quote gate: a prefix glued to a one-letter quotation cannot smuggle a long invented quote past the gate', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q7-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async () => 'הכותב דן ב"א" ואז "משפט ארוך שלא הופיע בשום מקור בכלל" בספרו.', voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'q7' });
  assert.deepEqual(r.failures.map((f) => [f.unit, f.gate]), [['U1', 'quote-not-in-evidence']]);
});

test('quote gate: two glued one-letter quotations restoring an even count still cannot hide an invented quote', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q8-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async () => 'הכותב דן ב"א" ואז "משפט ארוך שלא הופיע בשום מקור בכלל" וב"ב".', voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'q8' });
  assert.deepEqual(r.failures.map((f) => [f.unit, f.gate]), [['U1', 'quote-not-in-evidence']]);
});

test('quote gate: a quotation that ends in an acronym still passes when its text is in the evidence', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q9-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [{ id: 'p1', sourceId: 's1', quote: 'כדברי חז"ל' }, { id: 'p2', sourceId: 's1', quote: 'ציטוט ארוך מן המקור עצמו כלשונו' }] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async () => 'הוא כתב "כדברי חז"ל" ואחר כך "ציטוט ארוך מן המקור עצמו כלשונו" בספרו.', voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'q9' });
  assert.deepEqual(r.failures.map((f) => [f.unit, f.gate]), []);
});

test('quote gate: punctuation inside glued one-letter quotations cannot hide an invented quote', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q10-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async () => 'הכותב דן ב"א." ואז "משפט ארוך שלא הופיע בשום מקור בכלל" וב"ב.".', voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'q10' });
  assert.deepEqual(r.failures.map((f) => [f.unit, f.gate]), [['U1', 'quote-not-in-evidence']]);
});

test('quote gate: a one-letter quotation and a quotation ending in an acronym in one sentence pass with evidence', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q11-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [{ id: 'p1', sourceId: 's1', quote: 'כדברי חז"ל' }] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async () => 'הכותב דן ב"א" ואחר כך "כדברי חז"ל" בספרו.', voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'q11' });
  assert.deepEqual(r.failures.map((f) => [f.unit, f.gate]), []);
});

test('quote gate: a same-character nested quotation cannot hide an unsupported outer quotation', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q12-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async () => 'הוא כתב "אחד שניים "שלוש ארבע" חמש שש".', voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'q12' });
  assert.deepEqual(r.failures.map((f) => [f.unit, f.gate]), [['U1', 'quote-not-in-evidence']]);
});

test('quote gate: an English same-character nested quotation cannot hide an unsupported outer quotation', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q13-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async () => 'He wrote "one two "three four" five six".', voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'q13' });
  assert.deepEqual(r.failures.map((f) => [f.unit, f.gate]), [['U1', 'quote-not-in-evidence']]);
});

test('quote gate: a curly nested quotation is checked on its outer span', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q14-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async () => 'He wrote \u201Cone two \u201Cthree four\u201D five six\u201D in his book.', voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'q14' });
  assert.deepEqual(r.failures.map((f) => [f.unit, f.gate]), [['U1', 'quote-not-in-evidence']]);
});

test('quote gate: an unmatched curly opening quote fails closed', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q15-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async () => 'He wrote \u201Cone two three four five six seven in his book.', voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'q15' });
  assert.deepEqual(r.failures.map((f) => [f.unit, f.gate]), [['U1', 'quote-not-in-evidence']]);
});

test('quote gate: a nested quotation whose inner marks touch punctuation fails closed (English)', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q16-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async () => 'He wrote "one two "(three four)" five six".', voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'q16' });
  assert.deepEqual(r.failures.map((f) => [f.unit, f.gate]), [['U1', 'quote-not-in-evidence']]);
});

test('quote gate: a nested quotation whose inner marks touch punctuation fails closed (Hebrew)', async () => {
  const { mkdtempSync, mkdirSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const { setPathArguments } = await import('../src/paths.ts');
  const root = mkdtempSync(join(tmpdir(), 'aw-q17-')); const h = join(root, '.academic-helper'); mkdirSync(h, { recursive: true });
  writeFileSync(join(h, 'evidence.json'), JSON.stringify({ sources: [{ id: 's1' }], passages: [] }));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  const voice = { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } };
  __stubs({ gen: async () => 'הוא כתב "אחד שניים "(שלוש ארבע)" חמש שש".', voice });
  const r = await draftAll({ units: [{ id: 'U1', dependsOn: [] }] }, { runId: 'q17' });
  assert.deepEqual(r.failures.map((f) => [f.unit, f.gate]), [['U1', 'quote-not-in-evidence']]);
});
