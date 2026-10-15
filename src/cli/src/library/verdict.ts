import thresholds from '../../../thresholds.json' with { type: 'json' };
import {
  appendRow, containedDir, hasProjectFolder, listSpool, nowIso, readSpool, readSpoolJson, removeSpool, rowsForLookup, spoolDir, spoolFile, sweepSpool, textSha, withLedgerLock, writeSpool,
  type AppendResult, type LookupRow, type ShadowRow, type SupportsReason, type VerdictRow,
} from './ledger.ts';
import { coverage, tokens } from './textmatch.ts';
import { join } from 'node:path';

const limits = thresholds.library;

export type VerdictInput = {
  lookup: string;
  verdict: 'PASS' | 'FAIL';
  correctedPage: number | null;
  /** The sentence from the answering route's page that supports (or fails to support) the claim; empty when there is none. */
  quote: string;
  paragraph: string | null;
  run: string | null;
  /** The Trove page the citation names, when known: support is then judged on that page (and its neighbours) only. */
  page?: number | null;
};

export type Supports = { supports: boolean | null; reason: SupportsReason };

function sleep(ms: number): Promise<void> { return new Promise((resolveSleep) => { setTimeout(resolveSleep, ms); }); }

/**
 * Whether `quote` is on one shadow page, or on a page plus the page right after it (a sentence that runs
 * over a page break). Words found on pages that are not neighbours do not add up. With `page`, only that
 * page and its immediate neighbours are tried.
 */
export function pagesSupport(quote: string, pages: Array<{ page: number; text: string }>, page?: number | null): boolean {
  const byPage = new Map(pages.map((entry) => [entry.page, entry.text]));
  const covers = (text: string): boolean => coverage(quote, text) >= limits.supports.tokenCoverageMin;
  const any = page === undefined || page === null;
  for (const start of any ? [...byPage.keys()] : [page - 1, page]) {
    const first = byPage.get(start);
    if (first === undefined) continue;
    if ((any || start === page) && covers(first)) return true;
    const next = byPage.get(start + 1);
    if (next !== undefined && covers(`${first}\n${next}`)) return true;
  }
  return false;
}

/**
 * Does the shadow's page text also support the claim? Decided in code, with no model: the share of the
 * auditor's quote that appears, word by word, on one shadow page (or a page and the next). Null (not false)
 * when there is nothing to test: no quote, no shadow text, or the shadow is still running.
 */
export async function computeSupports(project: string, lookupId: string, quote: string, waitMs: number, page?: number | null): Promise<Supports> {
  if (tokens(quote).length < limits.supports.minQuoteTokens) return { supports: null, reason: 'no_quote' };
  const rows = await rowsForLookup(project, lookupId);
  const lookup = rows.find((row): row is LookupRow => row.row_type === 'lookup');
  if (!lookup || lookup.shadow_status !== 'pending') return { supports: null, reason: 'shadow_missing' };
  const deadline = Date.now() + waitMs;
  for (;;) {
    const spool = await readSpool(project, spoolFile(project, lookupId, 'shadow'));
    if (spool) {
      if (spool.too_large || spool.pages.length === 0) return { supports: null, reason: 'shadow_missing' };
      return pagesSupport(quote, spool.pages, page) ? { supports: true, reason: 'covered' } : { supports: false, reason: 'not_covered' };
    }
    const shadow = (await rowsForLookup(project, lookupId)).find((row): row is ShadowRow => row.row_type === 'shadow');
    if (shadow) return { supports: null, reason: 'shadow_missing' };
    if (Date.now() >= deadline) return { supports: null, reason: 'shadow_pending' };
    await sleep(limits.shadow.pollMs);
  }
}

const pendingName = (lookupId: string, paragraph: string | null): string => `pending-${lookupId}-${textSha(paragraph ?? '').slice(0, 8)}.json`;
const pendingFile = (project: string, lookupId: string, paragraph: string | null): string => join(spoolDir(project), pendingName(lookupId, paragraph));

type PendingVerdict = VerdictInput & { seq: number };

export type VerdictResult = { row: VerdictRow; append: AppendResult };

/** The verdict rows already written for one citation of one lookup. */
async function earlierVerdicts(project: string, lookup: string, paragraph: string | null): Promise<VerdictRow[]> {
  return (await rowsForLookup(project, lookup)).filter((row): row is VerdictRow => row.row_type === 'verdict' && row.paragraph_id === paragraph);
}

