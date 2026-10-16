import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import thresholds from '../../thresholds.json' with { type: 'json' };
import { Library } from '../src/library/adapter.ts';
import { runLibraryCli } from '../src/library/cli.ts';
import { loadLibraryConfig } from '../src/library/config.ts';
import { callCap, plainFailure } from '../src/library/index-cmd.ts';
import { readRows, type LookupRow, type ShadowRow } from '../src/library/ledger.ts';
import { setPathArguments } from '../src/paths.ts';

const limits = thresholds.library;
const SECRET = 'AIzaSyFAKEKEYFORTESTS0123456789abcdef';

// Fake `trove` and `pilib`: tiny node scripts. The fake pilib doubles as the "venv python" of the built-in helper: invoked as
// `python -c <bootstrap> <pilib arguments>`, it skips the two bootstrap words and then behaves exactly like pilib. State of
// indexed books lives in FAKE_STATE (one file per book), so meta/tree/read only work after index-trove ran.
const SHARED = `const text = (n) => 'the shared sentence number ' + n + ' about the long argument of this page';`;
const TROVE_FAKE = `
const fs = require('node:fs');
const args = process.argv.slice(2);
if (process.env.FAKE_LOG) fs.appendFileSync(process.env.FAKE_LOG, JSON.stringify({ tool: 'trove', env: Object.keys(process.env), cmd: args, google: process.env.GOOGLE_API_KEY ? 'set' : 'unset', gemini: process.env.GEMINI_API_KEY ? 'set' : 'unset' }) + '\\n');
if (process.env.FAKE_TROVE_FAIL || (process.env.FAKE_TROVE_FAIL_ID && args.includes(process.env.FAKE_TROVE_FAIL_ID))) { console.error(process.env.FAKE_TROVE_FAIL_MSG || 'trove: boom'); process.exit(1); }
${SHARED}
const books = (process.env.FAKE_TROVE_BOOKS || 'T-A').split(',');
const entries = Number(process.env.FAKE_TOC_N || 3);
const page = (n) => '── Page ' + n + ' ──\\n' + text(n) + '\\n';
if (args[0] === 'shelf') console.log('No active shelf in /tmp/project');
else if (args[0] === 'items' && args[1] === 'list') console.log(JSON.stringify({ items: books.map((id) => ({ id, title: 'Book ' + id, author: 'Au', pageCount: 5 })) }));
else if (args[0] === 'items' && args[1] === 'toc' && args.includes('--json')) console.log(JSON.stringify({ items: [{ id: args[2], title: 'Book ' + args[2], toc: Array.from({ length: entries }, (_, i) => ({ title: 'Part ' + (i + 1) + (process.env.FAKE_TOC_PLAIN ? '' : ' - what it argues'), page: i + 1, level: 1 })) }] }));
else if (args[0] === 'items' && args[1] === 'toc') console.log('Book ' + args[2] + '\\nID: ' + args[2]);
else if (args[0] === 'items' && args[1] === 'read') {
  const spec = args.includes('--pages') ? args[args.indexOf('--pages') + 1] : args[2].split(':')[1];
  const ids = spec === 'all' ? [1, 2, 3, 4, 5] : spec.split(',').flatMap((p) => { const [a, b] = p.split('-').map(Number); return Array.from({ length: (b || a) - a + 1 }, (_, i) => a + i); }).filter((n) => n <= 5);
  process.stdout.write('Book A\\n' + args[2].split(':')[0] + ' | 5 pages\\n' + ids.map(page).join(''));
} else { console.error('unexpected: ' + args.join(' ')); process.exit(2); }
`;
const PILIB_FAKE = `
const fs = require('node:fs');
const path = require('node:path');
let args = process.argv.slice(2);
let boot = null;
if (args[0] === '-c') { boot = args[1]; args = args.slice(2); }
const key = process.env.GEMINI_API_KEY;
const keyState = !key ? 'unset' : key === process.env.FAKE_EXPECT_KEY ? 'match' : 'other';
if (process.env.FAKE_LOG) fs.appendFileSync(process.env.FAKE_LOG, JSON.stringify({ tool: 'pilib', env: Object.keys(process.env), cmd: args, boot, gemini: keyState, google: process.env.GOOGLE_API_KEY ? 'set' : 'unset', jev: process.env.JEV_API_KEY ? 'set' : 'unset', cwd: process.cwd() }) + '\\n');
${SHARED}
const state = process.env.FAKE_STATE;
const indexed = (id) => (process.env.FAKE_INDEXED || '').split(',').includes(id) || (state && fs.existsSync(path.join(state, id)));
const flag = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : undefined; };
const [cmd, book, spec] = args;
const fail = (code, error, extra) => { console.log(JSON.stringify(Object.assign({ ok: false, command: 'index-trove', code, error }, extra || {}))); console.error('ERROR library index: ' + error); process.exit(1); };
if (cmd === 'health') console.log(JSON.stringify({ ok: true, pilib_version: '1.0.0', python: '3.12.1', tier: process.env.FAKE_TIER || 'core', pageindex_commit: null, litellm: '1.83.9', pageindex: false, weasyprint: false, library: '/x', books: 0 }));
else if (cmd === 'index-trove') {
  if (args.includes('--help')) {
    if (process.env.FAKE_OLD) { console.error("pilib: error: argument cmd: invalid choice: 'index-trove'"); process.exit(2); }
    console.log('usage: pilib index-trove'); process.exit(0);
  }
  const mode = flag('--summaries'); const cap = Number(flag('--max-calls')); const dry = args.includes('--dry-run');
  if (process.env.FAKE_INDEX_FAIL) fail(process.env.FAKE_INDEX_FAIL, 'boom text with ' + (process.env.FAKE_LEAK || 'nothing'), { calls: 2, failures: 1, prompt_tokens: 100, completion_tokens: 20, reasoning_tokens: 0, cost_usd: 0.001, cost_unknown_calls: 0, call_cap: cap });
  if (process.env.FAKE_FAIL_ON === book) fail('trove_failed', 'trove items toc failed');
  if (mode === 'gemini' && !dry && !process.env.GEMINI_API_KEY && !process.env.GOOGLE_API_KEY && !process.env.FAKE_NO_KEY_CHECK) fail('missing_key', 'no Gemini key is set in the environment');
  const bookId = flag('--book-id') || book;
  if (!dry && state) { fs.mkdirSync(state, { recursive: true }); fs.writeFileSync(path.join(state, bookId), 'indexed'); }
  const calls = mode === 'gemini' && !dry ? 3 : 0;
  console.log(JSON.stringify({ ok: true, command: 'index-trove', dry_run: dry, book_id: bookId, trove_id: book, title: 'Book ' + book, source: 'trove-toc', fallback: false, summaries: mode, model: mode === 'gemini' ? (flag('--model') || 'gemini/test-model') : null,
    n_pages: 5, toc_entries: 3, hinted_entries: 3, nodes: 3, nodes_with_summary: mode === 'none' ? 0 : 3, summaries_reused: 0, summaries_generated: calls, summary_failures: 0, expected_calls: mode === 'gemini' ? 3 : 0, input_chars: 900,
    calls, failures: 0, prompt_tokens: calls ? 1200 : 0, completion_tokens: calls ? 300 : 0, reasoning_tokens: 0, cost_usd: calls ? 0.0042 : 0, cost_unknown_calls: 0, call_cap: cap, seconds: 1.5, library: '/x/library',
    indexed_at: dry ? null : '2026-10-16T10:00:00Z', warnings: [], secret_probe: process.env.GEMINI_API_KEY || null }));
} else if (cmd === 'catalog') {
  const ids = (process.env.FAKE_INDEXED || '').split(',').filter(Boolean);
  console.log(JSON.stringify(Object.fromEntries(ids.map((id) => [id, { title: 'Library ' + id, author: 'Au', n_pages: 5, toc_source: 'x', top: [] }]))));
} else if (cmd === 'meta') {
  if (!indexed(book)) { console.error('book not indexed: ' + book); process.exit(1); }
  console.log(JSON.stringify({ book_id: book, title: 'Library ' + book, n_pages: Number(process.env.FAKE_META_PAGES || 5), origin: { trove: { trove_id: book, trove_pages: 5, toc_entries: Number(process.env.FAKE_META_TOC || 3) } }, trove_id: book, pagemap: null }));
} else if (cmd === 'tree') {
  if (!indexed(book)) { console.error('book not indexed: ' + book); process.exit(1); }
  const sum = process.env.FAKE_NO_SUMMARY ? {} : { summary: 'a summary' };
  console.log(JSON.stringify({ book_id: book, title: 'Library ' + book, n_pages: 5, structure: [Object.assign({ node_id: '1', title: 'Part 1 - x', start_index: 1, end_index: 2 }, sum), Object.assign({ node_id: '2', title: 'Part 2 - x', start_index: 3, end_index: 4 }, sum), Object.assign({ node_id: '3', title: 'Part 3 - x', start_index: 5, end_index: process.env.FAKE_BAD_RANGE ? 9 : 5 }, sum)] }));
} else if (cmd === 'read') {
  if (!indexed(book)) { console.error('book not indexed: ' + book); process.exit(1); }
  const ids = spec === 'all' ? [1, 2, 3, 4, 5] : spec.split(',').flatMap((p) => { const [a, b] = p.split('-').map(Number); return Array.from({ length: (b || a) - a + 1 }, (_, i) => a + i); }).filter((n) => n <= 5);
  console.log(JSON.stringify({ book_id: book, pages: ids.map((n) => ({ page: n, content: process.env.FAKE_READ_DIFF ? 'different words ' + n : text(n) })) }));
} else { console.error('unexpected: ' + args.join(' ')); process.exit(2); }
`;

