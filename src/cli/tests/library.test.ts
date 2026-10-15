import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import libraryConfigSchema from '../../schemas/library-config.schema.json' with { type: 'json' };
import thresholds from '../../thresholds.json' with { type: 'json' };
import { Library } from '../src/library/adapter.ts';
import { libraryConfigSchema as zodSchema, loadLibraryConfig } from '../src/library/config.ts';
import { runCommand, splitCommand } from '../src/library/exec.ts';
import { formatPageRanges, parseBanners, parsePageSpec, parseSourcePageMap, printedToTrove, relabelPages, troveToRoutePages } from '../src/library/pages.ts';
import { runLibraryCli } from '../src/library/cli.ts';
import { setPathArguments } from '../src/paths.ts';
import { LibraryError } from '../src/library/types.ts';

// Fake `trove` and `pilib` commands: tiny node scripts that print fixtures, so no real library is touched.
const TROVE_FAKE = `
const fs = require('node:fs');
const args = process.argv.slice(2);
if (process.env.FAKE_LOG) fs.appendFileSync(process.env.FAKE_LOG, 'trove ' + args.join(' ') + '\\n');
if (process.env.FAKE_CWD_LOG) fs.appendFileSync(process.env.FAKE_CWD_LOG, process.cwd() + '\\n');
if (process.env.FAKE_TROVE_FAIL) { console.error('trove: boom'); process.exit(1); }
if (process.env.FAKE_TROVE_HANG) setTimeout(() => {}, 60000);
else {
  const PAGES = 5;
  const page = (n) => '── Page ' + n + ' ──\\ntrove text p' + n + '\\n';
  if (args[0] === 'shelf') console.log('No active shelf in /tmp/project');
  else if (args[0] === 'items' && args[1] === 'list') console.log(JSON.stringify({ items: [{ id: 'T-A', title: 'Book A', author: 'Au', pageCount: PAGES }] }));
  else if (args[0] === 'items' && args[1] === 'toc' && args.includes('--json')) console.log(JSON.stringify({ items: [{ id: args[2], title: 'Book A', toc: [{ title: 'Intro', page: 1, level: 1 }, { title: 'Part', page: 3, level: 2 }] }] }));
  else if (args[0] === 'items' && args[1] === 'toc') console.log('Book A\\nID: ' + args[2]);
  else if (args[0] === 'items' && args[1] === 'read') {
    let spec = args.includes('--pages') ? args[args.indexOf('--pages') + 1] : args[2].split(':')[1];
    const ids = spec === 'all' ? Array.from({ length: PAGES }, (_, i) => i + 1) : spec.split(',').flatMap((p) => { const [a, b] = p.split('-').map(Number); return Array.from({ length: (b || a) - a + 1 }, (_, i) => a + i); }).filter((n) => n <= PAGES);
    process.stdout.write('Book A\\n' + args[2].split(':')[0] + ' | ' + PAGES + ' pages\\n' + ids.map(page).join(''));
  } else { console.error('unexpected: ' + args.join(' ')); process.exit(2); }
}
`;