function verdictRow(input: VerdictInput, seq: number, result: Supports, lookup: LookupRow | undefined, settled: boolean): VerdictRow {
  return {
    row_type: 'verdict',
    schema: 1,
    seq,
    ts: nowIso(),
    lookup_id: input.lookup,
    run_id: input.run ?? lookup?.run_id ?? null,
    paragraph_id: input.paragraph,
    verdict: input.verdict,
    corrected_page: input.correctedPage,
    shadow_supports: result.supports,
    shadow_supports_reason: result.reason,
    primary_route: lookup?.route_primary ?? null,
    mode: lookup?.mode ?? null,
    ...(settled ? { settled: true } : {}),
  };
}

/**
 * `aw library verdict`: record the auditor's call on one citation next to the lookup it was made from. Each
 * verdict for the same citation gets the next sequence number, and the report always follows the highest
 * number, so a later verdict is never replaced by an earlier one that settles late. The row is best effort:
 * a ledger problem is reported to the caller but never changes the verdict itself.
 */
export async function recordVerdict(project: string, input: VerdictInput, waitMs: number = limits.timeoutMs.verdictSettle): Promise<VerdictResult> {
  await sweepSpool(project);
  const lookup = (await rowsForLookup(project, input.lookup)).find((row): row is LookupRow => row.row_type === 'lookup');
  const result = await computeSupports(project, input.lookup, input.quote, waitMs, input.page);
  // Reading the highest sequence number and appending the next one is a single step under the ledger lock,
  // so two verdicts for the same citation can never get the same number.
  return withLedgerLock(project, async () => {
    const earlier = await earlierVerdicts(project, input.lookup, input.paragraph);
    const seq = earlier.reduce((top, row) => Math.max(top, row.seq), 0) + 1;
    // Any verdict still waiting for its shadow is older than this one now.
    await removeSpool(project, pendingFile(project, input.lookup, input.paragraph));
    const row = verdictRow(input, seq, result, lookup, false);
    const append = await appendRow(project, row);
    if (append.ok && result.reason === 'shadow_pending') {
      const pending: PendingVerdict = { ...input, seq };
      await writeSpool(project, pendingFile(project, input.lookup, input.paragraph), pending);
    }
    return { row, append };
  });
}

/**
 * Settle verdicts that were recorded while their shadow was still running: when the shadow's text (or its
 * failure) is there now, append the verdict again with the answer, under the same sequence number. A pending
 * verdict that a newer one has replaced is dropped, never written.
 */
export async function settlePending(project: string): Promise<{ settled: number; waiting: number }> {
  let settled = 0;
  let waiting = 0;
  if (!(await hasProjectFolder(project)) || !(await containedDir(project, ['retrieval', 'spool']))) return { settled, waiting };
  const files = await listSpool(project, (name) => name.startsWith('pending-') && name.endsWith('.json'));
  for (const file of files) {
    let input: PendingVerdict;
    try {
      input = (await readSpoolJson(project, file)) as PendingVerdict;
    } catch { await removeSpool(project, file); continue; }
    if (!Number.isInteger(input.seq) || typeof input.lookup !== 'string') { await removeSpool(project, file); continue; }
    const result = await computeSupports(project, input.lookup, input.quote, 0, input.page);
    if (result.reason === 'shadow_pending') { waiting += 1; continue; }
    const lookup = (await rowsForLookup(project, input.lookup)).find((row): row is LookupRow => row.row_type === 'lookup');
    // Check for a newer verdict and append under the same lock that numbers new verdicts.
    const outcome = await withLedgerLock(project, async (): Promise<'stale' | 'settled' | 'failed'> => {
      const earlier = await earlierVerdicts(project, input.lookup, input.paragraph ?? null);
      if (earlier.some((row) => row.seq > input.seq)) return 'stale';
      return (await appendRow(project, verdictRow({ ...input, paragraph: input.paragraph ?? null }, input.seq, result, lookup, true))).ok ? 'settled' : 'failed';
    });
    if (outcome === 'settled') settled += 1;
    if (outcome !== 'failed') await removeSpool(project, file);
  }
  return { settled, waiting };
}
