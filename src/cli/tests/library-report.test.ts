import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import retrievalSchema from '../../schemas/retrieval-row.schema.json' with { type: 'json' };
import { checkSchema, type JsonSchema } from '../src/library/jsonschema.ts';
import type { LookupRow, RetrievalRow, ShadowRow, SupportsReason, VerdictRow } from '../src/library/ledger.ts';
import { buildReport, formatReport, parseLocateRun, percentile, readUsageRows, reportFor } from '../src/library/report.ts';
import { runLibraryCli } from '../src/library/cli.ts';
import type { LedgerRow } from '../src/ledger.ts';
import { setPathArguments } from '../src/paths.ts';
import { LibraryError, type RouteName } from '../src/library/types.ts';

const TS = '2026-10-15T10:00:00.000Z';

function lookup(id: string, over: { run?: string | null; route?: RouteName; latency?: number; ok?: boolean; status?: string; op?: LookupRow['op']; mode?: LookupRow['mode']; est?: number; pages?: string | null; returned?: number } = {}): LookupRow {
  const route = over.route ?? 'trove';
  const ok = over.ok ?? true;
  return {
    row_type: 'lookup', schema: 1, ts: TS, lookup_id: id, run_id: over.run === undefined ? 'R1' : over.run, claim_id: null, op: over.op ?? 'read', source_id: 'T-A', mode: over.mode ?? 'both', route_primary: route,
    book_by_route: { trove: null, pageindex: null }, request: { printed: null, trove_pages: '2' },
    primary: {
      route, ok, route_pages: ok ? (over.pages === undefined ? '2' : over.pages) : null, latency_ms: over.latency ?? 10, bytes: 10, chars: 10, text_sha: ok ? '0123456789abcdef' : null, error: ok ? null : 'boom', error_code: ok ? null : 'exit',
      ...(over.est === undefined ? {} : { est_tokens: over.est, tokens_basis: 'estimate' as const }),
      ...(over.returned === undefined ? {} : { pages_returned: over.returned }),
    },
    shadow_status: over.status ?? 'pending',
  };
}

function shadow(id: string, over: { route?: RouteName; ok?: boolean; latency?: number; timedOut?: boolean; code?: string | null; agreed?: number; compared?: number | null; est?: number } = {}): ShadowRow {
  const ok = over.ok ?? true;
  const compared = over.compared === undefined ? 2 : over.compared;
  const agreed = over.agreed ?? compared ?? 0;
  return {
    row_type: 'shadow', schema: 1, ts: TS, lookup_id: id, run_id: 'R1', route: over.route ?? 'pageindex', ok, book: null, route_pages: ok ? '2' : null, latency_ms: over.latency ?? 100, bytes: 0, chars: 0, text_sha: null,
    error: ok ? null : 'x', error_code: ok ? null : (over.code ?? 'exit'), timed_out: over.timedOut ?? false,
    agree: ok && compared !== null ? { rate: compared === 0 ? null : agreed / compared, compared, agreed, pages: [] } : null,
    ...(over.est === undefined ? {} : { est_tokens: over.est, tokens_basis: 'estimate' as const }),
  };
}

function verdict(id: string, paragraph: string, word: 'PASS' | 'FAIL', supports: boolean | null, reason: SupportsReason, over: { corrected?: number; route?: RouteName; settled?: boolean; at?: number } = {}): VerdictRow {
  return {
    row_type: 'verdict', schema: 1, verdict_at: String(1760526000000000000n + BigInt(over.at ?? 1)), pid: 4242, nonce: '0123456789abcdef', ts: TS, lookup_id: id, run_id: 'R1', paragraph_id: paragraph, verdict: word, corrected_page: over.corrected ?? null, shadow_supports: supports, shadow_supports_reason: reason,
    primary_route: over.route ?? 'trove', mode: 'both', ...(over.settled ? { settled: true } : {}),
  };
}

