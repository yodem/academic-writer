import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, readdirSync, mkdtempSync, readFileSync, rmSync, statSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import thresholds from '../../thresholds.json' with { type: 'json' };
import type { AwCall } from '../src/library/eval/aw.ts';
import { pagesNamedIn, parseDraft, splitSentences } from '../src/library/eval/claims.ts';
import { evalPaths, readJson, validate, writeJson } from '../src/library/eval/files.ts';
import { importJudgments, normalizeImport } from '../src/library/eval/judgments.ts';
import { TEXT_UNAVAILABLE, buildPairs, routeLeak } from '../src/library/eval/pairs.ts';
import { buildPlan } from '../src/library/eval/plan.ts';
import { claimSha, fingerprintOf, planSha } from '../src/library/eval/runner.ts';
import { mappingCommitment, seededRandom, shuffle, slotOrders } from '../src/library/eval/seal.ts';
import { median, signTestP, wilson95 } from '../src/library/eval/stats.ts';
import { unblind } from '../src/library/eval/unblind.ts';
import { runEvalCli } from '../src/library/eval/cli.ts';
import type { Claim, Mapping, Pairs, Plan, Route, Run } from '../src/library/eval/types.ts';

const NOW = new Date('2026-10-16T10:00:00.000Z');
const minPairs = thresholds.library.eval.minPairs;

function project(): string {
  const dir = mkdtempSync(join(tmpdir(), 'aw-eval-test-'));
  mkdirSync(join(dir, '.academic-helper', 'drafts'), { recursive: true });
  return dir;
}

function write(dir: string, rel: string, text: string): void {
  mkdirSync(join(dir, rel, '..'), { recursive: true });
  writeFileSync(join(dir, rel), text, 'utf8');
}

// ------------------------------------------------------------------ statistics and shuffles

test('statistics: median, sign test and Wilson interval give the textbook numbers', () => {
  assert.equal(median([]), null);
  assert.equal(median([3, 1, 2]), 2);
  assert.equal(median([4, 1, 2, 3]), 2.5);
  assert.ok(Math.abs(signTestP(8, 10) - 0.109375) < 1e-9);
  assert.ok(Math.abs(signTestP(7, 9) - 0.1796875) < 1e-9);
  assert.ok(Math.abs(signTestP(5, 10) - 1) < 1e-9);
  assert.equal(signTestP(0, 0), 1);
  const [low, high] = wilson95(8, 10) as [number, number];
  assert.ok(Math.abs(low - 0.4902) < 0.001 && Math.abs(high - 0.9433) < 0.001, `${low} ${high}`);
  assert.equal(wilson95(0, 0), null);
  const [zeroLow, zeroHigh] = wilson95(0, 5) as [number, number];
  assert.equal(zeroLow, 0);
  assert.ok(zeroHigh > 0.4 && zeroHigh < 0.5);
});

test('the seeded shuffle repeats for one seed, differs for another, and slot orders are balanced', () => {
  const items = Array.from({ length: 20 }, (_, index) => index);
  assert.deepEqual(shuffle(items, seededRandom('seed-1')), shuffle(items, seededRandom('seed-1')));
  assert.notDeepEqual(shuffle(items, seededRandom('seed-1')), shuffle(items, seededRandom('seed-2')));
  assert.deepEqual([...shuffle(items, seededRandom('seed-1'))].sort((a, b) => a - b), items);
  for (const n of [1, 2, 7, 12]) {
    const orders = slotOrders(n, seededRandom(`s${n}`));
    assert.equal(orders.length, n);
    assert.equal(orders.filter(Boolean).length, Math.ceil(n / 2));
  }
});

// ------------------------------------------------------------------ claims from a draft

test('sentences: a footnote marker after the full stop stays with its sentence; abbreviations do not split', () => {
  const parts = splitSentences('Scholars (e.g. Smith) agree.[^a] A second point follows! A third? Yes. Initials like A. Cohen matter.[^b]');
  assert.equal(parts.length, 5);
  assert.ok(parts[0]?.endsWith('[^a]'));
  assert.ok(parts[4]?.includes('A. Cohen'));
  assert.deepEqual(splitSentences('פסוק ראשון הוא כך׃[^x] ועוד משפט.'), ['פסוק ראשון הוא כך׃[^x]', 'ועוד משפט.']);
});

test('page numbers named in a citation: English and Hebrew forms, ranges', () => {
  assert.deepEqual(pagesNamedIn('Au, Book A, p. 12.'), [12]);
  assert.deepEqual(pagesNamedIn('Au, Book A, pp. 12-14.'), [12, 13, 14]);
  assert.deepEqual(pagesNamedIn('מחבר, ספר, עמ׳ 33.'), [33]);
  assert.deepEqual(pagesNamedIn('no page here'), []);
});

test('parseDraft numbers paragraphs like the auditor (<unit>_p_<n>), strips markers and keeps the definitions', () => {
  const draft = parseDraft([
    '# Heading', '',
    'The ancient city was rebuilt twice in the sixth century.[^a1] A short one.[^a1]', '',
    'עיר הבירה נבנתה מחדש פעמיים במאה השישית לפני הספירה.[^a2]', '',
    '[^a1]: Au, Book A, p. 12.', '[^a2]: מחבר, ספר ב, עמ׳ 33.',
  ].join('\n'), 'u1');
  assert.deepEqual(draft.sentences.map((s) => [s.paragraphId, s.keys, s.text]), [
    ['u1_p_1', ['a1'], 'The ancient city was rebuilt twice in the sixth century.'],
    ['u1_p_1', ['a1'], 'A short one.'],
    ['u1_p_2', ['a2'], 'עיר הבירה נבנתה מחדש פעמיים במאה השישית לפני הספירה.'],
  ]);
  assert.equal(draft.definitions.get('a1'), 'Au, Book A, p. 12.');
});

// ------------------------------------------------------------------ plan

