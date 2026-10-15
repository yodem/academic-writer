import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, utimesSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import retrievalSchema from '../../schemas/retrieval-row.schema.json' with { type: 'json' };
import thresholds from '../../thresholds.json' with { type: 'json' };
import { Library } from '../src/library/adapter.ts';
import { runLibraryCli } from '../src/library/cli.ts';
import { checkSchema, type JsonSchema } from '../src/library/jsonschema.ts';
import { appendRow, clipError, readRows, spoolDir, writeSpool, type LookupRow, type RetrievalRow, type ShadowRow, type VerdictRow } from '../src/library/ledger.ts';
import { acquireSlot } from '../src/library/shadow.ts';
import { settlePending, recordVerdict, computeSupports } from '../src/library/verdict.ts';
import { buildReport } from '../src/library/report.ts';
import { setPathArguments } from '../src/paths.ts';
import { coverage, jaccard, normalizeText } from '../src/library/textmatch.ts';

const limits = thresholds.library;

// Fake `trove` and `pilib`: tiny node scripts. Page text is the same on both routes unless FAKE_PI_TEXT=other,
// so agreement and support can be tested both ways. FAKE_*_FAIL / FAKE_*_HANG break one route.
const SHARED_TEXT = `const text = (n) => 'the shared sentence number ' + n + ' about the long argument of this page';`;
const TROVE_FAKE = `
const fs = require('node:fs');
const args = process.argv.slice(2);
if (process.env.FAKE_LOG) fs.appendFileSync(process.env.FAKE_LOG, 'trove ' + args.join(' ') + '\\n');
if (process.env.FAKE_TROVE_FAIL) { console.error(process.env.FAKE_TROVE_FAIL_MSG || 'trove: boom'); process.exit(1); }
if (process.env.FAKE_TROVE_HANG || (process.env.FAKE_TROVE_HANG_SHELF && args[0] === 'shelf')) setTimeout(() => {}, 60000);
else {
  const PAGES = 5;
  ${SHARED_TEXT}
  const page = (n) => '── Page ' + n + ' ──\\n' + text(n) + '\\n';
  if (args[0] === 'shelf') console.log('No active shelf in /tmp/project');
  else if (args[0] === 'items' && args[1] === 'list') console.log(JSON.stringify({ items: [{ id: 'T-A', title: 'Book A', author: 'Au', pageCount: PAGES }] }));
  else if (args[0] === 'items' && args[1] === 'toc' && args.includes('--json')) console.log(JSON.stringify({ items: [{ id: args[2], title: 'Book A', toc: [{ title: 'Intro', page: 1, level: 1 }] }] }));
  else if (args[0] === 'items' && args[1] === 'toc') console.log('Book A\\nID: ' + args[2]);
  else if (args[0] === 'items' && args[1] === 'read') {
    const spec = args.includes('--pages') ? args[args.indexOf('--pages') + 1] : args[2].split(':')[1];
    const ids = spec === 'all' ? Array.from({ length: PAGES }, (_, i) => i + 1) : spec.split(',').flatMap((p) => { const [a, b] = p.split('-').map(Number); return Array.from({ length: (b || a) - a + 1 }, (_, i) => a + i); }).filter((n) => n <= PAGES);
    process.stdout.write('Book A\\n' + args[2].split(':')[0] + ' | ' + PAGES + ' pages\\n' + ids.map(page).join(''));
  } else { console.error('unexpected: ' + args.join(' ')); process.exit(2); }
}
`;
const PILIB_FAKE = `
const fs = require('node:fs');
const args = process.argv.slice(2);
if (process.env.FAKE_LOG) fs.appendFileSync(process.env.FAKE_LOG, 'pilib ' + args.join(' ') + '\\n');
if (process.env.FAKE_PILIB_FAIL) { console.error('pilib: boom'); process.exit(1); }
if (process.env.FAKE_PILIB_HANG) setTimeout(() => {}, 60000);
else {
  const books = { 'lib-a': { title: 'Library A', n_pages: 5, trove_id: 'T-A', pagemap: null } };
  ${SHARED_TEXT}
  const out = (n) => process.env.FAKE_PI_TEXT === 'other' ? 'entirely different words appear here ' + n : text(n);
  const range = (spec, max) => spec === 'all' ? Array.from({ length: max }, (_, i) => i + 1) : spec.split(',').flatMap((p) => { const [a, b] = p.split('-').map(Number); return Array.from({ length: (b || a) - a + 1 }, (_, i) => a + i); }).filter((n) => n <= max);
  const [cmd, book, spec] = args;
  if (cmd === 'catalog') console.log(JSON.stringify({ 'lib-a': { title: 'Library A', author: 'Au', n_pages: 5, toc_source: 'x', top: [] } }));
  else if (cmd === 'meta') console.log(JSON.stringify({ book_id: book, title: 'Library A', n_pages: 5, origin: {}, trove_id: 'T-A', pagemap: null }));
  else if (cmd === 'tree') console.log(JSON.stringify({ book_id: book, title: 'Library A', n_pages: 5, structure: [{ node_id: '1', title: 'Top', start_index: 1, end_index: 4 }] }));
  else if (cmd === 'read') {
    const pages = range(spec, books[book].n_pages);
    console.log(JSON.stringify({ book_id: book, pages: pages.map((n) => ({ page: n, content: out(n) })) }));
  } else { console.error('unexpected: ' + args.join(' ')); process.exit(2); }
}
`;

type Fixture = { root: string; project: string; env: NodeJS.ProcessEnv; log: string; cleanup: () => void };

function writeFake(dir: string, name: string, body: string): string {
  const file = join(dir, name);
  writeFileSync(file, `#!${process.execPath}\n${body}`, 'utf8');
  chmodSync(file, 0o755);
  return file;
}

const FAKE_KEYS = ['FAKE_TROVE_FAIL_MSG', 'FAKE_TROVE_HANG_SHELF', 'AW_LIBRARY_WORKER_ENTRY', 'FAKE_TROVE_FAIL', 'FAKE_TROVE_HANG', 'FAKE_PILIB_FAIL', 'FAKE_PILIB_HANG', 'FAKE_PI_TEXT', 'AW_LIBRARY_SHADOW', 'AW_LIBRARY_SHADOW_TIMEOUT_MS', 'AW_LIBRARY_TIMEOUT_MS'];

function fixture(config?: unknown, extra: Record<string, string> = {}): Fixture {
  const root = mkdtempSync(join(tmpdir(), 'aw-shadow-'));
  const project = join(root, 'project');
  mkdirSync(join(project, '.academic-helper'), { recursive: true });
  const bin = join(root, 'bin');
  mkdirSync(bin);
  const log = join(root, 'calls.log');
  const env: NodeJS.ProcessEnv = { ...process.env, AW_TROVE_COMMAND: writeFake(bin, 'trove', TROVE_FAKE), AW_PAGEINDEX_COMMAND: writeFake(bin, 'pilib', PILIB_FAKE), FAKE_LOG: log, ...extra };
  for (const key of FAKE_KEYS) if (!(key in extra)) delete env[key];
  if (config !== undefined) writeFileSync(join(project, '.academic-helper', 'library.json'), JSON.stringify(config), 'utf8');
  return { root, project, env, log, cleanup: () => rmSync(root, { recursive: true, force: true }) };
}