type Fixture = { root: string; project: string; env: NodeJS.ProcessEnv; log: string; state: string; pluginRoot: string; data: string; cleanup: () => void };
type Source = 'wrapper' | 'installed' | 'default' | 'library.json';

function writeFake(dir: string, name: string, body: string): string {
  mkdirSync(dir, { recursive: true });
  const file = join(dir, name);
  writeFileSync(file, `#!${process.execPath}\n${body}`, 'utf8');
  chmodSync(file, 0o755);
  return file;
}

const SCRUB = ['AW_PAGEINDEX_COMMAND', 'AW_PAGEINDEX_HOME', 'AW_TROVE_COMMAND', 'AW_LIBRARY_ROUTE', 'AW_LIBRARY_SHADOW', 'AW_LIBRARY_TIMEOUT_MS', 'CLAUDE_PLUGIN_DATA', 'CLAUDE_PLUGIN_ROOT', 'CLAUDE_PROJECT_DIR',
  'GOOGLE_API_KEY', 'GEMINI_API_KEY', 'JEV_API_KEY', 'FAKE_LOG', 'FAKE_STATE', 'FAKE_EXPECT_KEY'];

function fixture(source: Source, extra: Record<string, string> = {}, config?: unknown): Fixture {
  const root = mkdtempSync(join(tmpdir(), 'aw-index-'));
  const project = join(root, 'project');
  mkdirSync(join(project, '.academic-helper'), { recursive: true });
  const bin = join(root, 'bin');
  const log = join(root, 'calls.log');
  const state = join(root, 'state');
  const data = join(root, 'data');
  const pluginRoot = join(root, 'plugin');
  const env: NodeJS.ProcessEnv = { ...process.env };
  for (const key of [...SCRUB, ...Object.keys(env).filter((name) => name.startsWith('FAKE_'))]) delete env[key];
  Object.assign(env, { AW_TROVE_COMMAND: writeFake(bin, 'trove', TROVE_FAKE), FAKE_LOG: log, FAKE_STATE: state, FAKE_EXPECT_KEY: SECRET, GOOGLE_API_KEY: SECRET, JEV_API_KEY: 'jev-secret-value', ...extra });
  const pilib = writeFake(bin, 'pilib', PILIB_FAKE);
  // A wrapper reaches a computer that holds its own Gemini key: the fake there does not need ours.
  if (source === 'wrapper' || source === 'library.json') env.FAKE_NO_KEY_CHECK = '1';
  if (source === 'wrapper') env.AW_PAGEINDEX_COMMAND = pilib;
  if (source === 'installed') {
    mkdirSync(join(pluginRoot, 'scripts', 'pageindex'), { recursive: true });
    const home = join(data, 'pageindex');
    writeFake(join(home, 'venv', 'bin'), 'python', PILIB_FAKE);
    writeFileSync(join(home, 'installed.json'), JSON.stringify({ schema: 1, tier: 'core', python: '3.12.1', pageindex_commit: null, requirements_sha256: 'a'.repeat(64), pilib_version: '1.0.0', installed_at: '2026-10-16T09:00:00Z' }), 'utf8');
    Object.assign(env, { CLAUDE_PLUGIN_DATA: data, CLAUDE_PLUGIN_ROOT: pluginRoot });
  }
  if (source === 'library.json') config = { ...(config as object), pageindex: { command: pilib } };
  if (config !== undefined) writeFileSync(join(project, '.academic-helper', 'library.json'), JSON.stringify(config), 'utf8');
  // Commands get an allow-list of the environment: the fakes' own switches are named in AW_LIBRARY_PASS_ENV, as a researcher would for a variable a wrapper needs.
  env.AW_LIBRARY_PASS_ENV = Object.keys(env).filter((name) => name.startsWith('FAKE_')).join(',');
  return { root, project, env, log, state, pluginRoot, data, cleanup: () => rmSync(root, { recursive: true, force: true }) };
}

