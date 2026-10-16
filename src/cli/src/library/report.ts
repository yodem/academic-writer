import { lstat, readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import usageSchema from '../../../schemas/ledger-row.schema.json' with { type: 'json' };
import thresholds from '../../../thresholds.json' with { type: 'json' };
import type { LedgerRow } from '../ledger.ts';
import { checkSchema, type JsonSchema } from './jsonschema.ts';
import { compareVerdictKeys, containedDir, readRows, type LookupOp, type LookupRow, type RetrievalRow, type ShadowRow, type VerdictRow } from './ledger.ts';
import { LibraryError, type RouteName } from './types.ts';

const limits = thresholds.library;

type Latency = { p50: number | null; p90: number | null };
type Rate = number | null;

/** The usage-ledger step of one locating agent run of `aw library eval` (written by the eval runner). */
export const LOCATE_STEP = 'library.eval.locate';
/** The usage-ledger step of one `aw library index` run. */
export const INDEX_STEP = 'library.index';

/** What one kind of lookup (book list, table of contents, page read, whole-book read) cost a route. */
export type OpStats = { lookups: number; latency_ms: Latency; est_tokens: number };

export type RouteStats = {
  /** Lookups this route answered. */
  lookups: number;
  errors: number;
  error_rate: Rate;
  latency_ms: Latency;
  /** The same, split by kind of lookup; only kinds this route answered appear. */
  by_op: Partial<Record<LookupOp, OpStats>>;
  /** Quiet second lookups this route ran. */
  shadow_runs: number;
  shadow_errors: number;
  shadow_timeouts: number;
  /** Shadow runs that could not start because the book has no known page mapping on this route. */
  shadow_unmapped: number;
  shadow_latency_ms: Latency;
  /** Page text agreement, on lookups this route answered and the other route also ran. */
  agreement: { pages_compared: number; pages_agreed: number; rate: Rate };
  auditor: {
    verdicts: number;
    pass: number;
    fail: number;
    pass_rate: Rate;
    fail_with_corrected_page: number;
    shadow_checked: number;
    shadow_supports: number;
    shadow_supports_rate: Rate;
  };
  enough_data: boolean;
};

export type Confusion = { supports: number; not_supports: number; unknown: number };

/**
 * Returned-text tokens per route. ESTIMATES: characters divided by the ratios in thresholds.json library.tokens,
 * because Claude's tokenizer is not available offline. Rows written before the estimate existed carry none and are
 * left out (`lookups_measured` says how many lookups count). Exact agent tokens are in `agents`.
 */
export type TokenStats = {
  lookups_measured: number;
  total: number;
  per_lookup: Latency;
  /** Average estimated tokens per page returned, over page reads that name their pages. */
  per_page_avg: number | null;
  pages_measured: number;
  /** The quiet second lookups this route ran. */
  shadow: { runs_measured: number; total: number; per_run: Latency };
};
export type TokensReport = { basis: 'estimate'; hebrew_chars_per_token: number; other_chars_per_token: number; routes: Record<RouteName, TokenStats> };

/** Locating-agent runs of library-eval (usage rows with step library.eval.locate), by the route the run was forced to. */
export type AgentStats = {
  runs: number;
  failed: number;
  /** Runs recorded more than once under the same run id (an agent that was tried again). */
  retried: number;
  wall_ms: Latency;
  /** The agent's own token counts as its tool reported them (not estimates). */
  input_tokens: { total: number; median: number | null };
  output_tokens: { total: number; median: number | null };
  /** Null total when no run reported a cost (Codex does not). */
  cost_usd: { total: number | null; median: number | null; known_runs: number };
  /** Retrieval lookups the agent made (tool calls), per run, joined on the run id. */
  lookups_per_run: { median: number | null; total: number };
  /** ESTIMATED tokens of the text those lookups returned, per run. */
  returned_est_tokens_per_run: { median: number | null; total: number };
};
export type AgentsReport = { step: typeof LOCATE_STEP; runs: number; /** Rows whose run id does not name a route. */ unattributed: number; routes: Record<RouteName, AgentStats> };

/** `aw library index` runs (usage rows with step library.index). */
export type IndexingReport = {
  step: typeof INDEX_STEP;
  runs: number;
  failed: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: { total: number | null; known_runs: number };
  wall_ms: Latency;
  models: string[];
};

export type Report = {
  run: string | null;
  /** The library-eval id the report is limited to (run ids `<id>-<route>-c<NN>`), or null. */
  eval: string | null;
  rows: { lookup: number; shadow: number; verdict: number; invalid: number };
  modes: Record<string, number>;
  routes: Record<RouteName, RouteStats>;
  agreement: { lookups_compared: number; pages_compared: number; pages_agreed: number; rate: Rate };
  auditor: {
    verdicts: number;
    /** Distinct page reads that have at least one auditor verdict. */
    lookups_with_verdict: number;
    read_lookups: number;
    /** lookups_with_verdict over read_lookups, never above 100%. */
    verdict_coverage: Rate;
    /** For each auditor verdict, did the shadow's page text also support the claim. */
    shadow_supports_by_verdict: { PASS: Confusion; FAIL: Confusion };
  };
  tokens: TokensReport;
  agents: AgentsReport;
  indexing: IndexingReport;
  data_quality: {
    shadow_pending_verdicts: number;
    shadow_missing_verdicts: number;
    no_quote_verdicts: number;
    lookups_without_shadow_row: number;
    shadow_skipped: Record<string, number>;
    /** Unreadable lines in the usage ledgers (one usage.jsonl per run folder) that were skipped. */
    usage_invalid: number;
  };
  notes: string[];
};

/** Extra input of the report: the usage-ledger rows and the eval filter. Both optional so a retrieval-only report still builds. */
export type ReportInput = { eval?: string | null; usage?: LedgerRow[]; usageInvalid?: number };

function rate(part: number, whole: number): Rate { return whole === 0 ? null : Math.round((part / whole) * 1000) / 1000; }

/** Nearest-rank percentile of `values`; null when there are none. */
export function percentile(values: number[], p: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil((p / 100) * sorted.length) - 1)] as number;
}

