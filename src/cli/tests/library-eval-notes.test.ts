import { test } from 'node:test';
import assert from 'node:assert/strict';
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildPlan } from '../src/library/eval/plan.ts';
import { runEvalCli } from '../src/library/eval/cli.ts';
import { evalPaths, readJson } from '../src/library/eval/files.ts';
import { NoteResolver, fold, isIbid, loadSourceCards, matchSegment, pagesCited, surnamesOf, type SourceCard, type UnmatchedNote } from '../src/library/eval/notes.ts';
import type { Plan } from '../src/library/eval/types.ts';

const NOW = new Date('2026-10-16T10:00:00.000Z');

function fixtureDir(): string {
  let dir = dirname(fileURLToPath(import.meta.url));
  for (let up = 0; up < 8; up += 1) {
    const candidate = join(dir, 'tests', 'fixtures', 'library-eval', 'footnotes');
    if (existsSync(join(candidate, 'article.md'))) return candidate;
    dir = dirname(dir);
  }
  throw new Error('fixture tests/fixtures/library-eval/footnotes not found');
}

function projectWithFixture(): string {
  const dir = mkdtempSync(join(tmpdir(), 'aw-eval-notes-'));
  mkdirSync(join(dir, '.academic-helper', 'drafts'), { recursive: true });
  copyFileSync(join(fixtureDir(), 'sources.json'), join(dir, '.academic-helper', 'sources.json'));
  copyFileSync(join(fixtureDir(), 'article.md'), join(dir, '.academic-helper', 'drafts', 'article.md'));
  return dir;
}

const noAw = async (): Promise<string> => { throw new Error('no library is asked'); };

test('fold: case, accents, niqqud, final letters, quotes and punctuation are ignored', () => {
  assert.equal(fold('Pedersén, "South" Palace-Archives!'), fold('PEDERSEN south palace archives'));
  assert.equal(fold('לִיפְשִׁיץ'), fold('ליפשיץ'));
  assert.equal(fold('עמ׳ 5'), 'עמ 5');
  assert.equal(fold('Łódź Søren Ærø Straße'), 'lodz soren aero strasse');
});

test('surnames come from "Last, First", "First Last", several authors and lists', () => {
  assert.deepEqual(surnamesOf('Pedersén, Olof'), [['pedersen']]);
  assert.deepEqual(surnamesOf('Olof Pedersén'), [['pedersen']]);
  assert.deepEqual(surnamesOf('Alstola, Tero and Pedersén, Olof'), [['alstola'], ['pedersen']]);
  assert.deepEqual(surnamesOf(['van der Berg, Jan', { family: 'Cohen', given: 'D.' }]), [['van', 'der', 'berg'], ['cohen']]);
  assert.deepEqual(surnamesOf('ליפשיץ, עודד'), [['ליפשיצ']]);
});

test('pages cited: named pages, ranges, Hebrew forms and a bare closing number; a year is never a page', () => {
  assert.deepEqual(pagesCited('Pedersén, South Palace Archives, 14.', null), [14]);
  assert.deepEqual(pagesCited('Alstola, Judeans in Babylonia, pp. 27–29.', null), [27, 28, 29]);
  assert.deepEqual(pagesCited('ליפשיץ, יהודה בתקופה הבבלית, עמ׳ 33.', null), [33]);
  assert.deepEqual(pagesCited('Pedersén, South Palace Archives (Leiden, 2005), 14.', '2005'), [14]);
  assert.deepEqual(pagesCited('Pedersén, South Palace Archives, 2005.', '2005'), []);
  assert.deepEqual(pagesCited('Pedersén, South Palace Archives, xii.', null), []);
});

test('ibid forms: Ibid., ibidem, שם, with or without a page; a note that names an author is not one', () => {
  for (const note of ['Ibid., 15.', 'ibid.', 'Ibidem, p. 4', 'See ibid., 5', 'שם, עמ׳ 34.', 'שם']) assert.equal(isIbid(note), true, note);
  for (const note of ['Pedersén, South Palace Archives, 14.', 'Ibid. Pedersén, Archives, 3', 'שמואל, ספר, 3']) assert.equal(isIbid(note), false, note);
});