// Six Trove-answered lookups (latency 10..60, one failed), one PageIndex-answered lookup in another run.
const ROWS: RetrievalRow[] = [
  lookup('L1', { latency: 10 }), shadow('L1', { agreed: 2, compared: 2, latency: 100 }),
  lookup('L2', { latency: 20 }), shadow('L2', { agreed: 1, compared: 2, latency: 200 }),
  lookup('L3', { latency: 30, ok: false }), shadow('L3', { compared: null }),
  lookup('L4', { latency: 40 }), shadow('L4', { ok: false, timedOut: true, code: 'timeout', latency: 4000 }),
  lookup('L5', { latency: 50 }), shadow('L5', { ok: false, code: 'page_map', latency: 5 }),
  lookup('L6', { latency: 60 }),
  lookup('L7', { run: 'R2', route: 'pageindex', latency: 100 }), shadow('L7', { route: 'trove', agreed: 1, compared: 1, latency: 30 }),
  verdict('L1', 'P1', 'PASS', true, 'covered'),
  verdict('L1', 'P2', 'PASS', null, 'shadow_pending'),
  verdict('L1', 'P2', 'PASS', false, 'not_covered', { settled: true }),
  verdict('L2', 'P1', 'FAIL', false, 'not_covered', { corrected: 5 }),
  verdict('L4', 'P1', 'PASS', null, 'shadow_missing'),
  verdict('L5', 'P1', 'FAIL', null, 'no_quote'),
  verdict('L7', 'P1', 'PASS', true, 'covered', { route: 'pageindex' }),
];

test('the fixture rows are all valid ledger rows', () => {
  for (const row of ROWS) assert.deepEqual(checkSchema(retrievalSchema as JsonSchema, row), [], JSON.stringify(row));
});

test('percentiles are nearest rank', () => {
  assert.equal(percentile([], 50), null);
  assert.equal(percentile([7], 90), 7);
  assert.deepEqual([50, 90].map((p) => percentile([10, 20, 30, 40, 50, 60], p)), [30, 60]);
  assert.deepEqual([50, 90].map((p) => percentile([60, 10, 50, 20, 40, 30, 70, 80, 90, 100], p)), [50, 90]);
});

test('report: per route lookups, errors and latency', () => {
  const report = buildReport(ROWS, 0);
  assert.deepEqual(report.rows, { lookup: 7, shadow: 6, verdict: 6, invalid: 0 });
  const trove = report.routes.trove;
  assert.deepEqual([trove.lookups, trove.errors, trove.error_rate], [6, 1, 0.167]);
  assert.deepEqual(trove.latency_ms, { p50: 30, p90: 60 });
  assert.equal(trove.enough_data, true);
  const pageindex = report.routes.pageindex;
  assert.deepEqual([pageindex.lookups, pageindex.errors, pageindex.latency_ms.p50, pageindex.enough_data], [1, 0, 100, false]);
  assert.deepEqual(report.modes, { 'both, trove answers': 6, 'both, pageindex answers': 1 });
});

test('report: shadow runs, timeouts and unmapped books per route', () => {
  const report = buildReport(ROWS, 0);
  const pageindex = report.routes.pageindex;
  assert.deepEqual([pageindex.shadow_runs, pageindex.shadow_errors, pageindex.shadow_timeouts, pageindex.shadow_unmapped], [5, 1, 1, 1]);
  assert.deepEqual(pageindex.shadow_latency_ms, { p50: 100, p90: 4000 });
  assert.deepEqual([report.routes.trove.shadow_runs, report.routes.trove.shadow_latency_ms.p50], [1, 30]);
  assert.equal(report.data_quality.lookups_without_shadow_row, 1);
  assert.match(report.notes.join(' '), /1 second lookups left no result/);
  assert.match(report.notes.join(' '), /Only 1 lookups were answered by pageindex/);
});

test('report: page agreement is compared per page, for the route that answered', () => {
  const report = buildReport(ROWS, 0);
  assert.deepEqual(report.routes.trove.agreement, { pages_compared: 4, pages_agreed: 3, rate: 0.75 });
  assert.deepEqual(report.routes.pageindex.agreement, { pages_compared: 1, pages_agreed: 1, rate: 1 });
  assert.deepEqual([report.agreement.lookups_compared, report.agreement.pages_compared, report.agreement.pages_agreed, report.agreement.rate], [3, 5, 4, 0.8]);
});