const latency = (values: number[]): Latency => ({ p50: percentile(values, 50), p90: percentile(values, 90) });
const sum = (values: number[]): number => values.reduce((total, value) => total + value, 0);
const median = (values: number[]): number | null => percentile(values, 50);
/** Money is summed in micro-dollars so a long list of small costs does not collect float noise. */
const sumCost = (values: number[]): number | null => (values.length === 0 ? null : Math.round(sum(values) * 1e6) / 1e6);
const OPS: LookupOp[] = ['list', 'toc', 'read', 'get'];

/**
 * The run id of a locating agent is exactly `<evalId>-<route>-c<NN>` (route trove or pageindex, claim c01, c02, ...),
 * read from the RIGHT, so an eval id may itself contain the words trove or pageindex. Anything that does not fit is
 * not a locating-agent id: it is reported as unattributed, never guessed at.
 */
export function parseLocateRun(runId: string): { eval: string; route: RouteName; claim: string } | null {
  const match = runId.match(/^(.+)-(trove|pageindex)-(c\d+)$/u);
  return match ? { eval: match[1] as string, route: match[2] as RouteName, claim: match[3] as string } : null;
}
const emptyConfusion = (): Confusion => ({ supports: 0, not_supports: 0, unknown: 0 });
const ROUTES: RouteName[] = ['trove', 'pageindex'];