test('matchSegment: author plus distinctive title words, case, accent and niqqud insensitive; ties and strangers stay unmatched', () => {
  const cards = loadSourceCards(projectWithFixture());
  const id = (note: string): string => { const match = matchSegment(cards, note); return match.kind === 'source' ? match.card.id : match.kind === 'unmatched' ? `unmatched: ${match.reason}` : match.kind; };
  assert.equal(id('Pedersén, South Palace Archives, 14.'), 'cm-pedersen-south-palace');
  assert.equal(id('PEDERSEN, SOUTH PALACE ARCHIVES, 16.'), 'cm-pedersen-south-palace');
  assert.equal(id('Olof Pedersen, Archives and Libraries, 3'), 'cm-pedersen-assur');
  assert.equal(id('Pedersén 2005, p. 9'), 'cm-pedersen-south-palace', 'author and year, no title');
  assert.equal(id('Pedersén 1986, p. 9'), 'cm-pedersen-assur');
  assert.match(id('Pedersén, Archives, 14.'), /^unmatched: the note matches several sources equally \(cm-pedersen-south-palace, cm-pedersen-assur\)/u);
  assert.match(id('Pedersén, 14.'), /^unmatched: the author matches cm-pedersen-south-palace, cm-pedersen-assur but no title word or year/u);
  assert.match(id('Smith, Archives of Time, 3.'), /^unmatched: no source in sources.json has an author surname/u);
  assert.match(id('Alstola, Something Else Entirely, 3.'), /^unmatched: the author matches cm-alstola-judeans but no title/u);
  assert.equal(id('ליפשיץ, יהודה בתקופה הבבלית, עמ׳ 33.'), 'cm-lipschitz-judah');
  assert.equal(id('לִיפְשִׁיץ, יְהוּדָה בַּתְּקוּפָה הַבַּבְלִית, 35.'), 'cm-lipschitz-judah');
  assert.equal(id('ראו ליפשיץ, ביהודה בתקופה הבבלית, 35.'), 'cm-lipschitz-judah', 'a Hebrew prefix on a title word');
  assert.equal(id('Ibid., 3'), 'ibid');
});

test('the resolver repeats the previous source for Ibid., and never guesses when there is none or it is unmatched', () => {
  const cards: SourceCard[] = loadSourceCards(projectWithFixture());
  const first = new NoteResolver(cards);
  assert.match(first.resolve('1', 'Ibid., 3').unmatched[0]?.reason ?? '', /no earlier note/u);
  const resolver = new NoteResolver(cards);
  const a = resolver.resolve('1', 'Pedersén, South Palace Archives, 14.');
  const b = resolver.resolve('2', 'Ibid., 15.');
  assert.deepEqual([a.sources[0]?.printed, b.sources[0]?.sourceId, b.sources[0]?.printed], [[14], 'cm-pedersen-south-palace', [15]]);
  resolver.resolve('3', 'Smith, Archives of Time, 3.');
  assert.match(resolver.resolve('4', 'Ibid., 4').unmatched[0]?.reason ?? '', /previous note is unmatched/u);
  resolver.resolve('5', 'Pedersén, South Palace Archives, 14; Alstola, Judeans in Babylonia, 27.');
  assert.match(resolver.resolve('6', 'Ibid., 5').unmatched[0]?.reason ?? '', /several sources/u);
  assert.deepEqual(resolver.resolve('', '').unmatched.map((item) => item.reason), ['the note has no text to match']);
});

