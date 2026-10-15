import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildEvidence, __stubs } from '../src/evidence.ts';
import { Library } from '../src/library/adapter.ts';
import { runLibraryCli } from '../src/library/cli.ts';
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
    assert.deepEqual(first.passages.map((passage) => passage.quote), ['הנבואה היא שפע']);
    assert.match(first.passages[0]!.id, /^s1-[0-9a-f]{8}$/);
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

test('passage ids are stable across rebuilds and unique across sources', async () => {
  const { stablePassageId } = await import('../src/evidence.ts');
  const a = stablePassageId('sourceAlpha01', 'הנבואה  היא שפע');
  assert.equal(a, stablePassageId('sourceAlpha01', 'הנבואה היא שפע')); // whitespace-normalized
  assert.notEqual(a, stablePassageId('sourceBeta02', 'הנבואה היא שפע'));
});

test('a rebuild keeps previously extracted passages that are still verbatim', async () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-evidence-merge-'));
  setPathArguments(['--data-dir', join(root, 'd'), '--project-dir', join(root, 'p')]);
  let call = 0;
  __stubs({ fetchCk: async () => 'אלף בית גימל. דלת הא וו.', extract: async () => ({ passages: call++ === 0
    ? [{ id: 'x', sourceId: 'merge-src', locator: '1', quote: 'אלף בית גימל', gloss: '', relevance: 3 }]
    : [{ id: 'y', sourceId: 'merge-src', locator: '1', quote: 'דלת הא וו', gloss: '', relevance: 2 }] }) });
  try {
    const first = await buildEvidence({ sources: ['merge-src'], runId: 'm1' });
    const second = await buildEvidence({ sources: ['merge-src'], runId: 'm2' });
    assert.ok(second.passages.some((p) => p.id === first.passages[0]!.id));
    assert.equal(second.passages.length, 2);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

// ---------------------------------------------------------------- library routes (phase 4)

// Fake `trove` and `pilib` commands: tiny node scripts, so no real library is touched.
const FAKE_TROVE = `
const fs = require('node:fs');
const args = process.argv.slice(2);
if (process.env.FAKE_LOG) fs.appendFileSync(process.env.FAKE_LOG, 'trove ' + args.join(' ') + '\\n');
if (args[0] === 'items' && args[1] === 'read') setTimeout(() => process.stdout.write('**Trove Book**\\n\\n── Page 1 ──\\nהנבואה היא שפע מאת האל.\\n'), Number(process.env.FAKE_SLOW_READ_MS || 0));
else if (args[0] === 'shelf') console.log('No active shelf');
else if (args[0] === 'items' && args[1] === 'list') console.log(JSON.stringify({ items: JSON.parse(process.env.FAKE_LIST_JSON || '[]') }));
else if (args[0] === 'items' && args[1] === 'toc') console.log('==========\\nTrove Title\\nID: ' + args[2] + ' | 1 pages\\n==========');
else { console.error('unexpected: ' + args.join(' ')); process.exit(2); }
`;
const FAKE_PILIB = `
const fs = require('node:fs');
const args = process.argv.slice(2);
if (process.env.FAKE_LOG) fs.appendFileSync(process.env.FAKE_LOG, 'pilib ' + args.join(' ') + '\\n');
if (process.env.FAKE_PILIB_FAIL) { console.error('pilib: boom'); process.exit(1); }
const [cmd, book, spec] = args;
if (cmd === 'catalog') console.log(JSON.stringify({ 'lib-1': { title: 'PageIndex Title', author: 'Au', n_pages: 2, toc_source: 'x', top: [] }, ...JSON.parse(process.env.FAKE_PI_EXTRA || '{}') }));
else if (cmd === 'meta') console.log(JSON.stringify({ book_id: book, title: 'PageIndex Title', n_pages: 2, origin: {}, trove_id: process.env.FAKE_PI_TROVE_ID || 'T-1', pagemap: null }));
else if (cmd === 'read') console.log(JSON.stringify({ book_id: book, pages: [{ page: 1, content: 'פרק ראשון של המקור.' }, { page: 2, content: 'פרק שני של המקור.' }] }));
else { console.error('unexpected: ' + args.join(' ')); process.exit(2); }
`;

type Bench = { root: string; project: string; data: string; log: string; restore: () => void };

function bench(config?: unknown, extraEnv: Record<string, string> = {}): Bench {
  const root = mkdtempSync(join(tmpdir(), 'aw-evidence-lib-'));
  const project = join(root, 'p');
  const data = join(root, 'd');
  const bin = join(root, 'bin');
  mkdirSync(join(project, '.academic-helper'), { recursive: true });
  mkdirSync(bin);
  const write = (name: string, body: string): string => { const file = join(bin, name); writeFileSync(file, `#!${process.execPath}\n${body}`, 'utf8'); chmodSync(file, 0o755); return file; };
  const log = join(root, 'calls.log');
  const saved: Record<string, string | undefined> = {};
  const set = (key: string, value: string | undefined): void => { saved[key] = process.env[key]; if (value === undefined) delete process.env[key]; else process.env[key] = value; };
  set('AW_TROVE_COMMAND', write('trove', FAKE_TROVE));
  set('AW_PAGEINDEX_COMMAND', write('pilib', FAKE_PILIB));
  set('FAKE_LOG', log);
  set('AW_LIBRARY_SHADOW', 'inline');
  for (const [key, value] of Object.entries(extraEnv)) set(key, value);
  if (config !== undefined) writeFileSync(join(project, '.academic-helper', 'library.json'), JSON.stringify(config), 'utf8');
  setPathArguments(['--data-dir', data, '--project-dir', project]);
  return { root, project, data, log, restore: () => { for (const [key, value] of Object.entries(saved)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; } rmSync(root, { recursive: true, force: true }); } };
}
const loggedCalls = (b: Bench): string[] => (existsSync(b.log) ? readFileSync(b.log, 'utf8').split('\n').filter(Boolean) : []);
const noPassages = { extract: async () => ({ passages: [] }) };

test('library.json absent: the old call pattern, cache name and output are unchanged (stubbed seam)', async () => {
  const b = bench();
  const seen: Array<[string, string]> = [];
  __stubs({ fetchCk: async (id, route) => { seen.push([id, route]); return '**Stub Book**\n\nהנבואה היא שפע.'; }, ...noPassages });
  try {
    const result = await buildEvidence({ sources: ['S-1'], runId: 'r' });
    assert.deepEqual(seen, [['S-1', 'trove']]);
    assert.deepEqual(Object.keys(result.sources[0] ?? {}).sort(), ['author', 'id', 'isCoreText', 'role', 'title']);
    const cached = readdirSync(join(b.data, 'sources'));
    assert.equal(cached.length, 1);
    assert.match(cached[0] ?? '', /^S-1@[0-9a-f]{64}$/u); // the plain id: caches written before routes still hit
    assert.equal(existsSync(join(b.project, '.academic-helper', 'library.json')), false);
    assert.equal(existsSync(join(b.project, '.academic-helper', 'retrieval.jsonl')), false); // the stub never reaches the library
  } finally { __stubs({}); b.restore(); }
});

test('library.json absent: a real read is exactly `trove items read ID:all` then `trove items toc ID`', async () => {
  const b = bench();
  __stubs(noPassages);
  try {
    const result = await buildEvidence({ sources: ['T-1'], runId: 'r' });
    assert.deepEqual(loggedCalls(b), ['trove items read T-1:all', 'trove items toc T-1']);
    assert.equal(result.sources[0]?.title, 'Trove Title'); // from the toc line before ID:, as before
    assert.equal(readFileSync(join(b.data, 'sources', readdirSync(join(b.data, 'sources'))[0] ?? '', 'text.md'), 'utf8'), '**Trove Book**\n\n── Page 1 ──\nהנבואה היא שפע מאת האל.\n'); // Trove's own text, untouched
    const rows = readFileSync(join(b.project, '.academic-helper', 'retrieval.jsonl'), 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line) as { row_type: string; op: string; source_id: string });
    assert.deepEqual(rows.map((r) => [r.row_type, r.op, r.source_id]), [['lookup', 'get', 'T-1']]);
  } finally { __stubs({}); b.restore(); }
});

test('the source cache is keyed by route: a Trove text is never reused for PageIndex', async () => {
  const b = bench({ route: 'pageindex' });
  const seen: string[] = [];
  __stubs({ fetchCk: async (id, route) => { seen.push(`${route}:${id}`); return `text from ${route}`; }, ...noPassages });
  try {
    // an entry the Trove route wrote earlier, under the plain id
    mkdirSync(join(b.data, 'sources', 'T-1@abc'), { recursive: true });
    writeFileSync(join(b.data, 'sources', 'T-1@abc', 'text.md'), 'older Trove text', 'utf8');
    await buildEvidence({ sources: ['T-1'], runId: 'r' });
    assert.deepEqual(seen, ['pageindex:T-1']);
    assert.ok(readdirSync(join(b.data, 'sources')).some((name) => name.startsWith('pageindex~T-1@')));
  } finally { __stubs({}); b.restore(); }
});

test('route=pageindex reads through pilib with page banners and the PageIndex title', async () => {
  const b = bench({ route: 'pageindex' });
  __stubs(noPassages);
  try {
    const result = await buildEvidence({ sources: ['lib-1'], runId: 'r' });
    assert.equal(result.sources[0]?.title, 'PageIndex Title');
    const text = readFileSync(join(b.data, 'sources', readdirSync(join(b.data, 'sources'))[0] ?? '', 'text.md'), 'utf8');
    assert.match(text, /── Page 1 ──\nפרק ראשון של המקור\./u);
    assert.match(text, /── Page 2 ──\nפרק שני/u);
    assert.ok(!loggedCalls(b).some((line) => line.startsWith('trove ')), 'Trove is not asked on the PageIndex route');
  } finally { __stubs({}); b.restore(); }
});

test('route=both: Trove answers as before and the quiet PageIndex lookup is a shadow row; a failing shadow changes nothing', async () => {
  // Each run uses its own source id: the in-memory source cache outlives a test.
  const stable = async (id: string, env: Record<string, string>): Promise<{ sources: unknown; text: string; types: string[] }> => {
    const b = bench({ route: 'both' }, env);
    __stubs(noPassages);
    try {
      const result = await buildEvidence({ sources: [id], runId: 'r' });
      const text = readFileSync(join(b.data, 'sources', readdirSync(join(b.data, 'sources'))[0] ?? '', 'text.md'), 'utf8');
      const rows = readFileSync(join(b.project, '.academic-helper', 'retrieval.jsonl'), 'utf8').split('\n').filter(Boolean).map((line) => (JSON.parse(line) as { row_type: string }).row_type);
      return { sources: result.sources.map(({ id: _id, ...rest }) => rest), text, types: rows };
    } finally { __stubs({}); b.restore(); }
  };
  const healthy = await stable('T-healthy', { FAKE_PI_TROVE_ID: 'T-healthy' });
  const failing = await stable('T-failing', { FAKE_PI_TROVE_ID: 'T-failing', FAKE_PILIB_FAIL: '1' });
  assert.deepEqual(failing.sources, healthy.sources);
  assert.equal(failing.text, healthy.text);
  assert.ok(healthy.types.includes('lookup') && healthy.types.includes('shadow'), healthy.types.join(','));
  assert.ok(failing.types.includes('shadow'), 'the failed shadow is recorded, not raised');
});

test('a whole-book read may take longer than a page lookup: readAll timeout vs lookup timeout', async () => {
  const b = bench(undefined, { FAKE_SLOW_READ_MS: '1200' });
  try {
    const library = new Library(b.project, process.env, { shadow: 'off', timeoutMs: 400, readAllTimeoutMs: 6000 });
    const whole = await library.read({ source: 'T-slow', all: true, op: 'get' });
    assert.match(whole.raw ?? '', /Trove Book/u); // slower than the lookup timeout, inside the whole-book one
    await assert.rejects(library.read({ source: 'T-slow', pages: '1' }), /did not answer within 400 ms/u); // a page range keeps the lookup timeout
  } finally { b.restore(); }
});

test('evidence build reads a slow whole book (AW_LIBRARY_TIMEOUT_MS bounds lookups, the read-all seam bounds the book)', async () => {
  const b = bench(undefined, { FAKE_SLOW_READ_MS: '1200', AW_LIBRARY_TIMEOUT_MS: '400', AW_LIBRARY_READALL_TIMEOUT_MS: '6000' });
  __stubs(noPassages);
  try {
    const result = await buildEvidence({ sources: ['T-slow-evidence'], runId: 'r' });
    assert.equal(result.sources[0]?.title, 'Trove Title');
    assert.deepEqual(loggedCalls(b), ['trove items read T-slow-evidence:all', 'trove items toc T-slow-evidence']);
  } finally { __stubs({}); b.restore(); }
});

test('evidence lookups and their shadow carry the run id, so aw library report --run includes them', async () => {
  const b = bench({ route: 'both' }, { FAKE_PI_TROVE_ID: 'T-run' });
  __stubs(noPassages);
  try {
    await buildEvidence({ sources: ['T-run'], runId: 'run-evidence-1' });
    const rows = readFileSync(join(b.project, '.academic-helper', 'retrieval.jsonl'), 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line) as { row_type: string; run_id: string | null });
    assert.ok(rows.some((r) => r.row_type === 'lookup'));
    for (const row of rows) assert.equal(row.run_id, 'run-evidence-1', `${row.row_type} row has the run id`);
    let out = '';
    const code = await runLibraryCli(['report', '--run', 'run-evidence-1', '--json'], { out: (t) => { out += t; }, err: () => undefined });
    assert.equal(code, 0);
    const report = JSON.parse(out) as { rows: { lookup: number; shadow: number } };
    assert.ok(report.rows.lookup >= 1, out);
    assert.ok(report.rows.shadow >= 1, out);
  } finally { __stubs({}); b.restore(); }
});