/** Build the report from ledger rows. `run` keeps only that run's lookups, their shadow rows and their verdicts. */
export function buildReport(rows: RetrievalRow[], invalid: number, run: string | null = null, input: ReportInput = {}): Report {
  const evalId = input.eval ?? null;
  // --eval keeps the runs whose parsed eval id is exactly that id (not a prefix: "study" is not "study-trove-pilot").
  const inScope = (runId: string | null): boolean => (run === null || runId === run) && (evalId === null || (runId !== null && parseLocateRun(runId)?.eval === evalId));
  let lookups = rows.filter((row): row is LookupRow => row.row_type === 'lookup');
  if (run !== null || evalId !== null) lookups = lookups.filter((row) => inScope(row.run_id));
  const ids = new Set(lookups.map((row) => row.lookup_id));
  // One shadow row per lookup; a verdict is the row with the highest ordering key for each (lookup, citation).
  const shadows = new Map<string, ShadowRow>();
  const verdicts = new Map<string, VerdictRow>();
  for (const row of rows) {
    if (!ids.has(row.lookup_id)) continue;
    if (row.row_type === 'shadow') shadows.set(row.lookup_id, row);
    else if (row.row_type === 'verdict') {
      // The newest verdict for a citation is the one with the highest ordering key (when it was invoked, pid, nonce),
      // never the one written last; at an equal key a settled row replaces the pending row it settles.
      const key = `${row.lookup_id}\u0000${row.paragraph_id ?? ''}`;
      const held = verdicts.get(key);
      const order = held ? compareVerdictKeys(row, held) : 1;
      if (!held || order > 0 || (order === 0 && (row.settled === true || held.settled !== true))) verdicts.set(key, row);
    }
  }
  const routes = {} as Record<RouteName, RouteStats>;
  const totals = { lookups: 0, pages: 0, agreed: 0 };
  for (const name of ROUTES) {
    const answered = lookups.filter((row) => row.route_primary === name);
    const failed = answered.filter((row) => !row.primary.ok).length;
    const ran = [...shadows.values()].filter((row) => row.route === name);
    const compared = answered.flatMap((row) => { const agree = shadows.get(row.lookup_id)?.agree; return agree ? [agree] : []; });
    const mine = [...verdicts.values()].filter((row) => row.primary_route === name);
    const passes = mine.filter((row) => row.verdict === 'PASS').length;
    const checked = mine.filter((row) => row.shadow_supports !== null);
    const supported = checked.filter((row) => row.shadow_supports === true).length;
    const pagesCompared = compared.reduce((total, agree) => total + agree.compared, 0);
    const pagesAgreed = compared.reduce((total, agree) => total + agree.agreed, 0);
    totals.lookups += compared.length;
    totals.pages += pagesCompared;
    totals.agreed += pagesAgreed;
    routes[name] = {
      lookups: answered.length,
      errors: failed,
      error_rate: rate(failed, answered.length),
      latency_ms: latency(answered.map((row) => row.primary.latency_ms)),
      by_op: byOp(answered),
      shadow_runs: ran.length,
      shadow_errors: ran.filter((row) => !row.ok && row.error_code !== 'page_map').length,
      shadow_timeouts: ran.filter((row) => row.timed_out).length,
      shadow_unmapped: ran.filter((row) => !row.ok && row.error_code === 'page_map').length,
      shadow_latency_ms: latency(ran.map((row) => row.latency_ms)),
      agreement: { pages_compared: pagesCompared, pages_agreed: pagesAgreed, rate: rate(pagesAgreed, pagesCompared) },
      auditor: {
        verdicts: mine.length,
        pass: passes,
        fail: mine.length - passes,
        pass_rate: rate(passes, mine.length),
        fail_with_corrected_page: mine.filter((row) => row.verdict === 'FAIL' && row.corrected_page !== null).length,
        shadow_checked: checked.length,
        shadow_supports: supported,
        shadow_supports_rate: rate(supported, checked.length),
      },
      enough_data: answered.length >= limits.report.minLookups,
    };
  }
  const tokens = tokenReport(lookups, [...shadows.values()]);
  const usage = (input.usage ?? []).filter((row) => inScope(row.run_id));
  const confusion = { PASS: emptyConfusion(), FAIL: emptyConfusion() };
  for (const row of verdicts.values()) {
    const bucket = confusion[row.verdict];
    if (row.shadow_supports === true) bucket.supports += 1;
    else if (row.shadow_supports === false) bucket.not_supports += 1;
    else bucket.unknown += 1;
  }
  const readLookups = lookups.filter((row) => row.op === 'read' || row.op === 'get');
  const withVerdict = new Set([...verdicts.values()].map((row) => row.lookup_id).filter((id) => readLookups.some((lookup) => lookup.lookup_id === id))).size;
  const modes: Record<string, number> = {};
  for (const row of lookups) { const key = row.mode === 'both' ? `both, ${row.route_primary} answers` : row.mode; modes[key] = (modes[key] ?? 0) + 1; }
  const skipped: Record<string, number> = {};
  for (const row of lookups) if (row.shadow_status.startsWith('skipped:')) { const why = row.shadow_status.slice(8); skipped[why] = (skipped[why] ?? 0) + 1; }
  const settled = [...verdicts.values()];
  const report: Report = {
    run,
    eval: evalId,
    rows: { lookup: lookups.length, shadow: shadows.size, verdict: verdicts.size, invalid },
    modes,
    routes,
    agreement: { lookups_compared: totals.lookups, pages_compared: totals.pages, pages_agreed: totals.agreed, rate: rate(totals.agreed, totals.pages) },
    auditor: { verdicts: verdicts.size, lookups_with_verdict: withVerdict, read_lookups: readLookups.length, verdict_coverage: rate(withVerdict, readLookups.length), shadow_supports_by_verdict: confusion },
    tokens,
    agents: agentReport(usage, lookups),
    indexing: indexingReport(usage),
    data_quality: {
      shadow_pending_verdicts: settled.filter((row) => row.shadow_supports_reason === 'shadow_pending').length,
      shadow_missing_verdicts: settled.filter((row) => row.shadow_supports_reason === 'shadow_missing').length,
      no_quote_verdicts: settled.filter((row) => row.shadow_supports_reason === 'no_quote').length,
      lookups_without_shadow_row: lookups.filter((row) => row.shadow_status === 'pending' && !shadows.has(row.lookup_id)).length,
      shadow_skipped: skipped,
      usage_invalid: input.usageInvalid ?? 0,
    },
    notes: [],
  };
  if (lookups.length === 0) report.notes.push(evalId === null ? 'No lookups are recorded yet.' : `No lookups are recorded for evaluation ${evalId}.`);
  for (const name of ROUTES) if (routes[name].lookups > 0 && !routes[name].enough_data) report.notes.push(`Only ${routes[name].lookups} lookups were answered by ${name}; treat its rates as a rough guide (${limits.report.minLookups} or more is a fair sample).`);
  if (report.data_quality.shadow_pending_verdicts > 0) report.notes.push('Some verdicts were recorded while the second lookup was still running; run the report again with --settle to finish them.');
  if (report.data_quality.lookups_without_shadow_row > 0) report.notes.push(`${report.data_quality.lookups_without_shadow_row} second lookups left no result (still running, or stopped early).`);
  if (lookups.length > 0 && report.auditor.verdicts === 0) report.notes.push('No auditor verdicts are recorded yet, so pass rates and second-library support are empty.');
  if (report.data_quality.usage_invalid > 0) report.notes.push(`${report.data_quality.usage_invalid} unreadable lines in the usage ledgers were skipped.`);
  return report;
}