function listAw(ids: Record<Route, string[]>): (call: AwCall) => Promise<string> {
  return async (call) => {
    assert.deepEqual(call.args, ['list']);
    return JSON.stringify({ items: ids[call.route].map((id) => ({ id, title: id })) });
  };
}

function articleProject(): string {
  const dir = project();
  write(dir, '.academic-helper/sources.json', JSON.stringify([
    { sourceId: 'T-A', workTitle: 'Book A', pageMap: { kind: 'offset', trove_minus_printed: 2 } },
    { sourceId: 'T-B', workTitle: 'ספר ב', pageMap: { kind: 'identity' } },
    { sourceId: 'T-C', workTitle: 'Book C' },
    { sourceId: 'T-D', workTitle: 'Book D' },
  ]));
  write(dir, '.academic-helper/evidence.json', JSON.stringify({
    sources: [{ id: 'T-D', title: 'Book D', author: 'x', role: 'primary', isCoreText: true }],
    passages: [{ id: 'p1', sourceId: 'T-D', locator: 'Page 9 (orig. 4)', quote: 'q', gloss: 'g', relevance: 2 }],
  }));
  const body: string[] = [];
  for (let i = 1; i <= 4; i += 1) body.push(`Claim number ${i} about the first book is stated plainly here today.[^T-A]`);
  for (let i = 1; i <= 3; i += 1) body.push(`טענה מספר ${i} על הספר השני נאמרת כאן בבירור מלא.[^T-B]`);
  body.push('The third book holds one more claim that is long enough to count.[^T-C]');
  body.push('The fourth book says something about a passage cited by its evidence id.[^p1]');
  body.push('A sentence citing two sources at once is ambiguous for ground truth.[^T-A][^T-B]');
  body.push('Too short.[^T-A]');
  write(dir, '.academic-helper/drafts/u1.md', [
    body.join(' '), '',
    '[^T-A]: Au, Book A, p. 10.', '[^T-B]: מחבר, ספר ב, עמ׳ 7.', '[^T-C]: Au, Book C.',
  ].join('\n'));
  return dir;
}

test('plan: claims come from footnoted sentences, spread over sources, same seed gives the same plan', async () => {
  const dir = articleProject();
  const aw = listAw({ trove: ['T-A', 'T-B', 'T-C', 'T-D'], pageindex: ['T-A', 'T-B', 'T-C', 'T-D'] });
  const make = (seed: string, n: number) => buildPlan({ project: dir, evalId: 'ev-test', n, seed, routes: ['trove', 'pageindex'], resolve: true, aw, now: NOW });
  const plan = await make('s1', 6);
  assert.deepEqual(validate('plan', plan), []);
  assert.equal(plan.claims.length, 6);
  assert.deepEqual(plan.skipped, { too_short: 1, no_source: 0, multi_source: 1, unresolved: 0, over_cap: 3 });
  const perSource = new Map<string, number>();
  for (const claim of plan.claims) perSource.set(claim.source_id, (perSource.get(claim.source_id) ?? 0) + 1);
  assert.ok([...perSource.values()].every((count) => count <= 2), JSON.stringify([...perSource]));
  assert.deepEqual(plan.claims.map((claim) => claim.id), ['c01', 'c02', 'c03', 'c04', 'c05', 'c06']);
  assert.deepEqual(await make('s1', 6), plan);
  assert.notDeepEqual((await make('other-seed', 6)).claims.map((c) => c.text), plan.claims.map((c) => c.text));
  // Cited pages: printed 10 + offset 2 = Trove 12; Hebrew "עמ׳ 7" with an identity map; the evidence passage's own Trove page.
  const byText = new Map((await make('s1', 9)).claims.map((claim) => [claim.source_id, claim]));
  assert.deepEqual([byText.get('T-A')?.cited_trove_pages, byText.get('T-A')?.cited_printed_page], [[12], 10]);
  assert.deepEqual(byText.get('T-B')?.cited_trove_pages, [7]);
  assert.deepEqual([byText.get('T-D')?.cited_trove_pages, byText.get('T-D')?.cited_printed_page], [[9], 4]);
  assert.deepEqual(byText.get('T-C')?.cited_trove_pages, []);
  assert.ok(byText.get('T-B')?.text.includes('טענה מספר'));
  rmSync(dir, { recursive: true, force: true });
});

test('plan: a source that does not answer on every route is dropped; the claims file and limits are enforced', async () => {
  const dir = articleProject();
  const aw = listAw({ trove: ['T-A', 'T-B', 'T-C', 'T-D'], pageindex: ['T-A', 'T-C'] });
  const plan = await buildPlan({ project: dir, evalId: 'ev-test', n: 12, seed: 's', routes: ['trove', 'pageindex'], resolve: true, aw, now: NOW });
  assert.deepEqual([...new Set(plan.claims.map((claim) => claim.source_id))].sort(), ['T-A', 'T-C']);
  assert.equal(plan.skipped.unresolved, 4);
  assert.ok(plan.estimate.usd > 0 && plan.estimate.runs === plan.claims.length * 2);
  await assert.rejects(buildPlan({ project: dir, evalId: 'ev-test', n: thresholds.library.eval.maxClaims + 1, seed: 's', routes: ['trove', 'pageindex'], resolve: false, aw, now: NOW }), /--n must be between/);
  write(dir, 'mine.json', JSON.stringify([{ text: 'My own claim about the book that is long enough.', source: 'T-A', trove_pages: [3], printed_page: 1 }, { text: 'short', source: 'T-A' }]));
  const own = await buildPlan({ project: dir, evalId: 'ev-test', n: 5, seed: 's', routes: ['trove', 'pageindex'], claimsFile: 'mine.json', resolve: false, aw, now: NOW });
  assert.equal(own.claims.length, 1);
  assert.deepEqual([own.claims[0]?.cited_trove_pages, own.skipped.too_short], [[3], 1]);
  rmSync(dir, { recursive: true, force: true });
});