// ---------------------------------------------------------------- ids that reach a shell are validated where they enter

const HOSTILE_IDS = ["x'; printf INJECTED >&2; #", 'a;b', 'a$(touch /tmp/aw-pwned)b', 'a`id`b', 'has space'];

test('aw library list drops entries whose id is not plain (Trove and PageIndex) and says so', async () => {
  const items = [{ id: 'good-1', title: 'Good', author: 'A', pageCount: 3 }, ...HOSTILE_IDS.map((id) => ({ id, title: 'Bad', author: 'B', pageCount: 1 }))];
  for (const route of ['trove', 'pageindex']) {
    const extra = Object.fromEntries(HOSTILE_IDS.map((id) => [id, { title: 'Bad', author: 'B', n_pages: 1, toc_source: 'x', top: [] }]));
    const b = bench({ route }, { FAKE_LIST_JSON: JSON.stringify(items), FAKE_PI_EXTRA: JSON.stringify(extra) });
    try {
      const library = new Library(b.project, process.env, { shadow: 'off' });
      const listed = await library.list();
      const ids = listed.items.map((item) => item.id);
      assert.ok(ids.length >= 1 && ids.every((id) => /^[A-Za-z0-9_.#:-]+$/u.test(id)), `${route}: ${ids.join(' | ')}`);
      assert.equal(listed.skipped_invalid_ids, HOSTILE_IDS.length, route);
      let out = '';
      let err = '';
      setPathArguments(['--data-dir', join(b.root, 'd'), '--project-dir', b.project]);
      assert.equal(await runLibraryCli(['list'], { out: (t) => { out += t; }, err: (t) => { err += t; } }), 0);
      assert.ok(!out.includes('INJECTED') && !out.includes('$('), `${route}: hostile id reached the output`);
      assert.match(err, /skipped/u);
    } finally { b.restore(); }
  }
});

test('evidence build refuses a source id that is not plain, before any command runs and before evidence.json', async () => {
  for (const id of HOSTILE_IDS) {
    const b = bench();
    __stubs(noPassages);
    try {
      await assert.rejects(buildEvidence({ sources: ['good-ok', id], runId: 'r' }), /not a plain id/u);
      assert.deepEqual(loggedCalls(b), [], 'no command ran');
      assert.equal(existsSync(join(b.project, '.academic-helper', 'evidence.json')), false);
    } finally { __stubs({}); b.restore(); }
  }
});