function byOp(answered: LookupRow[]): Partial<Record<LookupOp, OpStats>> {
  const out: Partial<Record<LookupOp, OpStats>> = {};
  for (const op of OPS) {
    const mine = answered.filter((row) => row.op === op);
    if (mine.length === 0) continue;
    out[op] = { lookups: mine.length, latency_ms: latency(mine.map((row) => row.primary.latency_ms)), est_tokens: sum(mine.map((row) => (row.primary.ok ? row.primary.est_tokens ?? 0 : 0))) };
  }
  return out;
}

function tokenReport(lookups: LookupRow[], shadows: ShadowRow[]): TokensReport {
  const routes = {} as Record<RouteName, TokenStats>;
  for (const name of ROUTES) {
    const measured = lookups.filter((row) => row.route_primary === name && row.primary.ok && row.primary.est_tokens !== undefined);
    const estimates = measured.map((row) => row.primary.est_tokens as number);
    // Pages returned: only page reads that name their pages count towards the per-page average.
    // Per page: divide by the distinct pages the call returned (pages_returned), never by the route pages it names:
    // several route pages can merge into one returned page. Rows without that count give no per-page figure.
    const paged = measured.filter((row) => (row.op === 'read' || row.op === 'get') && (row.primary.pages_returned ?? 0) > 0);
    const pages = sum(paged.map((row) => row.primary.pages_returned as number));
    const quiet = shadows.filter((row) => row.route === name && row.ok && row.est_tokens !== undefined).map((row) => row.est_tokens as number);
    routes[name] = {
      lookups_measured: measured.length,
      total: sum(estimates),
      per_lookup: latency(estimates),
      per_page_avg: pages === 0 ? null : Math.round(sum(paged.map((row) => row.primary.est_tokens as number)) / pages),
      pages_measured: pages,
      shadow: { runs_measured: quiet.length, total: sum(quiet), per_run: latency(quiet) },
    };
  }
  return { basis: 'estimate', hebrew_chars_per_token: limits.tokens.hebrewCharsPerToken, other_chars_per_token: limits.tokens.otherCharsPerToken, routes };
}

