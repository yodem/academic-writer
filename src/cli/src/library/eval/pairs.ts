import { existsSync } from 'node:fs';
import { formatPageRanges } from '../pages.ts';
import { LibraryError } from '../types.ts';
import type { AwRunner } from './aw.ts';
import { fileSha, readJson, runFile, validate, writeJson, type EvalPaths } from './files.ts';
import { PROMPT_VERSION, claimSha, fingerprintOf, planSha } from './runner.ts';
import { mappingCommitment, newMapping, seededRandom, slotOrders, writeSealed } from './seal.ts';
import type { Mapping, Pair, PairOption, Pairs, Plan, Route, Run } from './types.ts';

export type PairsOptions = {
  evalId: string;
  paths: EvalPaths;
  plan: Plan;
  /** Seed of the A/B order; the default is random. It is kept only in the sealed mapping. */
  seed: string;
  aw: AwRunner;
  now: Date;
  force: boolean;
};

export type PairsSummary = { eval_id: string; pairs: number; auto_same: number; mapping_sha256: string; excluded: Array<{ claim_id: string; reason: string }> };

/** Shown in place of a page whose canonical text could not be read: the same words on both sides. */
export const TEXT_UNAVAILABLE = '[The text of this page could not be read.]';

const ROUTE_WORD = /trove|page-?index/iu;

/** The first place in `pairs` where a route name shows (in a key or a fixed field); page and claim text is the author's, not ours. */
export function routeLeak(pairs: Pairs): string | null {
  const scan = (value: unknown, path: string): string | null => {
    if (Array.isArray(value)) {
      for (const [index, item] of value.entries()) { const hit = scan(item, `${path}[${index}]`); if (hit) return hit; }
      return null;
    }
    if (typeof value === 'object' && value !== null) {
      for (const [key, item] of Object.entries(value)) {
        if (ROUTE_WORD.test(key)) return `${path}.${key}`;
        const hit = scan(item, `${path}.${key}`);
        if (hit) return hit;
      }
      return null;
    }
    const field = path.split('.').pop() ?? '';
    if (typeof value === 'string' && !['text', 'book_title'].includes(field) && ROUTE_WORD.test(value)) return path;
    return null;
  };
  return scan(pairs, 'pairs');
}

async function fetchTexts(options: PairsOptions, needed: Map<string, Set<number>>): Promise<Map<string, string>> {
  const texts = new Map<string, string>();
  for (const [book, pages] of needed) {
    const spec = formatPageRanges([...pages].sort((a, b) => a - b));
    let output: string;
    try { output = await options.aw({ args: ['read', '--source', book, '--pages', spec], route: 'trove', run: `chk-${options.evalId}` }); }
    catch (error) {
      // The library has none of the requested pages: every page of this book shows the placeholder (no text is recorded).
      if (/has none of the requested pages/u.test(error instanceof Error ? error.message : String(error))) continue;
      throw new LibraryError('exit', `ERROR library eval pairs: could not read pages ${spec} of ${book} for the judging page (${error instanceof Error ? error.message : String(error)})`);
    }
    let parsed: { pages?: Array<{ trove_page?: unknown; text?: unknown }> };
    try { parsed = JSON.parse(output) as typeof parsed; } catch { throw new LibraryError('parse', `ERROR library eval pairs: the page read of ${book} did not return JSON`); }
    for (const page of parsed.pages ?? []) {
      if (typeof page.trove_page === 'number' && typeof page.text === 'string') texts.set(`${book}\u0000${page.trove_page}`, page.text.normalize('NFC'));
    }
  }
  return texts;
}

type Built = { option: PairOption; valid: boolean; complete: boolean };

function optionFor(plan: Plan, run: Run, texts: Map<string, string>): Built {
  const answer = run.status === 'ok' ? run.answer : null;
  if (!answer) return { option: { book: null, book_title: null, pages: [] }, valid: false, complete: true };
  const pages = [...new Set(answer.pages)].sort((a, b) => a - b)
    .map((page) => ({ page, text: texts.get(`${answer.book}\u0000${page}`) }));
  return {
    option: { book: answer.book, book_title: plan.shelf.find((book) => book.id === answer.book)?.title ?? answer.book, pages: pages.map((entry) => ({ page: entry.page, text: entry.text ?? TEXT_UNAVAILABLE })) },
    valid: true, complete: pages.every((entry) => entry.text !== undefined),
  };
}

function sameOption(a: PairOption, b: PairOption): boolean {
  return a.book === b.book && a.pages.length === b.pages.length && a.pages.every((page, index) => page.page === b.pages[index]?.page);
}

/**
 * Whether a run file belongs to this plan, this claim and this route (the file slot it was read from), was made with the
 * current prompt, and has not been edited: its own fields reproduce its fingerprint.
 */
function runIsCurrent(plan: Plan, claim: Plan['claims'][number], route: Route, run: Run): boolean {
  return run.eval_id === plan.eval_id && run.claim_id === claim.id && run.route === route && run.prompt_version === PROMPT_VERSION
    && run.plan_sha256 === planSha(plan) && run.claim_sha256 === claimSha(claim) && run.fingerprint === fingerprintOf({
      plan_sha256: run.plan_sha256, claim_sha256: run.claim_sha256, claim_id: run.claim_id, route: run.route, engine: run.engine,
      model_requested: run.model_requested, prompt_version: run.prompt_version,
    });
}

