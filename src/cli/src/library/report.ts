import thresholds from '../../../thresholds.json' with { type: 'json' };
import { readRows, type LookupRow, type RetrievalRow, type ShadowRow, type VerdictRow } from './ledger.ts';
import type { RouteName } from './types.ts';

const limits = thresholds.library;

type Latency = { p50: number | null; p90: number | null };
type Rate = number | null;

export type RouteStats = {
  /** Lookups this route answered. */
  lookups: number;
  errors: number;
  error_rate: Rate;
  latency_ms: Latency;
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

export type Report = {
  run: string | null;
  rows: { lookup: number; shadow: number; verdict: number; invalid: number };
  modes: Record<string, number>;
  routes: Record<RouteName, RouteStats>;
  agreement: { lookups_compared: number; pages_compared: number; pages_agreed: number; rate: Rate };
  auditor: {
    verdicts: number;
    read_lookups: number;
    verdict_coverage: Rate;
    /** For each auditor verdict, did the shadow's page text also support the claim. */
    shadow_supports_by_verdict: { PASS: Confusion; FAIL: Confusion };
  };
  data_quality: {
    shadow_pending_verdicts: number;
    shadow_missing_verdicts: number;
    no_quote_verdicts: number;
    lookups_without_shadow_row: number;
    shadow_skipped: Record<string, number>;
  };
  notes: string[];
};

function rate(part: number, whole: number): Rate { return whole === 0 ? null : Math.round((part / whole) * 1000) / 1000; }

/** Nearest-rank percentile of `values`; null when there are none. */
export function percentile(values: number[], p: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil((p / 100) * sorted.length) - 1)] as number;
}

const latency = (values: number[]): Latency => ({ p50: percentile(values, 50), p90: percentile(values, 90) });
const emptyConfusion = (): Confusion => ({ supports: 0, not_supports: 0, unknown: 0 });
const ROUTES: RouteName[] = ['trove', 'pageindex'];

