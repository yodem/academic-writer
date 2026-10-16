import { existsSync } from 'node:fs';
import { formatPageRanges } from '../pages.ts';
import { LibraryError } from '../types.ts';
import type { AwRunner } from './aw.ts';
import { readJson, runFile, validate, writeJson, type EvalPaths } from './files.ts';
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

export type PairsSummary = { eval_id: string; pairs: number; auto_same: number; mapping_sha256: string };

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

function optionFor(plan: Plan, run: Run, texts: Map<string, string>): PairOption {
  const answer = run.status === 'ok' ? run.answer : null;
  if (!answer) return { book: null, book_title: null, pages: [] };
  const pages = [...new Set(answer.pages)].sort((a, b) => a - b)
    .map((page) => ({ page, text: texts.get(`${answer.book}\u0000${page}`) }))
    .filter((entry): entry is { page: number; text: string } => entry.text !== undefined);
  return { book: answer.book, book_title: plan.shelf.find((book) => book.id === answer.book)?.title ?? answer.book, pages };
}

function sameOption(a: PairOption, b: PairOption): boolean {
  return a.book === b.book && a.pages.length === b.pages.length && a.pages.every((page, index) => page.page === b.pages[index]?.page);
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
  for (const claim of plan.claims) {
    for (const route of routes) {
      const value = await readJson(runFile(paths, claim.id, route));
      if (value === null || validate('run', value).length > 0) missing.push(claim.id);
      else runs.set(`${claim.id}:${route}`, value as Run);
    }
  }
  if (missing.length > 0) throw new LibraryError('usage', `ERROR library eval pairs: ${new Set(missing).size} claim(s) have no finished locate run; run \`aw library eval run\` first`);

  const needed = new Map<string, Set<number>>();
  for (const run of runs.values()) {
    if (run.status === 'ok' && run.answer) {
      const set = needed.get(run.answer.book) ?? new Set<number>();
      for (const page of run.answer.pages) set.add(page);
      needed.set(run.answer.book, set);
    }
  }
  const texts = await fetchTexts(options, needed);
  const orders = slotOrders(plan.claims.length, seededRandom(`${options.seed}:order`));
  const pairs: Pair[] = [];
  const mapped: Mapping['pairs'] = [];
  for (const [index, claim] of plan.claims.entries()) {
    const pairId = `p${String(index + 1).padStart(2, '0')}`;
    const first = optionFor(plan, runs.get(`${claim.id}:${routes[0]}`) as Run, texts);
    const second = optionFor(plan, runs.get(`${claim.id}:${routes[1]}`) as Run, texts);
    const firstInA = orders[index] as boolean;
    pairs.push({
      pair_id: pairId, claim: { id: claim.id, text: claim.text }, auto_same: sameOption(first, second),
      options: firstInA ? { A: first, B: second } : { A: second, B: first },
    });
    mapped.push({ pair_id: pairId, claim_id: claim.id, A: firstInA ? routes[0] : routes[1], B: firstInA ? routes[1] : routes[0] });
  }
  const mapping = newMapping(plan.eval_id, options.seed, mapped);
  const document: Pairs = { schema: 1, eval_id: plan.eval_id, created_at: options.now.toISOString(), mapping_sha256: mappingCommitment(mapping), pairs };
  const problems = validate('pairs', document);
  if (problems.length > 0) throw new LibraryError('parse', `ERROR library eval pairs: the pairs do not match their schema (${problems[0]})`);
  const leak = routeLeak(document);
  if (leak) throw new LibraryError('parse', `ERROR library eval pairs: a library name would be visible to the judge at ${leak}; nothing was written`);
  await writeSealed(paths.sealedDir, paths.mapping, mapping);
  await writeJson(paths.pairs, document);
  return { pairs: document, mapping, summary: { eval_id: plan.eval_id, pairs: pairs.length, auto_same: pairs.filter((pair) => pair.auto_same).length, mapping_sha256: document.mapping_sha256 } };
}