function sleep(ms: number): Promise<void> { return new Promise((done) => { setTimeout(done, ms); }); }

async function rowsOf(fx: Fixture): Promise<RetrievalRow[]> { return (await readRows(fx.project)).rows; }
function ofType<T extends RetrievalRow['row_type']>(rows: RetrievalRow[], type: T): Array<Extract<RetrievalRow, { row_type: T }>> {
  return rows.filter((row): row is Extract<RetrievalRow, { row_type: T }> => row.row_type === type);
}

async function until<T>(what: string, probe: () => Promise<T | undefined>, timeoutMs = 15000): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const found = await probe();
    if (found !== undefined) return found;
    if (Date.now() > deadline) assert.fail(`timed out waiting for ${what}`);
    await sleep(50);
  }
}

function rawLedger(fx: Fixture): string[] {
  const file = join(fx.project, '.academic-helper', 'retrieval.jsonl');
  return existsSync(file) ? readFileSync(file, 'utf8').split('\n').filter(Boolean) : [];
}

/** Every line in the ledger must satisfy the shipped schema. */
function assertAllRowsValid(fx: Fixture): void {
  for (const line of rawLedger(fx)) assert.deepEqual(checkSchema(retrievalSchema as JsonSchema, JSON.parse(line)), [], line);
}

const WORDS = 'the shared sentence number 2 about the long argument of this page';

// ---------------------------------------------------------------- rows and schema

test('the schema accepts well formed rows of each type and refuses the rest', () => {
  const lookup: LookupRow = {
    row_type: 'lookup', schema: 1, ts: new Date().toISOString(), lookup_id: 'lk_1', run_id: null, claim_id: 'P1', op: 'read', source_id: 'T-A', mode: 'both', route_primary: 'trove',
    book_by_route: { trove: 'T-A', pageindex: null }, request: { printed: '3', trove_pages: '4' },
    primary: { route: 'trove', ok: true, route_pages: '4', latency_ms: 12, bytes: 40, chars: 40, text_sha: '0123456789abcdef', error: null, error_code: null }, shadow_status: 'pending',
  };
  const verdict: VerdictRow = { row_type: 'verdict', schema: 1, seq: 1, ts: lookup.ts, lookup_id: 'lk_1', run_id: null, paragraph_id: 'P1', verdict: 'PASS', corrected_page: null, shadow_supports: null, shadow_supports_reason: 'no_quote', primary_route: 'trove', mode: 'both' };
  assert.deepEqual(checkSchema(retrievalSchema as JsonSchema, lookup), []);
  assert.deepEqual(checkSchema(retrievalSchema as JsonSchema, verdict), []);
  const broken: unknown[] = [
    { ...lookup, extra: 1 },
    { ...lookup, op: 'write' },
    { ...lookup, shadow_status: 'skipped:Bad Reason' },
    { ...lookup, primary: { ...lookup.primary, latency_ms: -1 } },
    { ...verdict, verdict: 'PARTIAL' },
    { ...verdict, seq: 0 },
    { ...verdict, shadow_supports_reason: 'maybe' },
    { ...verdict, corrected_page: 0 },
    { row_type: 'other' },
    'text',
  ];
  for (const row of broken) assert.notDeepEqual(checkSchema(retrievalSchema as JsonSchema, row), [], JSON.stringify(row));
  const { run_id: _gone, ...missing } = lookup;
  assert.match(checkSchema(retrievalSchema as JsonSchema, missing).join(' '), /run_id: missing/);
});

test('appendRow checks the schema and never makes the project folder', async () => {
  const fx = fixture();
  try {
    const bad = { row_type: 'verdict' } as unknown as RetrievalRow;
    assert.equal((await appendRow(fx.project, bad)).ok, false);
    const noFolder = join(fx.root, 'elsewhere');
    mkdirSync(noFolder);
    const row: VerdictRow = { row_type: 'verdict', schema: 1, seq: 1, ts: new Date().toISOString(), lookup_id: 'lk_x', run_id: null, paragraph_id: null, verdict: 'FAIL', corrected_page: 9, shadow_supports: false, shadow_supports_reason: 'not_covered', primary_route: null, mode: null };
    assert.equal((await appendRow(noFolder, row)).ok, false);
    assert.equal(existsSync(join(noFolder, '.academic-helper')), false);
    assert.equal((await appendRow(fx.project, row)).ok, true);
    assert.equal((await readRows(fx.project)).rows.length, 1);
  } finally { fx.cleanup(); }
});

// ---------------------------------------------------------------- text matching

test('word comparison ignores niqqud, punctuation, quotes and spacing', () => {
  assert.equal(normalizeText('בְּרֵאשִׁ֖ית בָּרָ֣א, "אֱלֹהִ֑ים"  —  וגו׳'), 'בראשית ברא אלהים וגו');
  assert.equal(normalizeText('Hello,‏  WORLD!'), 'hello world');
  assert.equal(jaccard('a b c', 'c b a'), 1);
  assert.equal(jaccard('a b', 'c d'), 0);
  assert.equal(jaccard('', ''), 1);
  assert.equal(coverage('the long argument', WORDS), 1);
  assert.equal(coverage('', WORDS), 0);
  assert.ok(coverage('the long unrelated claim here', WORDS) < 0.8);
});

// ---------------------------------------------------------------- ledger rows (in-process, inline shadow)

test('route trove writes a lookup row and no shadow row, with or without library.json', async () => {
  for (const config of [undefined, { route: 'trove' }]) {
    const fx = fixture(config);
    try {
      const output = await new Library(fx.project, fx.env, { shadow: 'inline' }).read({ source: 'T-A', pages: '2', run: 'R1', claim: 'P1' });
      assert.equal(output.shadow_status, 'none');
      const rows = await rowsOf(fx);
      assert.deepEqual(rows.map((row) => row.row_type), ['lookup']);
      const lookup = rows[0] as LookupRow;
      assert.deepEqual([lookup.lookup_id, lookup.run_id, lookup.claim_id, lookup.op, lookup.mode, lookup.route_primary, lookup.shadow_status], [output.lookup_id, 'R1', 'P1', 'read', 'trove', 'trove', 'none']);
      assert.deepEqual([lookup.primary.ok, lookup.primary.route_pages, lookup.request.trove_pages, lookup.book_by_route.trove], [true, '2', '2', 'T-A']);
      assert.ok(lookup.primary.bytes > 0 && lookup.primary.chars > 0 && lookup.primary.text_sha?.length === 16);
      assert.ok(!readFileSync(join(fx.project, '.academic-helper', 'retrieval.jsonl'), 'utf8').includes('sentence number'), 'no page text in the ledger');
      assert.ok(!existsSync(spoolDir(fx.project)), 'a single route spools nothing');
      assert.ok(!readFileSync(fx.log, 'utf8').includes('pilib'), 'PageIndex is never called');
      assertAllRowsValid(fx);
    } finally { fx.cleanup(); }
  }
});