test('plan: the auditor verdict recorded for the claim paragraph and source is joined from the retrieval ledger', async () => {
  const dir = articleProject();
  const row = (extra: object) => JSON.stringify(extra);
  write(dir, '.academic-helper/retrieval.jsonl', [
    row({ row_type: 'lookup', schema: 1, ts: NOW.toISOString(), lookup_id: 'lk_1', run_id: 'R1', claim_id: null, op: 'read', source_id: 'T-A', mode: 'both', route_primary: 'trove', book_by_route: { trove: 'T-A', pageindex: null }, request: { printed: null, trove_pages: '12' }, primary: { route: 'trove', ok: true, route_pages: null, latency_ms: 5, bytes: 1, chars: 1, text_sha: null, error: null, error_code: null }, shadow_status: 'none' }),
    row({ row_type: 'verdict', schema: 1, ts: NOW.toISOString(), lookup_id: 'lk_1', run_id: 'R1', paragraph_id: 'u1_p_1', verdict_at: '1760526000000000001', pid: 1, nonce: 'aaaaaaaaaaaaaaaa', verdict: 'FAIL', corrected_page: 15, shadow_supports: null, shadow_supports_reason: 'no_quote', primary_route: 'trove', mode: 'both' }),
    row({ row_type: 'verdict', schema: 1, ts: NOW.toISOString(), lookup_id: 'lk_1', run_id: 'R1', paragraph_id: 'u1_p_1', verdict_at: '1760526000000000009', pid: 1, nonce: 'bbbbbbbbbbbbbbbb', verdict: 'PASS', corrected_page: null, shadow_supports: null, shadow_supports_reason: 'no_quote', primary_route: 'trove', mode: 'both' }),
  ].join('\n') + '\n');
  const plan = await buildPlan({ project: dir, evalId: 'ev-test', n: 12, seed: 's', routes: ['trove', 'pageindex'], resolve: false, aw: listAw({ trove: [], pageindex: [] }), now: NOW });
  const verdicts = plan.claims.filter((claim) => claim.source_id === 'T-A').map((claim) => claim.auditor_verdict);
  assert.ok(verdicts.every((verdict) => verdict === 'PASS'), JSON.stringify(verdicts));
  assert.ok(plan.claims.filter((claim) => claim.source_id !== 'T-A').every((claim) => claim.auditor_verdict === null));
  rmSync(dir, { recursive: true, force: true });
});

// ------------------------------------------------------------------ pairs, seal, import, unblind

type Scenario = { dir: string; plan: Plan; paths: ReturnType<typeof evalPaths> };

/** A project whose plan and finished runs are written directly: `pages[claimIndex][route]` is what each route answered. */
async function scenario(pages: Array<Record<Route, number[] | null>>, over: { auditor?: Array<'PASS' | 'FAIL' | null> } = {}): Promise<Scenario> {
  const dir = project();
  const claims: Claim[] = pages.map((_entry, index) => ({
    id: `c${String(index + 1).padStart(2, '0')}`, text: index % 2 === 0 ? `Claim ${index + 1} about the book, stated in full.` : `טענה ${index + 1} על הספר, כתובה במלואה.`,
    source_id: 'T-A', source_title: 'Book A', cited_trove_pages: [3], cited_printed_page: 1, paragraph_id: `u1_p_${index + 1}`,
    auditor_verdict: over.auditor?.[index] ?? null, corrected_page: null,
  }));
  const plan: Plan = {
    schema: 1, eval_id: 'ev-test', created_at: NOW.toISOString(), article: null, seed: 's', routes: ['trove', 'pageindex'],
    shelf: [{ id: 'T-A', title: 'Book A' }], claims, skipped: { too_short: 0, no_source: 0, multi_source: 0, unresolved: 0, over_cap: 0 }, estimate: { runs: claims.length * 2, usd: 1 },
  };
  const paths = evalPaths(dir, 'ev-test');
  await writeJson(paths.plan, plan);
  for (const [index, claim] of claims.entries()) {
    for (const route of ['trove', 'pageindex'] as Route[]) {
      const answer = pages[index]?.[route] ?? null;
      const run: Run = {
        schema: 1, eval_id: 'ev-test', claim_id: claim.id, route, engine: 'claude', model: 'm', status: answer ? 'ok' : 'error', attempts: 1, started_at: NOW.toISOString(),
        answer: answer ? { book: 'T-A', pages: answer, reason: 'the trove tree node says so' } : null, tool_calls: [], n_reads: 1, n_toc: 1, pages_per_read: [2], over_budget: false, permission_denials: 0,
        wall_ms: route === 'trove' ? 4000 : 6000, agent_ms: 1000, turns: 3, input_tokens: route === 'trove' ? 1000 : 2000, output_tokens: 100, cost_usd: route === 'trove' ? 0.05 : 0.07,
        returned_chars: 500, returned_est_tokens: route === 'trove' ? 200 : 300, agent_version: '1.0.0', error: answer ? null : 'no answer',
        plan_sha256: planSha(plan), claim_sha256: claimSha(claim), prompt_version: 'locate-v2', model_requested: 'm', violations: [],
        fingerprint: fingerprintOf({ plan_sha256: planSha(plan), claim_sha256: claimSha(claim), claim_id: claim.id, route, engine: 'claude', model_requested: 'm', prompt_version: 'locate-v2' }),
      };
      await writeJson(join(paths.runsDir, `${claim.id}-${route}.json`), run);
    }
  }
  return { dir, plan, paths };
}