function agentReport(usage: LedgerRow[], lookups: LookupRow[]): AgentsReport {
  const located = usage.filter((row) => row.step === LOCATE_STEP);
  const byRun = new Map<string, { count: number; est: number }>();
  for (const row of lookups) {
    if (row.run_id === null) continue;
    const held = byRun.get(row.run_id) ?? { count: 0, est: 0 };
    held.count += 1;
    if (row.primary.ok) held.est += row.primary.est_tokens ?? 0;
    byRun.set(row.run_id, held);
  }
  const routes = {} as Record<RouteName, AgentStats>;
  let unattributed = 0;
  for (const row of located) if (parseLocateRun(row.run_id) === null) unattributed += 1;
  for (const name of ROUTES) {
    const mine = located.filter((row) => parseLocateRun(row.run_id)?.route === name);
    const ids = [...new Set(mine.map((row) => row.run_id))];
    const costs = mine.flatMap((row) => (row.cost_usd === null ? [] : [row.cost_usd]));
    const counts = ids.map((id) => byRun.get(id)?.count ?? 0);
    const returned = ids.map((id) => byRun.get(id)?.est ?? 0);
    routes[name] = {
      runs: mine.length,
      failed: mine.filter((row) => row.exit !== 'OK').length,
      retried: mine.length - ids.length,
      wall_ms: latency(mine.map((row) => row.latency_ms)),
      input_tokens: { total: sum(mine.map((row) => row.input_tokens)), median: median(mine.map((row) => row.input_tokens)) },
      output_tokens: { total: sum(mine.map((row) => row.output_tokens)), median: median(mine.map((row) => row.output_tokens)) },
      cost_usd: { total: sumCost(costs), median: median(costs), known_runs: costs.length },
      lookups_per_run: { median: median(counts), total: sum(counts) },
      returned_est_tokens_per_run: { median: median(returned), total: sum(returned) },
    };
  }
  return { step: LOCATE_STEP, runs: located.length, unattributed, routes };
}