test('both with an inline shadow: a lookup row, then a shadow row joined on lookup_id, with page agreement', async () => {
  const fx = fixture({ route: 'both' });
  try {
    const output = await new Library(fx.project, fx.env, { shadow: 'inline' }).read({ source: 'T-A', pages: '2-3', claim: 'P7' });
    assert.equal(output.shadow_status, 'pending');
    assert.deepEqual(output.pages.map((page) => page.trove_page), [2, 3]);
    const rows = await rowsOf(fx);
    const lookup = ofType(rows, 'lookup')[0] as LookupRow;
    const shadow = ofType(rows, 'shadow')[0] as ShadowRow;
    assert.equal(lookup.lookup_id, output.lookup_id);
    assert.equal(shadow.lookup_id, output.lookup_id);
    assert.deepEqual([shadow.route, shadow.ok, shadow.book, shadow.route_pages, shadow.timed_out, shadow.error], ['pageindex', true, 'lib-a', '2-3', false, null]);
    assert.deepEqual([shadow.agree?.compared, shadow.agree?.agreed, shadow.agree?.rate], [2, 2, 1]);
    assert.equal(shadow.text_sha, lookup.primary.text_sha, 'the same text on both routes hashes the same');
    assertAllRowsValid(fx);
    const names = readdirSync(spoolDir(fx.project));
    assert.deepEqual(names, [`${output.lookup_id}.shadow.json`], 'the shadow text is kept for verdicts; the primary spool is cleaned up');
  } finally { fx.cleanup(); }
});

test('different text on the two routes shows as disagreement', async () => {
  const fx = fixture({ route: 'both', primary: 'trove' }, { FAKE_PI_TEXT: 'other' });
  try {
    await new Library(fx.project, fx.env, { shadow: 'inline' }).read({ source: 'T-A', pages: '2' });
    const shadow = ofType(await rowsOf(fx), 'shadow')[0] as ShadowRow;
    assert.deepEqual([shadow.ok, shadow.agree?.agreed, shadow.agree?.rate], [true, 0, 0]);
    assert.ok((shadow.agree?.pages[0]?.jaccard ?? 1) < limits.agree.jaccardMin);
  } finally { fx.cleanup(); }
});

test('PageIndex answering, Trove as the shadow, works the same way', async () => {
  const fx = fixture({ route: 'both', primary: 'pageindex' });
  try {
    const output = await new Library(fx.project, fx.env, { shadow: 'inline' }).read({ source: 'T-A', pages: '1' });
    assert.equal(output.route, 'pageindex');
    const rows = await rowsOf(fx);
    assert.equal((ofType(rows, 'lookup')[0] as LookupRow).route_primary, 'pageindex');
    const shadow = ofType(rows, 'shadow')[0] as ShadowRow;
    assert.deepEqual([shadow.route, shadow.ok, shadow.agree?.rate], ['trove', true, 1]);
  } finally { fx.cleanup(); }
});

test('whole-book reads are shadowed only up to the page limit, and list/toc get lookup rows too', async () => {
  const fx = fixture({ route: 'both' });
  try {
    const library = new Library(fx.project, fx.env, { shadow: 'inline' });
    const all = await library.read({ source: 'T-A', all: true, op: 'get' });
    assert.equal(all.shadow_status, 'pending', 'five pages is under the limit');
    await library.list();
    await library.toc('T-A');
    const rows = await rowsOf(fx);
    assert.deepEqual(ofType(rows, 'lookup').map((row) => row.op), ['get', 'list', 'toc']);
    assert.equal(ofType(rows, 'shadow').length, 3);
    assert.equal((ofType(rows, 'shadow')[0] as ShadowRow).agree?.compared, 5);
    assertAllRowsValid(fx);
    assert.ok(limits.shadow.readAllMaxPages >= 5);
  } finally { fx.cleanup(); }
});

test('a failing primary still gets a lookup row, with the error and no fallback', async () => {
  const fx = fixture({ route: 'both' }, { FAKE_TROVE_FAIL: '1' });
  try {
    await assert.rejects(new Library(fx.project, fx.env, { shadow: 'inline' }).read({ source: 'T-A', pages: '2' }), /boom/);
    const rows = await rowsOf(fx);
    const lookup = ofType(rows, 'lookup')[0] as LookupRow;
    assert.deepEqual([lookup.primary.ok, lookup.primary.error_code, lookup.shadow_status], [false, 'exit', 'pending']);
    assert.match(lookup.primary.error ?? '', /boom/);
    const shadow = ofType(rows, 'shadow')[0] as ShadowRow;
    assert.equal(shadow.ok, true, 'the shadow still ran');
    assert.equal(shadow.agree, null, 'nothing to compare against');
    assertAllRowsValid(fx);
  } finally { fx.cleanup(); }
});

test('a failing shadow never changes the primary answer, only its own row', async () => {
  const healthy = fixture({ route: 'both' });
  const failing = fixture({ route: 'both' }, { FAKE_PILIB_FAIL: '1' });
  try {
    const a = await new Library(healthy.project, healthy.env, { shadow: 'inline' }).read({ source: 'T-A', pages: '2-3' });
    const b = await new Library(failing.project, failing.env, { shadow: 'inline' }).read({ source: 'T-A', pages: '2-3' });
    const strip = (output: typeof a): unknown => ({ ...output, lookup_id: 0, latency_ms: 0 });
    assert.deepEqual(strip(b), strip(a));
    const shadow = ofType(await rowsOf(failing), 'shadow')[0] as ShadowRow;
    assert.deepEqual([shadow.ok, shadow.error_code, shadow.timed_out, shadow.agree], [false, 'exit', false, null]);
    assert.match(shadow.error ?? '', /boom/);
    assertAllRowsValid(failing);
  } finally { healthy.cleanup(); failing.cleanup(); }
});

test('a hanging shadow is cut off at the shadow timeout and recorded as timed out', async () => {
  const fx = fixture({ route: 'both' }, { FAKE_PILIB_HANG: '1', AW_LIBRARY_SHADOW_TIMEOUT_MS: '600' });
  try {
    const output = await new Library(fx.project, fx.env, { shadow: 'inline' }).read({ source: 'T-A', pages: '2' });
    assert.equal(output.pages[0]?.trove_page, 2);
    const shadow = ofType(await rowsOf(fx), 'shadow')[0] as ShadowRow;
    assert.deepEqual([shadow.ok, shadow.timed_out, shadow.error_code], [false, true, 'timeout']);
    assertAllRowsValid(fx);
  } finally { fx.cleanup(); }
});

test('the shadow is skipped, with a reason, when it should not run', async () => {
  const off = fixture({ route: 'both', shadow: { enabled: false } });
  const tooMany = fixture({ route: 'both' });
  const busy = fixture({ route: 'both' });
  try {
    assert.equal((await new Library(off.project, off.env, { shadow: 'inline' }).read({ source: 'T-A', pages: '1' })).shadow_status, 'disabled');
    assert.equal((await new Library(off.project, off.env).read({ source: 'T-A', pages: '1' })).shadow_status, 'disabled', 'a library made without a shadow mode never starts one');
    const first = limits.shadow.readAllMaxPages + 1;
    const output = await new Library(tooMany.project, tooMany.env, { shadow: 'inline' }).read({ source: 'T-A', pages: `1-${first}` });
    assert.equal(output.shadow_status, 'skipped:too_many_pages');
    const lookup = ofType(await rowsOf(tooMany), 'lookup')[0] as LookupRow;
    assert.equal(lookup.shadow_status, 'skipped:too_many_pages');
    assert.equal(ofType(await rowsOf(tooMany), 'shadow').length, 0);
    // Detached mode with every slot taken: busy, and nothing is spawned.
    mkdirSync(join(busy.project, '.academic-helper', 'retrieval', 'active'), { recursive: true });
    for (let index = 0; index < limits.shadow.maxConcurrent; index += 1) writeFileSync(join(busy.project, '.academic-helper', 'retrieval', 'active', `slot-${index}.lock`), JSON.stringify({ pid: process.pid, ts: new Date().toISOString() }));
    const result = await new Library(busy.project, busy.env, { shadow: 'detached' }).read({ source: 'T-A', pages: '1' });
    assert.equal(result.shadow_status, 'skipped:busy');
    assert.equal((ofType(await rowsOf(busy), 'lookup')[0] as LookupRow).shadow_status, 'skipped:busy');
  } finally { off.cleanup(); tooMany.cleanup(); busy.cleanup(); }
});