const readAw = async (call: AwCall): Promise<string> => {
  assert.equal(call.route, 'trove', 'the page text is read through one library only');
  const spec = String(call.args[call.args.indexOf('--pages') + 1]);
  const pages = spec.split(',').flatMap((part) => { const [a, b] = part.split('-').map(Number); return Array.from({ length: (b ?? a ?? 0) - (a ?? 0) + 1 }, (_, i) => (a ?? 0) + i); });
  return JSON.stringify({ pages: pages.map((page) => ({ trove_page: page, text: `Text of page ${page}. עמוד ${page}.` })) });
};

const SPLIT: Array<Record<Route, number[] | null>> = [
  { trove: [3], pageindex: [3] },          // identical
  { trove: [3], pageindex: [5] },
  { trove: [5, 3], pageindex: [4] },
  { trove: [2], pageindex: [3] },
  { trove: [3], pageindex: [3, 4] },
  { trove: [3], pageindex: null },         // one route found nothing
  { trove: [6], pageindex: [3] },
  { trove: [3], pageindex: [8] },
  { trove: [3], pageindex: [9] },
  { trove: [7], pageindex: [3] },
];

test('pairs: anonymous, sealed and committed; identical pages are marked same but still shown', async () => {
  const { dir, plan, paths } = await scenario(SPLIT);
  const { pairs, mapping, summary } = await buildPairs({ evalId: 'ev-test', paths, plan, seed: 'seed-x', aw: readAw, now: NOW, force: false });
  assert.deepEqual([summary.pairs, summary.auto_same], [10, 1]);
  assert.deepEqual(validate('pairs', pairs), []);
  assert.deepEqual(validate('mapping', mapping), []);
  assert.equal(pairs.pairs[0]?.auto_same, true);
  assert.equal(pairs.pairs[0]?.options.A.pages.length, 1, 'an identical pair still shows its pages');
  // Page order inside an option is sorted; both options show the same canonical text.
  assert.deepEqual(pairs.pairs.find((pair) => pair.claim.id === 'c03')?.options && [pairs.pairs[2]?.options.A.pages.map((p) => p.page), pairs.pairs[2]?.options.B.pages.map((p) => p.page)].map((p) => p?.join()).sort(), ['3,5', '4']);
  assert.equal(pairs.pairs[5]?.options.A.pages.length === 0 || pairs.pairs[5]?.options.B.pages.length === 0, true);
  // Judge-visible file: no route names, no timing, tokens, cost, reasons or tool vocabulary.
  const shown = readFileSync(paths.pairs, 'utf8');
  assert.ok(!/trove|pageindex|node|tree|latency|token|cost|reason|route|wall/iu.test(shown.replace(/Text of page/gu, '')), 'pairs.json leaks');
  assert.equal(routeLeak(pairs), null);
  assert.equal(routeLeak({ ...pairs, pairs: [{ ...pairs.pairs[0] as Pairs['pairs'][number], pair_id: 'p01', options: { ...(pairs.pairs[0] as Pairs['pairs'][number]).options, A: { book: 'trove-1', book_title: 'x', pages: [] } } }] }) !== null, true);
  // Sealed mapping: private modes, balanced, commitment matches.
  assert.equal(statSync(paths.mapping).mode & 0o777, 0o600);
  assert.equal(statSync(paths.sealedDir).mode & 0o777, 0o700);
  assert.equal(pairs.mapping_sha256, mappingCommitment(mapping));
  assert.equal(mapping.pairs.filter((pair) => pair.A === 'trove').length, 5);
  assert.notEqual(JSON.stringify(mapping).includes('seed-x'), false, 'the seed lives only in the sealed file');
  assert.ok(!shown.includes('seed-x') && !shown.includes(mapping.nonce));
  rmSync(dir, { recursive: true, force: true });
});

test('pairs: the same seed gives the same hidden order; another seed does not; pairing twice needs --force and never after judging', async () => {
  const { dir, plan, paths } = await scenario(SPLIT);
  const first = await buildPairs({ evalId: 'ev-test', paths, plan, seed: 'same-seed', aw: readAw, now: NOW, force: false });
  await assert.rejects(buildPairs({ evalId: 'ev-test', paths, plan, seed: 'same-seed', aw: readAw, now: NOW, force: false }), /already exist/);
  const again = await buildPairs({ evalId: 'ev-test', paths, plan, seed: 'same-seed', aw: readAw, now: NOW, force: true });
  const order = (m: Mapping): string => m.pairs.map((pair) => pair.A).join();
  assert.equal(order(first.mapping), order(again.mapping));
  assert.notEqual(first.mapping.nonce, again.mapping.nonce);
  const other = await buildPairs({ evalId: 'ev-test', paths, plan, seed: 'another-seed', aw: readAw, now: NOW, force: true });
  assert.notEqual(order(first.mapping), order(other.mapping));
  await importJudgments({ paths, evalId: 'ev-test', raw: { judgments: other.pairs.pairs.map((pair) => ({ pair_id: pair.pair_id, verdict: 'same' })) }, partial: false, now: NOW });
  await assert.rejects(buildPairs({ evalId: 'ev-test', paths, plan, seed: 'x', aw: readAw, now: NOW, force: true }), /judgments are already imported/);
  rmSync(dir, { recursive: true, force: true });
});

test('pairs: a missing locate run is refused', async () => {
  const { dir, plan, paths } = await scenario(SPLIT.slice(0, 2));
  rmSync(join(paths.runsDir, 'c02-pageindex.json'));
  await assert.rejects(buildPairs({ evalId: 'ev-test', paths, plan, seed: 'x', aw: readAw, now: NOW, force: false }), /no finished locate run/);
  rmSync(dir, { recursive: true, force: true });
});

