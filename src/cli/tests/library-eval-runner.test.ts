import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync, spawn } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { buildPrompt, commandProblem, commandViolations, deriveBudget, expectedFingerprint, returnedFor, runAll, runIdFor, wrapperScript, type RunnerOptions } from '../src/library/eval/runner.ts';
import { parseAnswer, parseClaude, parseCodex } from '../src/library/eval/agent.ts';
import { evalPaths, readJson, validate, writeJson } from '../src/library/eval/files.ts';
import { runEvalCli } from '../src/library/eval/cli.ts';
import type { Claim, Engine, Mapping, Plan, Route, Run } from '../src/library/eval/types.ts';

const NOW = new Date('2026-10-16T10:00:00.000Z');

// ------------------------------------------------------------------ fakes (no real model, library or aw is ever called)

const FAKE_AW = `
const fs = require('node:fs');
const path = require('node:path');
const all = process.argv.slice(2);
const at = all.indexOf('--project-dir');
const project = all[at + 1];
const rest = all.filter((_, i) => i !== at && i !== at + 1);
if (rest[0] !== 'library') process.exit(2);
const sub = rest[1];
const flag = (name) => { const i = rest.indexOf(name); return i < 0 ? undefined : rest[i + 1]; };
const route = process.env.AW_LIBRARY_ROUTE;
if (process.env.FAKE_AW_LOG) fs.appendFileSync(process.env.FAKE_AW_LOG, JSON.stringify({ sub, route, run: flag('--run'), claim: flag('--claim'), args: rest.slice(2) }) + '\\n');
function ledger(chars) {
  if (!flag('--run')) return;
  const row = { row_type: 'lookup', schema: 1, ts: new Date().toISOString(), lookup_id: 'lk_' + Math.random().toString(36).slice(2), run_id: flag('--run'), claim_id: flag('--claim') || null,
    op: sub, source_id: flag('--source') || null, mode: route, route_primary: route, book_by_route: { trove: null, pageindex: null }, request: { printed: null, trove_pages: null },
    primary: { route, ok: true, route_pages: null, latency_ms: 1, bytes: chars, chars, text_sha: null, error: null, error_code: null, est_tokens: Math.ceil(chars / 4) }, shadow_status: 'none' };
  fs.appendFileSync(path.join(project, '.academic-helper', 'retrieval.jsonl'), JSON.stringify(row) + '\\n');
}
const pagesOf = (spec) => spec.split(',').flatMap((part) => { const [a, b] = part.split('-').map(Number); return Array.from({ length: (b || a) - a + 1 }, (_, i) => a + i); });
if (sub === 'list') {
  const ids = JSON.parse(process.env['FAKE_BOOKS_' + String(route).toUpperCase()] || '["T-A","T-B","T-C"]');
  console.log(JSON.stringify({ route, items: ids.map((id) => ({ id, title: id })) }));
} else if (sub === 'toc') {
  if (process.env.FAKE_DETACH_PIDS) {
    // 'orphan': a node helper in its own group, left behind at once (found by the environment tag).
    // 'linger': a system binary in its own group (its environment is hidden on macOS), left behind after aw waits a while.
    const orphan = process.env.FAKE_DETACH_MODE === 'orphan';
    const child = orphan ? require('node:child_process').spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { detached: true, stdio: 'ignore' })
      : require('node:child_process').spawn('sleep', ['300'], { detached: true, stdio: 'ignore' });
    child.unref();
    fs.appendFileSync(process.env.FAKE_DETACH_PIDS, child.pid + '\\n');
    if (!orphan) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 700);
  }
  const text = JSON.stringify({ route, mode: route, source_id: flag('--source'), title: 'Book', toc: [{ title: 'Intro', page: 1, endPage: 9, level: 1 }] });
  ledger(text.length);
  console.log(text);
} else if (sub === 'read') {
  const pages = pagesOf(flag('--pages'));
  const text = pages.map((n) => 'text of ' + flag('--source') + ' p' + n).join('\\n');
  ledger(text.length);
  if (rest.includes('--text')) console.log(pages.map((n) => '── Page ' + n + ' ──\\ntext of ' + flag('--source') + ' p' + n).join('\\n'));
  else console.log(JSON.stringify({ route, pages: pages.map((n) => ({ trove_page: n, text: 'text of ' + flag('--source') + ' p' + n })) }));
} else process.exit(2);
`;

const FAKE_CLAUDE = `#!${process.execPath}
const fs = require('node:fs');
const cp = require('node:child_process');
const args = process.argv.slice(2);
let input = '';
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => main());
function main() {
  const tools = args.slice(args.indexOf('--allowedTools') + 1);
  const wrapper = /Bash\\((\\S+) toc:\\*\\)/.exec(tools[0])[1];
  if (process.env.FAKE_CLAUDE_LOG) fs.appendFileSync(process.env.FAKE_CLAUDE_LOG, JSON.stringify({ args, cwdFiles: fs.readdirSync(process.cwd()), prompt: input,
    env: { route: process.env.AW_LIBRARY_ROUTE || null, mds: process.env.CLAUDE_CODE_DISABLE_CLAUDE_MDS || null, google: process.env.GOOGLE_API_KEY || null } }) + '\\n');
  const mode = process.env.FAKE_CLAUDE_MODE || 'ok';
  if (mode === 'hang') {
    const child = cp.spawn('sleep', ['300'], { stdio: 'ignore' });
    fs.appendFileSync(process.env.FAKE_PID_FILE, child.pid + '\\n');
    if (process.env.FAKE_HANG_DETACH) {
      const helper = cp.spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { detached: true, stdio: 'ignore' });
      helper.unref();
      fs.appendFileSync(process.env.FAKE_PID_FILE, helper.pid + '\\n');
    }
    setInterval(() => {}, 1000);
    return;
  }
  let first = false;
  if (process.env.FAKE_COUNTER) { try { fs.closeSync(fs.openSync(process.env.FAKE_COUNTER, 'wx')); first = true; } catch { first = false; } }
  if ((mode === 'fail_once' || mode === 'fail_then_chain') && first) { process.stderr.write('boom'); process.exit(1); }
  const claim = /Claim from the article:\\n"([^"]*)"/.exec(input)[1];
  const answers = JSON.parse(fs.readFileSync(process.env.FAKE_ANSWERS, 'utf8'));
  const entry = answers[claim];
  const run = (...words) => cp.execFileSync(wrapper, words, { encoding: 'utf8' });
  const calls = [];
  const toc = JSON.parse((calls.push(wrapper + ' toc --source ' + entry.book), run('toc', '--source', entry.book)));
  const pages = entry[toc.route];
  const reads = mode === 'overbudget' ? 3 : 1;
  for (let i = 0; i < reads; i += 1) { const range = pages[0] + '-' + (pages[0] + (mode === 'overbudget' ? 6 : 1)); calls.push(wrapper + ' read --source ' + entry.book + ' --pages ' + range + ' --text'); run('read', '--source', entry.book, '--pages', range, '--text'); }
  if (mode === 'chain' || mode === 'fail_then_chain' || (mode === 'chain_once' && first)) calls.push(wrapper + ' toc --source ' + entry.book + ' ; cat /etc/hosts');
  const emit = (event) => console.log(JSON.stringify(event));
  emit({ type: 'system', subtype: 'init', model: 'claude-sonnet-5-5', claude_code_version: '9.9.9' });
  for (const command of calls) emit({ type: 'assistant', message: { content: [{ type: 'tool_use', name: 'Bash', input: { command } }] } });
  const text = mode === 'noanswer' ? 'I could not find it.' : '\`\`\`json\\n' + JSON.stringify({ book: entry.book, pages, reason: 'because the tree node says so' }) + '\\n\`\`\`';
  emit({ type: 'result', subtype: 'success', is_error: false, result: text, num_turns: 3, duration_ms: 1500, total_cost_usd: 0.05,
    usage: { input_tokens: 100, cache_read_input_tokens: 400, cache_creation_input_tokens: 50, output_tokens: 20 }, permission_denials: mode === 'deny' ? [{ tool_name: 'Bash' }] : [] });
}
`;