/** Run `aw library ...` with exactly fx.env as the process environment (nothing leaks in from the real one). */
async function cli(fx: Fixture, ...argv: string[]): Promise<{ code: number; out: string; err: string }> {
  const saved = { ...process.env };
  let out = '';
  let err = '';
  for (const key of Object.keys(process.env)) delete process.env[key];
  Object.assign(process.env, fx.env);
  setPathArguments(['--project-dir', fx.project]);
  try {
    const code = await runLibraryCli(argv, { out: (text) => { out += text; }, err: (text) => { err += text; } });
    return { code, out, err };
  } finally {
    for (const key of Object.keys(process.env)) delete process.env[key];
    Object.assign(process.env, saved);
  }
}

type LogLine = { tool: string; env: string[]; cmd: string[]; boot?: string | null; gemini: string; google: string; jev?: string; cwd?: string };
function calls(fx: Fixture): LogLine[] { return existsSync(fx.log) ? readFileSync(fx.log, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line) as LogLine) : []; }
function pilibCalls(fx: Fixture, name?: string): LogLine[] { return calls(fx).filter((line) => line.tool === 'pilib' && (name === undefined || line.cmd[0] === name)); }
function usageRows(fx: Fixture, run: string): Array<Record<string, unknown>> {
  const file = join(fx.project, '.academic-helper', 'runs', run, 'usage.jsonl');
  return existsSync(file) ? readFileSync(file, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line) as Record<string, unknown>) : [];
}
function everyFileText(dir: string): string {
  const parts: string[] = [];
  const walk = (current: string): void => {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const path = join(current, entry.name);
      if (entry.isDirectory()) walk(path); else parts.push(readFileSync(path, 'utf8'));
    }
  };
  walk(dir);
  return parts.join('\n');
}

// ---------------------------------------------------------------- aw library index: the built-in helper and a wrapper

test('index through a wrapper: a tree is built, read back against Trove, and one usage row is written; no key is forwarded', async () => {
  const fx = fixture('wrapper');
  try {
    const result = await cli(fx, 'index', '--trove-id', 'T-A', '--run', 'idx-1');
    assert.equal(result.code, 0, result.err);
    const out = JSON.parse(result.out) as Record<string, unknown> & { read_back: { ok: boolean; trove_compared: boolean; checks: Record<string, unknown> } };
    assert.deepEqual([out.ok, out.pageindex_source, out.book_id, out.trove_id, out.source, out.nodes, out.calls], [true, 'setting', 'T-A', 'T-A', 'trove-toc', 3, 3]);
    assert.deepEqual([out.read_back.ok, out.read_back.trove_compared, out.read_back.checks.meta, out.read_back.checks.tree, out.read_back.checks.pages, out.read_back.checks.trove_pages, out.read_back.checks.summaries], [true, true, true, true, true, true, '100%']);
    const rows = usageRows(fx, 'idx-1');
    assert.equal(rows.length, 1);
    assert.deepEqual([rows[0]?.step, rows[0]?.provider, rows[0]?.model, rows[0]?.input_tokens, rows[0]?.output_tokens, rows[0]?.cost_usd, rows[0]?.exit], ['library.index', 'gemini', 'gemini/test-model', 1200, 300, 0.0042, 'OK']);
    // A wrapper keeps its own key: the plugin hands nothing over, and strips the Google key and the Jev key from its environment.
    const index = pilibCalls(fx, 'index-trove').find((line) => !line.cmd.includes('--help'));
    assert.deepEqual([index?.gemini, index?.google, index?.jev], ['unset', 'unset', 'unset']);
    assert.ok(!JSON.stringify(calls(fx)).includes(SECRET));
    assert.ok(!result.out.includes(SECRET) && !result.err.includes(SECRET));
    assert.ok(!everyFileText(join(fx.project, '.academic-helper')).includes(SECRET));
  } finally { fx.cleanup(); }
});