test('pairs: a page whose text cannot be read is never dropped; it shows a placeholder and blocks the automatic "same"', async () => {
  const { dir, plan, paths } = await scenario([{ trove: [3], pageindex: [3] }, { trove: [3, 4], pageindex: [3, 4] }]);
  // Page 4 cannot be read; page 3 can.
  const partial = async (call: AwCall): Promise<string> => JSON.stringify({ pages: (JSON.parse(await readAw(call)) as { pages: Array<{ trove_page: number; text: string }> }).pages.filter((page) => page.trove_page !== 4) });
  const { pairs } = await buildPairs({ evalId: 'ev-test', paths, plan, seed: 's', aw: partial, now: NOW, force: false });
  const [whole, missing] = pairs.pairs;
  assert.equal(whole?.auto_same, true, 'complete and identical: decided by code');
  assert.equal(missing?.auto_same, false, 'a missing text means the judge must look');
  for (const slot of ['A', 'B'] as const) {
    const page = missing?.options[slot].pages.find((entry) => entry.page === 4);
    assert.equal(page?.text, TEXT_UNAVAILABLE, 'the same visible placeholder on both sides');
    assert.equal(missing?.options[slot].pages.length, 2, 'no page is dropped');
  }
  rmSync(dir, { recursive: true, force: true });
});

test('pairs: two failed runs are not an automatic "same"; a run with violations leaves its claim out and is reported', async () => {
  const { dir, plan, paths } = await scenario([{ trove: null, pageindex: null }, { trove: [3], pageindex: [3] }, { trove: [3], pageindex: [4] }]);
  const bad = await readJson(join(paths.runsDir, 'c03-pageindex.json')) as Run;
  await writeJson(join(paths.runsDir, 'c03-pageindex.json'), { ...bad, violations: ['<wrapper> toc --source $(cat x)'] });
  const { pairs, summary } = await buildPairs({ evalId: 'ev-test', paths, plan, seed: 's', aw: readAw, now: NOW, force: false });
  assert.deepEqual(pairs.pairs.map((pair) => [pair.claim.id, pair.auto_same]), [['c01', false], ['c02', true]]);
  assert.deepEqual(summary.excluded, [{ claim_id: 'c03', reason: 'an agent ran a command outside its allowed list' }]);
  assert.equal(pairs.pairs[0]?.options.A.pages.length + (pairs.pairs[0]?.options.B.pages.length ?? 0), 0);
  await importJudgments({ paths, evalId: 'ev-test', raw: [{ pair_id: 'p01', verdict: 'neither' }], partial: false, now: NOW });
  const report = await unblind({ paths, force: false, now: NOW });
  assert.deepEqual(report.excluded.map((entry) => [entry.claim_id, entry.route]), [['c03', 'pageindex']]);
  assert.match(readFileSync(paths.reportMd, 'utf8'), /command it was not allowed to run/);
  rmSync(dir, { recursive: true, force: true });
});

test('pairs: a run made for another plan or claim text is refused, as is an edited run', async () => {
  const { dir, plan, paths } = await scenario(SPLIT.slice(0, 3));
  const stale = { ...plan, seed: 'a different seed' };
  await assert.rejects(buildPairs({ evalId: 'ev-test', paths, plan: stale, seed: 'x', aw: readAw, now: NOW, force: false }), /no finished locate run for this plan/);
  const changed: Plan = { ...plan, claims: plan.claims.map((claim, index) => (index === 1 ? { ...claim, text: 'A different claim now.' } : claim)) };
  await assert.rejects(buildPairs({ evalId: 'ev-test', paths, plan: changed, seed: 'x', aw: readAw, now: NOW, force: false }), /no finished locate run for this plan/);
  const run = await readJson(join(paths.runsDir, 'c01-trove.json')) as Run;
  await writeJson(join(paths.runsDir, 'c01-trove.json'), { ...run, model_requested: 'edited' });
  await assert.rejects(buildPairs({ evalId: 'ev-test', paths, plan, seed: 'x', aw: readAw, now: NOW, force: false }), /no finished locate run for this plan/);
  rmSync(dir, { recursive: true, force: true });
});

test('containment: a symbolic link at library-eval, the evaluation, runs or sealed is refused; so is a linked run file', async () => {
  const outside = mkdtempSync(join(tmpdir(), 'aw-eval-outside-'));
  const make = (): string => project();
  const cases: Array<{ name: string; link: (dir: string) => void }> = [
    { name: 'library-eval', link: (dir) => symlinkSync(outside, join(dir, '.academic-helper', 'library-eval')) },
    { name: 'the evaluation folder', link: (dir) => { mkdirSync(join(dir, '.academic-helper', 'library-eval')); symlinkSync(outside, join(dir, '.academic-helper', 'library-eval', 'ev-test')); } },
    { name: 'runs', link: (dir) => { mkdirSync(join(dir, '.academic-helper', 'library-eval', 'ev-test'), { recursive: true }); symlinkSync(outside, join(dir, '.academic-helper', 'library-eval', 'ev-test', 'runs')); } },
    { name: 'sealed', link: (dir) => { mkdirSync(join(dir, '.academic-helper', 'library-eval', 'ev-test'), { recursive: true }); symlinkSync(outside, join(dir, '.academic-helper', 'library-eval', 'ev-test', 'sealed')); } },
  ];
  for (const entry of cases) {
    const dir = make();
    entry.link(dir);
    assert.throws(() => evalPaths(dir, 'ev-test'), /symbolic link/, entry.name);
    const err: string[] = [];
    assert.equal(await runEvalCli(['status', '--eval', 'ev-test'], { out: () => undefined, err: (t) => err.push(t), project: dir }), 3, entry.name);
    assert.equal(readdirOutside(outside), 0, 'nothing was written outside');
    rmSync(dir, { recursive: true, force: true });
  }
  // A project whose .academic-helper is itself a link to somewhere else is refused too.
  const linked = mkdtempSync(join(tmpdir(), 'aw-eval-linked-'));
  symlinkSync(outside, join(linked, '.academic-helper'));
  assert.throws(() => evalPaths(linked, 'ev-test'), /points outside the project/);
  // A run file that is a link is not read.
  const { dir, paths } = await scenario(SPLIT.slice(0, 1));
  writeFileSync(join(outside, 'x.json'), '{}');
  rmSync(join(paths.runsDir, 'c01-trove.json'));
  symlinkSync(join(outside, 'x.json'), join(paths.runsDir, 'c01-trove.json'));
  await assert.rejects(readJson(join(paths.runsDir, 'c01-trove.json')), /symbolic link/);
  rmSync(dir, { recursive: true, force: true });
  rmSync(linked, { recursive: true, force: true });
  rmSync(outside, { recursive: true, force: true });
});

