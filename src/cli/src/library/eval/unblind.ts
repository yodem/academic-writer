import { writeFile } from 'node:fs/promises';
import { stripFragment } from '../registry.ts';
import { LibraryError } from '../types.ts';
import { readJson, readValid, runFile, validate, writeJson, type EvalPaths } from './files.ts';
import { checkCommitment, effective } from './judgments.ts';
import { evalLimits } from './limits.ts';
import { median, signTestP, sum, wilson95 } from './stats.ts';
import type { Claim, Judgments, Plan, Route, Run } from './types.ts';

const NAME: Record<Route, string> = { trove: 'Trove', pageindex: 'PageIndex' };

type Rate = { eligible: number; hits: number; rate: number | null };
export type RouteReport = {
  route: Route;
  wins: number; losses: number; ties: number; neither: number;
  win_rate: number | null; win_rate_ci95: [number, number] | null;
  runs: { ok: number; error: number };
  cited_page_hit: Rate; auditor_pass_hit: Rate; corrected_page_hit: Rate;
  cost_usd: { total: number | null; median: number | null };
  tokens: { input_total: number; output_total: number; input_median: number | null; output_median: number | null };
  wall_s: { total: number; median: number | null };
  tool_calls_median: number | null;
  returned_est_tokens: { total: number | null; median: number | null };
  returned_chars: { total: number | null; median: number | null };
};

export type PairReport = {
  pair_id: string; claim_id: string; claim: string;
  judgment: 'A' | 'B' | 'same' | 'neither' | 'skip' | 'none'; by: 'judge' | 'auto' | 'none'; note: string;
  option_routes: { A: Route; B: Route };
  preferred: Route | null;
  pages: Record<Route, { book: string | null; pages: number[] }>;
};

export type Report = {
  schema: 1;
  eval_id: string;
  generated_at: string;
  forced: boolean;
  n_pairs: number; n_judged: number; n_auto_same: number; n_skipped: number; n_unjudged: number;
  decisive: number;
  routes: Record<string, RouteReport>;
  sign_test: { first: Route; second: Route; first_wins: number; decisive: number; p_value: number | null };
  enough_pairs: boolean;
  statement: string;
  auditor_agreement: { eligible: number; agree: number; disagree: number; rate: number | null };
  pairs: PairReport[];
};

function rate(eligible: number, hits: number): Rate { return { eligible, hits, rate: eligible === 0 ? null : hits / eligible }; }

function hitsOf(run: Run | undefined, claim: Claim, pages: number[]): boolean {
  if (!run || run.status !== 'ok' || !run.answer) return false;
  return stripFragment(run.answer.book) === stripFragment(claim.source_id) && run.answer.pages.some((page) => pages.includes(page));
}

function routeReport(route: Route, plan: Plan, runs: Map<string, Run>, tally: { wins: number; losses: number; ties: number; neither: number }): RouteReport {
  const own = plan.claims.map((claim) => ({ claim, run: runs.get(`${claim.id}:${route}`) }));
  const have = own.filter((entry): entry is { claim: Claim; run: Run } => entry.run !== undefined);
  const ok = have.filter((entry) => entry.run.status === 'ok');
  const costs = have.map((entry) => entry.run.cost_usd).filter((value): value is number => value !== null);
  const est = have.map((entry) => entry.run.returned_est_tokens).filter((value): value is number => value !== null);
  const chars = have.map((entry) => entry.run.returned_chars).filter((value): value is number => value !== null);
  const decisive = tally.wins + tally.losses;
  const cited = own.filter((entry) => entry.claim.cited_trove_pages.length > 0);
  const passed = cited.filter((entry) => entry.claim.auditor_verdict === 'PASS');
  const corrected = own.filter((entry) => entry.claim.auditor_verdict === 'FAIL' && entry.claim.corrected_page !== null);
  return {
    route, ...tally,
    win_rate: decisive === 0 ? null : tally.wins / decisive, win_rate_ci95: wilson95(tally.wins, decisive),
    runs: { ok: ok.length, error: have.length - ok.length },
    cited_page_hit: rate(cited.length, cited.filter((entry) => hitsOf(entry.run, entry.claim, entry.claim.cited_trove_pages)).length),
    auditor_pass_hit: rate(passed.length, passed.filter((entry) => hitsOf(entry.run, entry.claim, entry.claim.cited_trove_pages)).length),
    corrected_page_hit: rate(corrected.length, corrected.filter((entry) => hitsOf(entry.run, entry.claim, [entry.claim.corrected_page as number])).length),
    cost_usd: { total: costs.length === 0 ? null : sum(costs), median: median(ok.map((entry) => entry.run.cost_usd).filter((value): value is number => value !== null)) },
    tokens: {
      input_total: sum(have.map((entry) => entry.run.input_tokens)), output_total: sum(have.map((entry) => entry.run.output_tokens)),
      input_median: median(ok.map((entry) => entry.run.input_tokens)), output_median: median(ok.map((entry) => entry.run.output_tokens)),
    },
    wall_s: { total: sum(have.map((entry) => entry.run.wall_ms)) / 1000, median: ((m) => (m === null ? null : m / 1000))(median(ok.map((entry) => entry.run.wall_ms))) },
    tool_calls_median: median(ok.map((entry) => entry.run.n_reads + entry.run.n_toc)),
    returned_est_tokens: { total: est.length === 0 ? null : sum(est), median: median(est) },
    returned_chars: { total: chars.length === 0 ? null : sum(chars), median: median(chars) },
  };
}