// ---------------------------------------------------------------- verdicts

test('verdict: shadow_supports is computed in code from the quote against the shadow text', async () => {
  const fx = fixture({ route: 'both' });
  try {
    const output = await new Library(fx.project, fx.env, { shadow: 'inline' }).read({ source: 'T-A', pages: '2', run: 'R9', claim: 'P2' });
    const id = output.lookup_id;
    const supported = await recordVerdict(fx.project, { lookup: id, verdict: 'PASS', correctedPage: null, quote: 'The shared sentence, number 2 — about the long argument', paragraph: 'P2', run: null });
    assert.deepEqual([supported.row.shadow_supports, supported.row.shadow_supports_reason, supported.row.run_id, supported.row.primary_route, supported.row.mode], [true, 'covered', 'R9', 'trove', 'both']);
    const unsupported = await recordVerdict(fx.project, { lookup: id, verdict: 'FAIL', correctedPage: 7, quote: 'a claim that the page never makes at all anywhere', paragraph: 'P3', run: null });
    assert.deepEqual([unsupported.row.shadow_supports, unsupported.row.shadow_supports_reason, unsupported.row.corrected_page], [false, 'not_covered', 7]);
    const noQuote = await recordVerdict(fx.project, { lookup: id, verdict: 'FAIL', correctedPage: null, quote: '', paragraph: 'P4', run: null });
    assert.deepEqual([noQuote.row.shadow_supports, noQuote.row.shadow_supports_reason], [null, 'no_quote']);
    const short = await recordVerdict(fx.project, { lookup: id, verdict: 'PASS', correctedPage: null, quote: 'too short', paragraph: 'P5', run: null });
    assert.equal(short.row.shadow_supports_reason, 'no_quote');
    const unknown = await recordVerdict(fx.project, { lookup: 'lk_unknown', verdict: 'PASS', correctedPage: null, quote: WORDS, paragraph: null, run: null });
    assert.deepEqual([unknown.row.shadow_supports, unknown.row.shadow_supports_reason, unknown.row.primary_route], [null, 'shadow_missing', null]);
    assert.equal(ofType(await rowsOf(fx), 'verdict').length, 5);
    assertAllRowsValid(fx);
  } finally { fx.cleanup(); }
});

test('verdict: no shadow to test (single route, failed shadow) is shadow_missing, never false', async () => {
  const single = fixture({ route: 'trove' });
  const failing = fixture({ route: 'both' }, { FAKE_PILIB_FAIL: '1' });
  try {
    const a = await new Library(single.project, single.env, { shadow: 'inline' }).read({ source: 'T-A', pages: '2' });
    const one = await recordVerdict(single.project, { lookup: a.lookup_id, verdict: 'PASS', correctedPage: null, quote: WORDS, paragraph: 'P1', run: null });
    assert.deepEqual([one.row.shadow_supports, one.row.shadow_supports_reason], [null, 'shadow_missing']);
    const b = await new Library(failing.project, failing.env, { shadow: 'inline' }).read({ source: 'T-A', pages: '2' });
    const two = await recordVerdict(failing.project, { lookup: b.lookup_id, verdict: 'PASS', correctedPage: null, quote: WORDS, paragraph: 'P1', run: null });
    assert.deepEqual([two.row.shadow_supports, two.row.shadow_supports_reason], [null, 'shadow_missing']);
  } finally { single.cleanup(); failing.cleanup(); }
});

test('verdict while the shadow is still running is shadow_pending, and settles once its text lands', async () => {
  const fx = fixture({ route: 'both' });
  try {
    // A lookup whose worker has not reported: a lookup row says pending, and there is no shadow row or spool yet.
    const lookup: LookupRow = {
      row_type: 'lookup', schema: 1, ts: new Date().toISOString(), lookup_id: 'lk_slow', run_id: 'R1', claim_id: 'P1', op: 'read', source_id: 'T-A', mode: 'both', route_primary: 'trove',
      book_by_route: { trove: 'T-A', pageindex: null }, request: { printed: null, trove_pages: '2' },
      primary: { route: 'trove', ok: true, route_pages: '2', latency_ms: 5, bytes: 10, chars: 10, text_sha: '0123456789abcdef', error: null, error_code: null }, shadow_status: 'pending',
    };
    await appendRow(fx.project, lookup);
    assert.deepEqual(await computeSupports(fx.project, 'lk_slow', WORDS, 0), { supports: null, reason: 'shadow_pending' });
    const started = Date.now();
    const pending = await recordVerdict(fx.project, { lookup: 'lk_slow', verdict: 'PASS', correctedPage: null, quote: WORDS, paragraph: 'P1', run: null });
    assert.equal(pending.row.shadow_supports_reason, 'shadow_pending');
    assert.ok(Date.now() - started >= limits.timeoutMs.verdictSettle - 100, 'waits for the shadow, but only up to the settle limit');
    assert.deepEqual(await settlePending(fx.project), { settled: 0, waiting: 1 });
    mkdirSync(spoolDir(fx.project), { recursive: true });
    writeFileSync(join(spoolDir(fx.project), 'lk_slow.shadow.json'), JSON.stringify({ lookup_id: 'lk_slow', route: 'pageindex', ok: true, pages: [{ page: 2, text: WORDS }] }));
    assert.deepEqual(await settlePending(fx.project), { settled: 1, waiting: 0 });
    const verdicts = ofType(await rowsOf(fx), 'verdict');
    assert.deepEqual(verdicts.map((row) => [row.shadow_supports_reason, row.settled ?? false]), [['shadow_pending', false], ['covered', true]]);
    assert.deepEqual(await settlePending(fx.project), { settled: 0, waiting: 0 });
  } finally { fx.cleanup(); }
});

// ---------------------------------------------------------------- the aw library command

async function cli(fx: Fixture, ...argv: string[]): Promise<{ code: number; out: string; err: string }> {
  const saved = { ...process.env };
  let out = '';
  let err = '';
  Object.assign(process.env, fx.env, { AW_LIBRARY_SHADOW: 'inline' });
  setPathArguments(['--project-dir', fx.project]);
  try {
    const code = await runLibraryCli(argv, { out: (text) => { out += text; }, err: (text) => { err += text; } });
    return { code, out, err };
  } finally {
    for (const key of Object.keys(process.env)) if (!(key in saved)) delete process.env[key];
    Object.assign(process.env, saved);
  }
}