function readdirOutside(dir: string): number { return existsSync(dir) ? (readdirSync(dir) as string[]).length : 0; }

test('import: shapes, validation, auto-same, partial progress, append-only history with the newest entry counting', async () => {
  const { dir, plan, paths } = await scenario(SPLIT);
  const { pairs } = await buildPairs({ evalId: 'ev-test', paths, plan, seed: 's', aw: readAw, now: NOW, force: false });
  const ids = pairs.pairs.map((pair) => pair.pair_id);
  const base = (verdict: string) => ids.filter((id) => id !== 'p01').map((pair_id) => ({ pair_id, verdict }));
  assert.deepEqual(normalizeImport({ p02: { verdict: 'A', note: 'x' }, p03: 'B' }), { judgments: [{ pair_id: 'p02', verdict: 'A', note: 'x' }, { pair_id: 'p03', verdict: 'B' }] });
  assert.deepEqual(normalizeImport({ judgments: { p02: { verdict: 'A' } } }), { judgments: [{ pair_id: 'p02', verdict: 'A' }] });
  // Refusals.
  await assert.rejects(importJudgments({ paths, evalId: 'ev-test', raw: { judgments: [{ pair_id: 'p99', verdict: 'A' }] }, partial: true, now: NOW }), /unknown pair id/);
  await assert.rejects(importJudgments({ paths, evalId: 'ev-test', raw: { judgments: [{ pair_id: 'p02', verdict: 'best' }] }, partial: true, now: NOW }), /not valid/);
  await assert.rejects(importJudgments({ paths, evalId: 'ev-test', raw: { judgments: [{ pair_id: 'p02', verdict: 'A', note: 'x'.repeat(2001) }] }, partial: true, now: NOW }), /not valid/);
  await assert.rejects(importJudgments({ paths, evalId: 'ev-test', raw: { eval_id: 'other', judgments: [] }, partial: true, now: NOW }), /not ev-test/);
  await assert.rejects(importJudgments({ paths, evalId: 'ev-test', raw: { judgments: [{ pair_id: 'p02', verdict: 'A' }] }, partial: false, now: NOW }), /have no judgment/);
  assert.equal(existsSync(paths.judgments), false, 'a refused import writes nothing');
  // Partial progress, then the rest; the identical pair is judged "same" by itself.
  const partial = await importJudgments({ paths, evalId: 'ev-test', raw: { judgments: [{ pair_id: 'p02', verdict: 'A', note: 'לא ברור' }] }, partial: true, now: NOW });
  assert.deepEqual([partial.imported, partial.auto_same, partial.pending.length], [1, 1, 8]);
  const full = await importJudgments({ paths, evalId: 'ev-test', raw: [{ pair_id: 'p02', verdict: 'B', note: 'changed my mind' }, ...base('same').filter((entry) => entry.pair_id !== 'p02')], partial: false, now: NOW });
  assert.deepEqual([full.pending.length, full.judged], [0, 10]);
  const stored = await readJson(paths.judgments) as { entries: Array<{ pair_id: string; verdict: string; source: string; note: string }> };
  assert.deepEqual(validate('judgments', stored), []);
  const forP02 = stored.entries.filter((entry) => entry.pair_id === 'p02');
  assert.deepEqual(forP02.map((entry) => [entry.verdict, entry.note]), [['A', 'לא ברור'], ['B', 'changed my mind']], 'history is kept, newest last');
  assert.equal(stored.entries.find((entry) => entry.pair_id === 'p01')?.source, 'auto');
  const unchanged = await importJudgments({ paths, evalId: 'ev-test', raw: base('same').filter((entry) => entry.pair_id !== 'p02'), partial: false, now: NOW });
  assert.equal(unchanged.imported, 0);
  assert.equal(((await readJson(paths.judgments)) as { entries: unknown[] }).entries.length, stored.entries.length);
  rmSync(dir, { recursive: true, force: true });
});

test('tampering with the sealed mapping is caught at import and at unblind', async () => {
  const { dir, plan, paths } = await scenario(SPLIT);
  const { pairs, mapping } = await buildPairs({ evalId: 'ev-test', paths, plan, seed: 's', aw: readAw, now: NOW, force: false });
  const all = pairs.pairs.map((pair) => ({ pair_id: pair.pair_id, verdict: 'A' }));
  await importJudgments({ paths, evalId: 'ev-test', raw: all, partial: false, now: NOW });
  const swapped: Mapping = { ...mapping, pairs: mapping.pairs.map((pair) => ({ ...pair, A: pair.B, B: pair.A })) };
  await writeJson(paths.mapping, swapped, 0o600);
  await assert.rejects(unblind({ paths, force: true, now: NOW }), /does not match the commitment/);
  await assert.rejects(importJudgments({ paths, evalId: 'ev-test', raw: all, partial: false, now: NOW }), /does not match the commitment/);
  await writeJson(paths.mapping, mapping, 0o600);
  await unblind({ paths, force: false, now: NOW });
  rmSync(dir, { recursive: true, force: true });
});