/**
 * The unblinded result. Refused before judgments are imported (and when anything is unjudged) unless `force`; refused
 * always when the sealed mapping no longer matches the commitment pairs.json and the stored judgments carry.
 */
export async function unblind(options: { paths: EvalPaths; force: boolean; now: Date }): Promise<Report> {
  const { paths } = options;
  const plan = await readValid<Plan>('plan', paths.plan, 'plan');
  const { pairs, mapping, pairsSha } = await checkCommitment(paths);
  const raw = await readJson(paths.judgments);
  if (raw === null && !options.force) throw new LibraryError('usage', 'ERROR library eval unblind: refused: no judgments are imported yet. Judge the pairs and run `aw library eval import` first (--force overrides, and shows the key before anyone has judged)');
  if (raw !== null && validate('judgments', raw).length > 0) throw new LibraryError('parse', 'ERROR library eval unblind: judgments.json is not valid');
  const judgments = raw as Judgments | null;
  if (judgments && (judgments.mapping_sha256 !== pairs.mapping_sha256 || judgments.pairs_sha256 !== pairsSha)) {
    throw new LibraryError('parse', 'ERROR library eval unblind: the pairs or the sealed mapping changed after the judgments were stored; refusing to unblind');
  }
  const latest = effective(judgments);
  const unjudged = pairs.pairs.filter((pair) => !latest.has(pair.pair_id));
  if (unjudged.length > 0 && !options.force) throw new LibraryError('usage', `ERROR library eval unblind: refused: ${unjudged.length} pair(s) are not judged yet (--force overrides)`);

  const runs = new Map<string, Run>();
  for (const claim of plan.claims) {
    for (const route of plan.routes) {
      const value = await readJson(runFile(paths, claim.id, route));
      if (value !== null && validate('run', value).length === 0) runs.set(`${claim.id}:${route}`, value as Run);
    }
  }
  const [first, second] = plan.routes as [Route, Route];
  const tally: Record<Route, { wins: number; losses: number; ties: number; neither: number }> = {
    trove: { wins: 0, losses: 0, ties: 0, neither: 0 }, pageindex: { wins: 0, losses: 0, ties: 0, neither: 0 },
  };
  const claims = new Map(plan.claims.map((claim) => [claim.id, claim]));
  const rows: PairReport[] = [];
  let skipped = 0;
  let autoSame = 0;
  let judged = 0;
  let agree = 0;
  let disagree = 0;
  for (const entry of mapping.pairs) {
    const pair = pairs.pairs.find((candidate) => candidate.pair_id === entry.pair_id);
    const claim = claims.get(entry.claim_id);
    if (!pair || !claim) continue;
    const judgment = latest.get(entry.pair_id);
    const verdict = judgment?.verdict ?? 'none';
    const routeOf = { A: entry.A, B: entry.B };
    let preferred: Route | null = null;
    if (verdict === 'A' || verdict === 'B') {
      preferred = routeOf[verdict];
      const loser: Route = preferred === first ? second : first;
      tally[preferred].wins += 1;
      tally[loser].losses += 1;
    } else if (verdict === 'same') { tally[first].ties += 1; tally[second].ties += 1; }
    else if (verdict === 'neither') { tally[first].neither += 1; tally[second].neither += 1; }
    if (verdict === 'skip') skipped += 1;
    if (judgment?.source === 'auto') autoSame += 1;
    else if (verdict !== 'skip' && verdict !== 'none') judged += 1;
    const byRoute = (route: Route): { book: string | null; pages: number[] } => {
      const option = pair.options[entry.A === route ? 'A' : 'B'];
      return { book: option.book, pages: option.pages.map((page) => page.page) };
    };
    if (preferred && claim.auditor_verdict === 'PASS' && claim.cited_trove_pages.length > 0) {
      const hit = (route: Route): boolean => hitsOf(runs.get(`${claim.id}:${route}`), claim, claim.cited_trove_pages);
      if (hit(first) !== hit(second)) { if (hit(preferred)) agree += 1; else disagree += 1; }
    }
    rows.push({
      pair_id: entry.pair_id, claim_id: claim.id, claim: claim.text, judgment: verdict, by: judgment?.source ?? 'none', note: judgment?.note ?? '',
      option_routes: routeOf, preferred, pages: { trove: byRoute('trove'), pageindex: byRoute('pageindex') },
    });
  }
  const decisive = tally[first].wins + tally[first].losses;
  const routesReport: Record<string, RouteReport> = {
    [first]: routeReport(first, plan, runs, tally[first]),
    [second]: routeReport(second, plan, runs, tally[second]),
  };
  const enough = judged >= evalLimits.minPairs;
  const p = decisive === 0 ? null : signTestP(tally[first].wins, decisive);
  const report: Report = {
    schema: 1, eval_id: plan.eval_id, generated_at: options.now.toISOString(), forced: options.force && (raw === null || unjudged.length > 0),
    n_pairs: pairs.pairs.length, n_judged: judged, n_auto_same: autoSame, n_skipped: skipped, n_unjudged: unjudged.length,
    decisive, routes: routesReport, sign_test: { first, second, first_wins: tally[first].wins, decisive, p_value: p },
    enough_pairs: enough, statement: '',
    auditor_agreement: { eligible: agree + disagree, agree, disagree, rate: agree + disagree === 0 ? null : agree / (agree + disagree) },
    pairs: rows,
  };
  report.statement = statementFor(report);
  await writeJson(paths.reportJson, report);
  await writeFile(paths.reportMd, renderMarkdown(report), 'utf8');
  return report;
}