test('aw library verdict and report: arguments, ledger problems and the exit codes', async () => {
  const fx = fixture({ route: 'both' });
  try {
    const read = JSON.parse((await cli(fx, 'read', '--source', 'T-A', '--pages', '2', '--run', 'R1', '--claim', 'P1')).out) as { lookup_id: string };
    const ok = await cli(fx, 'verdict', '--lookup', read.lookup_id, '--verdict', 'pass', '--support-quote', 'the shared sentence number 2 about the long argument', '--paragraph', 'P1');
    assert.equal(ok.code, 0, ok.err);
    assert.deepEqual(JSON.parse(ok.out), { ok: true, lookup_id: read.lookup_id, verdict: 'PASS', shadow_supports: true, shadow_supports_reason: 'covered' });
    const fail = await cli(fx, 'verdict', '--lookup', read.lookup_id, '--verdict', 'FAIL', '--corrected-page', '3', '--support-quote', '', '--paragraph', 'P2');
    assert.equal(fail.code, 0);
    assert.equal((JSON.parse(fail.out) as { shadow_supports_reason: string }).shadow_supports_reason, 'no_quote');
    assert.equal((await cli(fx, 'verdict', '--verdict', 'PASS')).code, 2);
    assert.equal((await cli(fx, 'verdict', '--lookup', read.lookup_id, '--verdict', 'MAYBE')).code, 2);
    assert.equal((await cli(fx, 'verdict', '--lookup', read.lookup_id, '--verdict', 'FAIL', '--corrected-page', 'x')).code, 2);
    const rows = await rowsOf(fx);
    assert.equal(ofType(rows, 'verdict')[1]?.corrected_page, 3);
    const report = await cli(fx, 'report', '--json');
    assert.equal(report.code, 0);
    const json = JSON.parse(report.out) as { rows: { lookup: number; shadow: number; verdict: number }; routes: { trove: { lookups: number; auditor: { verdicts: number; pass: number } } } };
    assert.deepEqual([json.rows.lookup, json.rows.shadow, json.rows.verdict, json.routes.trove.lookups, json.routes.trove.auditor.verdicts, json.routes.trove.auditor.pass], [1, 1, 2, 1, 2, 1]);
    const text = await cli(fx, 'report');
    assert.match(text.out, /^Library report/u);
    assert.match(text.out, /Trove/u);
    assert.equal((await cli(fx, 'report', '--run', 'NOPE', '--json')).code, 0);
    // A project with no .academic-helper folder: the verdict is not recorded, and that is a note, not a failure.
    const bare = join(fx.root, 'bare');
    mkdirSync(bare);
    setPathArguments(['--project-dir', bare]);
    let err = '';
    const code = await runLibraryCli(['verdict', '--lookup', 'lk_1', '--verdict', 'PASS'], { out: () => undefined, err: (text) => { err += text; } });
    assert.equal(code, 0);
    assert.match(err, /not recorded/);
    assert.equal(existsSync(join(bare, '.academic-helper')), false);
  } finally { setPathArguments(['--project-dir', fx.project]); fx.cleanup(); }
});

// ---------------------------------------------------------------- the detached worker (a real process)

type Run = { code: number | null; out: string; ms: number };
function runAw(aw: string, fx: Fixture, ...argv: string[]): Promise<Run> {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const child = spawn(process.execPath, [aw, '--project-dir', fx.project, 'library', ...argv], { env: fx.env, stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '';
    child.stdout.on('data', (chunk: Buffer) => { out += chunk.toString('utf8'); });
    child.on('error', reject);
    child.on('close', (code) => { resolve({ code, out, ms: Date.now() - started }); });
  });
}

/** src/cli/src/main.ts, found by walking up from this file (the test bundle sits a few folders down in dist-test). */
function mainEntry(): string {
  let dir = dirname(fileURLToPath(import.meta.url));
  for (let step = 0; step < 6; step += 1, dir = dirname(dir)) if (existsSync(join(dir, 'src', 'main.ts'))) return join(dir, 'src', 'main.ts');
  throw new Error('cannot find src/main.ts');
}

async function buildAw(root: string): Promise<string> {
  const { build } = createRequire(import.meta.url)('esbuild') as typeof import('esbuild');
  const outfile = join(root, 'aw.mjs');
  await build({
    entryPoints: [mainEntry()], outfile, bundle: true, platform: 'node', target: 'node20', format: 'esm', loader: { '.md': 'text' }, logLevel: 'silent',
    banner: { js: "import { createRequire as __awCreateRequire } from 'node:module'; const require = __awCreateRequire(import.meta.url);" },
  });
  return outfile;
}

function normalized(run: Run): Record<string, unknown> {
  const parsed = JSON.parse(run.out) as Record<string, unknown>;
  return { ...parsed, lookup_id: 0, latency_ms: 0 };
}

test('detached shadow: a healthy, a failing and a hanging shadow leave the primary output, exit code and timing alone', async () => {
  const scratch = mkdtempSync(join(tmpdir(), 'aw-bundle-'));
  const hangMs = 4000;
  const healthy = fixture({ route: 'both' });
  const failing = fixture({ route: 'both' }, { FAKE_PILIB_FAIL: '1' });
  const hanging = fixture({ route: 'both' }, { FAKE_PILIB_HANG: '1', AW_LIBRARY_SHADOW_TIMEOUT_MS: String(hangMs) });
  const off = fixture({ route: 'both' }, { AW_LIBRARY_SHADOW: 'off' });
  try {
    const aw = await buildAw(scratch);
    const args = ['read', '--source', 'T-A', '--pages', '2-3', '--run', 'R1', '--claim', 'P1'];
    const base = await runAw(aw, healthy, ...args);
    const bad = await runAw(aw, failing, ...args);
    const slow = await runAw(aw, hanging, ...args);
    const quiet = await runAw(aw, off, ...args);
    for (const run of [base, bad, slow, quiet]) assert.equal(run.code, 0);
    assert.deepEqual(normalized(bad), normalized(base));
    assert.deepEqual(normalized(slow), normalized(base));
    assert.deepEqual({ ...normalized(quiet), shadow_status: 'pending' }, normalized(base), 'only the shadow status differs when the shadow is off');
    assert.equal((normalized(base) as { shadow_status: string }).shadow_status, 'pending');
    assert.ok(slow.ms < hangMs - 1000, `the answer came back in ${slow.ms} ms while the shadow hung for ${hangMs} ms`);

    // The workers land on their own: healthy agrees, failing reports its error, hanging is cut off.
    const shadowOf = async (fx: Fixture): Promise<ShadowRow> => until('a shadow row', async () => ofType(await rowsOf(fx), 'shadow')[0]);
    const good = await shadowOf(healthy);
    assert.deepEqual([good.ok, good.agree?.rate, good.route], [true, 1, 'pageindex']);
    const broke = await shadowOf(failing);
    assert.deepEqual([broke.ok, broke.error_code], [false, 'exit']);
    const stuck = await shadowOf(hanging);
    assert.deepEqual([stuck.ok, stuck.timed_out], [false, true]);
    assert.ok(stuck.latency_ms >= hangMs - 200 && stuck.latency_ms < hangMs + 5000);
    assert.equal(ofType(await rowsOf(off), 'shadow').length, 0);
    for (const fx of [healthy, failing, hanging]) {
      const lookups = ofType(await rowsOf(fx), 'lookup');
      assert.deepEqual([lookups.length, lookups[0]?.shadow_status, lookups[0]?.run_id, lookups[0]?.claim_id], [1, 'pending', 'R1', 'P1']);
      assert.equal(ofType(await rowsOf(fx), 'shadow')[0]?.lookup_id, lookups[0]?.lookup_id, 'joined on lookup_id');
      assertAllRowsValid(fx);
      await until('the worker slot to be released', async () => (existsSync(join(fx.project, '.academic-helper', 'retrieval', 'active')) && readdirSync(join(fx.project, '.academic-helper', 'retrieval', 'active')).length === 0 ? true : undefined));
      assert.ok(!readdirSync(join(fx.project, '.academic-helper', 'retrieval')).some((name) => name.startsWith('spec-')), 'the spec file is removed');
    }
    // The verdict from a separate process finds the spooled shadow text.
    const lookupId = (ofType(await rowsOf(healthy), 'lookup')[0] as LookupRow).lookup_id;
    const verdict = await runAw(aw, healthy, 'verdict', '--lookup', lookupId, '--verdict', 'PASS', '--support-quote', 'shared sentence number 2 about the long argument', '--paragraph', 'P1');
    assert.equal(verdict.code, 0);
    assert.equal((JSON.parse(verdict.out) as { shadow_supports: boolean }).shadow_supports, true);
    const report = JSON.parse((await runAw(aw, healthy, 'report', '--json')).out) as { routes: { trove: { lookups: number; agreement: { rate: number } }; pageindex: { shadow_runs: number } } };
    assert.deepEqual([report.routes.trove.lookups, report.routes.trove.agreement.rate, report.routes.pageindex.shadow_runs], [1, 1, 1]);
  } finally {
    // Let any worker still running finish before its folder goes away.
    await sleep(300);
    for (const fx of [healthy, failing, hanging, off]) fx.cleanup();
    rmSync(scratch, { recursive: true, force: true });
  }
});