const FAKE_CODEX = `#!${process.execPath}
const fs = require('node:fs');
const cp = require('node:child_process');
const args = process.argv.slice(2);
let input = '';
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => {
  if (process.env.FAKE_CODEX_LOG) fs.appendFileSync(process.env.FAKE_CODEX_LOG, JSON.stringify({ args }) + '\\n');
  const wrapper = /^(\\S+) toc --source/m.exec(input)[1];
  const claim = /Claim from the article:\\n"([^"]*)"/.exec(input)[1];
  const entry = JSON.parse(fs.readFileSync(process.env.FAKE_ANSWERS, 'utf8'))[claim];
  const toc = JSON.parse(cp.execFileSync(wrapper, ['toc', '--source', entry.book], { encoding: 'utf8' }));
  const pages = entry[toc.route];
  const emit = (event) => console.log(JSON.stringify(event));
  emit({ type: 'thread.started', thread_id: 't1' });
  emit({ type: 'item.completed', item: { id: 'i1', type: 'command_execution', command: "bash -lc '" + wrapper + " toc --source " + entry.book + "'", aggregated_output: '', exit_code: 0, status: 'completed' } });
  if (process.env.FAKE_CODEX_MODE === 'offlist') emit({ type: 'item.completed', item: { id: 'i2', type: 'command_execution', command: 'cat /etc/hosts', aggregated_output: '', exit_code: 0, status: 'completed' } });
  emit({ type: 'item.completed', item: { id: 'i3', type: 'agent_message', text: '\`\`\`json\\n' + JSON.stringify({ book: entry.book, pages, reason: 'r' }) + '\\n\`\`\`' } });
  emit({ type: 'turn.completed', usage: { input_tokens: 700, cached_input_tokens: 100, output_tokens: 40 } });
});
`;

type World = { dir: string; bin: string; env: NodeJS.ProcessEnv; awCommand: string[]; project: string; answersFile: string; logs: { aw: string; claude: string; codex: string; pids: string } };

function world(): World {
  const dir = mkdtempSync(join(tmpdir(), 'aw-eval-run-'));
  const project = join(dir, 'project');
  const bin = join(dir, 'bin');
  mkdirSync(join(project, '.academic-helper', 'drafts'), { recursive: true });
  mkdirSync(bin);
  const awScript = join(dir, 'fake-aw.cjs');
  writeFileSync(awScript, FAKE_AW);
  for (const [name, body] of [['claude', FAKE_CLAUDE], ['codex', FAKE_CODEX]] as const) { writeFileSync(join(bin, name), body); chmodSync(join(bin, name), 0o755); }
  const logs = { aw: join(dir, 'aw.log'), claude: join(dir, 'claude.log'), codex: join(dir, 'codex.log'), pids: join(dir, 'pids.log') };
  const answersFile = join(dir, 'answers.json');
  const env: NodeJS.ProcessEnv = {
    ...process.env, PATH: `${bin}:${process.env.PATH ?? ''}`, FAKE_AW_LOG: logs.aw, FAKE_CLAUDE_LOG: logs.claude, FAKE_CODEX_LOG: logs.codex, FAKE_PID_FILE: logs.pids,
    FAKE_ANSWERS: answersFile, FAKE_COUNTER: join(dir, 'counter'), GOOGLE_API_KEY: 'AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE12', AW_LIBRARY_ROUTE: 'pageindex',
  };
  return { dir, bin, env, awCommand: [process.execPath, awScript], project, answersFile, logs };
}

function lines(file: string): Array<Record<string, any>> { // eslint-disable-line @typescript-eslint/no-explicit-any
  return existsSync(file) ? readFileSync(file, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line) as Record<string, any>) : []; // eslint-disable-line @typescript-eslint/no-explicit-any
}

async function planFor(w: World, n = 2): Promise<{ plan: Plan; paths: ReturnType<typeof evalPaths> }> {
  const claims: Claim[] = Array.from({ length: n }, (_, index) => ({
    id: `c0${index + 1}`, text: index === 0 ? 'The city was rebuilt twice in the sixth century.' : 'טענה על העיר "שנבנתה" מחדש.', source_id: 'T-A', source_title: 'Book A',
    cited_trove_pages: [3], cited_printed_page: 1, paragraph_id: null, auditor_verdict: null, corrected_page: null,
  }));
  if (claims[1]) claims[1].text = 'טענה על העיר שנבנתה מחדש פעמיים.';
  const plan: Plan = {
    schema: 1, eval_id: 'ev-run', created_at: NOW.toISOString(), article: null, seed: 's', routes: ['trove', 'pageindex'], shelf: [{ id: 'T-A', title: 'Book A' }], claims,
    skipped: { too_short: 0, no_source: 0, multi_source: 0, unresolved: 0, over_cap: 0 }, estimate: { runs: n * 2, usd: 0.4 },
  };
  const paths = evalPaths(w.project, 'ev-run');
  await writeJson(paths.plan, plan);
  writeFileSync(w.answersFile, JSON.stringify(Object.fromEntries(claims.map((claim) => [claim.text, { book: 'T-A', trove: [3], pageindex: [5] }]))));
  return { plan, paths };
}

function options(w: World, plan: Plan, paths: ReturnType<typeof evalPaths>, engine: Engine = 'claude', over: Partial<RunnerOptions> = {}): RunnerOptions {
  return { project: w.project, paths, plan, engine, model: null, parallel: 2, routes: plan.routes as Route[], awCommand: w.awCommand, env: w.env, runTimeoutMs: 20000, now: () => NOW, progress: () => undefined, ...over };
}

// ------------------------------------------------------------------ parsing