test('plan from a real-style article: footnotes citing author and title resolve to the right source ids and pages; the rest are listed, not guessed', async () => {
  const dir = projectWithFixture();
  try {
    const unmatched: UnmatchedNote[] = [];
    const plan = await buildPlan({ project: dir, evalId: 'ev-notes', n: 30, seed: 's', routes: ['trove', 'pageindex'], resolve: false, aw: noAw, now: NOW, unmatched });
    const byStart = (start: string) => plan.claims.find((claim) => claim.text.startsWith(start));
    const got = (start: string): unknown[] => { const claim = byStart(start); return [claim?.source_id, claim?.cited_printed_page, claim?.cited_trove_pages]; };
    assert.deepEqual(got('The palace archives of Babylon'), ['cm-pedersen-south-palace', 14, [26]]);
    assert.deepEqual(got('The same tablets'), ['cm-pedersen-south-palace', 15, [27]], 'Ibid. repeats the note before, with its own page');
    assert.deepEqual(got('Judean deportees'), ['cm-alstola-judeans', 27, [40, 41, 42]]);
    assert.deepEqual(got('Writing a note in capital letters'), ['cm-pedersen-south-palace', 16, [28]]);
    assert.deepEqual(got('המחקר העברי'), ['cm-lipschitz-judah', 33, [33]]);
    assert.deepEqual(got('המחקר ממשיך'), ['cm-lipschitz-judah', 34, [34]], 'שם repeats the Hebrew note before');
    assert.deepEqual(got('המחבר מוסיף'), ['cm-lipschitz-judah', 35, [35]], 'niqqud in the note does not matter');
    assert.deepEqual(got('A claim backed by a source id'), ['cm-alstola-judeans', 30, [43]], 'the source-id key form still works');
    assert.equal(byStart('Another study'), undefined, 'two equally good sources: never guessed');
    assert.equal(byStart('A scholar of the Assyrian'), undefined);
    assert.equal(byStart('Two works are cited together'), undefined, 'two sources in one note is ambiguous ground truth');
    assert.equal(plan.claims.length, 8);
    assert.deepEqual([plan.skipped.no_source, plan.skipped.multi_source], [2, 1]);
    assert.deepEqual(unmatched.map((item) => item.note), ['4', '5']);
    assert.match(unmatched[0]?.reason ?? '', /several sources equally/u);
    assert.match(unmatched[1]?.reason ?? '', /no source in sources.json has an author surname/u);
    assert.ok(unmatched.every((item) => item.unit === 'article' && item.text.length > 0));
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test('eval plan prints the unmatched notes, saves them beside the plan, and keeps the closed plan schema', async () => {
  const dir = projectWithFixture();
  try {
    const out: string[] = [];
    const err: string[] = [];
    const code = await runEvalCli(['plan', '--eval', 'ev-notes', '--n', '30', '--no-resolve'], { out: (t) => out.push(t), err: (t) => err.push(t), project: dir, env: process.env, awCommand: ['unused'], now: () => NOW });
    assert.equal(code, 0, err.join(''));
    const printed = JSON.parse(out.join('')) as { claims: number; unmatched_notes: { count: number; first: Array<{ note: string; reason: string }>; file: string } };
    assert.deepEqual([printed.claims, printed.unmatched_notes.count, printed.unmatched_notes.first.map((item) => item.note)], [8, 2, ['4', '5']]);
    const saved = JSON.parse(readFileSync(printed.unmatched_notes.file, 'utf8')) as { unmatched: unknown[] };
    assert.equal(saved.unmatched.length, 2);
    const paths = evalPaths(dir, 'ev-notes');
    assert.ok(await readJson(paths.plan) as Plan);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

async function planOf(article: string): Promise<{ claims: Array<{ text: string; source_id: string; cited_printed_page: number | null }>; unmatched: UnmatchedNote[]; noSource: number }> {
  const dir = projectWithFixture();
  try {
    writeFileSync(join(dir, '.academic-helper', 'drafts', 'article.md'), article);
    const unmatched: UnmatchedNote[] = [];
    const plan = await buildPlan({ project: dir, evalId: 'ev-chain', n: 30, seed: 's', routes: ['trove', 'pageindex'], resolve: false, aw: noAw, now: NOW, unmatched });
    return { claims: plan.claims, unmatched, noSource: plan.skipped.no_source };
  } finally { rmSync(dir, { recursive: true, force: true }); }
}

for (const [label, ibid, second] of [['Ibid.', 'Ibid., 9.', 'Alstola, Judeans in Babylonia, 27.'], ['שם', 'שם, עמ׳ 9.', 'Alstola, Judeans in Babylonia, 27.']] as const) {
  test(`${label} repeats the nearest earlier note even when that note sits in a sentence too short to be a claim`, async () => {
    const { claims } = await planOf([
      'The first long claim in this article rests on one source.[^1] Short one here.[^2] The third long claim repeats the note just before.[^3]',
      '',
      '[^1]: Pedersén, South Palace Archives, 14.',
      `[^2]: ${second}`,
      `[^3]: ${ibid}`,
      '',
    ].join('\n'));
    const third = claims.find((claim) => claim.text.startsWith('The third long claim'));
    assert.equal(third?.source_id, 'cm-alstola-judeans', 'the previous note is the short sentence\'s, not the first claim\'s');
    assert.equal(third?.cited_printed_page, 9);
    assert.equal(claims.find((claim) => claim.text.startsWith('The first long claim'))?.source_id, 'cm-pedersen-south-palace');
    assert.equal(claims.find((claim) => claim.text.startsWith('Short one')), undefined, 'the short sentence itself is still not a claim');
  });
}

test('a note with several citations of which only some match is unresolved, and so is an Ibid. after it', async () => {
  const { claims, unmatched, noSource } = await planOf([
    'This claim cites one known source and one unknown one.[^1] The following claim repeats that whole note.[^2] A later claim cites a known source alone.[^3]',
    '',
    '[^1]: Pedersén, South Palace Archives, 14; Unknown, Other Book, 3.',
    '[^2]: Ibid., 15.',
    '[^3]: Alstola, Judeans in Babylonia, 27.',
    '',
  ].join('\n'));
  assert.deepEqual(claims.map((claim) => claim.source_id), ['cm-alstola-judeans'], 'neither the partial note nor the Ibid. after it is a claim');
  assert.equal(noSource, 2);
  assert.deepEqual(unmatched.map((item) => item.note), ['1', '2']);
  assert.match(unmatched[0]?.reason ?? '', /partial/u);
  assert.match(unmatched[1]?.reason ?? '', /previous note is unmatched \(partial/u);
});

test('the resolver marks a partly matched note as partial with no sources, and an Ibid. after it stays unmatched', () => {
  const resolver = new NoteResolver(loadSourceCards(projectWithFixture()));
  const partial = resolver.resolve('1', 'Pedersén, South Palace Archives, 14; Unknown, Other Book, 3.');
  assert.deepEqual([partial.partial, partial.sources.length, partial.unmatched.length], [true, 0, 1]);
  assert.match(resolver.resolve('2', 'Ibid., 4').unmatched[0]?.reason ?? '', /previous note is unmatched/u);
  assert.equal(resolver.resolve('3', 'Pedersén, South Palace Archives, 14.').partial, false);
});

test('a sentence carrying an unresolved Ibid. plus a valid footnote is not a claim', async () => {
  const { claims, noSource } = await planOf([
    'This claim cites one known source and one unknown one.[^1] A later claim carries an Ibid. note and a valid one together.[^2][^3] A clean claim cites a known source alone.[^4]',
    '',
    '[^1]: Pedersén, South Palace Archives, 14; Unknown, Other Book, 3.',
    '[^2]: Ibid., 15.',
    '[^3]: Alstola, Judeans in Babylonia, 27.',
    '[^4]: Alstola, Judeans in Babylonia, 30.',
    '',
  ].join('\n'));
  assert.deepEqual(claims.map((claim) => claim.text.slice(0, 7)), ['A clean'], 'the mixed sentence is rejected whole');
  assert.equal(noSource, 2);
});