test('detached shadow: a primary that fails exits 4 as before, and the worker records its own row', async () => {
  const scratch = mkdtempSync(join(tmpdir(), 'aw-bundle-'));
  const fx = fixture({ route: 'both' }, { FAKE_TROVE_FAIL: '1' });
  try {
    const aw = await buildAw(scratch);
    const run = await runAw(aw, fx, 'read', '--source', 'T-A', '--pages', '2');
    assert.equal(run.code, 4);
    const lookup = ofType(await rowsOf(fx), 'lookup')[0] as LookupRow;
    assert.deepEqual([lookup.primary.ok, lookup.primary.error_code], [false, 'exit']);
    const shadow = await until('a shadow row', async () => ofType(await rowsOf(fx), 'shadow')[0]);
    assert.deepEqual([shadow.ok, shadow.agree], [true, null]);
  } finally {
    await sleep(300);
    fx.cleanup();
    rmSync(scratch, { recursive: true, force: true });
  }
});

// ================================================================ review rework (T2 review findings)

let sharedAw: Promise<{ aw: string; dir: string }> | undefined;
/** One bundled `aw` for the tests that need a real worker process. */
function sharedBundle(): Promise<{ aw: string; dir: string }> {
  sharedAw ??= (async () => { const dir = mkdtempSync(join(tmpdir(), 'aw-bundle-')); return { aw: await buildAw(dir), dir }; })();
  return sharedAw;
}
test.after(async () => { if (sharedAw) rmSync((await sharedAw).dir, { recursive: true, force: true }); });

function lineCount(fx: Fixture): number { return rawLedger(fx).length; }

// HIGH 1: a timed-out shadow stops all further work
test('H1: a timed-out shadow spawns no further command and writes nothing after its timeout row', async () => {
  const fx = fixture({ route: 'both', primary: 'pageindex' }, { FAKE_TROVE_HANG_SHELF: '1', AW_LIBRARY_SHADOW_TIMEOUT_MS: '500' });
  try {
    await new Library(fx.project, fx.env, { shadow: 'inline' }).list();
    const rows = await rowsOf(fx);
    const shadow = ofType(rows, 'shadow')[0] as ShadowRow;
    assert.deepEqual([shadow.ok, shadow.timed_out, shadow.error_code], [false, true, 'timeout']);
    const before = lineCount(fx);
    const calls = readFileSync(fx.log, 'utf8').split('\n').filter(Boolean).length;
    await sleep(1500);
    const log = readFileSync(fx.log, 'utf8');
    assert.ok(!log.includes('items list'), `a command was started after the timeout:\n${log}`);
    assert.equal(log.split('\n').filter(Boolean).length, calls);
    assert.equal(lineCount(fx), before, 'nothing is written after the timeout row');
    assert.equal(ofType(await rowsOf(fx), 'shadow').length, 1);
  } finally { fx.cleanup(); }
});

// HIGH 2: atomic worker slots
test('H2: parallel lookups never start more workers than shadow.maxConcurrent', async () => {
  const { aw } = await sharedBundle();
  const fx = fixture({ route: 'both' }, { FAKE_PILIB_HANG: '1', AW_LIBRARY_SHADOW_TIMEOUT_MS: '2500', AW_LIBRARY_WORKER_ENTRY: aw });
  try {
    const library = new Library(fx.project, fx.env, { shadow: 'detached' });
    const results = await Promise.all(Array.from({ length: 8 }, () => library.read({ source: 'T-A', pages: '2' })));
    const started = results.filter((result) => result.shadow_status === 'pending').length;
    assert.ok(started <= limits.shadow.maxConcurrent, `${started} workers started, the limit is ${limits.shadow.maxConcurrent}`);
    assert.ok(started >= 1);
    assert.equal(results.filter((result) => result.shadow_status === 'skipped:busy').length, 8 - started);
    const active = join(fx.project, '.academic-helper', 'retrieval', 'active');
    await until('the worker slots to be released', async () => (!existsSync(active) || readdirSync(active).length === 0 ? true : undefined), 20000);
    assert.equal(ofType(await rowsOf(fx), 'shadow').length, started);
  } finally { await sleep(300); fx.cleanup(); }
});

test('H2: a slot held by a dead process is taken over, a live one is not', async () => {
  const fx = fixture({ route: 'both' }, { AW_LIBRARY_SHADOW: 'detached' });
  try {
    const active = join(fx.project, '.academic-helper', 'retrieval', 'active');
    mkdirSync(active, { recursive: true });
    const old = new Date(Date.now() - limits.shadow.reapGraceMs * 5);
    for (let slot = 0; slot < limits.shadow.maxConcurrent; slot += 1) {
      const file = join(active, `slot-${slot}.lock`);
      writeFileSync(file, JSON.stringify({ pid: slot === 0 ? process.pid : 2 ** 22 + 7, ts: old.toISOString() }));
      utimesSync(file, old, old);
    }
    const first = await acquireSlot(fx.project);
    assert.ok(first !== null, 'a dead holder frees its slot');
    assert.notEqual(first, 0, 'the slot held by this live process stays taken');
    const second = await acquireSlot(fx.project);
    assert.ok(second !== null && second !== first);
    assert.equal(await acquireSlot(fx.project), null, 'all three slots are taken now');
  } finally { fx.cleanup(); }
});