test('unblind is refused before judgments are imported, and while pairs are unjudged', async () => {
  const { dir, plan, paths } = await scenario(SPLIT);
  const { pairs } = await buildPairs({ evalId: 'ev-test', paths, plan, seed: 's', aw: readAw, now: NOW, force: false });
  await assert.rejects(unblind({ paths, force: false, now: NOW }), /no judgments are imported yet/);
  assert.equal(existsSync(paths.reportJson), false);
  await importJudgments({ paths, evalId: 'ev-test', raw: [{ pair_id: 'p02', verdict: 'A' }], partial: true, now: NOW });
  await assert.rejects(unblind({ paths, force: false, now: NOW }), /not judged yet/);
  const forced = await unblind({ paths, force: true, now: NOW });
  assert.equal(forced.forced, true);
  assert.match(forced.statement, /first look/);
  assert.equal(pairs.pairs.length, 10);
  rmSync(dir, { recursive: true, force: true });
});

/** The judge's verdict for pair `index` that prefers `route`, or 'same'/'neither'/'skip' as written. */
function prefer(mapping: Mapping, route: Route | 'same' | 'neither' | 'skip', index: number): { pair_id: string; verdict: string; note?: string } {
  const entry = mapping.pairs[index] as Mapping['pairs'][number];
  if (route === 'same' || route === 'neither' || route === 'skip') return { pair_id: entry.pair_id, verdict: route };
  return { pair_id: entry.pair_id, verdict: entry.A === route ? 'A' : 'B' };
}

test('unblind: exact win rates, Wilson interval, sign test, costs and agreement with the auditor', async () => {
  // Pair 1 is identical (auto same). The auditor passed claims 2 to 9 (cited page 3); see SPLIT for who found page 3.
  const auditor: Array<'PASS' | 'FAIL' | null> = [null, 'PASS', 'PASS', 'PASS', 'PASS', 'PASS', 'PASS', 'PASS', 'PASS', 'FAIL'];
  const { dir, plan, paths } = await scenario(SPLIT, { auditor });
  const { mapping } = await buildPairs({ evalId: 'ev-test', paths, plan, seed: 'u', aw: readAw, now: NOW, force: false });
  // Judge: Trove in pairs 2,3(wrong: picks pageindex),5,8,9,10(pageindex); skip 7; same 4; neither 6.
  const judgments = [
    prefer(mapping, 'trove', 1), prefer(mapping, 'pageindex', 2), prefer(mapping, 'same', 3), prefer(mapping, 'trove', 4), prefer(mapping, 'neither', 5),
    prefer(mapping, 'skip', 6), prefer(mapping, 'trove', 7), prefer(mapping, 'trove', 8), prefer(mapping, 'pageindex', 9),
  ];
  await importJudgments({ paths, evalId: 'ev-test', raw: judgments.map((entry, index) => (index === 8 ? { ...entry, note: 'ההפך' } : entry)), partial: false, now: NOW });
  const report = await unblind({ paths, force: false, now: NOW });
  const trove = report.routes.trove;
  const pageindex = report.routes.pageindex;
  assert.ok(trove && pageindex);
  assert.deepEqual([trove.wins, trove.losses, trove.ties, trove.neither], [4, 2, 1 + 1, 1]);
  assert.deepEqual([pageindex.wins, pageindex.losses, pageindex.ties, pageindex.neither], [2, 4, 2, 1]);
  assert.equal(trove.win_rate, 4 / 6);
  const [low, high] = trove.win_rate_ci95 as [number, number];
  assert.ok(Math.abs(low - 0.3) < 0.01 && Math.abs(high - 0.903) < 0.01, `${low} ${high}`);
  assert.ok(Math.abs((report.sign_test.p_value as number) - signTestP(report.sign_test.first_wins, 6)) < 1e-12);
  assert.deepEqual([report.n_pairs, report.n_judged, report.n_auto_same, report.n_skipped, report.n_unjudged], [10, 8, 1, 1, 0]);
  assert.equal(report.enough_pairs, 8 >= minPairs);
  assert.deepEqual([trove.runs.ok, trove.runs.error, pageindex.runs.ok, pageindex.runs.error], [10, 0, 9, 1]);
  assert.ok(Math.abs((trove.cost_usd.total as number) - 0.5) < 1e-9 && Math.abs((pageindex.cost_usd.total as number) - 0.7) < 1e-9);
  assert.ok(Math.abs((pageindex.cost_usd.median as number) - 0.07) < 1e-9);
  assert.deepEqual([trove.tokens.input_total, pageindex.tokens.input_total, trove.returned_est_tokens.total, pageindex.wall_s.median], [10000, 20000, 2000, 6]);
  // Ground truth: cited page 3 on claims with an auditor PASS: trove hit claims 2,3,4... see SPLIT.
  assert.deepEqual([trove.cited_page_hit.eligible, trove.cited_page_hit.hits], [10, 7]);
  assert.deepEqual([pageindex.cited_page_hit.eligible, pageindex.cited_page_hit.hits], [10, 5]);
  assert.deepEqual([trove.auditor_pass_hit.eligible, trove.auditor_pass_hit.hits], [8, 6]);
  // Agreement: pairs with a preference where exactly one route hit and the claim has auditor PASS.
  assert.deepEqual([report.auditor_agreement.eligible, report.auditor_agreement.agree, report.auditor_agreement.disagree, report.auditor_agreement.rate], [4, 3, 1, 0.75]);
  assert.ok(existsSync(paths.reportJson) && existsSync(paths.reportMd));
  const md = readFileSync(paths.reportMd, 'utf8');
  assert.match(md, /Trove/);
  assert.match(md, /PageIndex/);
  assert.match(md, /ההפך/);
  assert.equal(report.pairs.find((pair) => pair.by === 'auto')?.judgment, 'same');
  assert.deepEqual(validate('judgments', await readJson(paths.judgments)), []);
  rmSync(dir, { recursive: true, force: true });
});

