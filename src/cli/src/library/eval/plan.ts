import { existsSync, readFileSync } from 'node:fs';
import { isAbsolute, join, relative, resolve } from 'node:path';
import { PLAIN_ID } from '../backends.ts';
import { compareVerdictKeys, readRows, type LookupRow, type VerdictRow } from '../ledger.ts';
import { parsePageSpec } from '../pages.ts';
import { stripFragment } from '../registry.ts';
import { LibraryError } from '../types.ts';
import type { AwRunner } from './aw.ts';
import { KeyResolver, draftFiles, loadRegistry, parseDraft, wordCount } from './claims.ts';
import type { UnmatchedNote } from './notes.ts';
import { EVAL_ID } from './files.ts';
import { evalLimits } from './limits.ts';
import { seededRandom, shuffle } from './seal.ts';
import type { Book, Claim, Plan, Route, SkipCounts } from './types.ts';

export type PlanOptions = {
  project: string;
  evalId: string;
  /** A path to a draft file or folder, or a run id (then the project's drafts and that run's auditor verdicts). Default: the project's drafts. */
  article?: string;
  n: number;
  seed: string;
  routes: Route[];
  /** An author-written claim list (a JSON file), instead of the draft. */
  claimsFile?: string;
  /** Check that each source answers on every route (one `aw library list` per route). */
  resolve: boolean;
  aw: AwRunner;
  now: Date;
  /** Receives the footnotes that matched no source (or several equally), with the reason: never guessed. */
  unmatched?: UnmatchedNote[];
};

type Candidate = Omit<Claim, 'id' | 'auditor_verdict' | 'corrected_page'> & { order: number };

function emptySkips(): SkipCounts { return { too_short: 0, no_source: 0, multi_source: 0, unresolved: 0, over_cap: 0 }; }

function articleFiles(project: string, article: string | undefined): { files: Array<{ file: string; unit: string }>; runFilter: string | null; label: string | null } {
  const drafts = join(project, '.academic-helper', 'drafts');
  if (!article) return { files: draftFiles(drafts), runFilter: null, label: null };
  const asPath = isAbsolute(article) ? article : resolve(project, article);
  if (existsSync(asPath)) return { files: draftFiles(asPath), runFilter: null, label: relative(project, asPath) || '.' };
  if (EVAL_ID.test(article)) return { files: draftFiles(drafts), runFilter: article, label: `run ${article}` };
  throw new LibraryError('usage', `ERROR library eval plan: --article ${article} is neither a file or folder nor a run id`);
}

function candidatesFromDrafts(project: string, files: Array<{ file: string; unit: string }>, skips: SkipCounts, unmatched?: UnmatchedNote[]): Candidate[] {
  const registry = loadRegistry(project);
  const out: Candidate[] = [];
  const seen = new Set<string>();
  let order = 0;
  for (const { file, unit } of files) {
    const draft = parseDraft(readFileSync(file, 'utf8'), unit);
    const keysOf = new KeyResolver(project, registry, draft.definitions, unit, unmatched);
    for (const sentence of draft.sentences) {
      order += 1;
      if (wordCount(sentence.text) < evalLimits.minClaimWords) { skips.too_short += 1; continue; }
      const keys = sentence.keys.flatMap((key) => keysOf.resolve(key));
      if (keys.length === 0) { skips.no_source += 1; continue; }
      const sources = new Set(keys.map((key) => key.sourceId));
      if (sources.size > 1) { skips.multi_source += 1; continue; }
      const first = keys[0] as NonNullable<(typeof keys)[number]>;
      const marker = `${first.sourceId}\u0000${sentence.text}`;
      if (seen.has(marker)) continue;
      seen.add(marker);
      const trove = [...new Set(keys.flatMap((key) => key.trove))].sort((a, b) => a - b);
      const printed = keys.flatMap((key) => key.printed)[0] ?? null;
      out.push({ order, text: sentence.text, source_id: first.sourceId, source_title: first.title, cited_trove_pages: trove, cited_printed_page: printed, paragraph_id: sentence.paragraphId });
    }
  }
  return out;
}

/** `[{"text": "...", "source": "<id>", "trove_pages": [12], "printed_page": 5}]`: the author's own claims. */
function candidatesFromFile(project: string, file: string, skips: SkipCounts): Candidate[] {
  const path = isAbsolute(file) ? file : resolve(project, file);
  let raw: unknown;
  try { raw = JSON.parse(readFileSync(path, 'utf8')); } catch { throw new LibraryError('usage', `ERROR library eval plan: --claims ${file} is not a readable JSON file`); }
  const list: unknown = Array.isArray(raw) ? raw : (raw as { claims?: unknown } | null)?.claims;
  if (!Array.isArray(list)) throw new LibraryError('usage', 'ERROR library eval plan: --claims must hold a list of {text, source}');
  const registry = loadRegistry(project);
  const out: Candidate[] = [];
  list.forEach((entry: unknown, index) => {
    const item = (typeof entry === 'object' && entry !== null ? entry : {}) as Record<string, unknown>;
    const text = typeof item.text === 'string' ? item.text.normalize('NFC').replace(/\s+/gu, ' ').trim() : '';
    const source = String(item.source_id ?? item.source ?? '');
    if (!text || wordCount(text) < evalLimits.minClaimWords) { skips.too_short += 1; return; }
    if (!source || !PLAIN_ID.test(source)) { skips.no_source += 1; return; }
    const trove = Array.isArray(item.trove_pages) ? item.trove_pages.filter((page): page is number => Number.isInteger(page) && (page as number) > 0) : [];
    const printed = Number.isInteger(item.printed_page) && (item.printed_page as number) > 0 ? item.printed_page as number : null;
    out.push({
      order: index + 1, text, source_id: source, source_title: registry.sources.get(source) ?? source,
      cited_trove_pages: trove, cited_printed_page: printed, paragraph_id: null,
    });
  });
  return out;
}