/** Build the report from ledger rows. `run` keeps only that run's lookups, their shadow rows and their verdicts. */
export function buildReport(rows: RetrievalRow[], invalid: number, run: string | null = null): Report {
  let lookups = rows.filter((row): row is LookupRow => row.row_type === 'lookup');
  if (run !== null) lookups = lookups.filter((row) => row.run_id === run);
  const ids = new Set(lookups.map((row) => row.lookup_id));
  // One shadow row per lookup; a verdict is the last row for each (lookup, citation), so a settled row replaces a pending one.
  const shadows = new Map<string, ShadowRow>();
  const verdicts = new Map<string, VerdictRow>();
  for (const row of rows) {
    if (!ids.has(row.lookup_id)) continue;
    if (row.row_type === 'shadow') shadows.set(row.lookup_id, row);
    else if (row.row_type === 'verdict') verdicts.set(`${row.lookup_id}\u0000${row.paragraph_id ?? ''}`, row);
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
    const pagesCompared = compared.reduce((sum, agree) => sum + agree.compared, 0);
    const pagesAgreed = compared.reduce((sum, agree) => sum + agree.agreed, 0);
    totals.lookups += compared.length;
    totals.pages += pagesCompared;
    totals.agreed += pagesAgreed;
    routes[name] = {
      lookups: answered.length,
      errors: failed,
      error_rate: rate(failed, answered.length),
      latency_ms: latency(answered.map((row) => row.primary.latency_ms)),
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
  const confusion = { PASS: emptyConfusion(), FAIL: emptyConfusion() };
  for (const row of verdicts.values()) {
    const bucket = confusion[row.verdict];
    if (row.shadow_supports === true) bucket.supports += 1;
    else if (row.shadow_supports === false) bucket.not_supports += 1;
    else bucket.unknown += 1;
  }
  const readLookups = lookups.filter((row) => row.op === 'read' || row.op === 'get');
  const modes: Record<string, number> = {};
  for (const row of lookups) { const key = row.mode === 'both' ? `both, ${row.route_primary} answers` : row.mode; modes[key] = (modes[key] ?? 0) + 1; }
  const skipped: Record<string, number> = {};
  for (const row of lookups) if (row.shadow_status.startsWith('skipped:')) { const why = row.shadow_status.slice(8); skipped[why] = (skipped[why] ?? 0) + 1; }
  const settled = [...verdicts.values()];
  const report: Report = {
    run,
    rows: { lookup: lookups.length, shadow: shadows.size, verdict: verdicts.size, invalid },
    modes,
    routes,
    agreement: { lookups_compared: totals.lookups, pages_compared: totals.pages, pages_agreed: totals.agreed, rate: rate(totals.agreed, totals.pages) },
    auditor: { verdicts: verdicts.size, read_lookups: readLookups.length, verdict_coverage: rate(verdicts.size, readLookups.length), shadow_supports_by_verdict: confusion },
    data_quality: {
      shadow_pending_verdicts: settled.filter((row) => row.shadow_supports_reason === 'shadow_pending').length,
      shadow_missing_verdicts: settled.filter((row) => row.shadow_supports_reason === 'shadow_missing').length,
      no_quote_verdicts: settled.filter((row) => row.shadow_supports_reason === 'no_quote').length,
      lookups_without_shadow_row: lookups.filter((row) => row.shadow_status === 'pending' && !shadows.has(row.lookup_id)).length,
      shadow_skipped: skipped,
    },
    notes: [],
  };
  if (lookups.length === 0) report.notes.push('No lookups are recorded yet.');
  for (const name of ROUTES) if (routes[name].lookups > 0 && !routes[name].enough_data) report.notes.push(`Only ${routes[name].lookups} lookups were answered by ${name}; treat its rates as a rough guide (${limits.report.minLookups} or more is a fair sample).`);
  if (report.data_quality.shadow_pending_verdicts > 0) report.notes.push('Some verdicts were recorded while the second lookup was still running; run the report again with --settle to finish them.');
  if (report.data_quality.lookups_without_shadow_row > 0) report.notes.push(`${report.data_quality.lookups_without_shadow_row} second lookups left no result (still running, or stopped early).`);
  if (lookups.length > 0 && report.auditor.verdicts === 0) report.notes.push('No auditor verdicts are recorded yet, so pass rates and second-library support are empty.');
  return report;
}

export async function reportFor(project: string, run: string | null): Promise<Report> {
  const { rows, invalid } = await readRows(project);
  return buildReport(rows, invalid, run);
}

const pct = (value: Rate): string => (value === null ? 'n/a' : `${Math.round(value * 1000) / 10}%`);
const ms = (value: number | null): string => (value === null ? 'n/a' : `${value} ms`);

/** The report in plain words, for a researcher at a terminal (`--json` prints the Report object instead). */
export function formatReport(report: Report): string {
  const lines: string[] = [];
  lines.push(`Library report${report.run ? ` for run ${report.run}` : ''}`);
  lines.push(`Lookups ${report.rows.lookup}, second lookups ${report.rows.shadow}, auditor verdicts ${report.rows.verdict}${report.rows.invalid ? `, ${report.rows.invalid} unreadable lines skipped` : ''}`);
  const modes = Object.entries(report.modes);
  if (modes.length) lines.push(`Setups seen: ${modes.map(([mode, count]) => `${mode} (${count})`).join('; ')}`);
  for (const name of ROUTES) {
    const route = report.routes[name];
    if (route.lookups === 0 && route.shadow_runs === 0) continue;
    lines.push('', name === 'trove' ? 'Trove' : 'PageIndex');
    if (route.lookups > 0) lines.push(`  Answered ${route.lookups} lookups, ${route.errors} failed (${pct(route.error_rate)}); half finish within ${ms(route.latency_ms.p50)}, nine in ten within ${ms(route.latency_ms.p90)}`);
    if (route.shadow_runs > 0) lines.push(`  Ran quietly alongside ${route.shadow_runs} times: ${route.shadow_errors} failed, ${route.shadow_timeouts} timed out, ${route.shadow_unmapped} had no page mapping; half within ${ms(route.shadow_latency_ms.p50)}, nine in ten within ${ms(route.shadow_latency_ms.p90)}`);
    if (route.agreement.pages_compared > 0) lines.push(`  When ${name} answered, the other library returned the same page text for ${route.agreement.pages_agreed} of ${route.agreement.pages_compared} pages (${pct(route.agreement.rate)})`);
    if (route.auditor.verdicts > 0) lines.push(`  Auditor: ${route.auditor.pass} of ${route.auditor.verdicts} citations passed (${pct(route.auditor.pass_rate)}), ${route.auditor.fail_with_corrected_page} failed with a corrected page; the other library's page also supported the claim for ${route.auditor.shadow_supports} of ${route.auditor.shadow_checked} checked (${pct(route.auditor.shadow_supports_rate)})`);
  }
  lines.push('', `Page agreement overall: ${report.agreement.pages_agreed} of ${report.agreement.pages_compared} pages (${pct(report.agreement.rate)}) over ${report.agreement.lookups_compared} lookups`);
  const confusion = report.auditor.shadow_supports_by_verdict;
  lines.push(`Auditor verdicts recorded: ${report.auditor.verdicts} for ${report.auditor.read_lookups} page reads (${pct(report.auditor.verdict_coverage)})`);
  lines.push(`  Passed: the other library supports ${confusion.PASS.supports}, does not ${confusion.PASS.not_supports}, unknown ${confusion.PASS.unknown}`);
  lines.push(`  Failed: the other library supports ${confusion.FAIL.supports}, does not ${confusion.FAIL.not_supports}, unknown ${confusion.FAIL.unknown}`);
  const quality = report.data_quality;
  lines.push(`Gaps: ${quality.shadow_pending_verdicts} verdicts waiting on the second lookup, ${quality.shadow_missing_verdicts} with no second-lookup text, ${quality.no_quote_verdicts} without a usable quote, ${quality.lookups_without_shadow_row} second lookups with no result`);
  const skipped = Object.entries(quality.shadow_skipped);
  if (skipped.length) lines.push(`Second lookups skipped: ${skipped.map(([why, count]) => `${why.replace(/_/gu, ' ')} (${count})`).join(', ')}`);
  for (const note of report.notes) lines.push('', note);
  return `${lines.join('\n')}\n`;
}