const pct = (value: number | null): string => (value === null ? 'n/a' : `${Math.round(value * 100)}%`);
const usd = (value: number | null): string => (value === null ? 'n/a' : `$${value.toFixed(value < 1 ? 3 : 2)}`);
const num = (value: number | null, digits = 0): string => (value === null ? 'n/a' : value.toLocaleString('en-US', { maximumFractionDigits: digits }));

export function statementFor(report: Report): string {
  const { first, second } = report.sign_test;
  const a = report.routes[first] as RouteReport;
  const b = report.routes[second] as RouteReport;
  if (!report.enough_pairs) {
    return `Only ${report.n_judged} pair${report.n_judged === 1 ? ' was' : 's were'} judged by you, and at least ${evalLimits.minPairs} are needed before this report says which library is better. Read the numbers below as a first look, not a verdict.`;
  }
  if (report.decisive === 0) return `None of the ${report.n_judged} judged pairs had a clear winner, so the two libraries look alike on these claims.`;
  if (a.wins === b.wins) return `The two libraries won the same number of pairs (${a.wins} each, out of ${report.decisive} with a clear winner): no difference on these claims.`;
  const leader = a.wins > b.wins ? a : b;
  const ci = leader.win_rate_ci95;
  const range = ci ? ` (95% range ${pct(ci[0])} to ${pct(ci[1])})` : '';
  const p = report.sign_test.p_value;
  const clear = p !== null && p < 0.05;
  return `${NAME[leader.route]} won ${leader.wins} of the ${report.decisive} pairs with a clear winner, a win rate of ${pct(leader.win_rate)}${range}. ${clear ? 'That is unlikely to be chance' : 'With this few pairs it could still be chance'} (sign test p = ${p === null ? 'n/a' : p.toFixed(3)}).`;
}