test('index with the built-in helper: the key reaches the child only as GEMINI_API_KEY, never in an argument, the output or a file', async () => {
  const fx = fixture('installed');
  try {
    const result = await cli(fx, 'index', '--trove-id', 'T-A', '--run', 'idx-2');
    assert.equal(result.code, 0, result.err);
    const out = JSON.parse(result.out) as { pageindex_source: string; read_back: { ok: boolean } };
    assert.deepEqual([out.pageindex_source, out.read_back.ok], ['installed', true]);
    const index = pilibCalls(fx, 'index-trove').find((line) => !line.cmd.includes('--help'));
    assert.deepEqual([index?.gemini, index?.google, index?.jev], ['match', 'unset', 'unset']);
    // The command is the private Python with the bootstrap that points at the plugin's own pilib source and the data folder's library.
    assert.ok(index?.boot?.includes(JSON.stringify(join(fx.pluginRoot, 'scripts', 'pageindex'))), 'the bootstrap names the plugin source');
    assert.ok(index?.boot?.includes(JSON.stringify(join(fx.data, 'pageindex', 'library'))), 'the bootstrap names the library folder');
    assert.ok(!JSON.stringify(calls(fx).map((line) => [line.cmd, line.boot])).includes(SECRET), 'never in argv');
    assert.ok(!result.out.includes(SECRET) && !result.err.includes(SECRET));
    assert.ok(!everyFileText(join(fx.project, '.academic-helper')).includes(SECRET), 'never in the ledger');
    // Trove, which has nothing to do with Gemini, never sees the key either.
    assert.ok(calls(fx).filter((line) => line.tool === 'trove').every((line) => line.google === 'unset' && line.gemini === 'unset'));
  } finally { fx.cleanup(); }
});

test('index with the built-in helper and no Gemini key stops before any model call and says what to do; hints work without a key', async () => {
  const fx = fixture('installed');
  delete fx.env.GOOGLE_API_KEY;
  try {
    const none = await cli(fx, 'index', '--trove-id', 'T-A', '--run', 'idx-3');
    assert.equal(none.code, 4);
    const out = JSON.parse(none.out) as { ok: boolean; code: string; error: string };
    assert.deepEqual([out.ok, out.code], [false, 'missing_key']);
    assert.match(out.error, /Google \(Gemini\) key/);
    assert.equal(pilibCalls(fx, 'index-trove').filter((line) => !line.cmd.includes('--help')).length, 0, 'the helper was never asked to index');
    const hints = await cli(fx, 'index', '--trove-id', 'T-A', '--summaries', 'hints', '--run', 'idx-3');
    assert.equal(hints.code, 0, hints.err);
    assert.deepEqual([JSON.parse(hints.out).summaries, usageRows(fx, 'idx-3')[0]?.provider], ['hints', 'pilib']);
  } finally { fx.cleanup(); }
});

test('an old pilib (no index-trove) is refused up front with a plain message and nothing is recorded', async () => {
  const fx = fixture('wrapper', { FAKE_OLD: '1' });
  try {
    const result = await cli(fx, 'index', '--trove-id', 'T-A', '--run', 'idx-4');
    assert.equal(result.code, 3);
    assert.match(result.err, /older than this plugin.*cannot index books/s);
    assert.match(result.err, /aw library install/);
    assert.equal(usageRows(fx, 'idx-4').length, 0);
    assert.equal(pilibCalls(fx, 'index-trove').filter((line) => !line.cmd.includes('--help')).length, 0);
  } finally { fx.cleanup(); }
});

test('no PageIndex command at all: a plain message that points to the built-in helper', async () => {
  const fx = fixture('default');
  fx.env.PATH = join(fx.root, 'empty-path');
  try {
    mkdirSync(fx.env.PATH);
    const result = await cli(fx, 'index', '--trove-id', 'T-A');
    assert.equal(result.code, 3);
    assert.match(result.err, /No PageIndex command is set up/);
    assert.match(result.err, /aw library install/);
  } finally { fx.cleanup(); }
});

test('every pilib failure code becomes a plain sentence, exit 4, JSON on stdout and a failed usage row', async () => {
  const cases: Array<[string, RegExp]> = [
    ['busy', /being indexed by another process/], ['structure_helper_missing', /full helper that finds the structure/], ['trove_failed', /Trove could not be read/],
    ['core_helper_missing', /summary helper is not installed/], ['model_failed', /Gemini did not answer/], ['empty_book', /no pages in Trove/], ['internal', /stopped unexpectedly/],
  ];
  for (const [code, pattern] of cases) {
    const fx = fixture('wrapper', { FAKE_INDEX_FAIL: code });
    try {
      const result = await cli(fx, 'index', '--trove-id', 'T-A', '--run', 'idx-f');
      assert.equal(result.code, 4, code);
      const out = JSON.parse(result.out) as { ok: boolean; code: string; error: string };
      assert.deepEqual([out.ok, out.code], [false, code]);
      assert.match(out.error, pattern, code);
      assert.match(result.err, /^ERROR library index: /);
      const rows = usageRows(fx, 'idx-f');
      assert.deepEqual([rows.length, rows[0]?.exit, rows[0]?.input_tokens], [1, 'ERROR', 100], code);
    } finally { fx.cleanup(); }
  }
});

test('a secret in the helper\'s error text never reaches the output', () => {
  const text = plainFailure('model_failed', `bad key ${SECRET} and Authorization: Bearer abcdefghijklmnop`);
  assert.ok(!text.includes(SECRET) && !/abcdefghijklmnop/.test(text), text);
});

test('without --yes a Gemini run is capped at askAboveCalls; --yes lifts the cap; the cap failure says to ask first', async () => {
  const fx = fixture('wrapper');
  try {
    assert.deepEqual([callCap({ summaries: 'gemini', yes: false }), callCap({ summaries: 'gemini', yes: true }), callCap({ summaries: 'gemini', yes: false, maxCalls: 10 }), callCap({ summaries: 'hints', yes: false })],
      [limits.index.askAboveCalls, limits.index.maxCalls, 10, limits.index.maxCalls]);
    await cli(fx, 'index', '--trove-id', 'T-A', '--run', 'idx-5');
    await cli(fx, 'index', '--trove-id', 'T-A', '--yes', '--run', 'idx-5');
    const caps = pilibCalls(fx, 'index-trove').filter((line) => !line.cmd.includes('--help')).map((line) => line.cmd[line.cmd.indexOf('--max-calls') + 1]);
    assert.deepEqual(caps, [String(limits.index.askAboveCalls), String(limits.index.maxCalls)]);
  } finally { fx.cleanup(); }
  const capped = fixture('wrapper', { FAKE_INDEX_FAIL: 'call_cap' });
  try {
    const result = await cli(capped, 'index', '--trove-id', 'T-A', '--run', 'idx-6');
    assert.equal(result.code, 4);
    const out = JSON.parse(result.out) as { needs_yes: boolean; error: string };
    assert.equal(out.needs_yes, true);
    assert.match(out.error, /ask the researcher, then run it again with --yes/);
    assert.equal(usageRows(capped, 'idx-6')[0]?.exit, 'CAP_REACHED');
  } finally { capped.cleanup(); }
});