test('report: auditor pass rate and shadow support by route; the last verdict row for a citation wins', () => {
  const report = buildReport(ROWS, 0);
  const trove = report.routes.trove.auditor;
  // P2 on L1 was pending, then settled to not_covered: one row, not two.
  assert.deepEqual([trove.verdicts, trove.pass, trove.fail, trove.pass_rate, trove.fail_with_corrected_page], [5, 3, 2, 0.6, 1]);
  assert.deepEqual([trove.shadow_checked, trove.shadow_supports, trove.shadow_supports_rate], [3, 1, 0.333]);
  const pageindex = report.routes.pageindex.auditor;
  assert.deepEqual([pageindex.verdicts, pageindex.pass_rate, pageindex.shadow_supports_rate], [1, 1, 1]);
  assert.deepEqual(report.auditor.shadow_supports_by_verdict, { PASS: { supports: 2, not_supports: 1, unknown: 1 }, FAIL: { supports: 0, not_supports: 1, unknown: 1 } });
  assert.deepEqual([report.auditor.verdicts, report.auditor.lookups_with_verdict, report.auditor.read_lookups, report.auditor.verdict_coverage], [6, 5, 7, 0.714]);
  assert.deepEqual([report.data_quality.shadow_pending_verdicts, report.data_quality.shadow_missing_verdicts, report.data_quality.no_quote_verdicts], [0, 1, 1]);
});

test('report: the verdict with the highest ordering key stands, wherever it sits in the file', () => {
  const rows: RetrievalRow[] = [
    lookup('S1'),
    verdict('S1', 'P1', 'FAIL', null, 'no_quote', { at: 2 }),
    verdict('S1', 'P1', 'PASS', true, 'covered', { at: 1, settled: true }),
    verdict('S1', 'P2', 'PASS', null, 'shadow_pending', { at: 1 }),
    verdict('S1', 'P2', 'PASS', true, 'covered', { at: 1, settled: true }),
  ];
  const report = buildReport(rows, 0);
  assert.deepEqual([report.routes.trove.auditor.verdicts, report.routes.trove.auditor.pass, report.routes.trove.auditor.fail], [2, 1, 1]);
  assert.equal(report.data_quality.shadow_pending_verdicts, 0, 'the settled row replaces the pending one at the same key');
});

test('report: coverage counts lookups with a verdict, so several verdicts on one lookup never pass 100%', () => {
  const rows: RetrievalRow[] = [
    lookup('C1'),
    verdict('C1', 'P1', 'PASS', true, 'covered'),
    verdict('C1', 'P2', 'FAIL', null, 'no_quote'),
    verdict('C1', 'P3', 'PASS', null, 'shadow_missing'),
  ];
  const report = buildReport(rows, 0);
  assert.deepEqual([report.auditor.verdicts, report.auditor.lookups_with_verdict, report.auditor.read_lookups, report.auditor.verdict_coverage], [3, 1, 1, 1]);
  assert.match(formatReport(report), /Lookups with an auditor verdict: 1 of 1 page reads \(100%\)/);
  assert.ok(buildReport([...rows, lookup('C2')], 0).auditor.verdict_coverage === 0.5);
});

test('report: a run filter keeps that run only, and skipped shadows are counted by reason', () => {
  const report = buildReport([...ROWS, lookup('L8', { run: 'R2', status: 'skipped:busy' }), lookup('L9', { run: 'R2', status: 'skipped:busy' }), lookup('L10', { status: 'none', mode: 'trove' })], 0, 'R2');
  assert.deepEqual(report.rows, { lookup: 3, shadow: 1, verdict: 1, invalid: 0 });
  assert.deepEqual([report.routes.pageindex.lookups, report.routes.trove.lookups], [1, 2]);
  assert.deepEqual(report.data_quality.shadow_skipped, { busy: 2 });
  assert.equal(report.run, 'R2');
});

test('report: an empty ledger says so instead of dividing by zero', () => {
  const report = buildReport([], 2);
  assert.deepEqual([report.routes.trove.error_rate, report.routes.trove.latency_ms, report.agreement.rate, report.auditor.verdict_coverage], [null, { p50: null, p90: null }, null, null]);
  assert.match(report.notes[0] ?? '', /No lookups/);
  assert.match(formatReport(report), /2 unreadable lines skipped/);
});

test('report text uses plain words and the numbers of the report', () => {
  const text = formatReport(buildReport(ROWS, 0));
  assert.match(text, /^Library report\n/u);
  assert.match(text, /Answered 6 lookups, 1 failed \(16\.7%\); half finish within 30 ms, nine in ten within 60 ms/);
  assert.match(text, /returned the same page text for 3 of 4 pages \(75%\)/);
  assert.match(text, /3 of 5 citations passed \(60%\), 1 failed with a corrected page/);
  assert.match(text, /supported the claim for 1 of 3 checked \(33\.3%\)/);
  assert.match(text, /Second lookups skipped|Gaps: 0 verdicts waiting/);
  assert.doesNotMatch(text, /shadow/i, 'researchers read "second lookup", not "shadow"');
});