/** The newest auditor verdict recorded for a claim's paragraph and source: PASS or FAIL, and a corrected page. */
async function auditorFor(candidate: Candidate, runFilter: string | null, rows: Awaited<ReturnType<typeof readRows>>['rows']): Promise<{ verdict: 'PASS' | 'FAIL' | null; corrected: number | null }> {
  if (!candidate.paragraph_id) return { verdict: null, corrected: null };
  const lookups = new Map(rows.filter((row): row is LookupRow => row.row_type === 'lookup').map((row) => [row.lookup_id, row]));
  const verdicts = rows.filter((row): row is VerdictRow => row.row_type === 'verdict' && row.paragraph_id === candidate.paragraph_id && (runFilter === null || row.run_id === runFilter));
  const sameSource = verdicts.filter((row) => lookups.get(row.lookup_id)?.source_id !== undefined && stripFragment(lookups.get(row.lookup_id)?.source_id ?? '') === stripFragment(candidate.source_id));
  const onPage = candidate.cited_trove_pages.length === 0 ? [] : sameSource.filter((row) => {
    const requested = parsePageSpec(lookups.get(row.lookup_id)?.request.trove_pages ?? '');
    return requested === 'all' || candidate.cited_trove_pages.some((page) => requested.includes(page));
  });
  const pool = onPage.length > 0 ? onPage : sameSource;
  const newest = pool.reduce<VerdictRow | null>((best, row) => (best === null || compareVerdictKeys(row, best) > 0 ? row : best), null);
  return newest ? { verdict: newest.verdict, corrected: newest.corrected_page } : { verdict: null, corrected: null };
}

async function resolvableIds(aw: AwRunner, route: Route, evalId: string): Promise<Set<string>> {
  let text: string;
  try { text = await aw({ args: ['list'], route, run: `chk-${evalId}` }); }
  catch (error) {
    throw new LibraryError('exit', `ERROR library eval plan: the ${route} library could not list its books (${error instanceof Error ? error.message : String(error)}); fix that, or plan without the check using --no-resolve`);
  }
  try {
    const parsed = JSON.parse(text) as { items?: Array<{ id?: unknown }> };
    return new Set((parsed.items ?? []).map((item) => String(item.id ?? '')).filter(Boolean));
  } catch { throw new LibraryError('parse', `ERROR library eval plan: the ${route} library answered with something that is not a book list`); }
}

/**
 * Choose the claims: the sentences of the article that carry a footnote, kept when their source answers on every
 * route, spread over the sources (no source supplies more than a third), picked with a seeded shuffle so the same
 * article and seed always give the same plan. Offline except for the one `list` per route.
 */
export async function buildPlan(options: PlanOptions): Promise<Plan> {
  if (options.n < 1 || options.n > evalLimits.maxClaims) {
    throw new LibraryError('usage', `ERROR library eval plan: --n must be between 1 and ${evalLimits.maxClaims}`);
  }
  const skipped = emptySkips();
  const article = articleFiles(options.project, options.article);
  let candidates = options.claimsFile
    ? candidatesFromFile(options.project, options.claimsFile, skipped)
    : candidatesFromDrafts(options.project, article.files, skipped, options.unmatched);
  if (options.resolve) {
    const sets = await Promise.all(options.routes.map((route) => resolvableIds(options.aw, route, options.evalId)));
    const before = candidates.length;
    candidates = candidates.filter((candidate) => sets.every((ids) => ids.has(candidate.source_id) || [...ids].some((id) => stripFragment(id) === stripFragment(candidate.source_id))));
    skipped.unresolved = before - candidates.length;
  }
  // Spread over the sources: sources in a seeded order, claims within a source in a seeded order, one from each in turn.
  const bySource = new Map<string, Candidate[]>();
  for (const candidate of candidates) bySource.set(candidate.source_id, [...(bySource.get(candidate.source_id) ?? []), candidate]);
  const target = Math.min(options.n, candidates.length);
  const cap = Math.ceil(options.n / evalLimits.perSourceShare);
  const groups = shuffle([...bySource.keys()].sort(), seededRandom(`${options.seed}:sources`))
    .map((source) => shuffle(bySource.get(source) as Candidate[], seededRandom(`${options.seed}:${source}`)).slice(0, cap));
  const picked: Candidate[] = [];
  for (let round = 0; picked.length < target && round < cap; round += 1) {
    for (const group of groups) {
      const next = group[round];
      if (next && picked.length < target) picked.push(next);
    }
  }
  skipped.over_cap = candidates.length - picked.length;
  picked.sort((a, b) => a.order - b.order);

  const { rows } = await readRows(options.project);
  const claims: Claim[] = [];
  for (const [index, candidate] of picked.entries()) {
    const { verdict, corrected } = await auditorFor(candidate, article.runFilter, rows);
    const { order: _order, ...rest } = candidate;
    claims.push({ id: `c${String(index + 1).padStart(2, '0')}`, ...rest, auditor_verdict: verdict, corrected_page: corrected });
  }
  const shelf: Book[] = [...new Map(claims.map((claim) => [claim.source_id, { id: claim.source_id, title: claim.source_title }])).values()];
  const runs = claims.length * options.routes.length;
  return {
    schema: 1, eval_id: options.evalId, created_at: options.now.toISOString(), article: article.label, seed: options.seed,
    routes: options.routes, shelf, claims, skipped, estimate: { runs, usd: Math.round(runs * evalLimits.expectedUsdPerRun * 100) / 100 },
  };
}