// HIGH 3: _shadow only deletes spec files it validated in its own folder
test('H3: aw library _shadow never deletes a file it was merely pointed at', async () => {
  const fx = fixture({ route: 'both' });
  try {
    const victim = join(fx.root, 'victim.json');
    writeFileSync(victim, '{"keep":true}');
    assert.equal((await cli(fx, '_shadow', victim)).code, 0);
    assert.ok(existsSync(victim), 'an unrelated file survives');
    const notJson = join(fx.root, 'notes.txt');
    writeFileSync(notJson, 'hello');
    await cli(fx, '_shadow', notJson);
    assert.ok(existsSync(notJson));
    // A well formed spec that sits outside the project's retrieval folder is refused and kept.
    const spec = { v: 1, lookup_id: 'lk_outside', run_id: null, claim_id: null, op: 'list', route: 'pageindex', project: fx.project, source: null, pages: null, slot: null };
    const outside = join(fx.root, 'spec-lk_outside.json');
    writeFileSync(outside, JSON.stringify(spec));
    await cli(fx, '_shadow', outside);
    assert.ok(existsSync(outside));
    assert.equal(ofType(await rowsOf(fx), 'shadow').length, 0, 'and no lookup was made for it');
    // The same spec inside the retrieval folder, under its own name, is run and removed.
    const dir = join(fx.project, '.academic-helper', 'retrieval');
    mkdirSync(dir, { recursive: true });
    const inside = join(dir, 'spec-lk_outside.json');
    writeFileSync(inside, JSON.stringify(spec));
    await cli(fx, '_shadow', inside);
    assert.ok(!existsSync(inside));
    assert.equal(ofType(await rowsOf(fx), 'shadow').length, 1);
    // A valid spec in that folder under a name that is not its own is kept.
    const odd = join(dir, 'other.json');
    writeFileSync(odd, JSON.stringify(spec));
    await cli(fx, '_shadow', odd);
    assert.ok(existsSync(odd));
  } finally { fx.cleanup(); }
});

// HIGH 4: containment after resolving symlinks
test('H4: the ledger and the spool never follow a symlink out of the project', async () => {
  const row: VerdictRow = { row_type: 'verdict', schema: 1, seq: 1, ts: new Date().toISOString(), lookup_id: 'lk_x', run_id: null, paragraph_id: null, verdict: 'PASS', corrected_page: null, shadow_supports: null, shadow_supports_reason: 'no_quote', primary_route: null, mode: null };
  const linkedFolder = fixture();
  const linkedFile = fixture();
  const linkedSpool = fixture();
  try {
    // .academic-helper is a symlink to a folder outside the project.
    const elsewhere = join(linkedFolder.root, 'elsewhere');
    mkdirSync(elsewhere);
    rmSync(join(linkedFolder.project, '.academic-helper'), { recursive: true });
    symlinkSync(elsewhere, join(linkedFolder.project, '.academic-helper'));
    assert.equal((await appendRow(linkedFolder.project, row)).ok, false);
    assert.deepEqual(readdirSync(elsewhere), [], 'nothing written outside');
    assert.equal(await writeSpool(linkedFolder.project, join(spoolDir(linkedFolder.project), 'x.json'), { a: 1 }), false);
    assert.deepEqual(readdirSync(elsewhere), []);
    // retrieval.jsonl is a symlink to a file outside the project.
    const target = join(linkedFile.root, 'target.txt');
    writeFileSync(target, 'precious\n');
    symlinkSync(target, join(linkedFile.project, '.academic-helper', 'retrieval.jsonl'));
    assert.equal((await appendRow(linkedFile.project, row)).ok, false);
    assert.equal(readFileSync(target, 'utf8'), 'precious\n');
    // The spool folder is a symlink to a folder outside the project.
    const outsideSpool = join(linkedSpool.root, 'outside-spool');
    mkdirSync(outsideSpool);
    mkdirSync(join(linkedSpool.project, '.academic-helper', 'retrieval'), { recursive: true });
    symlinkSync(outsideSpool, join(linkedSpool.project, '.academic-helper', 'retrieval', 'spool'));
    assert.equal(await writeSpool(linkedSpool.project, join(spoolDir(linkedSpool.project), 'x.json'), { a: 1 }), false);
    assert.deepEqual(readdirSync(outsideSpool), []);
    // A project that is itself reached through a symlink still works.
    const real = fixture();
    const alias = join(real.root, 'alias');
    symlinkSync(real.project, alias);
    assert.equal((await appendRow(alias, row)).ok, true);
    assert.equal(rawLedger(real).length, 1);
    real.cleanup();
  } finally { linkedFolder.cleanup(); linkedFile.cleanup(); linkedSpool.cleanup(); }
});

// HIGH 5: verdicts are versioned per citation
test('H5: a newer verdict is never replaced by settling an older pending one', async () => {
  const fx = fixture({ route: 'both' });
  try {
    const lookup: LookupRow = {
      row_type: 'lookup', schema: 1, ts: new Date().toISOString(), lookup_id: 'lk_seq', run_id: 'R1', claim_id: 'P1', op: 'read', source_id: 'T-A', mode: 'both', route_primary: 'trove',
      book_by_route: { trove: 'T-A', pageindex: null }, request: { printed: null, trove_pages: '2' },
      primary: { route: 'trove', ok: true, route_pages: '2', latency_ms: 5, bytes: 10, chars: 10, text_sha: '0123456789abcdef', error: null, error_code: null }, shadow_status: 'pending',
    };
    await appendRow(fx.project, lookup);
    const first = await recordVerdict(fx.project, { lookup: 'lk_seq', verdict: 'PASS', correctedPage: null, quote: WORDS, paragraph: 'P1', run: null }, 0);
    assert.equal(first.row.shadow_supports_reason, 'shadow_pending');
    const second = await recordVerdict(fx.project, { lookup: 'lk_seq', verdict: 'FAIL', correctedPage: 4, quote: '', paragraph: 'P1', run: null }, 0);
    assert.equal(second.row.verdict, 'FAIL');
    assert.ok(second.row.seq > first.row.seq, 'later verdicts get a higher sequence number');
    mkdirSync(spoolDir(fx.project), { recursive: true });
    writeFileSync(join(spoolDir(fx.project), 'lk_seq.shadow.json'), JSON.stringify({ lookup_id: 'lk_seq', route: 'pageindex', ok: true, pages: [{ page: 2, text: WORDS }] }));
    await settlePending(fx.project);
    const { rows } = await readRows(fx.project);
    const report = buildReport(rows, 0);
    assert.deepEqual([report.routes.trove.auditor.pass, report.routes.trove.auditor.fail], [0, 1], 'the newest verdict (FAIL) stands');
    assert.equal(ofType(rows, 'verdict').filter((row) => row.verdict === 'PASS' && row.settled).length, 0, 'the stale PASS is not settled');
    // A pending verdict that nothing replaced still settles, and settles once.
    const lone = await recordVerdict(fx.project, { lookup: 'lk_seq', verdict: 'PASS', correctedPage: null, quote: WORDS, paragraph: 'P9', run: null }, 0);
    assert.equal(lone.row.shadow_supports_reason, 'covered', 'the spool is there now');
    // Even with rows in the ledger in the "wrong" order, the highest seq wins.
    const swapped = [...(await readRows(fx.project)).rows].reverse();
    assert.deepEqual([buildReport(swapped, 0).routes.trove.auditor.pass, buildReport(swapped, 0).routes.trove.auditor.fail], [1, 1]);
  } finally { fx.cleanup(); }
});

