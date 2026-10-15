import { readdir, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import thresholds from '../../../thresholds.json' with { type: 'json' };
import {
  appendRow, hasProjectFolder, nowIso, readSpool, rowsForLookup, spoolDir, spoolFile, sweepSpool, textSha, writeSpool,
  type AppendResult, type LookupRow, type ShadowRow, type SupportsReason, type VerdictRow,
} from './ledger.ts';
import { coverage, tokens } from './textmatch.ts';

const limits = thresholds.library;

export type VerdictInput = {
  lookup: string;
  verdict: 'PASS' | 'FAIL';
  correctedPage: number | null;
  /** The sentence from the answering route's page that supports (or fails to support) the claim; empty when there is none. */
  quote: string;
  paragraph: string | null;
  run: string | null;
};

export type Supports = { supports: boolean | null; reason: SupportsReason };

function sleep(ms: number): Promise<void> { return new Promise((resolveSleep) => { setTimeout(resolveSleep, ms); }); }

/**
 * Does the shadow's page text also support the claim? Decided in code, with no model: the share of the
 * auditor's quote that appears, word by word, in the shadow's text for the same lookup. Null (not false)
 * when there is nothing to test: no quote, no shadow text, or the shadow is still running.
 */
export async function computeSupports(project: string, lookupId: string, quote: string, waitMs: number): Promise<Supports> {
  if (tokens(quote).length < limits.supports.minQuoteTokens) return { supports: null, reason: 'no_quote' };
  const rows = await rowsForLookup(project, lookupId);
  const lookup = rows.find((row): row is LookupRow => row.row_type === 'lookup');
  if (!lookup || lookup.shadow_status !== 'pending') return { supports: null, reason: 'shadow_missing' };
  const deadline = Date.now() + waitMs;
  for (;;) {
    const spool = await readSpool(spoolFile(project, lookupId, 'shadow'));
    if (spool) {
      if (spool.too_large || spool.pages.length === 0) return { supports: null, reason: 'shadow_missing' };
      const text = spool.pages.map((page) => page.text).join('\n');
      return coverage(quote, text) >= limits.supports.tokenCoverageMin ? { supports: true, reason: 'covered' } : { supports: false, reason: 'not_covered' };
    }
    const shadow = (await rowsForLookup(project, lookupId)).find((row): row is ShadowRow => row.row_type === 'shadow');
    if (shadow) return { supports: null, reason: 'shadow_missing' };
    if (Date.now() >= deadline) return { supports: null, reason: 'shadow_pending' };
    await sleep(limits.shadow.pollMs);
  }
}

const pendingFile = (project: string, lookupId: string, paragraph: string | null): string => join(spoolDir(project), `pending-${lookupId}-${textSha(paragraph ?? '').slice(0, 8)}.json`);

type PendingVerdict = VerdictInput;

export type VerdictResult = { row: VerdictRow; append: AppendResult };

/**
 * `aw library verdict`: record the auditor's call on one citation next to the lookup it was made from. The
 * row is best effort: a ledger problem is reported to the caller but never changes the verdict itself.
 */
export async function recordVerdict(project: string, input: VerdictInput): Promise<VerdictResult> {
  await sweepSpool(project);
  const lookup = (await rowsForLookup(project, input.lookup)).find((row): row is LookupRow => row.row_type === 'lookup');
  const result = await computeSupports(project, input.lookup, input.quote, limits.timeoutMs.verdictSettle);
  const row: VerdictRow = {
    row_type: 'verdict',
    schema: 1,
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
  };
  const append = await appendRow(project, row);
  if (append.ok && result.reason === 'shadow_pending') await writeSpool(project, pendingFile(project, input.lookup, input.paragraph), input);
  return { row, append };
}

/**
 * Settle verdicts that were recorded while their shadow was still running: when the shadow's text (or its
 * failure) is there now, append the verdict again with the answer. The report keeps the last row for each
 * citation, so the settled row replaces the pending one.
 */
export async function settlePending(project: string): Promise<{ settled: number; waiting: number }> {
  let settled = 0;
  let waiting = 0;
  if (!(await hasProjectFolder(project))) return { settled, waiting };
  let names: string[] = [];
  try { names = (await readdir(spoolDir(project))).filter((name) => name.startsWith('pending-') && name.endsWith('.json')); } catch { return { settled, waiting }; }
  for (const name of names) {
    const file = join(spoolDir(project), name);
    let input: PendingVerdict;
    try { input = JSON.parse(await readFile(file, 'utf8')) as PendingVerdict; } catch { await rm(file, { force: true }); continue; }
    const result = await computeSupports(project, input.lookup, input.quote, 0);
    if (result.reason === 'shadow_pending') { waiting += 1; continue; }
    const lookup = (await rowsForLookup(project, input.lookup)).find((row): row is LookupRow => row.row_type === 'lookup');
    const row: VerdictRow = {
      row_type: 'verdict',
      schema: 1,
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
      settled: true,
    };
    if ((await appendRow(project, row)).ok) { settled += 1; await rm(file, { force: true }); }
  }
  return { settled, waiting };
}