test('the run id of a locate run is <evalId>-<route>-c<NN>, which the report parses from the right', () => {
  const pattern = /^(.+)-(trove|pageindex)-c(\d+)$/u;
  for (const [evalId, route, claim] of [['ev-20261016-ashk', 'pageindex', 'c07'], ['ev-x', 'trove', 'c01'], ['a-trove-b', 'trove', 'c12']] as const) {
    const parsed = pattern.exec(runIdFor(evalId, route, claim));
    assert.deepEqual([parsed?.[1], parsed?.[2], parsed?.[3]], [evalId, route, claim.slice(1)]);
  }
  assert.equal(runIdFor('ev-20261016-ashk', 'pageindex', 'c07'), 'ev-20261016-ashk-pageindex-c07');
});

test('parseClaude reads the init, tool and result events and sums the token kinds', () => {
  const parsed = parseClaude([
    JSON.stringify({ type: 'system', subtype: 'init', model: 'm1', claude_code_version: '2.1.0' }),
    'not json at all',
    JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: 'hi' }, { type: 'tool_use', name: 'Bash', input: { command: 'x toc --source A' } }, { type: 'tool_use', name: 'Read', input: { file_path: '/etc/passwd' } }] } }),
    JSON.stringify({ type: 'user', message: { content: [{ type: 'tool_result', is_error: true, content: 'denied' }] } }),
    JSON.stringify({ type: 'result', subtype: 'error_max_turns', is_error: false, result: 'x', num_turns: 12, duration_ms: 99.4, total_cost_usd: 0.3, usage: { input_tokens: 5, cache_read_input_tokens: 10, cache_creation_input_tokens: 20, output_tokens: 7 }, permission_denials: [{}, {}] }),
  ].join('\n'));
  assert.deepEqual([parsed.model, parsed.version, parsed.calls.length, parsed.toolErrors, parsed.inputTokens, parsed.outputTokens, parsed.costUsd, parsed.agentMs, parsed.turns, parsed.permissionDenials, parsed.stopReason],
    ['m1', '2.1.0', 2, ['denied'], 35, 7, 0.3, 99, 12, 2, 'error_max_turns']);
  assert.equal(parseClaude('').text, null);
});

test('parseCodex reads commands, the last message and the summed usage; cost stays unknown', () => {
  const parsed = parseCodex([
    JSON.stringify({ type: 'thread.started' }),
    JSON.stringify({ type: 'item.completed', item: { type: 'command_execution', command: 'a toc', exit_code: 0 } }),
    JSON.stringify({ type: 'item.completed', item: { type: 'agent_message', text: 'first' } }),
    JSON.stringify({ type: 'turn.completed', usage: { input_tokens: 10, cached_input_tokens: 5, output_tokens: 3 } }),
    JSON.stringify({ type: 'item.completed', item: { type: 'agent_message', text: 'last' } }),
    JSON.stringify({ type: 'turn.completed', usage: { input_tokens: 1, output_tokens: 1 } }),
  ].join('\n'));
  assert.deepEqual([parsed.text, parsed.calls, parsed.inputTokens, parsed.outputTokens, parsed.costUsd, parsed.turns], ['last', ['a toc'], 16, 4, null, 2]);
});

test('parseAnswer takes the last valid fenced block, distinct positive pages, at most three', () => {
  const text = 'x\n```json\n{"book":"A","pages":[1]}\n```\nlater\n```json\n{"book":"B","pages":[4,4,"7",0,-2,9,11],"reason":"ok"}\n```';
  assert.deepEqual(parseAnswer(text, 3), { book: 'B', pages: [4, 7, 9], reason: 'ok' });
  assert.equal(parseAnswer('```json\n{"book":"A","pages":[]}\n```', 3), null);
  assert.equal(parseAnswer(null, 3), null);
  assert.deepEqual(parseAnswer('so: {"book":"C","pages":[2]}', 3), { book: 'C', pages: [2], reason: '' });
});

test('budget and allow-list checks: chained commands count one by one; codex shell wrappers are looked through', () => {
  const w = '/tmp/x/awlib';
  assert.deepEqual(deriveBudget([`${w} toc --source A; ${w} read --source A --pages 3-4 --text && ${w} read --source A --pages 7-9,11 --text`], w),
    { n_reads: 2, n_toc: 1, pages_per_read: [2, 4], over_budget: false });
  assert.equal(deriveBudget([`${w} read --source A --pages 1-9`], w).over_budget, true);
  assert.equal(deriveBudget([`${w} read --source A --pages 1-2`, `${w} read --source A --pages 3-4`, `${w} read --source A --pages 5-6`], w).over_budget, true);
  assert.deepEqual(commandViolations([`bash -lc '${w} toc --source A'`, `/bin/zsh -lc "${w} read --source A --pages 1-2"`, 'cat /etc/hosts', `${w} toc --source A; cat x`], w), ['cat /etc/hosts', '<wrapper> toc --source A; cat x']);
});

test('commands are checked strictly: exact subcommands and options, plain ids and page lists, no shell metacharacters', () => {
  const w = '/tmp/x/awlib';
  const fine = [`${w} toc --source T-A`, `${w} toc --source 'cm1.x_y#2:z'`, `${w} read --source T-A --pages 3-4 --text`, `${w} read --text --pages 3,5-6 --source T-A`, `${w} read --source "T-A" --pages 7`];
  for (const call of fine) assert.equal(commandProblem(call, w), null, call);
  const bad = [
    `${w} toc --source $(cat /etc/hosts)`, `${w} toc --source A\`id\``, `${w} toc --source A; ls`, `${w} toc --source A && ls`, `${w} toc --source A | cat`,
    `${w} toc --source A > out`, `${w} toc --source A < in`, `${w} toc --source (A)`, `${w} toc --source A\nls`, `${w} toc --source A\\x`,
    `${w} verdict --lookup x --verdict PASS`, `${w} status`, `${w} list`, `${w}`, `${w} toc`, `${w} toc --source A --pages 1`, `${w} toc --source A --source B`,
    `${w} toc --source A --run other`, `${w} toc --source A --claim c9`, `${w} read --source A`, `${w} read --pages 1-2`, `${w} read --source A --pages 1-2 --all`,
    `${w} read --source A --pages 1-2 --text --text`, `${w} read --source A --pages all`, `${w} read --source A --pages 1-`, `${w} read --source ../A --pages 1-2`,
    `${w}x toc --source A`, `${w}  toc --source A extra`, '[Read] {"file_path":"/etc/hosts"}', `cat ${w}`, `${w} read --source "A --pages 1`,
  ];
  for (const call of bad) assert.notEqual(commandProblem(call, w), null, call);
});