// MEDIUM 6: redaction
test('M6: secrets in backend messages are redacted before they reach the ledger', async () => {
  const samples: Array<[string, RegExp]> = [
    ['Authorization: Bearer abcDEF123456.tokenvalue-xyz', /abcDEF123456/],
    ['request to https://user:hunter2pass@example.org/path failed', /hunter2pass/],
    ['TROVE_API_KEY=sk-live-1234567890abcdef rejected', /1234567890abcdef/],
    ['export GOOGLE_API_KEY="AIzaSyA-abcdefghijklmnopqrstuvwxyz012345"', /AIzaSyA-abcdefghijklmnopqrstuvwxyz012345/],
    ['run with --token abcd1234efgh5678 and --api-key=zzyyxx998877', /abcd1234efgh5678|zzyyxx998877/],
    ['password: correct-horse-battery', /correct-horse/],
    ['bad key 0123456789abcdef0123456789abcdef01234567', /0123456789abcdef0123456789abcdef01234567/],
    ['jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r', /eyJhbGciOiJIUzI1NiJ9/],
    ['aws AKIAIOSFODNN7EXAMPLE and ghp_abcdefghijklmnopqrstuvwxyz0123456789', /AKIAIOSFODNN7EXAMPLE|ghp_abcdefghij/],
    ['blob c2VjcmV0LXZhbHVlLXRoYXQtaXMtbG9uZy1lbm91Z2gtdG8tbG9vay1saWtlLWEta2V5Cg==', /c2VjcmV0LXZhbHVl/],
  ];
  for (const [text, secret] of samples) {
    const clean = clipError(text);
    assert.doesNotMatch(clean, secret, `${text} -> ${clean}`);
    assert.match(clean, /redacted/u);
  }
  assert.equal(clipError('trove: items read failed on page 12 of /path/to/book'), 'trove: items read failed on page 12 of /path/to/book', 'ordinary messages are untouched');
  assert.ok(clipError(`x ${'word '.repeat(200)}`).length <= limits.ledger.maxErrorChars);
  // End to end: a failing backend that echoes a credential.
  const fx = fixture({ route: 'both' }, { FAKE_TROVE_FAIL: '1', FAKE_TROVE_FAIL_MSG: 'denied: Authorization: Bearer SECRETSECRET123456 for TROVE_TOKEN=tok_abcdef123456' });
  try {
    await assert.rejects(new Library(fx.project, fx.env, { shadow: 'inline' }).read({ source: 'T-A', pages: '2' }));
    const text = rawLedger(fx).join('\n');
    assert.doesNotMatch(text, /SECRETSECRET123456|tok_abcdef123456/);
    assert.match(text, /denied/);
  } finally { fx.cleanup(); }
});

// MEDIUM 7: support is judged page by page
test('M7: quote words scattered over unrelated pages do not count as support', async () => {
  const fx = fixture({ route: 'both' });
  try {
    const lookup: LookupRow = {
      row_type: 'lookup', schema: 1, ts: new Date().toISOString(), lookup_id: 'lk_pages', run_id: null, claim_id: null, op: 'read', source_id: 'T-A', mode: 'both', route_primary: 'trove',
      book_by_route: { trove: 'T-A', pageindex: null }, request: { printed: null, trove_pages: '2-6' },
      primary: { route: 'trove', ok: true, route_pages: '2-6', latency_ms: 5, bytes: 10, chars: 10, text_sha: '0123456789abcdef', error: null, error_code: null }, shadow_status: 'pending',
    };
    await appendRow(fx.project, lookup);
    mkdirSync(spoolDir(fx.project), { recursive: true });
    const pages = [
      { page: 2, text: 'alpha beta gamma delta epsilon' },
      { page: 3, text: 'zeta eta theta iota kappa' },
      { page: 5, text: 'lambda mu nu xi omicron' },
      { page: 6, text: 'pi rho sigma tau upsilon' },
    ];
    writeFileSync(join(spoolDir(fx.project), 'lk_pages.shadow.json'), JSON.stringify({ lookup_id: 'lk_pages', route: 'pageindex', ok: true, pages }));
    const supports = async (quote: string, page?: number): Promise<boolean | null> => (await computeSupports(fx.project, 'lk_pages', quote, 0, page)).supports;
    assert.equal(await supports('alpha beta gamma delta'), true, 'one page covers it');
    assert.equal(await supports('alpha beta lambda mu'), false, 'pages 2 and 5 are not neighbours');
    assert.equal(await supports('zeta eta lambda mu'), false, 'pages 3 and 5 are not neighbours either');
    assert.equal(await supports('delta epsilon zeta eta'), true, 'a page and its immediate spill-over');
    assert.equal(await supports('delta epsilon pi rho'), false);
    assert.equal(await supports('alpha beta gamma delta', 2), true, 'a cited page is checked on its own');
    assert.equal(await supports('alpha beta gamma delta', 5), false, 'and not on the others');
  } finally { fx.cleanup(); }
});

// Concurrent appends
test('appends from many writers at once keep every line whole', async () => {
  const fx = fixture({ route: 'both' });
  try {
    const rows = Array.from({ length: 300 }, (_, index): VerdictRow => ({
      row_type: 'verdict', schema: 1, seq: index + 1, ts: new Date().toISOString(), lookup_id: `lk_${index}`, run_id: 'x'.repeat(150), paragraph_id: 'p'.repeat(150), verdict: 'PASS',
      corrected_page: null, shadow_supports: null, shadow_supports_reason: 'no_quote', primary_route: 'trove', mode: 'both',
    }));
    const results = await Promise.all(rows.map((row) => appendRow(fx.project, row)));
    assert.ok(results.every((result) => result.ok));
    const { aw } = await sharedBundle();
    const lookup: LookupRow = {
      row_type: 'lookup', schema: 1, ts: new Date().toISOString(), lookup_id: 'lk_many', run_id: null, claim_id: null, op: 'read', source_id: 'T-A', mode: 'both', route_primary: 'trove',
      book_by_route: { trove: null, pageindex: null }, request: { printed: null, trove_pages: '2' },
      primary: { route: 'trove', ok: true, route_pages: '2', latency_ms: 5, bytes: 10, chars: 10, text_sha: '0123456789abcdef', error: null, error_code: null }, shadow_status: 'none',
    };
    await appendRow(fx.project, lookup);
    const processes = await Promise.all(Array.from({ length: 6 }, (_, index) => runAw(aw, fx, 'verdict', '--lookup', 'lk_many', '--verdict', 'PASS', '--paragraph', `proc${index}`)));
    assert.ok(processes.every((run) => run.code === 0));
    const lines = rawLedger(fx);
    assert.equal(lines.length, 300 + 1 + 6);
    for (const line of lines) assert.deepEqual(checkSchema(retrievalSchema as JsonSchema, JSON.parse(line)), []);
  } finally { fx.cleanup(); }
});