test('--dry-run plans only: no ledger row, no read-back, the flag reaches the helper', async () => {
  const fx = fixture('wrapper');
  try {
    const result = await cli(fx, 'index', '--trove-id', 'T-A', '--dry-run', '--run', 'idx-7');
    assert.equal(result.code, 0, result.err);
    const out = JSON.parse(result.out) as { dry_run: boolean; read_back?: unknown; ledger?: unknown; expected_calls: number };
    assert.deepEqual([out.dry_run, out.read_back, out.ledger, out.expected_calls], [true, undefined, undefined, 3]);
    assert.equal(usageRows(fx, 'idx-7').length, 0);
    assert.deepEqual(pilibCalls(fx).map((line) => line.cmd[0]), ['index-trove', 'index-trove']);
    assert.ok(pilibCalls(fx, 'index-trove')[1]?.cmd.includes('--dry-run'));
  } finally { fx.cleanup(); }
});

test('the read-back fails the run when the library differs from Trove, the outline is broken, or summaries are missing', async () => {
  const cases: Array<[Record<string, string>, RegExp]> = [
    [{ FAKE_READ_DIFF: '1' }, /differ from the pages in Trove/], [{ FAKE_META_PAGES: '4' }, /says 4 pages/], [{ FAKE_BAD_RANGE: '1' }, /point outside the book/],
    [{ FAKE_NO_SUMMARY: '1' }, /carry a summary/],
  ];
  for (const [extra, pattern] of cases) {
    const fx = fixture('wrapper', extra);
    try {
      const result = await cli(fx, 'index', '--trove-id', 'T-A', '--run', 'idx-rb');
      assert.equal(result.code, 4, JSON.stringify(extra));
      const out = JSON.parse(result.out) as { code: string; error: string; read_back: { ok: boolean; problems: string[] } };
      assert.deepEqual([out.code, out.read_back.ok], ['read_back_failed', false]);
      assert.match(out.read_back.problems.join(' | '), pattern, JSON.stringify(extra));
      assert.equal(usageRows(fx, 'idx-rb')[0]?.exit, 'ERROR');
    } finally { fx.cleanup(); }
  }
  // Trove not answering on this computer is a note, not a failure: the library may live on another one.
  const away = fixture('wrapper', { FAKE_TROVE_FAIL: '1' });
  try {
    const result = await cli(away, 'index', '--trove-id', 'T-A', '--run', 'idx-rb');
    assert.equal(result.code, 0, result.err);
    const out = JSON.parse(result.out) as { read_back: { ok: boolean; trove_compared: boolean; checks: Record<string, unknown> } };
    assert.deepEqual([out.read_back.ok, out.read_back.trove_compared, String(out.read_back.checks.trove_pages)], [true, false, 'not compared (Trove did not answer here)']);
  } finally { away.cleanup(); }
});

test('ids and options are checked before anything runs: a shell word never reaches the helper', async () => {
  const fx = fixture('wrapper');
  try {
    for (const argv of [['index', '--trove-id', 'a;b'], ['index', '--trove-id', 'T-A', '--book-id', '$(x)'], ['index'], ['index', '--trove-id', 'T-A', '--summaries', 'all'], ['index', '--trove-id', 'T-A', '--model', 'x y'], ['index', '--trove-id', 'T-A', '--max-calls', '0'],
      ['backfill'], ['backfill', '--ids', 'a,b c'], ['backfill', '--all', '--shelf-current'], ['install', '--tier', 'full'], ['install', '--python', '-m']]) {
      const result = await cli(fx, ...argv);
      assert.equal(result.code, 2, argv.join(' '));
    }
    assert.equal(calls(fx).length, 0, 'nothing was run');
  } finally { fx.cleanup(); }
});

// ---------------------------------------------------------------- backfill

test('backfill --dry-run prints the plan with an estimate and changes nothing', async () => {
  const fx = fixture('wrapper', { FAKE_TROVE_BOOKS: 'T-A,T-B,T-C', FAKE_INDEXED: 'T-B' });
  try {
    const result = await cli(fx, 'backfill', '--all', '--dry-run', '--skip-existing', '--run', 'bf-1');
    assert.equal(result.code, 0, result.err);
    const out = JSON.parse(result.out) as { dry_run: boolean; books: number; to_index: number; skipped: number; estimated_calls: number; ask_required: boolean; plan: Array<{ id: string; action: string; reason: string | null; expected_calls: number | null }> };
    assert.deepEqual([out.dry_run, out.books, out.to_index, out.skipped, out.estimated_calls, out.ask_required], [true, 3, 2, 1, 6, false]);
    assert.deepEqual(out.plan.map((line) => [line.id, line.action]), [['T-A', 'index'], ['T-B', 'skip'], ['T-C', 'index']]);
    assert.match(out.plan[1]?.reason ?? '', /already indexed/);
    assert.equal(pilibCalls(fx, 'index-trove').filter((line) => !line.cmd.includes('--help')).length, 0);
    assert.equal(usageRows(fx, 'bf-1').length, 0);
  } finally { fx.cleanup(); }
});

test('backfill copies two Trove books, reads each back, and appends one usage row per book', async () => {
  const fx = fixture('installed', { FAKE_TROVE_BOOKS: 'T-A,T-B' });
  try {
    const result = await cli(fx, 'backfill', '--shelf-current', '--run', 'bf-2');
    assert.equal(result.code, 0, result.err);
    const out = JSON.parse(result.out) as { ok: boolean; indexed: number; failed: number; calls: number; prompt_tokens: number; cost_usd: number; results: Array<{ id: string; status: string; read_back_ok: boolean }> };
    assert.deepEqual([out.ok, out.indexed, out.failed, out.calls, out.prompt_tokens], [true, 2, 0, 6, 2400]);
    assert.deepEqual(out.results.map((entry) => [entry.id, entry.status, entry.read_back_ok]), [['T-A', 'indexed', true], ['T-B', 'indexed', true]]);
    assert.equal(usageRows(fx, 'bf-2').length, 2);
    assert.ok(existsSync(join(fx.state, 'T-A')) && existsSync(join(fx.state, 'T-B')));
    assert.ok(!result.out.includes(SECRET) && !everyFileText(join(fx.project, '.academic-helper')).includes(SECRET));
  } finally { fx.cleanup(); }
});