export function renderMarkdown(report: Report): string {
  const [first, second] = [report.sign_test.first, report.sign_test.second];
  const routes = [report.routes[first], report.routes[second]] as RouteReport[];
  const line = (label: string, cell: (route: RouteReport) => string): string => `| ${label} | ${routes.map(cell).join(' | ')} |`;
  const lines: string[] = [
    `# Which library found the right pages? (${report.eval_id})`, '',
    ...(report.forced ? ['> The key was opened before every pair was judged (forced). Do not treat this as a finished result.', ''] : []),
    report.statement, '',
    `Pairs: ${report.n_pairs} in all, ${report.n_judged} judged by you, ${report.n_auto_same} identical (marked "same" automatically), ${report.n_skipped} skipped, ${report.n_unjudged} not judged.`, '',
    '## By library', '',
    `| | ${routes.map((route) => NAME[route.route]).join(' | ')} |`, `| --- | ${routes.map(() => '---').join(' | ')} |`,
    line('Pairs won', (r) => String(r.wins)), line('Pairs lost', (r) => String(r.losses)), line('Same', (r) => String(r.ties)), line('Neither found it', (r) => String(r.neither)),
    line('Win rate (wins / decisive pairs)', (r) => `${pct(r.win_rate)}${r.win_rate_ci95 ? ` (${pct(r.win_rate_ci95[0])} to ${pct(r.win_rate_ci95[1])})` : ''}`),
    line('Locate runs that finished / failed', (r) => `${r.runs.ok} / ${r.runs.error}`),
    line('Median time per claim', (r) => (r.wall_s.median === null ? 'n/a' : `${r.wall_s.median.toFixed(1)} s`)),
    line('Median agent tokens in / out', (r) => `${num(r.tokens.input_median)} / ${num(r.tokens.output_median)}`),
    line('Total agent tokens in / out', (r) => `${num(r.tokens.input_total)} / ${num(r.tokens.output_total)}`),
    line('Median / total cost', (r) => `${usd(r.cost_usd.median)} / ${usd(r.cost_usd.total)}`),
    line('Median tool calls per claim', (r) => num(r.tool_calls_median, 1)),
    line('Text returned to the agent (estimated tokens, total)', (r) => num(r.returned_est_tokens.total)),
    '', '## Against the citations you already have', '',
    `| | ${routes.map((route) => NAME[route.route]).join(' | ')} |`, `| --- | ${routes.map(() => '---').join(' | ')} |`,
    line('Found the page your article cites', (r) => `${r.cited_page_hit.hits} of ${r.cited_page_hit.eligible} (${pct(r.cited_page_hit.rate)})`),
    line('...where the citation checker said PASS', (r) => `${r.auditor_pass_hit.hits} of ${r.auditor_pass_hit.eligible} (${pct(r.auditor_pass_hit.rate)})`),
    line('Found the corrected page where the checker said FAIL', (r) => `${r.corrected_page_hit.hits} of ${r.corrected_page_hit.eligible} (${pct(r.corrected_page_hit.rate)})`),
    '', report.auditor_agreement.eligible === 0
      ? 'Your preference and the citation checker could not be compared: no pair had exactly one library finding the cited page.'
      : `Your preference matched the citation checker in ${report.auditor_agreement.agree} of ${report.auditor_agreement.eligible} pairs where exactly one library found the cited page (${pct(report.auditor_agreement.rate)}).`,
    '', '## Pair by pair', '',
  ];
  for (const pair of report.pairs) {
    const verdict = pair.preferred ? `${NAME[pair.preferred]} was better` : (pair.judgment === 'same' ? 'same' : pair.judgment === 'neither' ? 'neither found it' : pair.judgment === 'skip' ? 'skipped' : 'not judged');
    lines.push(`### ${pair.pair_id}: ${pair.claim}`, '');
    lines.push(`- Your verdict: ${verdict}${pair.by === 'auto' ? ' (automatic: both libraries chose the same pages)' : ''}`);
    for (const route of [first, second]) lines.push(`- ${NAME[route]}: ${pair.pages[route].book ?? 'no answer'}${pair.pages[route].pages.length ? `, pages ${pair.pages[route].pages.join(', ')}` : ''}`);
    if (pair.note) lines.push(`- Your note: ${pair.note}`);
    lines.push('');
  }
  return `${lines.join('\n')}\n`;
}