const PILIB_FAKE = `
const fs = require('node:fs');
const args = process.argv.slice(2);
if (process.env.FAKE_LOG) fs.appendFileSync(process.env.FAKE_LOG, 'pilib ' + args.join(' ') + '\\n');
if (process.env.FAKE_CWD_LOG) fs.appendFileSync(process.env.FAKE_CWD_LOG, process.cwd() + '\\n');
if (process.env.FAKE_PILIB_FAIL) { console.error('pilib: boom'); process.exit(1); }
if (process.env.FAKE_PILIB_HANG) setTimeout(() => {}, 60000);
else {
  // lib-a: 12 pages, same pages as Trove (exported). lib-b: rendered, 6 PDF pages -> Trove pages 1,1,2,3,3,3.
  const books = {
    'lib-a': { title: 'Library A', n_pages: 12, trove_id: 'T-A', pagemap: null },
    'lib-b': { title: 'Library B', n_pages: 6, trove_id: 'T-B', pagemap: [1, 1, 2, 3, 3, 3] },
  };
  const text = (id, n) => 'pi ' + id + ' p' + n;
  const range = (spec, max) => spec === 'all' ? Array.from({ length: max }, (_, i) => i + 1) : spec.split(',').flatMap((p) => { const [a, b] = p.split('-').map(Number); return Array.from({ length: (b || a) - a + 1 }, (_, i) => a + i); }).filter((n) => n <= max);
  const [cmd, book, spec] = args;
  if (cmd === 'catalog') console.log(JSON.stringify(Object.fromEntries(Object.entries(books).map(([id, b]) => [id, { title: b.title, author: 'Au', n_pages: b.n_pages, toc_source: 'x', top: [] }]))));
  else if (cmd === 'meta') {
    if (process.env.FAKE_NO_META || !books[book]) { console.error('no meta'); process.exit(1); }
    const b = books[book];
    console.log(JSON.stringify({ book_id: book, title: b.title, n_pages: b.n_pages, origin: { trove: { trove_id: b.trove_id } }, trove_id: b.trove_id, pagemap: b.pagemap }));
  } else if (cmd === 'tree') console.log(JSON.stringify({ book_id: book, title: books[book].title, n_pages: books[book].n_pages, structure: [{ node_id: '1', title: 'Top', start_index: 1, end_index: 4, nodes: [{ node_id: '2', title: 'Sub', start_index: 3, end_index: 4 }] }] }));
  else if (cmd === 'read') {
    const json = args.includes('--json');
    if (json && process.env.FAKE_NO_JSON) { console.error('pilib: error: unrecognized arguments: --json'); process.exit(2); }
    const dropped = (process.env.FAKE_DROP || '').split(',').filter(Boolean).map(Number);
    const pages = range(spec, books[book].n_pages).filter((n) => !dropped.includes(n));
    if (!json && pages.length > 10) { console.error('asked for ' + pages.length + ' pages; at most 10 per read'); process.exit(1); }
    if (json) console.log(JSON.stringify({ book_id: book, pages: pages.map((n) => ({ page: n, content: text(book, n) })) }));
    else pages.forEach((n) => { console.log('── Page ' + n + ' ──'); console.log(text(book, n)); });
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

function fixture(config?: unknown, extra: Record<string, string> = {}): Fixture {
  const root = mkdtempSync(join(tmpdir(), 'aw-library-'));
  const project = join(root, 'project');
  mkdirSync(join(project, '.academic-helper'), { recursive: true });
  const bin = join(root, 'bin');
  mkdirSync(bin);
  const log = join(root, 'calls.log');
  const env: NodeJS.ProcessEnv = { ...process.env, AW_TROVE_COMMAND: writeFake(bin, 'trove', TROVE_FAKE), AW_PAGEINDEX_COMMAND: writeFake(bin, 'pilib', PILIB_FAKE), FAKE_LOG: log, ...extra };
  for (const key of ['FAKE_TROVE_FAIL', 'FAKE_TROVE_HANG', 'FAKE_PILIB_FAIL', 'FAKE_PILIB_HANG', 'FAKE_NO_JSON', 'FAKE_NO_META', 'FAKE_DROP', 'FAKE_CWD_LOG']) if (!(key in extra)) delete env[key];
  if (config !== undefined) writeFileSync(join(project, '.academic-helper', 'library.json'), JSON.stringify(config), 'utf8');
  return { root, project, env, log, cleanup: () => rmSync(root, { recursive: true, force: true }) };
}

function calls(fx: Fixture): string[] { return existsSync(fx.log) ? readFileSync(fx.log, 'utf8').split('\n').filter(Boolean) : []; }

async function rejects(promise: Promise<unknown>, code: string): Promise<LibraryError> {
  try { await promise; } catch (error) {
    assert.ok(error instanceof LibraryError, `expected LibraryError, got ${String(error)}`);
    assert.equal(error.code, code, error.message);
    return error;
  }
  assert.fail(`expected a ${code} error`);
}

// ---------------------------------------------------------------- config

test('no library.json means Trove only, no shadow, not configured', () => {
  const fx = fixture();
  try {
    const config = loadLibraryConfig(fx.project, {});
    assert.deepEqual([config.configured, config.route, config.primary, config.secondary, config.shadowEnabled], [false, 'trove', 'trove', null, false]);
    assert.deepEqual(config.troveCommand, ['trove']);
    assert.deepEqual(config.pageindexCommand, ['pilib']);
  } finally { fx.cleanup(); }
});

test('both defaults to Trove answering; primary pageindex flips it; shadow can be switched off', () => {
  const both = fixture({ route: 'both' });
  const flipped = fixture({ route: 'both', primary: 'pageindex' });
  const off = fixture({ route: 'both', shadow: { enabled: false } });
  try {
    assert.deepEqual([loadLibraryConfig(both.project, {}).primary, loadLibraryConfig(both.project, {}).secondary, loadLibraryConfig(both.project, {}).shadowEnabled], ['trove', 'pageindex', true]);
    assert.deepEqual([loadLibraryConfig(flipped.project, {}).primary, loadLibraryConfig(flipped.project, {}).secondary], ['pageindex', 'trove']);
    assert.equal(loadLibraryConfig(off.project, {}).shadowEnabled, false);
  } finally { both.cleanup(); flipped.cleanup(); off.cleanup(); }
});

test('bad library.json is a config error with a plain message', () => {
  const cases: unknown[] = [{ route: 'nope' }, { route: 'trove', primary: 'pageindex' }, { route: 'both', extra: 1 }, { primary: 'trove' }];
  for (const config of cases) {
    const fx = fixture(config);
    try { assert.throws(() => loadLibraryConfig(fx.project, {}), (error: unknown) => error instanceof LibraryError && error.code === 'config'); }
    finally { fx.cleanup(); }
  }
  const broken = fixture();
  try {
    writeFileSync(join(broken.project, '.academic-helper', 'library.json'), '{not json', 'utf8');
    assert.throws(() => loadLibraryConfig(broken.project, {}), /not valid JSON/);
  } finally { broken.cleanup(); }
});

test('PageIndex command: env beats the file beats the default; words are split without a shell', () => {
  const fx = fixture({ route: 'pageindex', pageindex: { command: ['wrapper', '--flag'], shelf: 'shelf.json' } });
  try {
    assert.deepEqual(loadLibraryConfig(fx.project, {}).pageindexCommand, ['wrapper', '--flag']);
    assert.deepEqual(loadLibraryConfig(fx.project, { AW_PAGEINDEX_COMMAND: 'ssh example-host "pilib x"' }).pageindexCommand, ['ssh', 'example-host', 'pilib x']);
    assert.equal(loadLibraryConfig(fx.project, {}).shelfPath, join(fx.project, 'shelf.json'));
    assert.deepEqual(splitCommand(`a 'b c' "d e"  f`), ['a', 'b c', 'd e', 'f']);
    assert.throws(() => splitCommand('a "b'), /unbalanced/);
  } finally { fx.cleanup(); }
});

test('the JSON schema and the validator agree on the route words', () => {
  const props = libraryConfigSchema.properties;
  assert.deepEqual(props.route.enum, ['trove', 'pageindex', 'both']);
  assert.deepEqual(props.primary.enum, ['trove', 'pageindex']);
  assert.deepEqual(libraryConfigSchema.required, ['route']);
  for (const route of props.route.enum) assert.ok(zodSchema.safeParse({ route }).success);
  assert.ok(!zodSchema.safeParse({ route: 'other' }).success);
  assert.ok(!zodSchema.safeParse({ route: 'both', pageindex: { host: 'x' } }).success);
});

test('library thresholds are numbers', () => {
  const library = thresholds.library;
  for (const value of [library.timeoutMs.primary, library.timeoutMs.check, library.maxBufferBytes, library.maxRequestPages, library.maxPageNumber, library.pageindex.readChunkPages, library.pageindex.chunkConcurrency, library.pageindex.metaScanMax, library.pageindex.metaScanConcurrency]) {
    assert.ok(Number.isInteger(value) && value > 0);
  }
});

// ---------------------------------------------------------------- pages

test('page lists parse and format', () => {
  assert.deepEqual(parsePageSpec('7-9,12'), [7, 8, 9, 12]);
  assert.deepEqual(parsePageSpec(' 3 , 1-2,2 '), [1, 2, 3]);
  assert.equal(parsePageSpec('all'), 'all');
  assert.equal(formatPageRanges([12, 7, 8, 9, 7]), '7-9,12');
  for (const bad of ['', '0', '5-3', 'a', '1-', '-4']) assert.throws(() => parsePageSpec(bad), (error: unknown) => error instanceof LibraryError && error.code === 'usage', bad);
  assert.throws(() => parsePageSpec(`1-${thresholds.library.maxRequestPages + 1}`), /more than/);
});

test('banner output parses, with the header kept apart', () => {
  const parsed = parseBanners('Book A\nT-A | 5 pages\n── Page 2 ──\nalpha\nbeta\n\n── Page 3 ──\ngamma\n');
  assert.deepEqual(parsed.header, ['Book A', 'T-A | 5 pages']);
  assert.equal(parsed.pageCount, 5);
  assert.deepEqual(parsed.pages, [{ page: 2, text: 'alpha\nbeta' }, { page: 3, text: 'gamma' }]);
  const ruled = parseBanners('────────\nBook A\nID: T-A | 316 pages\n────────\n\n── Page 2 ──\nalpha\n');
  assert.deepEqual([ruled.header, ruled.pageCount], [['Book A', 'ID: T-A | 316 pages'], 316]);
  assert.deepEqual(parseBanners('no banners').pages, []);
});

test('printed pages map to Trove pages: identity, offset, crosswalk', () => {
  const fx = fixture();
  try {
    assert.deepEqual(printedToTrove([3, 4], { kind: 'identity' }, fx.project), [3, 4]);
    assert.deepEqual(printedToTrove([3, 4], { kind: 'offset', trove_minus_printed: 1 }, fx.project), [4, 5]);
    assert.throws(() => printedToTrove([1], { kind: 'offset', trove_minus_printed: -1 }, fx.project), /below Trove page 1/);
    assert.throws(() => printedToTrove([1], undefined, fx.project), /structured pageMap/);
    mkdirSync(join(fx.project, '.academic-helper', 'crosswalks'));
    writeFileSync(join(fx.project, '.academic-helper', 'crosswalks', 'a.json'), JSON.stringify({ volumes: [{ volume: 1, stored_to_ck: { '1': 2, '2': 3, '4': 5 } }, { volume: 2, stored_to_ck: { '1': 40 } }] }));
    const map = { kind: 'crosswalk' as const, file: 'crosswalks/a.json' };
    assert.deepEqual(printedToTrove([1, 2, 4], map, fx.project), [2, 3, 5]);
    assert.deepEqual(printedToTrove([1], { ...map, volume: 2 }, fx.project), [40]);
    assert.deepEqual(printedToTrove([2], { ...map, stored_minus_printed: -1 }, fx.project), [2]);
    assert.throws(() => printedToTrove([3], map, fx.project), /no Trove page/);
    assert.throws(() => printedToTrove([1], { kind: 'crosswalk', file: '../../outside.json' }, fx.project), /inside the project/);
    assert.throws(() => printedToTrove([1], { ...map, volume: 9 }, fx.project), /no volume 9/);
  } finally { fx.cleanup(); }
});

test('legacy free-text pageMap is ignored with a warning', () => {
  assert.equal(parseSourcePageMap('CK page = printed + 1').map, undefined);
  assert.match(parseSourcePageMap('CK page = printed + 1').warning ?? '', /free text/);
  assert.deepEqual(parseSourcePageMap({ kind: 'offset', trove_minus_printed: 1 }).map, { kind: 'offset', trove_minus_printed: 1 });
  assert.equal(parseSourcePageMap(undefined).warning, undefined);
});

test('Trove pages and PDF pages map both ways, many PDF pages to one Trove page', () => {
  const rp = { kind: 'pagemap' as const, pdfToTrove: [1, 1, 2, 3, 3, 3] };
  assert.deepEqual(troveToRoutePages([1, 3, 9], rp), { route: [1, 2, 4, 5, 6], missing: [9] });
  assert.deepEqual(relabelPages([{ page: 1, text: 'a' }, { page: 2, text: 'b' }, { page: 4, text: 'c' }, { page: 99, text: 'x' }], rp), [
    { page: 1, text: 'a\nb', routePages: [1, 2] }, { page: 3, text: 'c', routePages: [4] }]);
  assert.deepEqual(troveToRoutePages([4], { kind: 'identity' }), { route: [4], missing: [] });
});

// ---------------------------------------------------------------- the Trove route

test('route trove: list, toc, read pages and all come from the trove command', async () => {
  const fx = fixture();
  try {
    const library = new Library(fx.project, fx.env);
    assert.equal(library.config.configured, false);
    const list = await library.list();
    assert.deepEqual(list.items, [{ id: 'T-A', title: 'Book A', author: 'Au', pageCount: 5 }]);
    const toc = await library.toc('T-A#frag');
    assert.deepEqual(toc.toc, [{ title: 'Intro', page: 1, endPage: null, level: 1 }, { title: 'Part', page: 3, endPage: null, level: 2 }]);
    assert.equal(toc.source_id, 'T-A');
    const read = await library.read({ source: 'T-A', pages: '2-3' });
    assert.deepEqual(read.pages.map((page) => [page.trove_page, page.text]), [[2, 'trove text p2'], [3, 'trove text p3']]);
    assert.equal(read.route, 'trove');
    assert.equal(read.shadow_status, 'none');
    assert.match(read.lookup_id, /^lk_/);
    assert.deepEqual(read.missing_pages, []);
    assert.equal(read.title, 'Book A');
    const all = await library.read({ source: 'T-A', all: true });
    assert.equal(all.pages.length, 5);
    assert.equal(all.page_count, 5);
    assert.match(all.raw ?? '', /── Page 5 ──/);
    assert.ok(calls(fx).every((line) => line.startsWith('trove ')), 'pilib must not be called on route trove');
  } finally { fx.cleanup(); }
});

test('pages the route lacks are reported; none at all is an error', async () => {
  const fx = fixture();
  try {
    const library = new Library(fx.project, fx.env);
    const read = await library.read({ source: 'T-A', pages: '4-8' });
    assert.deepEqual(read.pages.map((page) => page.trove_page), [4, 5]);
    assert.deepEqual(read.missing_pages, [6, 7, 8]);
    await rejects(library.read({ source: 'T-A', pages: '8-9' }), 'page_missing');
    await rejects(library.read({ source: 'T-A' }), 'usage');
  } finally { fx.cleanup(); }
});

test('--printed uses the structured pageMap in sources.json', async () => {
  const fx = fixture();
  try {
    writeFileSync(join(fx.project, '.academic-helper', 'sources.json'), JSON.stringify([
      { sourceId: 'T-A', pageMap: { kind: 'offset', trove_minus_printed: 1 } }, { sourceId: 'T-FREE', pageMap: 'CK page = printed + 1' }]));
    const library = new Library(fx.project, fx.env);
    const read = await library.read({ source: 'T-A#note', printed: '2-3' });
    assert.deepEqual(read.pages.map((page) => page.trove_page), [3, 4]);
    assert.deepEqual(read.printed_pages, [2, 3]);
    const free = await rejects(library.read({ source: 'T-FREE', printed: '2' }), 'usage');
    assert.match(free.message, /free text/);
    await rejects(library.read({ source: 'T-NONE', printed: '2' }), 'usage');
  } finally { fx.cleanup(); }
});

// ---------------------------------------------------------------- the PageIndex route

test('route pageindex: a Trove-exported book keeps its pages; a rendered book is mapped through its pagemap', async () => {
  const fx = fixture({ route: 'pageindex' });
  try {
    const library = new Library(fx.project, fx.env);
    // lib-a is found by its Trove id (pilib meta), lib-b too; each page is relabelled to the Trove page.
    const exported = await library.read({ source: 'T-A', pages: '2-3' });
    assert.deepEqual(exported.pages.map((page) => [page.trove_page, page.text]), [[2, 'pi lib-a p2'], [3, 'pi lib-a p3']]);
    assert.equal(exported.route, 'pageindex');
    const rendered = await library.read({ source: 'T-B', pages: '1,3' });
    assert.deepEqual(rendered.pages.map((page) => [page.trove_page, page.route_pages, page.text]), [[1, [1, 2], 'pi lib-b p1\npi lib-b p2'], [3, [4, 5, 6], 'pi lib-b p4\npi lib-b p5\npi lib-b p6']]);
    const all = await library.read({ source: 'T-B', all: true });
    assert.deepEqual(all.pages.map((page) => page.trove_page), [1, 2, 3]);
    assert.ok(calls(fx).every((line) => line.startsWith('pilib ')), 'trove must not be called on route pageindex');
  } finally { fx.cleanup(); }
});

test('route pageindex: the library id works as the source id; unknown ids fail loud', async () => {
  const fx = fixture({ route: 'pageindex' });
  try {
    const library = new Library(fx.project, fx.env);
    const read = await library.read({ source: 'lib-a', pages: '1' });
    assert.equal(read.pages[0]?.text, 'pi lib-a p1');
    await rejects(library.read({ source: 'T-UNKNOWN', pages: '1' }), 'page_map');
  } finally { fx.cleanup(); }
});

test('route pageindex: the shelf map wins, and the shelf limits what is listed', async () => {
  const fx = fixture({ route: 'pageindex', pageindex: { shelf: '.academic-helper/shelf.json' } });
  try {
    writeFileSync(join(fx.project, '.academic-helper', 'shelf.json'), JSON.stringify({ books: ['lib-a'], map: { 'T-MAPPED': { book: 'lib-b', pages: { pagemap: [1, 2, 2, 2, 3, 3] } } } }));
    const library = new Library(fx.project, fx.env);
    const read = await library.read({ source: 'T-MAPPED', pages: '2' });
    assert.deepEqual(read.pages.map((page) => page.route_pages), [[2, 3, 4]]);
    const list = await library.list();
    assert.deepEqual(list.items.map((item) => item.id).sort(), ['T-MAPPED', 'lib-a']);
    // lib-b is not on the shelf by its own id, so it cannot be reached through the id scan.
    await rejects(library.read({ source: 'T-B', pages: '1' }), 'page_map');
    const toc = await library.toc('T-MAPPED');
    assert.deepEqual(toc.toc.map((entry) => [entry.title, entry.page, entry.endPage]), [['Top', 1, 2], ['Sub', 2, 2]]);
  } finally { fx.cleanup(); }
});

test('shelf map without pages asks pilib meta; without meta it fails loud', async () => {
  const shelf = { books: ['lib-b'], map: { 'T-B': { book: 'lib-b' } } };
  const fx = fixture({ route: 'pageindex', pageindex: { shelf: 'shelf.json' } });
  const noMeta = fixture({ route: 'pageindex', pageindex: { shelf: 'shelf.json' } }, { FAKE_NO_META: '1' });
  try {
    writeFileSync(join(fx.project, 'shelf.json'), JSON.stringify(shelf));
    writeFileSync(join(noMeta.project, 'shelf.json'), JSON.stringify(shelf));
    assert.deepEqual((await new Library(fx.project, fx.env).read({ source: 'T-B', pages: '2' })).pages.map((page) => page.route_pages), [[3]]);
    await rejects(new Library(noMeta.project, noMeta.env).read({ source: 'T-B', pages: '2' }), 'page_map');
  } finally { fx.cleanup(); noMeta.cleanup(); }
});

test('pilib without read --json is read in chunks of ten pages', async () => {
  const fx = fixture({ route: 'pageindex' }, { FAKE_NO_JSON: '1' });
  try {
    const library = new Library(fx.project, fx.env);
    const all = await library.read({ source: 'lib-a', all: true });
    assert.equal(all.pages.length, 12);
    assert.equal(all.pages[11]?.text, 'pi lib-a p12');
    const plainReads = calls(fx).filter((line) => /^pilib read lib-a \S+$/.test(line)).sort();
    assert.deepEqual(plainReads, ['pilib read lib-a 1-10', 'pilib read lib-a 11-12']);
  } finally { fx.cleanup(); }
});

test('pilib with read --json reads a whole book in one call', async () => {
  const fx = fixture({ route: 'pageindex' });
  try {
    await new Library(fx.project, fx.env).read({ source: 'lib-a', all: true });
    assert.equal(calls(fx).filter((line) => line.startsWith('pilib read ')).length, 1);
    assert.ok(calls(fx).some((line) => line === 'pilib read lib-a all --json'));
  } finally { fx.cleanup(); }
});

// ---------------------------------------------------------------- both: primary only

test('route both runs the primary only; the shadow is stubbed as disabled', async () => {
  const trovePrimary = fixture({ route: 'both' });
  const pageindexPrimary = fixture({ route: 'both', primary: 'pageindex' });
  try {
    const a = await new Library(trovePrimary.project, trovePrimary.env).read({ source: 'T-A', pages: '2' });
    assert.deepEqual([a.route, a.mode, a.shadow_status, a.pages[0]?.text], ['trove', 'both', 'disabled', 'trove text p2']);
    assert.ok(calls(trovePrimary).every((line) => line.startsWith('trove ')));
    const b = await new Library(pageindexPrimary.project, pageindexPrimary.env).read({ source: 'T-A', pages: '2' });
    assert.deepEqual([b.route, b.shadow_status, b.pages[0]?.text], ['pageindex', 'disabled', 'pi lib-a p2']);
    assert.ok(calls(pageindexPrimary).every((line) => line.startsWith('pilib ')));
  } finally { trovePrimary.cleanup(); pageindexPrimary.cleanup(); }
});

test('a failing or hanging primary fails the call: no fallback to the other route', async () => {
  const failing = fixture({ route: 'both', primary: 'pageindex' }, { FAKE_PILIB_FAIL: '1' });
  const hanging = fixture({ route: 'both' }, { FAKE_TROVE_HANG: '1', AW_LIBRARY_TIMEOUT_MS: '400' });
  try {
    const error = await rejects(new Library(failing.project, failing.env).read({ source: 'T-A', pages: '1' }), 'exit');
    assert.match(error.message, /boom/);
    assert.ok(calls(failing).every((line) => line.startsWith('pilib ')), 'the other route must not answer in its place');
    const started = Date.now();
    await rejects(new Library(hanging.project, hanging.env).read({ source: 'T-A', pages: '1' }), 'timeout');
    assert.ok(Date.now() - started < 5000, 'a hanging route is cut off at the deadline');
  } finally { failing.cleanup(); hanging.cleanup(); }
});

test('runCommand settles at the deadline even when a child keeps the pipe open', async () => {
  const fx = fixture();
  try {
    const script = join(fx.root, 'bin', 'sleeper');
    writeFileSync(script, '#!/bin/sh\nsleep 30\n', 'utf8');
    chmodSync(script, 0o755);
    const started = Date.now();
    await rejects(runCommand([script], [], { timeoutMs: 300, maxBuffer: 1024 }), 'timeout');
    assert.ok(Date.now() - started < 3000);
    await rejects(runCommand([join(fx.root, 'missing-command')], [], { timeoutMs: 1000, maxBuffer: 1024 }), 'spawn');
  } finally { fx.cleanup(); }
});

// ---------------------------------------------------------------- status and CLI

test('status reports the route; --check probes each route in play', async () => {
  const fx = fixture({ route: 'both' }, { FAKE_PILIB_FAIL: '1' });
  try {
    const library = new Library(fx.project, fx.env);
    const plain = await library.status(false);
    assert.deepEqual([plain.route, plain.primary, plain.secondary, plain.configured, plain.enabled], ['both', 'trove', 'pageindex', true, true]);
    assert.equal(plain.check, undefined);
    const checked = await library.status(true) as { check: Record<string, { ok: boolean; count: number | null; error: string | null }> };
    assert.equal(checked.check.trove?.ok, true);
    assert.equal(checked.check.trove?.count, 1);
    assert.equal(checked.check.pageindex?.ok, false);
    assert.match(checked.check.pageindex?.error ?? '', /boom/);
  } finally { fx.cleanup(); }
});

test('status: a profile that turns Trove off makes the Trove route disabled', async () => {
  const fx = fixture();
  try {
    writeFileSync(join(fx.project, '.academic-helper', 'profile.md'), '# Academic Writer Profile\n\n## Tools\n\n```json\n{ "trove": { "enabled": false } }\n```\n');
    assert.equal((await new Library(fx.project, fx.env).status(false)).enabled, false);
    writeFileSync(join(fx.project, '.academic-helper', 'library.json'), JSON.stringify({ route: 'pageindex' }));
    assert.equal((await new Library(fx.project, fx.env).status(false)).enabled, true);
  } finally { fx.cleanup(); }
});

async function cli(fx: Fixture, ...argv: string[]): Promise<{ code: number; out: string; err: string }> {
  const saved = { ...process.env };
  let out = '';
  let err = '';
  Object.assign(process.env, fx.env);
  setPathArguments(['--project-dir', fx.project]);
  try {
    const code = await runLibraryCli(argv, { out: (text) => { out += text; }, err: (text) => { err += text; } });
    return { code, out, err };
  } finally {
    for (const key of Object.keys(process.env)) if (!(key in saved)) delete process.env[key];
    Object.assign(process.env, saved);
  }
}

test('aw library: JSON on stdout, exit 0; usage 2; config 3; failed primary 4', async () => {
  const fx = fixture({ route: 'pageindex' });
  try {
    const read = await cli(fx, 'read', '--source', 'T-A', '--pages', '2');
    assert.equal(read.code, 0, read.err);
    const parsed = JSON.parse(read.out) as { route: string; pages: Array<{ trove_page: number; text: string }>; raw?: string };
    assert.deepEqual([parsed.route, parsed.pages[0]?.trove_page, parsed.pages[0]?.text], ['pageindex', 2, 'pi lib-a p2']);
    assert.equal(parsed.raw, undefined);
    const text = await cli(fx, 'read', '--source', 'T-A', '--pages', '2', '--text');
    assert.equal(text.out, '── Page 2 ──\npi lib-a p2\n');
    const get = await cli(fx, 'get', '--source', 'T-A');
    assert.equal((JSON.parse(get.out) as { pages: unknown[] }).pages.length, 12);
    assert.equal((await cli(fx, 'read', '--pages', '2')).code, 2);
    assert.equal((await cli(fx, 'read', '--source', 'T-A')).code, 2);
    assert.equal((await cli(fx, 'read', '--source', 'T-A', '--bogus')).code, 2);
    assert.equal((await cli(fx, 'nonsense')).code, 2);
    assert.equal((await cli(fx, 'read', '--source', 'T-UNKNOWN', '--pages', '1')).code, 4);
    assert.equal((await cli(fx, 'status')).code, 0);
    writeFileSync(join(fx.project, '.academic-helper', 'library.json'), '{"route":"x"}');
    assert.equal((await cli(fx, 'status')).code, 3);
  } finally { fx.cleanup(); }
});

test('aw library with no library.json behaves as route trove', async () => {
  const fx = fixture();
  try {
    const status = JSON.parse((await cli(fx, 'status')).out) as { route: string; configured: boolean };
    assert.deepEqual([status.route, status.configured], ['trove', false]);
    const list = JSON.parse((await cli(fx, 'list')).out) as { route: string; items: unknown[] };
    assert.deepEqual([list.route, list.items.length], ['trove', 1]);
  } finally { fx.cleanup(); }
});

// ---------------------------------------------------------------- review findings (T1-fix)

test('page specs beyond the sane maximum are usage errors, never a hang', () => {
  const max = thresholds.library.maxPageNumber;
  const usage = (error: unknown): boolean => error instanceof LibraryError && error.code === 'usage';
  for (const bad of ['9007199254740992', '9007199254740993-9007199254740995', `${max + 1}`, `${max}-${max + 1}`, '1,9007199254740992']) assert.throws(() => parsePageSpec(bad), usage, bad);
  assert.deepEqual(parsePageSpec(`${max}`), [max]);
});

test('a configured shelf that is missing, unreadable or malformed is a config error, not an open catalog', async () => {
  const cases: Array<[string, (project: string) => void]> = [
    ['missing', () => undefined],
    ['unreadable (a directory)', (project) => mkdirSync(join(project, 'shelf.json'))],
    ['not JSON', (project) => writeFileSync(join(project, 'shelf.json'), '{nope')],
    ['wrong shape', (project) => writeFileSync(join(project, 'shelf.json'), '{"shelf":["lib-a"]}')],
    ['books not strings', (project) => writeFileSync(join(project, 'shelf.json'), '{"books":[1,2]}')],
    ['a JSON scalar', (project) => writeFileSync(join(project, 'shelf.json'), '3')],
  ];
  for (const [label, prepare] of cases) {
    const fx = fixture({ route: 'pageindex', pageindex: { shelf: 'shelf.json' } });
    try {
      prepare(fx.project);
      await rejects(new Library(fx.project, fx.env).list(), 'config');
      await rejects(new Library(fx.project, fx.env).read({ source: 'lib-a', pages: '1' }), 'config');
      const out = await cli(fx, 'list');
      assert.equal(out.code, 3, `${label}: ${out.err}`);
      assert.match(out.err, /shelf/iu, label);
      assert.equal(out.out, '', `${label}: nothing may be listed`);
    } finally { fx.cleanup(); }
  }
  // Unconfigured stays "no restriction"; a shelf with only a map restricts to the mapped books.
  const open = fixture({ route: 'pageindex' });
  const mapOnly = fixture({ route: 'pageindex', pageindex: { shelf: 'shelf.json' } });
  try {
    assert.equal((await new Library(open.project, open.env).list()).items.length, 2);
    writeFileSync(join(mapOnly.project, 'shelf.json'), JSON.stringify({ map: { 'T-A': { book: 'lib-a', pages: 'identity' } } }));
    assert.deepEqual((await new Library(mapOnly.project, mapOnly.env).list()).items.map((item) => item.id), ['T-A']);
  } finally { open.cleanup(); mapOnly.cleanup(); }
});

test('a Trove page spilling over several PDF pages is complete only when every PDF page came back', async () => {
  const half = fixture({ route: 'pageindex' }, { FAKE_DROP: '2' });
  const none = fixture({ route: 'pageindex' }, { FAKE_DROP: '1,2' });
  const whole = fixture({ route: 'pageindex' }, { FAKE_DROP: '5' });
  try {
    // lib-b maps PDF pages 1..6 to Trove 1,1,2,3,3,3; PDF page 2 is missing, so Trove page 1 is incomplete.
    const read = await new Library(half.project, half.env).read({ source: 'T-B', pages: '1-3' });
    assert.deepEqual(read.pages.map((page) => page.trove_page), [2, 3]);
    assert.deepEqual(read.missing_pages, [1]);
    await rejects(new Library(half.project, half.env).read({ source: 'T-B', pages: '1' }), 'page_missing');
    const gone = await new Library(none.project, none.env).read({ source: 'T-B', pages: '1-2' });
    assert.deepEqual([gone.pages.map((page) => page.trove_page), gone.missing_pages], [[2], [1]]);
    // Trove page 3 has PDF pages 4,5,6; with 5 missing it is incomplete too, and `all` says so.
    const all = await new Library(whole.project, whole.env).read({ source: 'T-B', all: true });
    assert.deepEqual([all.pages.map((page) => page.trove_page), all.missing_pages], [[1, 2], [3]]);
  } finally { half.cleanup(); none.cleanup(); whole.cleanup(); }
});

test('the project dir is the working directory of the trove and pilib children', async () => {
  const fx = fixture({ route: 'both' }, {});
  const pageindex = fixture({ route: 'pageindex' }, {});
  try {
    for (const [target, route] of [[fx, 'trove'], [pageindex, 'pageindex']] as const) {
      const cwdLog = join(target.root, 'cwd.log');
      const env = { ...target.env, FAKE_CWD_LOG: cwdLog };
      assert.notEqual(realpathSync(process.cwd()), realpathSync(target.project));
      await new Library(target.project, env).read({ source: route === 'trove' ? 'T-A' : 'lib-a', pages: '1' });
      const seen = readFileSync(cwdLog, 'utf8').split('\n').filter(Boolean);
      assert.ok(seen.length > 0, route);
      for (const dir of seen) assert.equal(realpathSync(dir), realpathSync(target.project), route);
    }
  } finally { fx.cleanup(); pageindex.cleanup(); }
});
