import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import retrievalSchema from '../../schemas/retrieval-row.schema.json' with { type: 'json' };
import { checkSchema, type JsonSchema } from '../src/library/jsonschema.ts';
import type { LookupRow, RetrievalRow, ShadowRow, SupportsReason, VerdictRow } from '../src/library/ledger.ts';
import { buildReport, formatReport, percentile, reportFor } from '../src/library/report.ts';
import { runLibraryCli } from '../src/library/cli.ts';
import { setPathArguments } from '../src/paths.ts';
import type { RouteName } from '../src/library/types.ts';

const TS = '2026-10-15T10:00:00.000Z';

function lookup(id: string, over: { run?: string | null; route?: RouteName; latency?: number; ok?: boolean; status?: string; op?: LookupRow['op']; mode?: LookupRow['mode'] } = {}): LookupRow {
  const route = over.route ?? 'trove';
  const ok = over.ok ?? true;
  return {
    row_type: 'lookup', schema: 1, ts: TS, lookup_id: id, run_id: over.run === undefined ? 'R1' : over.run, claim_id: null, op: over.op ?? 'read', source_id: 'T-A', mode: over.mode ?? 'both', route_primary: route,
    book_by_route: { trove: null, pageindex: null }, request: { printed: null, trove_pages: '2' },
    primary: { route, ok, route_pages: ok ? '2' : null, latency_ms: over.latency ?? 10, bytes: 10, chars: 10, text_sha: ok ? '0123456789abcdef' : null, error: ok ? null : 'boom', error_code: ok ? null : 'exit' },
    shadow_status: over.status ?? 'pending',
  };
}

function shadow(id: string, over: { route?: RouteName; ok?: boolean; latency?: number; timedOut?: boolean; code?: string | null; agreed?: number; compared?: number | null } = {}): ShadowRow {
  const ok = over.ok ?? true;
  const compared = over.compared === undefined ? 2 : over.compared;
  const agreed = over.agreed ?? compared ?? 0;
  return {
    row_type: 'shadow', schema: 1, ts: TS, lookup_id: id, run_id: 'R1', route: over.route ?? 'pageindex', ok, book: null, route_pages: ok ? '2' : null, latency_ms: over.latency ?? 100, bytes: 0, chars: 0, text_sha: null,
    error: ok ? null : 'x', error_code: ok ? null : (over.code ?? 'exit'), timed_out: over.timedOut ?? false,
    agree: ok && compared !== null ? { rate: compared === 0 ? null : agreed / compared, compared, agreed, pages: [] } : null,
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