test('unblind: too few judged pairs never says which library is better', async () => {
  const { dir, plan, paths } = await scenario(SPLIT.slice(0, 3));
  const { mapping } = await buildPairs({ evalId: 'ev-test', paths, plan, seed: 'u', aw: readAw, now: NOW, force: false });
  await importJudgments({ paths, evalId: 'ev-test', raw: [prefer(mapping, 'trove', 1), prefer(mapping, 'trove', 2)], partial: false, now: NOW });
  const report = await unblind({ paths, force: false, now: NOW });
  assert.equal(report.enough_pairs, false);
  assert.doesNotMatch(report.statement, /won|better than/);
  assert.match(report.statement, new RegExp(`at least ${minPairs}`));
  rmSync(dir, { recursive: true, force: true });
});

test('a clear win with enough pairs is named, with the interval and the sign test', async () => {
  const many: Array<Record<Route, number[] | null>> = Array.from({ length: 10 }, () => ({ trove: [3], pageindex: [5] }));
  const { dir, plan, paths } = await scenario(many);
  const { mapping } = await buildPairs({ evalId: 'ev-test', paths, plan, seed: 'u', aw: readAw, now: NOW, force: false });
  await importJudgments({ paths, evalId: 'ev-test', raw: many.map((_entry, index) => prefer(mapping, index < 9 ? 'trove' : 'pageindex', index)), partial: false, now: NOW });
  const report = await unblind({ paths, force: false, now: NOW });
  assert.match(report.statement, /^Trove won 9 of the 10 pairs/);
  assert.match(report.statement, /unlikely to be chance/);
  rmSync(dir, { recursive: true, force: true });
});

// ------------------------------------------------------------------ the command line

test('the command line: usage errors, status shows progress without library names, page fills the template', async () => {
  const { dir, plan, paths } = await scenario(SPLIT);
  const out: string[] = [];
  const err: string[] = [];
  const io = { out: (text: string) => out.push(text), err: (text: string) => err.push(text), project: dir, now: () => NOW, awCommand: [process.execPath, '-e', 'process.exit(1)'] };
  assert.equal(await runEvalCli([], io), 2);
  assert.equal(await runEvalCli(['frobnicate'], io), 2);
  assert.equal(await runEvalCli(['status'], io), 2);
  assert.equal(await runEvalCli(['status', '--eval', 'bad id!'], io), 2);
  assert.equal(await runEvalCli(['plan', '--n', '0'], io), 2);
  assert.equal(await runEvalCli(['unblind', '--eval', 'ev-test'], io), 2, 'no pairs yet');
  assert.equal(await runEvalCli(['import', '--eval', 'ev-test'], io), 2);
  out.length = 0;
  assert.equal(await runEvalCli(['status', '--eval', 'ev-test'], io), 0);
  const first = JSON.parse(out.join(''));
  assert.deepEqual([first.stage, first.runs.expected, first.runs.finished, first.runs.failed], ['located', 20, 19, 1]);
  assert.ok(!/trove|pageindex/iu.test(out.join('')), 'status names no library');
  // pairs through the command, with the fake page reader replaced by a tiny script.
  const reader = join(dir, 'reader.cjs');
  writeFileSync(reader, `const a=process.argv.slice(2);const s=a[a.indexOf('--pages')+1];const pages=[];for(const part of s.split(',')){const [x,y]=part.split('-').map(Number);for(let p=x;p<=(y||x);p++)pages.push({trove_page:p,text:'Page '+p});}console.log(JSON.stringify({pages}));`);
  const readerIo = { ...io, awCommand: [process.execPath, reader] };
  out.length = 0;
  assert.equal(await runEvalCli(['pairs', '--eval', 'ev-test', '--seed', 'cli'], readerIo), 0, err.join(''));
  const summary = JSON.parse(out.join(''));
  assert.deepEqual(Object.keys(summary).sort(), ['auto_same', 'eval_id', 'excluded', 'mapping_sha256', 'pairs']);
  assert.equal(await runEvalCli(['pairs', '--eval', 'ev-test'], readerIo), 2, 'a second pairing needs --force');
  // The judging page.
  const template = join(dir, 'template.html');
  writeFileSync(template, '<!doctype html><title>Judge</title><script type="application/json" id="pairs">{}</script><script>/* app </script> ok */</script>');
  out.length = 0;
  assert.equal(await runEvalCli(['page', '--eval', 'ev-test', '--template', template], readerIo), 0, err.join(''));
  const html = readFileSync(paths.judgeHtml, 'utf8');
  assert.match(html, /"pair_id":"p01"/u);
  assert.ok(!html.includes('"mapping"') && !/trove|pageindex/iu.test(html.replace(/<script type="application\/json" id="pairs">[\s\S]*?<\/script>/u, '')));
  writeFileSync(template, '<!doctype html><p>Compare Trove and PageIndex</p><script type="application/json" id="pairs">{}</script>');
  assert.equal(await runEvalCli(['page', '--eval', 'ev-test', '--template', template], readerIo), 3);
  writeFileSync(template, '<!doctype html><p>no slot</p>');
  assert.equal(await runEvalCli(['page', '--eval', 'ev-test', '--template', template], readerIo), 3);
  // import from stdin and unblind through the command.
  const mapping = await readJson(paths.mapping) as Mapping;
  const stdin = JSON.stringify({ judgments: mapping.pairs.map((_entry, index) => prefer(mapping, index % 3 === 0 ? 'pageindex' : 'trove', index)) });
  assert.equal(await runEvalCli(['import', '--eval', 'ev-test', '--stdin'], { ...readerIo, stdin: async () => stdin }), 0, err.join(''));
  out.length = 0;
  assert.equal(await runEvalCli(['unblind', '--eval', 'ev-test'], readerIo), 0, err.join(''));
  assert.match(out.join(''), /# Which library found the right pages\?/);
  out.length = 0;
  assert.equal(await runEvalCli(['status', '--eval', 'ev-test'], io), 0);
  assert.equal(JSON.parse(out.join('')).stage, 'unblinded');
  assert.equal(plan.claims.length, 10);
  rmSync(dir, { recursive: true, force: true });
});