test('the wrapper script pins one route and stamps the run and claim; the prompt names no library and has the rules', () => {
  const script = wrapperScript({ awCommand: ['/usr/bin/node', "/a b/aw.mjs"], project: "/p/it's", route: 'pageindex', runId: 'ev-x-pageindex-c01', claimId: 'c01', env: { PATH: '/bin', AW_PAGEINDEX_COMMAND: 'wrap --x', HOME: '/h', GOOGLE_API_KEY: 'secret', AW_LIBRARY_ROUTE: 'trove' } });
  assert.match(script, /^#!\/bin\/sh/u);
  assert.match(script, /AW_LIBRARY_ROUTE='pageindex'; export AW_LIBRARY_ROUTE/u);
  assert.ok(script.includes("AW_PAGEINDEX_COMMAND='wrap --x'; export AW_PAGEINDEX_COMMAND"));
  assert.ok(!script.includes('secret') && !script.includes('HOME=') && !script.includes("='trove'"));
  assert.ok(script.includes(`exec '/usr/bin/node' '/a b/aw.mjs' --project-dir '/p/it'\\''s' library "$@" --run 'ev-x-pageindex-c01' --claim 'c01'`));
  const claim = { id: 'c01', text: 'A claim.' } as Claim;
  const prompt = buildPrompt({ shelf: [{ id: 'T-A', title: 'Book A' }, { id: 'T-B', title: 'ספר ב' }] } as Plan, claim, '/tmp/w/awlib');
  assert.ok(!/trove|page-?index|node|tree/iu.test(prompt), 'the prompt names no library');
  assert.match(prompt, /- T-B: ספר ב/u);
  assert.match(prompt, /"A claim\."/u);
});

// ------------------------------------------------------------------ the runner, with fake agents

test('runner (claude): isolated agents, one forced route each, usage rows, joined retrieval figures, resumable', async () => {
  const w = world();
  const { plan, paths } = await planFor(w);
  const summary = await runAll(options(w, plan, paths));
  assert.deepEqual([summary.planned, summary.done, summary.skipped, summary.failed], [4, 4, 0, 0]);
  assert.ok(Math.abs(summary.cost_usd - 0.2) < 1e-9);
  const runs = new Map<string, Run>();
  for (const claim of plan.claims) for (const route of plan.routes) {
    const run = await readJson(join(paths.runsDir, `${claim.id}-${route}.json`)) as Run;
    assert.deepEqual(validate('run', run), []);
    runs.set(`${claim.id}:${route}`, run);
  }
  const trove = runs.get('c01:trove') as Run;
  const pageindex = runs.get('c01:pageindex') as Run;
  assert.deepEqual([trove.status, trove.answer?.pages, pageindex.answer?.pages], ['ok', [3], [5]], 'each agent reached its own route');
  assert.deepEqual([trove.input_tokens, trove.output_tokens, trove.cost_usd, trove.turns, trove.agent_ms, trove.agent_version, trove.model, trove.attempts], [550, 20, 0.05, 3, 1500, '9.9.9', 'claude-sonnet-5-5', 1]);
  assert.deepEqual([trove.n_reads, trove.n_toc, trove.pages_per_read, trove.over_budget], [1, 1, [2], false]);
  assert.ok((trove.returned_chars ?? 0) > 0 && (trove.returned_est_tokens ?? 0) > 0, 'figures joined from the retrieval ledger by run id');
  assert.ok(trove.tool_calls.every((call) => !call.includes('/awlib')), 'the temp wrapper path is not stored');
  // The usage ledger rows.
  const rows = lines(join(w.project, '.academic-helper', 'runs', 'ev-run-trove-c01', 'usage.jsonl'));
  assert.equal(rows.length, 1);
  assert.deepEqual([rows[0]?.step, rows[0]?.provider, rows[0]?.model, rows[0]?.input_tokens, rows[0]?.output_tokens, rows[0]?.cost_usd, rows[0]?.exit], ['library.eval.locate', 'claude-code', 'claude-sonnet-5-5', 550, 20, 0.05, 'OK']);
  assert.ok(existsSync(join(w.project, '.academic-helper', 'runs', 'ev-run-pageindex-c02', 'usage.jsonl')));
  // Isolation: the recipe from the benchmark, an empty cwd, no route in the agent's env, no key.
  const launched = lines(w.logs.claude);
  assert.equal(launched.length, 4);
  for (const entry of launched) {
    const args = entry.args as string[];
    for (const flag of ['-p', '--strict-mcp-config', '--no-session-persistence', '--verbose']) assert.ok(args.includes(flag), flag);
    assert.deepEqual([args[args.indexOf('--setting-sources') + 1], args[args.indexOf('--tools') + 1], args[args.indexOf('--output-format') + 1]], ['project', 'Bash', 'stream-json']);
    assert.deepEqual(JSON.parse(args[args.indexOf('--settings') + 1] as string), { disableAllHooks: true });
    assert.equal(args[args.indexOf('--model') + 1], 'claude-sonnet-5-5');
    assert.deepEqual(args.slice(args.indexOf('--allowedTools') + 1).map((tool) => tool.replace(/\(\S+ /u, '(<w> ')), ['Bash(<w> toc:*)', 'Bash(<w> read:*)']);
    assert.deepEqual([entry.cwdFiles, entry.env], [[], { route: null, mds: '1', google: null }]);
    assert.ok(!/trove|page-?index/iu.test(String(entry.prompt)), 'the agent prompt is identical in kind for both libraries');
  }
  // Every library call went through one forced route and carried the run and claim ids.
  const calls = lines(w.logs.aw);
  assert.ok(calls.length >= 8 && calls.every((call) => call.route === 'trove' || call.route === 'pageindex'));
  assert.ok(calls.filter((call) => call.run === 'ev-run-pageindex-c01').every((call) => call.route === 'pageindex' && call.claim === 'c01'));
  // Resumable: finished runs are skipped; one deleted run is redone alone.
  const again = await runAll(options(w, plan, paths));
  assert.deepEqual([again.done, again.skipped], [0, 4]);
  assert.equal(lines(w.logs.claude).length, 4);
  rmSync(join(paths.runsDir, 'c02-trove.json'));
  const third = await runAll(options(w, plan, paths));
  assert.deepEqual([third.done, third.skipped], [1, 3]);
  rmSync(w.dir, { recursive: true, force: true });
});

test('runner: a failed first attempt is retried once; a run that never answers is recorded as an error, both attempts costed', async () => {
  const w = world();
  const { plan, paths } = await planFor(w, 1);
  w.env.FAKE_CLAUDE_MODE = 'fail_once';
  await runAll(options(w, plan, paths));
  const retried = await readJson(join(paths.runsDir, 'c01-trove.json')) as Run;
  const other = await readJson(join(paths.runsDir, 'c01-pageindex.json')) as Run;
  assert.equal(retried.attempts + other.attempts, 3, 'exactly one of the two runs needed a second try');
  assert.deepEqual([retried.status, other.status], ['ok', 'ok']);
  assert.equal(lines(join(w.project, '.academic-helper', 'runs', 'ev-run-trove-c01', 'usage.jsonl')).length + lines(join(w.project, '.academic-helper', 'runs', 'ev-run-pageindex-c01', 'usage.jsonl')).length, 3);
  rmSync(join(paths.runsDir, 'c01-trove.json'));
  rmSync(join(paths.runsDir, 'c01-pageindex.json'));
  w.env.FAKE_CLAUDE_MODE = 'noanswer';
  const summary = await runAll(options(w, plan, paths));
  assert.deepEqual([summary.done, summary.failed], [0, 2]);
  const failed = await readJson(join(paths.runsDir, 'c01-trove.json')) as Run;
  assert.deepEqual([failed.status, failed.attempts, failed.answer, failed.error, failed.cost_usd], ['error', 2, null, 'no parsable answer', 0.1]);
  assert.deepEqual(validate('run', failed), []);
  // A permission denial and an over-budget run are recorded.
  rmSync(join(paths.runsDir, 'c01-trove.json'));
  w.env.FAKE_CLAUDE_MODE = 'overbudget';
  await runAll(options(w, plan, paths));
  assert.equal(((await readJson(join(paths.runsDir, 'c01-trove.json'))) as Run).over_budget, true);
  rmSync(w.dir, { recursive: true, force: true });
});

test('runner: a hung agent is stopped at the deadline and its whole process group is killed', async () => {
  const w = world();
  const { plan, paths } = await planFor(w, 1);
  w.env.FAKE_CLAUDE_MODE = 'hang';
  const started = Date.now();
  const summary = await runAll(options(w, plan, paths, 'claude', { runTimeoutMs: 4000, parallel: 2 }));
  assert.ok(Date.now() - started < 30000);
  assert.deepEqual([summary.done, summary.failed], [0, 2]);
  const run = await readJson(join(paths.runsDir, 'c01-trove.json')) as Run;
  assert.match(run.error ?? '', /timed out/);
  const pids = readFileSync(w.logs.pids, 'utf8').split('\n').filter(Boolean).map(Number);
  assert.ok(pids.length >= 2, 'the agents started and left a grandchild behind');
  await new Promise((resolve) => setTimeout(resolve, 200));
  for (const pid of pids) assert.throws(() => process.kill(pid, 0), `grandchild ${pid} is gone`);
  rmSync(w.dir, { recursive: true, force: true });
});

test('runner: a missing agent command stops the run with a plain message and leaves no run files', async () => {
  const w = world();
  const { plan, paths } = await planFor(w, 1);
  w.env.AW_EVAL_CLAUDE_COMMAND = join(w.dir, 'no-such-claude');
  await assert.rejects(runAll(options(w, plan, paths)), /needs Claude Code installed on this computer/);
  assert.equal(existsSync(join(paths.runsDir, 'c01-trove.json')), false);
  rmSync(w.dir, { recursive: true, force: true });
});

test('runner (codex): commands parsed from events, usage kept, an off-list command makes the run an error', async () => {
  const w = world();
  const { plan, paths } = await planFor(w, 1);
  await runAll(options(w, plan, paths, 'codex', { model: 'some-model' }));
  const run = await readJson(join(paths.runsDir, 'c01-pageindex.json')) as Run;
  assert.deepEqual([run.status, run.engine, run.answer?.pages, run.input_tokens, run.output_tokens, run.cost_usd, run.model, run.n_toc], ['ok', 'codex', [5], 800, 40, null, 'some-model', 1]);
  const args = lines(w.logs.codex)[0]?.args as string[];
  assert.deepEqual(args.slice(0, 2), ['exec', '--json']);
  for (const flag of ['--skip-git-repo-check', '--ephemeral', '--ignore-user-config']) assert.ok(args.includes(flag), flag);
  assert.deepEqual([args[args.indexOf('--sandbox') + 1], args[args.indexOf('-m') + 1], args.at(-1)], ['read-only', 'some-model', '-']);
  const usage = lines(join(w.project, '.academic-helper', 'runs', 'ev-run-pageindex-c01', 'usage.jsonl'))[0];
  assert.deepEqual([usage?.provider, usage?.cost_usd], ['codex', null]);
  rmSync(join(paths.runsDir, 'c01-trove.json'));
  rmSync(join(paths.runsDir, 'c01-pageindex.json'));
  w.env.FAKE_CODEX_MODE = 'offlist';
  await runAll(options(w, plan, paths, 'codex'));
  const bad = await readJson(join(paths.runsDir, 'c01-trove.json')) as Run;
  assert.deepEqual([bad.status, bad.error], ['error', 'the agent ran a command that is not on its allowed list']);
  rmSync(w.dir, { recursive: true, force: true });
});

test('a cached run is reused only for the same plan, claim text, route, model, engine and prompt', async () => {
  const w = world();
  const { plan, paths } = await planFor(w, 2);
  await runAll(options(w, plan, paths));
  const launches = (): number => lines(w.logs.claude).length;
  assert.equal(launches(), 4);
  assert.deepEqual([(await runAll(options(w, plan, paths))).skipped, launches()], [4, 4], 'the same plan reuses every run');
  // Another plan with the same claim ids (as after `plan --force` with a new seed or draft): nothing is reused.
  const replaced: Plan = { ...plan, seed: 'another seed' };
  await writeJson(paths.plan, replaced);
  assert.deepEqual([(await runAll(options(w, replaced, paths))).skipped, launches()], [0, 8]);
  // Same ids, different claim text.
  const reworded: Plan = { ...replaced, claims: replaced.claims.map((claim, index) => (index === 0 ? { ...claim, text: `${claim.text} Reworded.` } : claim)) };
  writeFileSync(w.answersFile, JSON.stringify(Object.fromEntries(reworded.claims.map((claim) => [claim.text, { book: 'T-A', trove: [3], pageindex: [5] }]))));
  const afterText = await runAll(options(w, reworded, paths));
  assert.deepEqual([afterText.skipped, afterText.done, launches()], [0, 4, 12], 'the plan changed with the claim, so nothing is reused');
  // Another model or engine.
  assert.equal((await runAll(options(w, reworded, paths, 'claude', { model: 'another-model' }))).skipped, 0);
  assert.equal((await runAll(options(w, reworded, paths, 'codex'))).skipped, 0);
  assert.notEqual(expectedFingerprint({ plan, engine: 'claude', model: null }, plan.claims[0] as Claim, 'trove'), expectedFingerprint({ plan, engine: 'claude', model: null }, plan.claims[0] as Claim, 'pageindex'));
  rmSync(w.dir, { recursive: true, force: true });
});

test('commands outside the allowed list make the run invalid (claude too), and the violation is recorded', async () => {
  const w = world();
  const { plan, paths } = await planFor(w, 1);
  w.env.FAKE_CLAUDE_MODE = 'chain';
  await runAll(options(w, plan, paths));
  const run = await readJson(join(paths.runsDir, 'c01-trove.json')) as Run;
  assert.deepEqual([run.status, run.error, run.violations.length > 0], ['error', 'the agent ran a command that is not on its allowed list', true]);
  assert.ok(run.violations.every((entry) => entry.length <= 120 && !entry.includes('/awlib')));
  assert.deepEqual(validate('run', run), []);
  rmSync(w.dir, { recursive: true, force: true });
});

for (const mode of ['orphan', 'linger']) {
  test(`everything an agent started is stopped, including library commands that left its process group (${mode})`, async () => {
    const w = world();
    const { plan, paths } = await planFor(w, 1);
    const pidFile = join(w.dir, 'detached.log');
    Object.assign(w.env, { FAKE_DETACH_PIDS: pidFile, FAKE_DETACH_MODE: mode });
    await runAll(options(w, plan, paths));
    const pids = readFileSync(pidFile, 'utf8').split('\n').filter(Boolean).map(Number);
    assert.equal(pids.length, 2, 'one detached helper per route');
    for (const pid of pids) assert.throws(() => process.kill(pid, 0), `detached helper ${pid} is gone`);
    rmSync(w.dir, { recursive: true, force: true });
  });
}

test('a violation on any attempt invalidates the claim for good: a clean retry cannot hide it, and a rerun does not try again', async () => {
  const w = world();
  const { plan, paths } = await planFor(w, 1);
  const only = (over: Partial<RunnerOptions> = {}): RunnerOptions => options(w, plan, paths, 'claude', { routes: ['trove'], parallel: 1, ...over });
  w.env.FAKE_CLAUDE_MODE = 'chain_once';
  const summary = await runAll(only());
  const run = await readJson(join(paths.runsDir, 'c01-trove.json')) as Run;
  assert.deepEqual([summary.invalid, summary.done, run.status, run.attempts, run.violations.length > 0], [1, 0, 'error', 1, true], 'no second attempt is made after a violation');
  assert.equal(lines(w.logs.claude).length, 1);
  const again = await runAll(only());
  assert.deepEqual([again.invalid, again.done, lines(w.logs.claude).length], [1, 0, 1], 'the invalid run is not run again');
  // A first attempt that failed for another reason, then a second that broke the rule: the violation is kept.
  rmSync(join(paths.runsDir, 'c01-trove.json'));
  rmSync(w.env.FAKE_COUNTER as string, { force: true });
  w.env.FAKE_CLAUDE_MODE = 'fail_then_chain';
  await runAll(only());
  const second = await readJson(join(paths.runsDir, 'c01-trove.json')) as Run;
  assert.deepEqual([second.attempts, second.status, second.violations.length > 0], [2, 'error', true]);
  rmSync(w.dir, { recursive: true, force: true });
});

test('once pairs exist the runs are not rewritten; run --reset archives the old generation and starts again', async () => {
  const w = world();
  const { plan, paths } = await planFor(w, 1);
  await runAll(options(w, plan, paths));
  writeFileSync(paths.pairs, '{}');
  await assert.rejects(runAll(options(w, plan, paths)), /pairs already exist for this evaluation/);
  const out: string[] = [];
  const err: string[] = [];
  const io = { out: (t: string) => out.push(t), err: (t: string) => err.push(t), project: w.project, env: w.env, awCommand: w.awCommand, now: () => NOW };
  assert.equal(await runEvalCli(['run', '--eval', 'ev-run'], io), 2);
  assert.equal(await runEvalCli(['run', '--eval', 'ev-run', '--reset'], io), 0, err.join(''));
  assert.equal(JSON.parse(out.join('')).done, 2);
  const archives = readdirSync(paths.archiveDir);
  assert.equal(archives.length, 1);
  assert.deepEqual(readdirSync(join(paths.archiveDir, archives[0] as string)).sort(), ['pairs.json', 'runs']);
  assert.equal(existsSync(paths.pairs), false);
  assert.equal(existsSync(join(paths.runsDir, 'c01-trove.json')), true);
  rmSync(w.dir, { recursive: true, force: true });
});

test('an interrupt stops the agents AND everything they started before the program exits with the signal code', async () => {
  const w = world();
  const { plan, paths } = await planFor(w, 1);
  const root = existsSync(join(process.cwd(), 'src', 'main.ts')) ? process.cwd() : join(process.cwd(), 'src', 'cli');
  const driverSource = join(w.dir, 'driver.ts');
  writeFileSync(driverSource, `import { runAll } from ${JSON.stringify(join(root, 'src', 'library', 'eval', 'runner.ts'))};
const cfg = JSON.parse(process.env.DRIVER_CFG as string);
await runAll({ ...cfg, env: process.env, now: () => new Date(), progress: () => undefined });
`);
  const driver = join(w.dir, 'driver.mjs');
  const code = `import { build } from 'esbuild'; await build({ entryPoints: [${JSON.stringify(driverSource)}], outfile: ${JSON.stringify(driver)}, bundle: true, platform: 'node', target: 'node20', format: 'esm', logLevel: 'error', loader: { '.md': 'text' }, banner: { js: "import { createRequire as __r } from 'node:module'; const require = __r(import.meta.url);" } });`;
  execFileSync(process.execPath, ['--input-type=module', '-e', code], { cwd: root });
  Object.assign(w.env, { FAKE_CLAUDE_MODE: 'hang', FAKE_HANG_DETACH: '1' });
  const cfg = { project: w.project, paths, plan, engine: 'claude', model: null, parallel: 2, routes: plan.routes, awCommand: w.awCommand, runTimeoutMs: 120000 };
  const child = spawn(process.execPath, [driver], { env: { ...w.env, DRIVER_CFG: JSON.stringify(cfg) }, stdio: 'ignore' });
  const exited = new Promise<number | null>((resolve) => { child.on('exit', (status) => resolve(status)); });
  const started = Date.now();
  const pidList = (): number[] => (existsSync(w.logs.pids) ? readFileSync(w.logs.pids, 'utf8').split('\n').filter(Boolean).map(Number) : []);
  while (pidList().length < 4 && Date.now() - started < 30000) await new Promise((resolve) => setTimeout(resolve, 100));
  const pids = pidList();
  assert.equal(pids.length, 4, 'both agents started and left a plain and a detached helper each');
  child.kill('SIGTERM');
  assert.equal(await exited, 143, 'exit code of SIGTERM');
  for (const pid of pids) assert.throws(() => process.kill(pid, 0), `process ${pid} is gone`);
  assert.equal(pidList().length, 4, 'no new agent was started while stopping (no retry after the interrupt)');
  rmSync(w.dir, { recursive: true, force: true });
});

const TROVE_FAKE = `
const fs = require('node:fs');
const args = process.argv.slice(2);
fs.appendFileSync(process.env.LIB_LOG, 'trove ' + args.join(' ') + '\\n');
const page = (n) => '── Page ' + n + ' ──\\ntrove text p' + n + '\\n';
if (args[0] === 'items' && args[1] === 'list') console.log(JSON.stringify({ items: [{ id: 'T-A', title: 'Book A', author: 'Au', pageCount: 9 }] }));
else if (args[0] === 'items' && args[1] === 'toc' && args.includes('--json')) console.log(JSON.stringify({ items: [{ id: args[2], title: 'Book A', toc: [{ title: 'Intro', page: 1, level: 1 }] }] }));
else if (args[0] === 'items' && args[1] === 'read') {
  const spec = args.includes('--pages') ? args[args.indexOf('--pages') + 1] : args[2].split(':')[1];
  const ids = spec.split(',').flatMap((p) => { const [a, b] = p.split('-').map(Number); return Array.from({ length: (b || a) - a + 1 }, (_, i) => a + i); });
  process.stdout.write('Book A\\n' + args[2].split(':')[0] + ' | 9 pages\\n' + ids.map(page).join(''));
} else { console.error('unexpected: ' + args.join(' ')); process.exit(2); }
`;
const PILIB_FAKE = `
const fs = require('node:fs');
const args = process.argv.slice(2);
fs.appendFileSync(process.env.LIB_LOG, 'pilib ' + args.join(' ') + '\\n');
const [cmd, book, spec] = args;
const info = { book_id: 'lib-a', title: 'Library A', n_pages: 9, origin: { trove: { trove_id: 'T-A' } }, trove_id: 'T-A', pagemap: null };
if (cmd === 'catalog') console.log(JSON.stringify({ 'lib-a': { title: 'Library A', author: 'Au', n_pages: 9, toc_source: 'x', top: [] } }));
else if (cmd === 'meta') console.log(JSON.stringify(info));
else if (cmd === 'tree') console.log(JSON.stringify({ book_id: book, title: 'Library A', n_pages: 9, structure: [{ node_id: '1', title: 'Top', start_index: 1, end_index: 4 }] }));
else if (cmd === 'read') {
  const pages = spec.split(',').flatMap((p) => { const [a, b] = p.split('-').map(Number); return Array.from({ length: (b || a) - a + 1 }, (_, i) => a + i); });
  if (args.includes('--json')) console.log(JSON.stringify({ book_id: book, pages: pages.map((n) => ({ page: n, content: 'pi text p' + n })) }));
  else pages.forEach((n) => { console.log('── Page ' + n + ' ──'); console.log('pi text p' + n); });
} else { console.error('unexpected: ' + args.join(' ')); process.exit(2); }
`;

/** The real `aw` (bundled from src/main.ts into a temp file), so the route forcing is the adapter's own. */
function bundleAw(dir: string): string {
  const root = existsSync(join(process.cwd(), 'src', 'main.ts')) ? process.cwd() : join(process.cwd(), 'src', 'cli');
  const outfile = join(dir, 'aw.mjs');
  const code = `import { build } from 'esbuild'; await build({ entryPoints: [${JSON.stringify(join(root, 'src', 'main.ts'))}], outfile: ${JSON.stringify(outfile)}, bundle: true, platform: 'node', target: 'node20', format: 'esm', logLevel: 'error', loader: { '.md': 'text' }, banner: { js: "import { createRequire as __r } from 'node:module'; const require = __r(import.meta.url);" } });`;
  execFileSync(process.execPath, ['--input-type=module', '-e', code], { cwd: root });
  return outfile;
}

test('an eval locate run reaches exactly one library through the real aw, whatever library.json says', async () => {
  const w = world();
  const bin = join(w.dir, 'libs');
  mkdirSync(bin);
  for (const [name, body] of [['trove', TROVE_FAKE], ['pilib', PILIB_FAKE]] as const) { writeFileSync(join(bin, name), `#!${process.execPath}\n${body}`); chmodSync(join(bin, name), 0o755); }
  const libLog = join(w.dir, 'lib.log');
  Object.assign(w.env, { AW_TROVE_COMMAND: join(bin, 'trove'), AW_PAGEINDEX_COMMAND: join(bin, 'pilib'), LIB_LOG: libLog, AW_LIBRARY_ROUTE: undefined });
  writeFileSync(join(w.project, '.academic-helper', 'library.json'), JSON.stringify({ route: 'both' }));
  const awScript = bundleAw(w.dir);
  const { plan, paths } = await planFor(w, 1);
  writeFileSync(w.answersFile, JSON.stringify(Object.fromEntries(plan.claims.map((claim) => [claim.text, { book: 'T-A', trove: [3], pageindex: [4] }]))));
  const logged = (): string[] => (existsSync(libLog) ? readFileSync(libLog, 'utf8').split('\n').filter(Boolean) : []);
  for (const route of ['trove', 'pageindex'] as Route[]) {
    rmSync(libLog, { force: true });
    rmSync(join(paths.runsDir), { recursive: true, force: true });
    rmSync(join(w.project, '.academic-helper', 'retrieval.jsonl'), { force: true });
    const summary = await runAll(options(w, plan, paths, 'claude', { routes: [route], awCommand: [process.execPath, awScript], parallel: 1 }));
    assert.deepEqual([summary.done, summary.failed], [1, 0], route);
    const run = await readJson(join(paths.runsDir, `c01-${route}.json`)) as Run;
    assert.deepEqual([run.status, run.answer?.pages], ['ok', route === 'trove' ? [3] : [4]], route);
    const used = logged();
    assert.ok(used.length > 0);
    const other = route === 'trove' ? 'pilib' : 'trove';
    assert.deepEqual(used.filter((line) => line.startsWith(`${other} `)), [], `${route}: the other library is never asked, although library.json says both`);
    await new Promise((resolve) => setTimeout(resolve, 600)); // a shadow worker, if one had started, would show by now
    assert.deepEqual(logged().filter((line) => line.startsWith(`${other} `)), [], `${route}: no shadow lookup either`);
    const rows = lines(join(w.project, '.academic-helper', 'retrieval.jsonl'));
    assert.ok(rows.length > 0 && rows.every((row) => row.row_type === 'lookup' && row.route_primary === route && row.shadow_status === 'none'), JSON.stringify(rows.map((row) => [row.row_type, row.route_primary, row.shadow_status])));
  }
  rmSync(w.dir, { recursive: true, force: true });
});

test('returnedFor: sums only this run id lookup rows and says null when the ledger has none', async () => {
  const w = world();
  assert.deepEqual(await returnedFor(w.project, 'r1'), { chars: null, est: null });
  const row = (run: string, chars: number, est?: number) => JSON.stringify({ row_type: 'lookup', run_id: run, primary: { chars, ...(est === undefined ? {} : { est_tokens: est }) } });
  writeFileSync(join(w.project, '.academic-helper', 'retrieval.jsonl'), [row('r1', 10, 3), row('r1-extra', 99, 99), row('r1', 20, 5), 'torn {', JSON.stringify({ row_type: 'verdict', run_id: 'r1' })].join('\n'));
  assert.deepEqual(await returnedFor(w.project, 'r1'), { chars: 30, est: 8 });
  writeFileSync(join(w.project, '.academic-helper', 'retrieval.jsonl'), [row('r2', 10), row('r2', 20, 5)].join('\n'));
  assert.deepEqual(await returnedFor(w.project, 'r2'), { chars: 30, est: null }, 'an estimate is only reported when every row has one');
  rmSync(w.dir, { recursive: true, force: true });
});

// ------------------------------------------------------------------ the whole round through the command line

test('a full round: plan, run, pairs, import, unblind through runEvalCli with fake agents', async () => {
  const w = world();
  mkdirSync(join(w.project, '.academic-helper'), { recursive: true });
  writeFileSync(join(w.project, '.academic-helper', 'sources.json'), JSON.stringify(['T-A', 'T-B', 'T-C'].map((id) => ({ sourceId: id, workTitle: `Book ${id}`, pageMap: { kind: 'identity' } }))));
  const sentences: string[] = [];
  for (const id of ['T-A', 'T-B', 'T-C']) for (let i = 1; i <= 2; i += 1) sentences.push(`The claim number ${i} about ${id} is written in a full sentence here.[^${id}]`);
  writeFileSync(join(w.project, '.academic-helper', 'drafts', 'u1.md'), [sentences.join(' '), '', '[^T-A]: Au, A, p. 3.', '[^T-B]: Au, B, p. 4.', '[^T-C]: Au, C, p. 5.'].join('\n'));
  const out: string[] = [];
  const err: string[] = [];
  const io = { out: (t: string) => out.push(t), err: (t: string) => err.push(t), project: w.project, env: w.env, awCommand: w.awCommand, now: () => NOW };
  const call = async (...argv: string[]): Promise<{ code: number; json: Record<string, any> | null; text: string }> => { // eslint-disable-line @typescript-eslint/no-explicit-any
    out.length = 0; err.length = 0;
    const code = await runEvalCli(argv, io);
    const text = out.join('');
    let json: Record<string, any> | null = null; // eslint-disable-line @typescript-eslint/no-explicit-any
    try { json = JSON.parse(text) as Record<string, any>; } catch { json = null; } // eslint-disable-line @typescript-eslint/no-explicit-any
    return { code, json, text };
  };
  const planned = await call('plan', '--eval', 'ev-full', '--n', '6', '--seed', 'abc');
  assert.equal(planned.code, 0, err.join(''));
  assert.deepEqual([planned.json?.claims, planned.json?.runs, planned.json?.estimated_usd], [6, 12, 1.2]);
  assert.equal((await call('plan', '--eval', 'ev-full')).code, 2, 'an existing plan needs --force');
  const plan = await readJson(evalPaths(w.project, 'ev-full').plan) as Plan;
  writeFileSync(w.answersFile, JSON.stringify(Object.fromEntries(plan.claims.map((claim, index) => [claim.text, { book: claim.source_id, trove: [claim.cited_trove_pages[0]], pageindex: index % 3 === 0 ? [claim.cited_trove_pages[0]] : [9] }]))));
  assert.deepEqual(plan.claims.map((claim) => claim.cited_trove_pages), plan.claims.map((claim) => [{ 'T-A': 3, 'T-B': 4, 'T-C': 5 }[claim.source_id] as number]));
  const staleRun = join(w.project, '.academic-helper', 'library-eval', 'ev-full', 'runs', 'c01-trove.json');
  mkdirSync(join(staleRun, '..'), { recursive: true });
  writeFileSync(staleRun, '{}');
  assert.equal((await call('plan', '--eval', 'ev-full', '--n', '6', '--seed', 'abc', '--force')).code, 0, err.join(''));
  assert.equal(existsSync(staleRun), false, '`plan --force` clears the runs of the plan it replaces');
  const status0 = await call('status', '--eval', 'ev-full');
  assert.equal(status0.json?.stage, 'planned');
  const ran = await call('run', '--eval', 'ev-full', '--parallel', '3');
  assert.equal(ran.code, 0, err.join(''));
  assert.deepEqual([ran.json?.done, ran.json?.failed, ran.json?.planned], [12, 0, 12]);
  assert.ok(!/trove|pageindex/iu.test(err.join('') + ran.text), 'run output names no library');
  assert.equal((await call('status', '--eval', 'ev-full')).json?.stage, 'located');
  const paired = await call('pairs', '--eval', 'ev-full', '--seed', 'cli-seed');
  assert.equal(paired.code, 0, err.join(''));
  assert.deepEqual([paired.json?.pairs, paired.json?.auto_same], [6, 2], 'claims 1 and 4 got the same pages from both libraries');
  const shown = readFileSync(evalPaths(w.project, 'ev-full').pairs, 'utf8');
  assert.ok(!/trove|pageindex/iu.test(shown));
  assert.equal((await call('unblind', '--eval', 'ev-full')).code, 2, 'refused before judging');
  assert.match(err.join(''), /no judgments are imported yet/);
  const mapping = await readJson(evalPaths(w.project, 'ev-full').mapping) as Mapping;
  const shownPairs = (await readJson(evalPaths(w.project, 'ev-full').pairs) as { pairs: Array<{ pair_id: string; auto_same: boolean }> }).pairs;
  // The judge leaves the identical pairs alone (they are marked "same" by themselves).
  const judged = mapping.pairs.filter((entry) => !shownPairs.find((pair) => pair.pair_id === entry.pair_id)?.auto_same).map((entry) => ({ pair_id: entry.pair_id, verdict: entry.A === 'trove' ? 'A' : 'B' }));
  const file = join(w.dir, 'judgments.json');
  writeFileSync(file, JSON.stringify({ eval_id: 'ev-full', judgments: judged.map((entry, index) => (index === 1 ? { ...entry, note: 'עדיף' } : entry)) }));
  const imported = await call('import', '--eval', 'ev-full', '--file', file);
  assert.equal(imported.code, 0, err.join(''));
  assert.deepEqual([imported.json?.pairs, imported.json?.pending], [6, []]);
  const final = await call('unblind', '--eval', 'ev-full', '--json');
  assert.equal(final.code, 0, err.join(''));
  // Trove found the cited page on every claim; PageIndex on claims 1 and 4. The judge always picked the Trove side.
  const trove = final.json?.routes.trove;
  const pageindex = final.json?.routes.pageindex;
  assert.deepEqual([trove.wins, trove.losses, pageindex.wins, pageindex.losses], [4, 0, 0, 4]);
  assert.deepEqual([trove.cited_page_hit.hits, pageindex.cited_page_hit.hits], [6, 2]);
  assert.equal(final.json?.n_auto_same, 2);
  assert.equal(final.json?.enough_pairs, false);
  assert.equal((await call('status', '--eval', 'ev-full')).json?.stage, 'unblinded');
  rmSync(w.dir, { recursive: true, force: true });
});