function indexingReport(usage: LedgerRow[]): IndexingReport {
  const mine = usage.filter((row) => row.step === INDEX_STEP);
  const costs = mine.flatMap((row) => (row.cost_usd === null ? [] : [row.cost_usd]));
  return {
    step: INDEX_STEP,
    runs: mine.length,
    failed: mine.filter((row) => row.exit !== 'OK').length,
    input_tokens: sum(mine.map((row) => row.input_tokens)),
    output_tokens: sum(mine.map((row) => row.output_tokens)),
    cost_usd: { total: sumCost(costs), known_runs: costs.length },
    wall_ms: latency(mine.map((row) => row.latency_ms)),
    models: [...new Set(mine.map((row) => row.model))].sort(),
  };
}

/**
 * The usage-ledger rows of this project that the report uses (steps library.eval.locate and library.index), read from
 * `.academic-helper/runs/<run id>/usage.jsonl`. Only real folders and files inside the project are read (a symlink is
 * skipped), and every line is checked against the usage-row schema; unreadable lines are counted, not returned.
 */
export async function readUsageRows(project: string): Promise<{ rows: LedgerRow[]; invalid: number }> {
  const rows: LedgerRow[] = [];
  let invalid = 0;
  const dir = await containedDir(project, ['runs']);
  if (!dir) return { rows, invalid };
  let names: string[];
  try { names = (await readdir(dir)).sort(); } catch { return { rows, invalid }; }
  for (const name of names) {
    let text: string;
    try {
      const folder = join(dir, name);
      if (!(await lstat(folder)).isDirectory()) continue;
      const file = join(folder, 'usage.jsonl');
      const info = await lstat(file);
      if (!info.isFile() || info.size > limits.maxBufferBytes) continue;
      text = await readFile(file, 'utf8');
    } catch { continue; }
    for (const line of text.split('\n')) {
      if (!line.trim()) continue;
      try {
        const parsed: unknown = JSON.parse(line);
        if (checkSchema(usageSchema as JsonSchema, parsed).length > 0) invalid += 1;
        else if ((parsed as LedgerRow).step === LOCATE_STEP || (parsed as LedgerRow).step === INDEX_STEP) rows.push(parsed as LedgerRow);
      } catch { invalid += 1; }
    }
  }
  return { rows, invalid };
}

/**
 * Report options: `eval` limits the report to one library-eval (lookups and agent runs whose run id parses as `<eval>-<route>-c<NN>` with exactly that eval id);
 * it cannot be combined with an exact `run`.
 */
export type ReportOptions = { eval?: string | null };