test('the report reads the ledger file, skips unreadable lines, and the command prints text or JSON', async () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-report-'));
  try {
    mkdirSync(join(root, '.academic-helper'));
    const lines = [...ROWS.map((row) => JSON.stringify(row)), '{not json', JSON.stringify({ row_type: 'lookup' })];
    writeFileSync(join(root, '.academic-helper', 'retrieval.jsonl'), `${lines.join('\n')}\n`, 'utf8');
    const direct = await reportFor(root, null);
    assert.deepEqual([direct.rows.lookup, direct.rows.invalid], [7, 2]);
    setPathArguments(['--project-dir', root]);
    let out = '';
    assert.equal(await runLibraryCli(['report', '--json'], { out: (text) => { out += text; }, err: () => undefined }), 0);
    assert.deepEqual(JSON.parse(out), JSON.parse(JSON.stringify(direct)));
    out = '';
    assert.equal(await runLibraryCli(['report', '--run', 'R2'], { out: (text) => { out += text; }, err: () => undefined }), 0);
    assert.match(out, /^Library report for run R2\n/u);
    const empty = join(root, 'empty');
    mkdirSync(empty);
    setPathArguments(['--project-dir', empty]);
    out = '';
    assert.equal(await runLibraryCli(['report', '--json'], { out: (text) => { out += text; }, err: () => undefined }), 0);
    assert.equal((JSON.parse(out) as { rows: { lookup: number } }).rows.lookup, 0);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

// ---------------------------------------------------------------- tokens, agents, indexing

function usage(runId: string, over: Partial<LedgerRow> = {}): LedgerRow {
  return { run_id: runId, step: 'library.eval.locate', provider: 'claude-code', model: 'test-model', input_tokens: 1000, output_tokens: 100, cost_usd: 0.1, latency_ms: 40000, exit: 'OK', same_family: false, ...over };
}

// Trove answered five lookups (three carry an estimate, one is an old row without one, one failed) and PageIndex one.
const MEASURED: RetrievalRow[] = [
  lookup('M1', { run: 'EV1-trove-c01', est: 100, pages: '2-3', returned: 2 }),
  lookup('M2', { run: 'EV1-trove-c01', est: 200, pages: '4', returned: 1 }),
  lookup('M3', { run: 'EV1-trove-c02', op: 'toc', est: 50, pages: null, latency: 90 }),
  lookup('M4', { run: 'EV2-trove-c01' }),
  lookup('M5', { run: 'EV2-trove-c01', ok: false }),
  lookup('M6', { run: 'EV1-pageindex-c01', route: 'pageindex', est: 400, pages: '1-4', returned: 4 }), shadow('M6', { route: 'trove', est: 123 }),
];
const USAGE: LedgerRow[] = [
  usage('EV1-trove-c01'),
  usage('EV1-trove-c02', { input_tokens: 3000, output_tokens: 300, cost_usd: 0.3, latency_ms: 60000 }),
  usage('EV1-pageindex-c01', { provider: 'codex', input_tokens: 2000, output_tokens: 200, cost_usd: null, latency_ms: 20000, exit: 'ERROR' }),
  usage('EV2-trove-c01', { input_tokens: 500, output_tokens: 50, cost_usd: 0.05, latency_ms: 10000 }),
  usage('index-1', { step: 'library.index', provider: 'gemini', model: 'gemini-test', input_tokens: 8000, output_tokens: 800, cost_usd: 0.02, latency_ms: 30000 }),
  usage('index-2', { step: 'library.index', provider: 'gemini', model: 'gemini-test', input_tokens: 2000, output_tokens: 200, cost_usd: 0.01, latency_ms: 10000 }),
  usage('R1', { step: 'ocr', provider: 'gemini' }),
];

test('old rows with no token estimate still validate and render, with no token section', () => {
  for (const row of ROWS) assert.deepEqual(checkSchema(retrievalSchema as JsonSchema, row), []);
  const report = buildReport(ROWS, 0);
  const trove = report.tokens.routes.trove;
  assert.deepEqual([trove.lookups_measured, trove.total, trove.per_lookup, trove.per_page_avg, trove.shadow.runs_measured], [0, 0, { p50: null, p90: null }, null, 0]);
  assert.deepEqual([report.agents.runs, report.indexing.runs, report.eval], [0, 0, null]);
  const text = formatReport(report);
  assert.doesNotMatch(text, /Returned text|Locating agents|Indexing/);
  assert.match(text, /Agent tokens and cost are recorded only for library-eval runs/);
  assert.doesNotMatch(text, /shadow/i);
});

test('the schema takes est_tokens and tokens_basis on a lookup call and a shadow row, and nothing else', () => {
  assert.deepEqual(checkSchema(retrievalSchema as JsonSchema, MEASURED[0]), []);
  assert.deepEqual(checkSchema(retrievalSchema as JsonSchema, MEASURED[6]), []);
  const first = MEASURED[0] as LookupRow;
  assert.deepEqual(checkSchema(retrievalSchema as JsonSchema, { ...(MEASURED[0] as LookupRow), primary: { ...(MEASURED[0] as LookupRow).primary, pages_returned: 0 } }), []);
  for (const bad of [{ est_tokens: -1 }, { est_tokens: 1.5 }, { est_tokens: '3' }, { tokens_basis: 'exact' }, { pages_returned: -1 }, { pages_returned: 1.5 }]) {
    assert.notDeepEqual(checkSchema(retrievalSchema as JsonSchema, { ...first, primary: { ...first.primary, ...bad } }), [], JSON.stringify(bad));
  }
});

test('report: returned-text estimates per route, per lookup and per page; old rows and failures are left out', () => {
  const report = buildReport(MEASURED, 0);
  const trove = report.tokens.routes.trove;
  assert.equal(report.tokens.basis, 'estimate');
  // M1 100 (2 pages), M2 200 (1 page), M3 50 (a table of contents); the old row M4 and the failed M5 carry no estimate.
  assert.deepEqual([trove.lookups_measured, trove.total, trove.per_lookup], [3, 350, { p50: 100, p90: 200 }]);
  assert.deepEqual([trove.pages_measured, trove.per_page_avg], [3, 100]);
  assert.deepEqual([report.tokens.routes.pageindex.total, report.tokens.routes.pageindex.per_page_avg, report.tokens.routes.pageindex.pages_measured], [400, 100, 4]);
  assert.equal(report.tokens.routes.pageindex.shadow.runs_measured, 0);
  // The quiet second lookup of M6 ran on Trove.
  assert.deepEqual(report.tokens.routes.trove.shadow, { runs_measured: 1, total: 123, per_run: { p50: 123, p90: 123 } });
});

test('report: latency and returned text split by kind of lookup', () => {
  const trove = buildReport(MEASURED, 0).routes.trove;
  assert.deepEqual(Object.keys(trove.by_op), ['toc', 'read']);
  assert.deepEqual(trove.by_op.toc, { lookups: 1, latency_ms: { p50: 90, p90: 90 }, est_tokens: 50 });
  assert.deepEqual([trove.by_op.read?.lookups, trove.by_op.read?.est_tokens], [4, 300]);
  const text = formatReport(buildReport(MEASURED, 0));
  assert.match(text, /By kind: tables of contents 1 \(half within 90 ms\); page reads 4 \(half within 10 ms\)/);
});

test('report: locating agents per route from the usage rows, joined to their lookups on the run id', () => {
  const report = buildReport(MEASURED, 0, null, { usage: USAGE });
  assert.equal(report.agents.runs, 4);
  const trove = report.agents.routes.trove;
  assert.deepEqual([trove.runs, trove.failed, trove.retried], [3, 0, 0]);
  assert.deepEqual(trove.wall_ms, { p50: 40000, p90: 60000 });
  assert.deepEqual([trove.input_tokens, trove.output_tokens], [{ total: 4500, median: 1000 }, { total: 450, median: 100 }]);
  assert.deepEqual(trove.cost_usd, { total: 0.45, median: 0.1, known_runs: 3 });
  // c01 made 2 lookups (100 + 200), c02 one (50), EV2-c01 two (an old row and a failed one: nothing estimated).
  assert.deepEqual(trove.lookups_per_run, { median: 2, total: 5 });
  assert.deepEqual(trove.returned_est_tokens_per_run, { median: 50, total: 350 });
  const pageindex = report.agents.routes.pageindex;
  assert.deepEqual([pageindex.runs, pageindex.failed, pageindex.cost_usd], [1, 1, { total: null, median: null, known_runs: 0 }]);
  assert.deepEqual(pageindex.lookups_per_run, { median: 1, total: 1 });
});

test('report: a retried agent run is counted and flagged, and a run id that names no route is set aside', () => {
  const report = buildReport([], 0, null, { usage: [usage('EV1-trove-c01'), usage('EV1-trove-c01', { exit: 'ERROR' }), usage('loose-run')] });
  assert.deepEqual([report.agents.routes.trove.runs, report.agents.routes.trove.failed, report.agents.routes.trove.retried, report.agents.unattributed, report.agents.runs], [2, 1, 1, 1, 3]);
  assert.match(formatReport(report), /1 locating-agent runs have a run id that names no route/);
});

test('report: indexing runs sum tokens and cost from the usage rows', () => {
  const report = buildReport([], 0, null, { usage: USAGE });
  assert.deepEqual(report.indexing, { step: 'library.index', runs: 2, failed: 0, input_tokens: 10000, output_tokens: 1000, cost_usd: { total: 0.03, known_runs: 2 }, wall_ms: { p50: 10000, p90: 30000 }, models: ['gemini-test'] });
});

test('report: --eval keeps the lookups and agent runs whose run id starts with the id; --run stays exact', () => {
  const report = buildReport(MEASURED, 0, null, { eval: 'EV1', usage: USAGE });
  assert.equal(report.eval, 'EV1');
  assert.deepEqual([report.rows.lookup, report.routes.trove.lookups, report.routes.pageindex.lookups], [4, 3, 1]);
  assert.deepEqual([report.agents.routes.trove.runs, report.agents.routes.trove.input_tokens.total, report.agents.routes.pageindex.runs, report.indexing.runs], [2, 4000, 1, 0]);
  assert.deepEqual(report.agents.routes.trove.cost_usd, { total: 0.4, median: 0.1, known_runs: 2 });
  assert.deepEqual([report.agents.routes.trove.lookups_per_run.median, report.agents.routes.trove.returned_est_tokens_per_run.total], [1, 350]);
  assert.match(formatReport(report), /^Library report for evaluation EV1\n/u);
  // The id is a prefix up to the dash: EV1 does not pick up EV10.
  assert.equal(buildReport([lookup('X', { run: 'EV10-trove-c01' })], 0, null, { eval: 'EV1' }).rows.lookup, 0);
  assert.match(buildReport([], 0, null, { eval: 'EV9' }).notes[0] ?? '', /No lookups are recorded for evaluation EV9/);
  const exact = buildReport(MEASURED, 0, 'EV1-trove-c01', { usage: USAGE });
  assert.deepEqual([exact.rows.lookup, exact.agents.runs, exact.indexing.runs], [2, 1, 0]);
  assert.deepEqual([exact.run, exact.eval], ['EV1-trove-c01', null]);
});

test('report text: estimates are labelled as estimates; agent and indexing figures come from the tools; no engine words', () => {
  const text = formatReport(buildReport(MEASURED, 0, null, { usage: USAGE }));
  assert.match(text, /Returned text \(token figures are estimates: about 2 Hebrew or 4 other characters per token, so Claude's own counts will differ\)/);
  assert.match(text, /Trove: 5 lookups answered \(3 carry an estimate; older rows do not\), about 350 tokens in all; half return 100 or fewer, nine in ten 200 or fewer; about 100 per page; second lookups 1, about 123 tokens in all/);
  assert.match(text, /PageIndex: 1 lookups answered, about 400 tokens in all/);
  assert.match(text, /Locating agents \(library-eval runs; the agent tokens and cost are what the agent's own tool reported\)/);
  assert.match(text, /Trove: 3 runs \(0 failed\); half finish within 40\.0 s, nine in ten within 60\.0 s; per run, median 1,000 tokens in and 100 out; cost \$0\.450 in all \(median \$0\.100; reported for 3 of 3 runs\); median 2 lookups per run returning about 50 tokens \(estimate\)/);
  assert.match(text, /PageIndex: 1 runs \(1 failed\);.*cost not reported/);
  assert.match(text, /Indexing \(page summaries for PageIndex, from the usage ledger\)\n  2 runs \(0 failed\), 10,000 tokens in and 1,000 out, cost \$0\.030 \(reported for 2 of 2 runs\); half finish within 10\.0 s; model gemini-test/);
  assert.doesNotMatch(text, /shadow/i);
  assert.doesNotMatch(text, /Agent tokens and cost are recorded only/);
});

test('agent run ids split into eval, route and claim', () => {
  assert.deepEqual(parseLocateRun('ev-20261020-a-pageindex-c01'), { eval: 'ev-20261020-a', route: 'pageindex', claim: 'c01' });
  assert.equal(parseLocateRun('index-3'), null);
});

test('locate run ids are <eval>-<route>-c<NN>, parsed from the right: an eval id may contain route words', () => {
  assert.deepEqual(parseLocateRun('study-trove-pilot-pageindex-c01'), { eval: 'study-trove-pilot', route: 'pageindex', claim: 'c01' });
  assert.deepEqual(parseLocateRun('pageindex-pilot-trove-c12'), { eval: 'pageindex-pilot', route: 'trove', claim: 'c12' });
  assert.deepEqual(parseLocateRun('a-trove-pageindex-trove-c007'), { eval: 'a-trove-pageindex', route: 'trove', claim: 'c007' });
  // Anything else is not guessed at.
  for (const bad of ['EV1-trove-x1', 'EV1-trove-c', 'EV1-trove-c01-extra', 'EV1-trove-c-1', 'trove-c01', '-trove-c01', 'EV1-Trove-c01', 'EV1-both-c01', 'EV1_trove_c01', 'EV1-trove-C01', '']) {
    assert.equal(parseLocateRun(bad), null, bad);
  }
});

test('report: an eval id with route words in it is attributed to its own route and eval, and malformed ids are unattributed', () => {
  const rows: LedgerRow[] = [
    usage('study-trove-pilot-pageindex-c01', { input_tokens: 10 }),
    usage('study-trove-pilot-trove-c01', { input_tokens: 20 }),
    usage('study-trove-c01', { input_tokens: 40 }),
    usage('study-trove-x1', { input_tokens: 80 }),
    usage('study-trove-c01-extra', { input_tokens: 160 }),
  ];
  const report = buildReport([], 0, null, { usage: rows });
  assert.deepEqual([report.agents.routes.pageindex.runs, report.agents.routes.pageindex.input_tokens.total], [1, 10]);
  assert.deepEqual([report.agents.routes.trove.runs, report.agents.routes.trove.input_tokens.total], [2, 60]);
  assert.deepEqual([report.agents.unattributed, report.agents.runs], [2, 5]);
  // --eval means the parsed eval id, never a prefix: "study" owns only study-trove-c01, not the "study-trove-pilot" runs.
  const study = buildReport([], 0, null, { eval: 'study', usage: rows });
  assert.deepEqual([study.agents.runs, study.agents.routes.trove.input_tokens.total, study.agents.routes.pageindex.runs], [1, 40, 0]);
  assert.equal(buildReport([], 0, null, { eval: 'study-trove', usage: rows }).agents.runs, 0);
  const pilot = buildReport([], 0, null, { eval: 'study-trove-pilot', usage: rows });
  assert.deepEqual([pilot.agents.runs, pilot.agents.routes.pageindex.runs, pilot.agents.routes.trove.runs, pilot.agents.unattributed], [2, 1, 1, 0]);
  const lookups = [lookup('A', { run: 'study-trove-pilot-pageindex-c01', route: 'pageindex' }), lookup('B', { run: 'study-trove-c01' }), lookup('C', { run: 'study-trove-pilot' })];
  assert.equal(buildReport(lookups, 0, null, { eval: 'study-trove-pilot' }).rows.lookup, 1);
});

test('report: the per-page average divides by the pages actually returned, not by the pages named in route_pages', () => {
  // Six PDF pages merged into two Trove pages: 200 tokens over 2 returned pages is 100 a page, not 33.
  const merged = buildReport([
    lookup('P1', { est: 200, pages: '1-6', returned: 2 }),
    lookup('P2', { est: 100, pages: '9', returned: 1 }),
    lookup('P3', { est: 5000, pages: '1-5' }),
    lookup('P4', { est: 70, pages: null, op: 'toc' }),
  ], 0);
  const trove = merged.tokens.routes.trove;
  assert.deepEqual([trove.pages_measured, trove.per_page_avg, trove.lookups_measured, trove.total], [3, 100, 4, 5370]);
  assert.match(formatReport(merged), /about 100 per page/);
  const old = buildReport([lookup('P5', { est: 300, pages: '1-3' })], 0).tokens.routes.trove;
  assert.deepEqual([old.pages_measured, old.per_page_avg], [0, null], 'rows without a returned-page count give no per-page figure');
  assert.doesNotMatch(formatReport(buildReport([lookup('P5', { est: 300, pages: '1-3' })], 0)), /per page/);
});

test('usage rows are read from real run folders only, checked against the schema, and the report command shows the new fields', async () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-report-usage-'));
  const outside = mkdtempSync(join(tmpdir(), 'aw-report-outside-'));
  try {
    const home = join(root, '.academic-helper');
    mkdirSync(join(home, 'runs', 'EV1-trove-c01'), { recursive: true });
    mkdirSync(join(home, 'runs', 'index-1'));
    mkdirSync(join(home, 'runs', 'linked-file'));
    writeFileSync(join(home, 'retrieval.jsonl'), `${MEASURED.map((row) => JSON.stringify(row)).join('\n')}\n`, 'utf8');
    const rows = [usage('EV1-trove-c01'), usage('R1', { step: 'ocr' })].map((row) => JSON.stringify(row)).join('\n');
    writeFileSync(join(home, 'runs', 'EV1-trove-c01', 'usage.jsonl'), `${rows}\n{not json\n${JSON.stringify({ run_id: 'x', step: 'library.index' })}\n`, 'utf8');
    writeFileSync(join(home, 'runs', 'index-1', 'usage.jsonl'), `${JSON.stringify(USAGE[4])}\n`, 'utf8');
    // A usage file that is a link, and a run folder that is a link, are never followed.
    writeFileSync(join(outside, 'usage.jsonl'), `${JSON.stringify(usage('EV1-trove-c99'))}\n`, 'utf8');
    symlinkSync(join(outside, 'usage.jsonl'), join(home, 'runs', 'linked-file', 'usage.jsonl'));
    symlinkSync(outside, join(home, 'runs', 'linked-dir'));
    const read = await readUsageRows(root);
    assert.deepEqual(read.rows.map((row) => row.run_id).sort(), ['EV1-trove-c01', 'index-1']);
    assert.equal(read.invalid, 2, 'a line that is not JSON and a row that breaks the schema are counted, not returned');
    const report = await reportFor(root, null);
    assert.deepEqual([report.agents.routes.trove.runs, report.indexing.runs, report.data_quality.usage_invalid], [1, 1, 2]);
    assert.match(report.notes.join(' '), /2 unreadable lines in the usage ledgers were skipped/);
    const scoped = await reportFor(root, null, { eval: 'EV1' });
    assert.deepEqual([scoped.eval, scoped.agents.routes.trove.runs, scoped.indexing.runs, scoped.rows.lookup], ['EV1', 1, 0, 4]);
    await assert.rejects(reportFor(root, 'R1', { eval: 'EV1' }), (error: unknown) => error instanceof LibraryError && error.code === 'usage');
    await assert.rejects(reportFor(root, null, { eval: 'EV 1; rm' }), (error: unknown) => error instanceof LibraryError && error.code === 'usage');
    setPathArguments(['--project-dir', root]);
    let out = '';
    assert.equal(await runLibraryCli(['report', '--json'], { out: (text) => { out += text; }, err: () => undefined }), 0);
    const json = JSON.parse(out) as { tokens: { basis: string }; agents: { runs: number }; indexing: { runs: number }; eval: null };
    assert.deepEqual([json.tokens.basis, json.agents.runs, json.indexing.runs, json.eval], ['estimate', 1, 1, null]);
    // A project with no runs folder at all is an empty usage ledger, not an error.
    const bare = join(root, 'bare');
    mkdirSync(join(bare, '.academic-helper'), { recursive: true });
    assert.deepEqual(await readUsageRows(bare), { rows: [], invalid: 0 });
    assert.deepEqual(await readUsageRows(join(root, 'missing')), { rows: [], invalid: 0 });
  } finally { rmSync(root, { recursive: true, force: true }); rmSync(outside, { recursive: true, force: true }); }
});