test('backfill asks first: a large estimate, or a book without a hinted table of contents, needs --yes', async () => {
  const big = fixture('wrapper', { FAKE_TROVE_BOOKS: 'T-A,T-B', FAKE_TOC_N: String(limits.index.askAboveCalls) });
  const plain = fixture('wrapper', { FAKE_TROVE_BOOKS: 'T-A', FAKE_TOC_PLAIN: '1' });
  try {
    const refused = await cli(big, 'backfill', '--ids', 'T-A,T-B', '--run', 'bf-3');
    assert.equal(refused.code, 2);
    const out = JSON.parse(refused.out) as { code: string; ask_required: boolean; estimated_calls: number; error: string };
    assert.deepEqual([out.code, out.ask_required, out.estimated_calls], ['needs_confirmation', true, limits.index.askAboveCalls * 2]);
    assert.match(out.error, /ask, then run it again with --yes/);
    assert.equal(pilibCalls(big, 'index-trove').filter((line) => !line.cmd.includes('--help')).length, 0);
    const refusedPlain = await cli(plain, 'backfill', '--ids', 'T-A', '--run', 'bf-3');
    assert.equal(refusedPlain.code, 2);
    const allowed = await cli(big, 'backfill', '--ids', 'T-A,T-B', '--yes', '--run', 'bf-3');
    assert.equal(allowed.code, 0, allowed.err);
    // Without a Gemini summary there is nothing to ask about.
    const free = await cli(plain, 'backfill', '--ids', 'T-A', '--summaries', 'hints', '--run', 'bf-3');
    assert.equal(free.code, 0, free.err);
  } finally { big.cleanup(); plain.cleanup(); }
});

test('backfill stops at a failure every later book would repeat, continues past one that is just that book\'s', async () => {
  const stop = fixture('wrapper', { FAKE_TROVE_BOOKS: 'T-A,T-B,T-C', FAKE_INDEX_FAIL: 'missing_key' });
  const mixed = fixture('wrapper', { FAKE_TROVE_BOOKS: 'T-A,T-B,T-C', FAKE_FAIL_ON: 'T-B' });
  try {
    const first = await cli(stop, 'backfill', '--all', '--yes', '--run', 'bf-4');
    assert.equal(first.code, 4);
    const out = JSON.parse(first.out) as { failed: number; not_run: number; results: Array<{ status: string }> };
    assert.deepEqual([out.failed, out.not_run, out.results.map((entry) => entry.status)], [1, 2, ['failed', 'not_run', 'not_run']]);
    const second = await cli(mixed, 'backfill', '--all', '--yes', '--run', 'bf-4');
    assert.equal(second.code, 4);
    assert.deepEqual((JSON.parse(second.out) as { results: Array<{ status: string }> }).results.map((entry) => entry.status), ['indexed', 'failed', 'indexed']);
  } finally { stop.cleanup(); mixed.cleanup(); }
});

test('a backfill where books cannot be read from Trove fails: unreadable books count as failed, the exit is non-zero, no secret is printed', async () => {
  const leak = 'trove: login failed. Authorization: Bearer abcdefghijklmnop token=SUPERSECRETVALUE123 AIzaSyFAKEKEYFORTESTS0123456789abcdef';
  const all = fixture('wrapper', { FAKE_TROVE_FAIL: '1', FAKE_TROVE_FAIL_MSG: leak });
  const some = fixture('wrapper', { FAKE_TROVE_BOOKS: 'T-A,T-B', FAKE_TROVE_FAIL_ID: 'T-B', FAKE_TROVE_FAIL_MSG: leak });
  try {
    const result = await cli(all, 'backfill', '--ids', 'T-A,T-B', '--summaries', 'hints', '--run', 'bf-u');
    assert.equal(result.code, 4, result.out);
    const out = JSON.parse(result.out) as { ok: boolean; failed: number; indexed: number; unreadable: Array<{ id: string; error: string }>; results: Array<{ id: string; status: string; code?: string; error?: string }> };
    assert.deepEqual([out.ok, out.failed, out.indexed], [false, 2, 0]);
    assert.deepEqual(out.results.map((entry) => [entry.id, entry.status, entry.code]), [['T-A', 'failed', 'trove_failed'], ['T-B', 'failed', 'trove_failed']]);
    assert.equal(out.unreadable.length, 2);
    for (const text of [result.out, result.err]) assert.ok(!/abcdefghijklmnop|SUPERSECRETVALUE123|AIzaSy/.test(text), `a secret was printed: ${text}`);
    assert.match(out.results[0]?.error ?? '', /Trove could not be read/);
    assert.equal(pilibCalls(all, 'index-trove').filter((line) => !line.cmd.includes('--help')).length, 0);
    // the plan shows the same, redacted, and does not fail by itself
    const plan = await cli(all, 'backfill', '--ids', 'T-A', '--dry-run');
    assert.equal(plan.code, 0, plan.err);
    assert.ok(!/abcdefghijklmnop|SUPERSECRETVALUE123|AIzaSy/.test(plan.out));
    assert.equal((JSON.parse(plan.out) as { unreadable: unknown[] }).unreadable.length, 1);
    // one readable, one not: the readable one is indexed and the run still fails
    const mixed = await cli(some, 'backfill', '--all', '--summaries', 'hints', '--run', 'bf-u');
    assert.equal(mixed.code, 4);
    const mixedOut = JSON.parse(mixed.out) as { ok: boolean; failed: number; indexed: number };
    assert.deepEqual([mixedOut.ok, mixedOut.failed, mixedOut.indexed], [false, 1, 1]);
  } finally { all.cleanup(); some.cleanup(); }
});

