import thresholds from '../../../thresholds.json' with { type: 'json' };
import { PLAIN_ID, TroveBackend } from './backends.ts';
import { ensureCanIndex, indexBook, pilibJson, plainFailure, type Indexer, type IndexRequest, type SummaryMode } from './index-cmd.ts';
import { runCommand } from './exec.ts';
import { childEnv } from './install.ts';
import { clipError } from './ledger.ts';
import { errorMessage, LibraryError } from './types.ts';

const limits = thresholds.library;

export type BackfillSelector = { kind: 'ids'; ids: string[] } | { kind: 'shelf' } | { kind: 'all' };

export type BackfillRequest = {
  selector: BackfillSelector;
  limit?: number;
  skipExisting: boolean;
  dryRun: boolean;
  yes: boolean;
  summaries: SummaryMode;
  noFallback: boolean;
  maxCalls?: number;
  model?: string;
  run: string;
  verify: boolean;
};

type Candidate = { id: string; title: string; pages: number | null; tocEntries: number; hinted: number };

type PlanLine = {
  id: string; title: string; pages: number | null; toc_entries: number; hinted_entries: number;
  action: 'index' | 'skip'; reason: string | null;
  /** Gemini calls this book is expected to need (one per outline entry); null when there is no table of contents to count. */
  expected_calls: number | null;
  /** No table of contents with hints: the book needs the full helper (structure detection), at a cost that cannot be counted ahead. */
  likely_fallback: boolean;
};

const whole = (value: unknown): number | null => (typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null);

async function listTrove(indexer: Indexer, selector: BackfillSelector): Promise<Array<{ id: string; title: string; pages: number | null }>> {
  const env = childEnv(indexer.env, { kind: 'trove' });
  const timeoutMs = limits.timeoutMs.readAll;
  if (selector.kind === 'ids') return selector.ids.map((id) => ({ id, title: '', pages: null }));
  if (selector.kind === 'shelf') return (await new TroveBackend({ command: indexer.config.troveCommand, env, timeoutMs, cwd: indexer.project }).list()).map((book) => ({ id: book.id, title: book.title, pages: book.pageCount }));
  const out = await runCommand(indexer.config.troveCommand, ['items', 'list', '--json'], { timeoutMs, maxBuffer: limits.maxBufferBytes, env, cwd: indexer.project });
  let parsed: unknown;
  try { parsed = JSON.parse(out); } catch { throw new LibraryError('parse', 'ERROR library backfill: trove items list did not return JSON'); }
  const items = Array.isArray((parsed as { items?: unknown } | null)?.items) ? (parsed as { items: unknown[] }).items : [];
  return items.flatMap((item) => {
    const record = typeof item === 'object' && item !== null ? item as Record<string, unknown> : {};
    return typeof record.id === 'string' && PLAIN_ID.test(record.id) ? [{ id: record.id, title: typeof record.title === 'string' ? record.title : '', pages: whole(record.pageCount) }] : [];
  });
}

/** The books a backfill would touch, with the outline Trove holds for each (read-only on Trove). */
async function candidates(indexer: Indexer, request: BackfillRequest): Promise<{ list: Candidate[]; unreadable: Array<{ id: string; error: string }> }> {
  const base = await listTrove(indexer, request.selector);
  const trove = new TroveBackend({ command: indexer.config.troveCommand, env: childEnv(indexer.env, { kind: 'trove' }), timeoutMs: limits.timeoutMs.primary, cwd: indexer.project });
  const list: Candidate[] = [];
  const unreadable: Array<{ id: string; error: string }> = [];
  for (const book of base) {
    try {
      const toc = await trove.toc(book.id);
      list.push({ id: book.id, title: book.title || toc.title || book.id, pages: book.pages, tocEntries: toc.toc.length, hinted: toc.toc.filter((entry) => entry.title.includes(' - ')).length });
    } catch (error) { // A backend's stderr can echo a credential: the same redaction as the ledger, one short line.
      unreadable.push({ id: book.id, error: clipError(errorMessage(error).replace(/^ERROR library: /u, '')) }); }
  }
  return { list, unreadable };
}

/** The same Trove book already indexed with the same page count and outline length: nothing to do. */
async function alreadyIndexed(indexer: Indexer, book: Candidate): Promise<boolean> {
  const meta = await pilibJson(indexer, ['meta', book.id]);
  const origin = (typeof meta?.origin === 'object' && meta.origin !== null ? meta.origin as { trove?: Record<string, unknown> } : {}).trove;
  if (!origin) return false;
  const pages = whole(origin.trove_pages);
  const entries = whole(origin.toc_entries);
  return pages !== null && entries !== null && entries === book.tocEntries && (book.pages === null || book.pages === pages);
}

async function plan(indexer: Indexer, request: BackfillRequest): Promise<{ lines: PlanLine[]; unreadable: Array<{ id: string; error: string }> }> {
  const { list, unreadable } = await candidates(indexer, request);
  const lines: PlanLine[] = [];
  let planned = 0;
  for (const book of list) {
    const fallback = book.tocEntries === 0 || book.hinted * 2 < book.tocEntries;
    const line: PlanLine = { id: book.id, title: book.title, pages: book.pages, toc_entries: book.tocEntries, hinted_entries: book.hinted, action: 'index', reason: null, expected_calls: request.summaries === 'gemini' ? (fallback ? null : book.tocEntries) : 0, likely_fallback: fallback };
    if (request.limit !== undefined && planned >= request.limit) { line.action = 'skip'; line.reason = 'over the --limit'; }
    else if (request.skipExisting && await alreadyIndexed(indexer, book)) { line.action = 'skip'; line.reason = 'already indexed (same pages and outline length)'; }
    else if (fallback && request.noFallback) { line.action = 'skip'; line.reason = 'no table of contents with hints and --no-fallback was given'; }
    else planned += 1;
    lines.push(line);
  }
  return { lines, unreadable };
}

