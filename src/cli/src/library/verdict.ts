import thresholds from '../../../thresholds.json' with { type: 'json' };
import {
  appendRow, compareVerdictKeys, containedDir, hasProjectFolder, listSpool, nowIso, readSpool, readSpoolJson, removeSpool, rowsForLookup, spoolDir, spoolFile, sweepSpool, textSha, writeSpool,
  type AppendResult, type LookupRow, type ShadowRow, type SupportsReason, type VerdictRow,
} from './ledger.ts';
import { coverage, tokens } from './textmatch.ts';
import { randomBytes } from 'node:crypto';
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
export async function computeSupports(project: string, lookupId: string, quote: string, waitMs: number, page?: number | null, probe?: { afterFirstSpoolRead?: () => Promise<void> }): Promise<Supports> {
  if (tokens(quote).length < limits.supports.minQuoteTokens) return { supports: null, reason: 'no_quote' };
  const rows = await rowsForLookup(project, lookupId);
  const lookup = rows.find((row): row is LookupRow => row.row_type === 'lookup');
  if (!lookup || lookup.shadow_status !== 'pending') return { supports: null, reason: 'shadow_missing' };
  const deadline = Date.now() + waitMs;
  const judge = (spool: { too_large?: boolean; pages: Array<{ page: number; text: string }> }): Supports => {
    if (spool.too_large || spool.pages.length === 0) return { supports: null, reason: 'shadow_missing' };
    return pagesSupport(quote, spool.pages, page) ? { supports: true, reason: 'covered' } : { supports: false, reason: 'not_covered' };
  };
  const spoolPath = spoolFile(project, lookupId, 'shadow');
  let first = true;
  for (;;) {
    const spool = await readSpool(project, spoolPath);
    if (first) { first = false; await probe?.afterFirstSpoolRead?.(); }
    if (spool) return judge(spool);
    const shadow = (await rowsForLookup(project, lookupId)).find((row): row is ShadowRow => row.row_type === 'shadow');
    if (shadow) {
      // The worker writes its spool before its row, so a row seen now may have been published after the spool
      // read above: look at the spool again before deciding. Only a shadow that failed, or left no text, is missing.
      const again = await readSpool(project, spoolPath);
      return again ? judge(again) : { supports: null, reason: 'shadow_missing' };
    }
    if (Date.now() >= deadline) return { supports: null, reason: 'shadow_pending' };
    await sleep(limits.shadow.pollMs);
  }
}

/** Epoch nanoseconds: the wall clock at start-up plus the monotonic clock since, so two calls in one process never go backwards. */
const WALL_AT_START = BigInt(Date.now()) * 1_000_000n;
const MONO_AT_START = process.hrtime.bigint();
function nowNs(): string { return String(WALL_AT_START + (process.hrtime.bigint() - MONO_AT_START)); }

/** Who and when: the ordering key of one verdict. It is fixed when `aw library verdict` is invoked and never changes, even when the verdict settles later. */
type VerdictKey = { verdict_at: string; pid: number; nonce: string };
function newKey(): VerdictKey { return { verdict_at: nowNs(), pid: process.pid, nonce: randomBytes(8).toString('hex') }; }

// One pending file per verdict (named by its nonce), so a newer and an older pending verdict for the same citation never overwrite each other.
const pendingName = (lookupId: string, paragraph: string | null, nonce: string): string => `pending-${lookupId}-${textSha(paragraph ?? '').slice(0, 8)}-${nonce}.json`;
const pendingFile = (project: string, lookupId: string, paragraph: string | null, nonce: string): string => join(spoolDir(project), pendingName(lookupId, paragraph, nonce));

type PendingVerdict = VerdictInput & VerdictKey;

export type VerdictResult = { row: VerdictRow; append: AppendResult };

/** The verdict rows already written for one citation of one lookup. */
async function earlierVerdicts(project: string, lookup: string, paragraph: string | null): Promise<VerdictRow[]> {
  return (await rowsForLookup(project, lookup)).filter((row): row is VerdictRow => row.row_type === 'verdict' && row.paragraph_id === paragraph);
}

function verdictRow(input: VerdictInput, key: VerdictKey, result: Supports, lookup: LookupRow | undefined, settled: boolean): VerdictRow {
  return {
    row_type: 'verdict',
    schema: 1,
    ...key,
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
 * `aw library verdict`: record the auditor's call on one citation next to the lookup it was made from. The
 * ledger needs no lock: each verdict row carries its own ordering key (when this command was invoked, pid,
 * a random nonce) and is appended as one write, so rows from several processes can land in any order and the
 * newest verdict is still the one with the highest key. The row is best effort: a ledger problem is reported
 * to the caller but never changes the verdict itself.
 */
export async function recordVerdict(project: string, input: VerdictInput, waitMs: number = limits.timeoutMs.verdictSettle): Promise<VerdictResult> {
  const key = newKey();
  await sweepSpool(project);
  const lookup = (await rowsForLookup(project, input.lookup)).find((row): row is LookupRow => row.row_type === 'lookup');
  const result = await computeSupports(project, input.lookup, input.quote, waitMs, input.page);
  const row = verdictRow(input, key, result, lookup, false);
  const append = await appendRow(project, row);
  if (append.ok && result.reason === 'shadow_pending') {
    const pending: PendingVerdict = { ...input, ...key };
    await writeSpool(project, pendingFile(project, input.lookup, input.paragraph, key.nonce), pending);
  }
  return { row, append };
}

/**
 * Settle verdicts that were recorded while their shadow was still running: when the shadow's text (or its
 * failure) is there now, append the verdict again with the answer, under the SAME ordering key it was first
 * recorded with, so a late settle can never outrank a verdict invoked after it. A pending verdict that a newer
 * one has replaced is dropped without writing.
 */
export async function settlePending(project: string): Promise<{ settled: number; waiting: number }> {
  let settled = 0;
  let waiting = 0;
  if (!(await hasProjectFolder(project)) || !(await containedDir(project, ['retrieval', 'spool']))) return { settled, waiting };
  const files = await listSpool(project, (name) => name.startsWith('pending-') && name.endsWith('.json'));
  for (const file of files) {
    let input: PendingVerdict;
    try { input = (await readSpoolJson(project, file)) as PendingVerdict; } catch { await removeSpool(project, file); continue; }
    if (typeof input.lookup !== 'string' || typeof input.verdict_at !== 'string' || typeof input.nonce !== 'string' || !Number.isInteger(input.pid)) { await removeSpool(project, file); continue; }
    const paragraph = input.paragraph ?? null;
    const earlier = await earlierVerdicts(project, input.lookup, paragraph);
    if (earlier.some((row) => compareVerdictKeys(row, input) > 0)) { await removeSpool(project, file); continue; }
    const result = await computeSupports(project, input.lookup, input.quote, 0, input.page);
    if (result.reason === 'shadow_pending') { waiting += 1; continue; }
    const lookup = (await rowsForLookup(project, input.lookup)).find((row): row is LookupRow => row.row_type === 'lookup');
    const key: VerdictKey = { verdict_at: input.verdict_at, pid: input.pid, nonce: input.nonce };
    if ((await appendRow(project, verdictRow({ ...input, paragraph }, key, result, lookup, true))).ok) { settled += 1; await removeSpool(project, file); }
  }
  return { settled, waiting };
}