test('backfill --limit and --skip-existing (same pages and outline length) decide what is indexed', async () => {
  const fx = fixture('wrapper', { FAKE_TROVE_BOOKS: 'T-A,T-B,T-C', FAKE_INDEXED: 'T-A', FAKE_META_TOC: '2' });
  try {
    const stale = await cli(fx, 'backfill', '--all', '--dry-run', '--skip-existing');
    assert.deepEqual((JSON.parse(stale.out) as { plan: Array<{ action: string }> }).plan.map((line) => line.action), ['index', 'index', 'index'], 'a different outline length means the old index is stale');
    const fresh = fixture('wrapper', { FAKE_TROVE_BOOKS: 'T-A,T-B,T-C', FAKE_INDEXED: 'T-A' });
    try {
      const limited = await cli(fresh, 'backfill', '--all', '--dry-run', '--skip-existing', '--limit', '1');
      assert.deepEqual((JSON.parse(limited.out) as { plan: Array<{ action: string; reason: string | null }> }).plan.map((line) => line.action), ['skip', 'index', 'skip']);
    } finally { fresh.cleanup(); }
  } finally { fx.cleanup(); }
});

// ---------------------------------------------------------------- the three routes against an installed helper and a wrapper

for (const source of ['installed', 'wrapper'] as const) {
  test(`routes trove, pageindex and both answer through ${source}`, async () => {
    for (const route of ['trove', 'pageindex', 'both'] as const) {
      const fx = fixture(source, { FAKE_INDEXED: 'T-A' }, { route });
      try {
        const library = new Library(fx.project, fx.env, { shadow: 'inline' });
        const answer = await library.read({ source: 'T-A', pages: '2-3' });
        assert.deepEqual([answer.route, answer.mode, answer.pages.map((page) => page.trove_page)], [route === 'pageindex' ? 'pageindex' : 'trove', route, [2, 3]], `${source} ${route}`);
        assert.match(answer.pages[0]?.text ?? '', /shared sentence number 2/);
        const reads = pilibCalls(fx, 'read');
        if (route === 'trove') assert.equal(pilibCalls(fx).length, 0, 'Trove only: the PageIndex command is never run');
        else assert.ok(reads.length >= 1, `${route} reads through PageIndex`);
        if (route === 'both') {
          const shadow = (await readRows(fx.project)).rows.find((row): row is ShadowRow => row.row_type === 'shadow');
          assert.deepEqual([shadow?.ok, shadow?.agree?.rate, shadow?.route], [true, 1, 'pageindex']);
          assert.equal((await readRows(fx.project)).rows.filter((row): row is LookupRow => row.row_type === 'lookup').length, 1);
        }
        assert.ok(!JSON.stringify(calls(fx).map((line) => [line.cmd, line.boot])).includes(SECRET));
        if (source === 'installed') assert.ok(pilibCalls(fx).every((line) => line.boot?.includes(JSON.stringify(join(fx.data, 'pageindex', 'library')))), 'every call goes through the bootstrap');
      } finally { fx.cleanup(); }
    }
  });
}

const SECRET_NAMES = ['GOOGLE_API_KEY', 'GEMINI_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GITHUB_TOKEN', 'AWS_SECRET_ACCESS_KEY', 'JEV_API_KEY', 'AW_SOME_API_KEY'];

test('no lookup, index or backfill command ever sees a key, token or secret set where aw runs; an allow-list passes what a command needs', async () => {
  for (const source of ['wrapper', 'installed'] as const) {
    const fx = fixture(source, { FAKE_INDEXED: 'T-A', FAKE_TROVE_BOOKS: 'T-A', MY_WRAPPER_VAR: 'needed', LC_ALL: 'C', SSH_AUTH_SOCK: '/tmp/agent.sock', AW_LIBRARY_PASS_ENV_EXTRA: 'x' }, { route: 'both' });
    try {
      for (const name of SECRET_NAMES) fx.env[name] = 'secret-value-that-must-not-travel';
      fx.env.AW_LIBRARY_PASS_ENV = `${fx.env.AW_LIBRARY_PASS_ENV},MY_WRAPPER_VAR`;
      const library = new Library(fx.project, fx.env, { shadow: 'inline' });
      await library.read({ source: 'T-A', pages: '2' });
      await library.toc('T-A');
      assert.equal((await cli(fx, 'index', '--trove-id', 'T-A', '--summaries', 'hints', '--run', 'env-1')).code, 0);
      assert.equal((await cli(fx, 'backfill', '--ids', 'T-A', '--summaries', 'hints', '--run', 'env-2')).code, 0);
      const seen = calls(fx);
      assert.ok(seen.length > 6, 'both commands ran several times');
      for (const line of seen) {
        for (const name of SECRET_NAMES) assert.ok(!line.env.includes(name), `${name} reached ${line.tool} ${line.cmd.join(' ')}`);
        for (const name of ['PATH', 'HOME', 'LC_ALL', 'SSH_AUTH_SOCK', 'MY_WRAPPER_VAR', 'AW_TROVE_COMMAND']) assert.ok(line.env.includes(name), `${name} should reach ${line.tool}`);
      }
    } finally { fx.cleanup(); }
  }
  // the one exception, by design: the built-in helper that writes the summaries gets the Gemini key, as GEMINI_API_KEY and nothing else
  const fx = fixture('installed');
  try {
    fx.env.ANTHROPIC_API_KEY = 'secret-value-that-must-not-travel';
    assert.equal((await cli(fx, 'index', '--trove-id', 'T-A', '--run', 'env-3')).code, 0);
    const index = pilibCalls(fx, 'index-trove').find((line) => !line.cmd.includes('--help'));
    assert.deepEqual([index?.env.includes('GEMINI_API_KEY'), index?.env.includes('GOOGLE_API_KEY'), index?.env.includes('ANTHROPIC_API_KEY')], [true, false, false]);
  } finally { fx.cleanup(); }
});