/**
 * Build the anonymous A/B pairs. Both options show page text fetched ONCE through the Trove route, so only the choice
 * of pages differs (never the layout); the agents' free-text reasons are dropped; pages inside an option are sorted;
 * which route is A and which B comes from a balanced seeded shuffle. The mapping goes to sealed/mapping.json (0600) and
 * pairs.json carries only its sha256 commitment.
 */
export async function buildPairs(options: PairsOptions): Promise<{ pairs: Pairs; mapping: Mapping; summary: PairsSummary }> {
  const { plan, paths } = options;
  if (plan.routes.length !== 2 || plan.routes[0] === plan.routes[1]) throw new LibraryError('usage', 'ERROR library eval pairs: a comparison needs exactly two different libraries in the plan');
  if (existsSync(paths.judgments)) throw new LibraryError('usage', 'ERROR library eval pairs: judgments are already imported; building new pairs would break them');
  if (existsSync(paths.pairs) && !options.force) throw new LibraryError('usage', 'ERROR library eval pairs: pairs already exist for this evaluation (--force builds them again, with a new hidden order)');
  const routes = plan.routes as [Route, Route];
  const runs = new Map<string, Run>();
  const missing: string[] = [];
  const excluded: PairsSummary['excluded'] = [];
  for (const claim of plan.claims) {
    for (const route of routes) {
      const value = await readJson(runFile(paths, claim.id, route));
      if (value === null || validate('run', value).length > 0 || !runIsCurrent(plan, claim, route, value as Run)) missing.push(claim.id);
      else runs.set(`${claim.id}:${route}`, value as Run);
    }
  }
  if (missing.length > 0) throw new LibraryError('usage', `ERROR library eval pairs: ${new Set(missing).size} claim(s) have no finished locate run for this plan; run \`aw library eval run\` first`);
  // A run that ran a command outside its allowed list is invalid: its claim is left out and reported.
  const claims = plan.claims.filter((claim) => {
    const bad = routes.some((route) => (runs.get(`${claim.id}:${route}`) as Run).violations.length > 0);
    if (bad) excluded.push({ claim_id: claim.id, reason: 'an agent ran a command outside its allowed list' });
    return !bad;
  });
  if (claims.length === 0) throw new LibraryError('usage', 'ERROR library eval pairs: every claim was left out; nothing to compare');

  const needed = new Map<string, Set<number>>();
  for (const run of runs.values()) {
    if (run.status === 'ok' && run.answer) {
      const set = needed.get(run.answer.book) ?? new Set<number>();
      for (const page of run.answer.pages) set.add(page);
      needed.set(run.answer.book, set);
    }
  }
  const texts = await fetchTexts(options, needed);
  const orders = slotOrders(claims.length, seededRandom(`${options.seed}:order`));
  const pairs: Pair[] = [];
  const mapped: Mapping['pairs'] = [];
  for (const [index, claim] of claims.entries()) {
    const pairId = `p${String(index + 1).padStart(2, '0')}`;
    const first = optionFor(plan, runs.get(`${claim.id}:${routes[0]}`) as Run, texts);
    const second = optionFor(plan, runs.get(`${claim.id}:${routes[1]}`) as Run, texts);
    const firstInA = orders[index] as boolean;
    // "Same" is decided by code only when both answers are real, name the same pages, and every page text was read.
    pairs.push({
      pair_id: pairId, claim: { id: claim.id, text: claim.text },
      auto_same: first.valid && second.valid && first.complete && second.complete && sameOption(first.option, second.option),
      options: firstInA ? { A: first.option, B: second.option } : { A: second.option, B: first.option },
    });
    mapped.push({ pair_id: pairId, claim_id: claim.id, A: firstInA ? routes[0] : routes[1], B: firstInA ? routes[1] : routes[0] });
  }
  const snapshot: Mapping['runs'] = [];
  for (const claim of claims) {
    for (const route of routes) snapshot.push({ claim_id: claim.id, route, sha256: await fileSha(runFile(paths, claim.id, route)) as string });
  }
  const mapping = newMapping(plan.eval_id, options.seed, planSha(plan), snapshot, mapped);
  const document: Pairs = { schema: 1, eval_id: plan.eval_id, created_at: options.now.toISOString(), mapping_sha256: mappingCommitment(mapping), pairs };
  const problems = validate('pairs', document);
  if (problems.length > 0) throw new LibraryError('parse', `ERROR library eval pairs: the pairs do not match their schema (${problems[0]})`);
  const leak = routeLeak(document);
  if (leak) throw new LibraryError('parse', `ERROR library eval pairs: a library name would be visible to the judge at ${leak}; nothing was written`);
  await writeSealed(paths.sealedDir, paths.mapping, mapping);
  await writeJson(paths.pairs, document);
  return { pairs: document, mapping, summary: { eval_id: plan.eval_id, pairs: pairs.length, auto_same: pairs.filter((pair) => pair.auto_same).length, mapping_sha256: document.mapping_sha256, excluded } };
}