export async function reportFor(project: string, run: string | null, options: ReportOptions = {}): Promise<Report> {
  const evalId = options.eval ?? null;
  if (evalId !== null) {
    if (run !== null) throw new LibraryError('usage', 'ERROR library report: use --run or --eval, not both');
    if (!/^[A-Za-z0-9][A-Za-z0-9._#:-]{0,79}$/u.test(evalId)) throw new LibraryError('usage', 'ERROR library report: --eval must be a plain id (letters, digits and . _ # : - only)');
  }
  const [{ rows, invalid }, usage] = await Promise.all([readRows(project), readUsageRows(project)]);
  return buildReport(rows, invalid, run, { eval: evalId, usage: usage.rows, usageInvalid: usage.invalid });
}

const pct = (value: Rate): string => (value === null ? 'n/a' : `${Math.round(value * 1000) / 10}%`);
const ms = (value: number | null): string => (value === null ? 'n/a' : `${value} ms`);
const secs = (value: number | null): string => (value === null ? 'n/a' : `${(Math.round(value / 100) / 10).toFixed(1)} s`);
const num = (value: number | null): string => (value === null ? 'n/a' : value.toLocaleString('en-US'));
const usd = (value: number | null): string => (value === null ? 'n/a' : `$${value.toFixed(value >= 1 ? 2 : 3)}`);
const KIND: Record<LookupOp, string> = { list: 'book lists', toc: 'tables of contents', read: 'page reads', get: 'whole-book reads' };
const ROUTE_NAME: Record<RouteName, string> = { trove: 'Trove', pageindex: 'PageIndex' };

/** The returned-text, locating-agent and indexing sections; each is left out when there is nothing to say. */
function formatMeasures(report: Report): string[] {
  const lines: string[] = [];
  const { tokens, agents, indexing } = report;
  const tokenLines: string[] = [];
  for (const name of ROUTES) {
    const route = report.routes[name];
    const stats = tokens.routes[name];
    if (stats.lookups_measured === 0 && stats.shadow.runs_measured === 0) continue;
    const parts: string[] = [];
    if (stats.lookups_measured > 0) {
      parts.push(`${route.lookups} lookups answered${stats.lookups_measured < route.lookups ? ` (${stats.lookups_measured} carry an estimate; older rows do not)` : ''}, about ${num(stats.total)} tokens in all; half return ${num(stats.per_lookup.p50)} or fewer, nine in ten ${num(stats.per_lookup.p90)} or fewer${stats.per_page_avg === null ? '' : `; about ${num(stats.per_page_avg)} per page`}`);
    }
    if (stats.shadow.runs_measured > 0) parts.push(`second lookups ${stats.shadow.runs_measured}, about ${num(stats.shadow.total)} tokens in all`);
    tokenLines.push(`  ${ROUTE_NAME[name]}: ${parts.join('; ')}`);
  }
  if (tokenLines.length > 0) {
    lines.push('', `Returned text (token figures are estimates: about ${tokens.hebrew_chars_per_token} Hebrew or ${tokens.other_chars_per_token} other characters per token, so Claude's own counts will differ)`, ...tokenLines);
  }
  const agentLines: string[] = [];
  for (const name of ROUTES) {
    const stats = agents.routes[name];
    if (stats.runs === 0) continue;
    const cost = stats.cost_usd.known_runs === 0 ? 'cost not reported' : `cost ${usd(stats.cost_usd.total)} in all (median ${usd(stats.cost_usd.median)}; reported for ${stats.cost_usd.known_runs} of ${stats.runs} runs)`;
    agentLines.push(`  ${ROUTE_NAME[name]}: ${stats.runs} runs (${stats.failed} failed${stats.retried > 0 ? `, ${stats.retried} tried again` : ''}); half finish within ${secs(stats.wall_ms.p50)}, nine in ten within ${secs(stats.wall_ms.p90)}; per run, median ${num(stats.input_tokens.median)} tokens in and ${num(stats.output_tokens.median)} out; ${cost}; median ${num(stats.lookups_per_run.median)} lookups per run returning about ${num(stats.returned_est_tokens_per_run.median)} tokens (estimate)`);
  }
  if (agentLines.length > 0) lines.push('', "Locating agents (library-eval runs; the agent tokens and cost are what the agent's own tool reported)", ...agentLines);
  else if (report.rows.lookup > 0 && agents.unattributed === 0) lines.push('', 'Agent tokens and cost are recorded only for library-eval runs (none here); the citation checker running inside a writing session does not report its tokens.');
  if (agents.unattributed > 0) lines.push(`  ${agents.unattributed} locating-agent runs have a run id that names no route and are not counted per route.`);
  if (indexing.runs > 0) {
    const cost = indexing.cost_usd.known_runs === 0 ? 'cost not reported' : `cost ${usd(indexing.cost_usd.total)} (reported for ${indexing.cost_usd.known_runs} of ${indexing.runs} runs)`;
    lines.push('', 'Indexing (page summaries for PageIndex, from the usage ledger)', `  ${indexing.runs} runs (${indexing.failed} failed), ${num(indexing.input_tokens)} tokens in and ${num(indexing.output_tokens)} out, ${cost}; half finish within ${secs(indexing.wall_ms.p50)}${indexing.models.length > 0 ? `; model ${indexing.models.join(', ')}` : ''}`);
  }
  return lines;
}

/** The report in plain words, for a researcher at a terminal (`--json` prints the Report object instead). */
export function formatReport(report: Report): string {
  const lines: string[] = [];
  lines.push(`Library report${report.run ? ` for run ${report.run}` : ''}${report.eval ? ` for evaluation ${report.eval}` : ''}`);
  lines.push(`Lookups ${report.rows.lookup}, second lookups ${report.rows.shadow}, auditor verdicts ${report.rows.verdict}${report.rows.invalid ? `, ${report.rows.invalid} unreadable lines skipped` : ''}`);
  const modes = Object.entries(report.modes);
  if (modes.length) lines.push(`Setups seen: ${modes.map(([mode, count]) => `${mode} (${count})`).join('; ')}`);
  for (const name of ROUTES) {
    const route = report.routes[name];
    if (route.lookups === 0 && route.shadow_runs === 0) continue;
    lines.push('', name === 'trove' ? 'Trove' : 'PageIndex');
    if (route.lookups > 0) lines.push(`  Answered ${route.lookups} lookups, ${route.errors} failed (${pct(route.error_rate)}); half finish within ${ms(route.latency_ms.p50)}, nine in ten within ${ms(route.latency_ms.p90)}`);
    const kinds = OPS.flatMap((op) => { const stats = route.by_op[op]; return stats ? [`${KIND[op]} ${stats.lookups} (half within ${ms(stats.latency_ms.p50)})`] : []; });
    if (kinds.length > 1) lines.push(`  By kind: ${kinds.join('; ')}`);
    if (route.shadow_runs > 0) lines.push(`  Ran quietly alongside ${route.shadow_runs} times: ${route.shadow_errors} failed, ${route.shadow_timeouts} timed out, ${route.shadow_unmapped} had no page mapping; half within ${ms(route.shadow_latency_ms.p50)}, nine in ten within ${ms(route.shadow_latency_ms.p90)}`);
    if (route.agreement.pages_compared > 0) lines.push(`  When ${name} answered, the other library returned the same page text for ${route.agreement.pages_agreed} of ${route.agreement.pages_compared} pages (${pct(route.agreement.rate)})`);
    if (route.auditor.verdicts > 0) lines.push(`  Auditor: ${route.auditor.pass} of ${route.auditor.verdicts} citations passed (${pct(route.auditor.pass_rate)}), ${route.auditor.fail_with_corrected_page} failed with a corrected page; the other library's page also supported the claim for ${route.auditor.shadow_supports} of ${route.auditor.shadow_checked} checked (${pct(route.auditor.shadow_supports_rate)})`);
  }
  lines.push('', `Page agreement overall: ${report.agreement.pages_agreed} of ${report.agreement.pages_compared} pages (${pct(report.agreement.rate)}) over ${report.agreement.lookups_compared} lookups`);
  const confusion = report.auditor.shadow_supports_by_verdict;
  lines.push(`Lookups with an auditor verdict: ${report.auditor.lookups_with_verdict} of ${report.auditor.read_lookups} page reads (${pct(report.auditor.verdict_coverage)}); ${report.auditor.verdicts} verdicts in all`);
  lines.push(`  Passed: the other library supports ${confusion.PASS.supports}, does not ${confusion.PASS.not_supports}, unknown ${confusion.PASS.unknown}`);
  lines.push(`  Failed: the other library supports ${confusion.FAIL.supports}, does not ${confusion.FAIL.not_supports}, unknown ${confusion.FAIL.unknown}`);
  const quality = report.data_quality;
  lines.push(`Gaps: ${quality.shadow_pending_verdicts} verdicts waiting on the second lookup, ${quality.shadow_missing_verdicts} with no second-lookup text, ${quality.no_quote_verdicts} without a usable quote, ${quality.lookups_without_shadow_row} second lookups with no result`);
  const skipped = Object.entries(quality.shadow_skipped);
  if (skipped.length) lines.push(`Second lookups skipped: ${skipped.map(([why, count]) => `${why.replace(/_/gu, ' ')} (${count})`).join(', ')}`);
  lines.push(...formatMeasures(report));
  for (const note of report.notes) lines.push('', note);
  return `${lines.join('\n')}\n`;
}