test('with no library.json the plugin behaves as before: Trove only, the helper is never started, even when installed', async () => {
  const fx = fixture('installed', { FAKE_INDEXED: 'T-A' });
  try {
    const result = await cli(fx, 'read', '--source', 'T-A', '--pages', '2');
    assert.equal(result.code, 0, result.err);
    assert.deepEqual([JSON.parse(result.out).route, JSON.parse(result.out).mode], ['trove', 'trove']);
    assert.equal(pilibCalls(fx).length, 0);
  } finally { fx.cleanup(); }
});

// ---------------------------------------------------------------- resolution order and status

test('the PageIndex command is resolved: setting, then library.json, then the built-in helper, then pilib', () => {
  const all = fixture('installed', {}, { route: 'pageindex', pageindex: { command: 'from-file' } });
  const fileOnly = fixture('installed', {}, { route: 'pageindex', pageindex: { command: ['from-file', '--x'] } });
  const installed = fixture('installed', {}, { route: 'pageindex' });
  const none = fixture('default');
  try {
    all.env.AW_PAGEINDEX_COMMAND = 'from-setting --flag';
    const settingWins = loadLibraryConfig(all.project, all.env);
    assert.deepEqual([settingWins.pageindexSource, settingWins.pageindexCommand], ['setting', ['from-setting', '--flag']]);
    const file = loadLibraryConfig(fileOnly.project, fileOnly.env);
    assert.deepEqual([file.pageindexSource, file.pageindexCommand], ['library.json', ['from-file', '--x']]);
    const built = loadLibraryConfig(installed.project, installed.env);
    assert.equal(built.pageindexSource, 'installed');
    assert.equal(built.pageindexCommand[0], join(installed.data, 'pageindex', 'venv', 'bin', 'python'));
    assert.equal(built.pageindexCommand[1], '-c');
    assert.equal(built.pageindexHome, join(installed.data, 'pageindex'));
    const plain = loadLibraryConfig(none.project, none.env);
    assert.deepEqual([plain.pageindexSource, plain.pageindexCommand, plain.pageindexHome], ['default', ['pilib'], null]);
    // AW_PAGEINDEX_HOME (what the SessionStart hook exports) finds the helper without any data folder.
    const viaHome = fixture('installed', {}, { route: 'pageindex' });
    try {
      const home = join(viaHome.data, 'pageindex');
      delete viaHome.env.CLAUDE_PLUGIN_DATA;
      viaHome.env.AW_PAGEINDEX_HOME = home;
      assert.equal(loadLibraryConfig(viaHome.project, viaHome.env).pageindexSource, 'installed');
    } finally { viaHome.cleanup(); }
    // A record without its private Python (or an unreadable record) is not an installed helper.
    rmSync(join(installed.data, 'pageindex', 'venv'), { recursive: true, force: true });
    assert.equal(loadLibraryConfig(installed.project, installed.env).pageindexSource, 'default');
  } finally { all.cleanup(); fileOnly.cleanup(); installed.cleanup(); none.cleanup(); }
});

test('status reports where the command came from and, with --check, what the command can do (old pilib: a warning)', async () => {
  const fx = fixture('installed', {}, { route: 'pageindex' });
  const old = fixture('wrapper', { FAKE_OLD: '1' }, { route: 'pageindex' });
  try {
    const plain = JSON.parse((await cli(fx, 'status')).out) as { pageindex_source: string; installed: { installed: boolean; tier: string; pilib_version: string }; pilib?: unknown; warnings: string[] };
    assert.deepEqual([plain.pageindex_source, plain.installed.installed, plain.installed.tier, plain.installed.pilib_version, plain.pilib], ['installed', true, 'core', '1.0.0', undefined]);
    const checked = JSON.parse((await cli(fx, 'status', '--check')).out) as { pilib: { ok: boolean; pilib_version: string; tier: string; index_trove: boolean }; warnings: string[] };
    assert.deepEqual([checked.pilib.ok, checked.pilib.pilib_version, checked.pilib.tier, checked.pilib.index_trove, checked.warnings], [true, '1.0.0', 'core', true, []]);
    const stale = JSON.parse((await cli(old, 'status', '--check')).out) as { pageindex_source: string; installed: { installed: boolean }; pilib: { index_trove: boolean }; warnings: string[] };
    assert.deepEqual([stale.pageindex_source, stale.installed.installed, stale.pilib.index_trove], ['setting', false, false]);
    assert.match(stale.warnings.join(' '), /cannot index books/);
    assert.match(stale.warnings.join(' '), /cannot read books indexed by the built-in helper/);
  } finally { fx.cleanup(); old.cleanup(); }
});

// ---------------------------------------------------------------- wiring: report --eval and eval

test('aw library report accepts --eval, rejects --run with it and a bad id', async () => {
  const fx = fixture('wrapper');
  try {
    const result = await cli(fx, 'report', '--eval', 'ev-20261020-a', '--json');
    assert.equal(result.code, 0, result.err);
    assert.equal((JSON.parse(result.out) as { eval: string }).eval, 'ev-20261020-a');
    assert.equal((await cli(fx, 'report', '--eval', 'ev-1', '--run', 'r1')).code, 2);
    assert.equal((await cli(fx, 'report', '--eval', 'bad id!')).code, 2);
    assert.match((await cli(fx, 'report', '--eval', 'ev-1', '--run', 'r1')).err, /not both/);
  } finally { fx.cleanup(); }
});

test('aw library eval is dispatched to the evaluation engine, with the engine\'s own flags and exit codes', async () => {
  const fx = fixture('wrapper');
  try {
    const noSub = await cli(fx, 'eval');
    assert.equal(noSub.code, 2);
    assert.match(noSub.err, /expected aw library eval plan\|run\|pairs\|page\|import\|unblind\|status/);
    const status = await cli(fx, 'eval', 'status', '--eval', 'ev-none');
    assert.equal(status.code, 2, status.err);
    assert.match(status.err, /library eval/);
    // Flags only the engine knows (--article, --n) pass the library parser untouched.
    const plan = await cli(fx, 'eval', 'plan', '--eval', 'ev-x', '--article', join(fx.project, 'missing.md'), '--n', '3');
    assert.notEqual(plan.code, 0);
    assert.ok(!/unknown option --article/.test(plan.err), plan.err);
  } finally { fx.cleanup(); }
});