// A failure that every later book would repeat: stop instead of trying them all.
const STOP_CODES = new Set(['missing_key', 'core_helper_missing', 'model_failed']);

/**
 * `aw library backfill`: copy books that are already in Trove into PageIndex, one at a time (idempotent per book: running it again
 * re-indexes, reusing the summaries already paid for). Prints the plan with an estimate of Gemini calls first; a run that could cost
 * more than askAboveCalls (or has books without a hinted table of contents) needs --yes, which the skill passes after asking.
 * Returns the JSON to print and the exit code.
 */
export async function runBackfill(indexer: Indexer, request: BackfillRequest): Promise<{ output: Record<string, unknown>; exit: number }> {
  await ensureCanIndex(indexer);
  const { lines, unreadable } = await plan(indexer, request);
  const todo = lines.filter((line) => line.action === 'index');
  const estimated = todo.reduce((sum, line) => sum + (line.expected_calls ?? 0), 0);
  const fallbackBooks = todo.filter((line) => line.likely_fallback).length;
  const askRequired = request.summaries === 'gemini' && (estimated > limits.index.askAboveCalls || fallbackBooks > 0);
  const summary = {
    command: 'library backfill', run_id: request.run, summaries: request.summaries, model: request.summaries === 'gemini' ? (request.model ?? limits.index.summaryModel) : null,
    pageindex_source: indexer.source, books: lines.length, to_index: todo.length, skipped: lines.length - todo.length, unreadable,
    estimated_calls: estimated, estimated_calls_note: 'one Gemini call per outline entry; books without a hinted table of contents are not counted',
    books_without_hinted_toc: fallbackBooks, ask_required: askRequired, ask_above_calls: limits.index.askAboveCalls, plan: lines,
  };
  if (request.dryRun) return { output: { ok: true, dry_run: true, ...summary }, exit: 0 };
  if (askRequired && !request.yes) {
    return { output: { ok: false, code: 'needs_confirmation', error: `This backfill would send book text to Google (Gemini) for about ${estimated} summaries${fallbackBooks > 0 ? ` plus ${fallbackBooks} book${fallbackBooks === 1 ? '' : 's'} without a hinted table of contents, whose cost cannot be counted ahead` : ''}. Show the plan to the researcher, ask, then run it again with --yes.`, ...summary }, exit: 2 };
  }
  // A book whose table of contents could not be read from Trove was not indexed: it is a failure of this run.
  const results: Array<Record<string, unknown>> = unreadable.map((entry) => ({ id: entry.id, title: '', status: 'failed', code: 'trove_failed', error: plainFailure('trove_failed', entry.error) }));
  let calls = 0;
  let promptTokens = 0;
  let completionTokens = 0;
  let cost = 0;
  let costKnown = false;
  let stopped: string | null = null;
  for (const line of lines) {
    if (line.action === 'skip') { results.push({ id: line.id, title: line.title, status: 'skipped', reason: line.reason }); continue; }
    if (stopped) { results.push({ id: line.id, title: line.title, status: 'not_run', reason: stopped }); continue; }
    const one: IndexRequest = { troveId: line.id, summaries: request.summaries, noFallback: request.noFallback, maxCalls: request.maxCalls, model: request.model, dryRun: false, yes: request.yes, run: request.run, verify: request.verify };
    try {
      const outcome = await indexBook(indexer, one);
      const result = outcome.result;
      calls += whole(result.calls) ?? 0;
      promptTokens += whole(result.prompt_tokens) ?? 0;
      completionTokens += whole(result.completion_tokens) ?? 0;
      if (typeof result.cost_usd === 'number') { cost += result.cost_usd; costKnown = true; }
      results.push({ id: line.id, title: line.title, status: outcome.ok ? 'indexed' : 'failed', ...(outcome.code ? { code: outcome.code } : {}), ...(outcome.message ? { error: outcome.message } : {}),
        source: result.source ?? null, fallback: result.fallback ?? null, nodes: result.nodes ?? null, n_pages: result.n_pages ?? null, calls: result.calls ?? 0, cost_usd: result.cost_usd ?? null,
        ...(outcome.read_back ? { read_back_ok: outcome.read_back.ok } : {}) });
      if (!outcome.ok && outcome.code && STOP_CODES.has(outcome.code)) stopped = `stopped after ${line.id}: ${outcome.code}`;
    } catch (error) {
      results.push({ id: line.id, title: line.title, status: 'failed', code: error instanceof LibraryError ? error.code : 'internal', error: plainFailure('internal', errorMessage(error).replace(/^ERROR library[a-z ]*: /u, '')) });
    }
  }
  const failed = results.filter((entry) => entry.status === 'failed').length;
  return {
    output: { ok: failed === 0, command: 'library backfill', run_id: request.run, summaries: request.summaries, pageindex_source: indexer.source,
      books: lines.length, indexed: results.filter((entry) => entry.status === 'indexed').length, skipped: results.filter((entry) => entry.status === 'skipped').length, failed,
      not_run: results.filter((entry) => entry.status === 'not_run').length, calls, prompt_tokens: promptTokens, completion_tokens: completionTokens, cost_usd: costKnown ? Math.round(cost * 1e6) / 1e6 : null, unreadable, results },
    exit: failed === 0 ? 0 : 4,
  };
}
