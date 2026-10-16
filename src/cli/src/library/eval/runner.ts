import { randomBytes } from 'node:crypto';
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { constants as osConstants, tmpdir } from 'node:os';
import { join } from 'node:path';
import { appendUsage, canonicalJson, readJson, runFile, sha256, validate, writeJson, type EvalPaths } from './files.ts';
import { ChildGroup, RUN_TAG_ENV, TreeTracker, parseAgent, parseAnswer, reapTagged, runAgent, type Parsed } from './agent.ts';
import { evalLimits } from './limits.ts';
import { LibraryError } from '../types.ts';
import { redact } from '../redact.ts';
import { FILTER_SOURCE } from './filter-source.ts';
import type { Claim, Engine, Plan, Route, Run } from './types.ts';

export type RunnerOptions = {
  project: string;
  paths: EvalPaths;
  plan: Plan;
  engine: Engine;
  /** Model for the agent; default for claude is thresholds.library.eval.locateModel, for codex the user's own default. */
  model: string | null;
  parallel: number;
  routes: Route[];
  awCommand: string[];
  env: NodeJS.ProcessEnv;
  runTimeoutMs: number;
  now: () => Date;
  /** Progress, with no route names in it. */
  progress: (line: string) => void;
};

/** One claim whose runs were invalidated: how many runs, why in plain words, and the (clipped, wrapper-hidden) commands that broke the rule. No library is named. */
export type InvalidClaim = { claim_id: string; runs: number; reason: string; commands: string[] };

export type RunSummary = { planned: number; done: number; skipped: number; failed: number; invalid: number; cost_usd: number; invalid_runs: InvalidClaim[] };

const MAX_ATTEMPTS = 2;

function quote(value: string): string { return `'${value.replace(/'/gu, `'\\''`)}'`; }

export function runIdFor(evalId: string, route: Route, claimId: string): string { return `${evalId}-${route}-${claimId}`; }

/**
 * The one door an agent gets to the library: a shell script that runs `aw library <toc|read ...>` for ONE route
 * (AW_LIBRARY_ROUTE forces it and turns the shadow off) and stamps every call with the run and claim ids, so the
 * retrieval ledger can be joined to this run. Agents see the same two commands whichever route stands behind them.
 */
export function wrapperScript(options: { awCommand: string[]; project: string; route: Route; runId: string; claimId: string; env: NodeJS.ProcessEnv; work: string; filter: string; errorLog: string }): string {
  const exported = Object.entries(options.env)
    .filter(([key, value]) => value !== undefined && (key === 'PATH' || (key.startsWith('AW_') && key !== 'AW_LIBRARY_ROUTE')))
    .map(([key, value]) => `${key}=${quote(String(value))}; export ${key}`);
  return [
    '#!/bin/sh',
    ...exported,
    `AW_LIBRARY_ROUTE=${quote(options.route)}; export AW_LIBRARY_ROUTE`,
    `out=${quote(options.work)}/out.$$; err=${quote(options.work)}/err.$$`,
    `${options.awCommand.map(quote).join(' ')} --project-dir ${quote(options.project)} library "$@" --run ${quote(options.runId)} --claim ${quote(options.claimId)} >"$out" 2>"$err"`,
    'code=$?',
    // The agent sees the output with everything that names the library removed (see filter-source.ts).
    `exec ${quote(process.execPath)} ${quote(options.filter)} "$code" "$out" "$err" ${quote(options.errorLog)}`,
    '',
  ].join('\n');
}

/** Write the wrapper and its output filter into `bin`; returns the wrapper path and the error log the filter fills. */
export async function writeWrapper(bin: string, options: { awCommand: string[]; project: string; route: Route; runId: string; claimId: string; env: NodeJS.ProcessEnv }): Promise<{ wrapper: string; errorLog: string }> {
  const wrapper = join(bin, 'awlib');
  const filter = join(bin, 'filter.cjs');
  const errorLog = join(bin, 'lookup-errors.log');
  await writeFile(filter, FILTER_SOURCE, { mode: 0o600 });
  await writeFile(wrapper, wrapperScript({ ...options, work: bin, filter, errorLog }), { mode: 0o700 });
  return { wrapper, errorLog };
}

/** What the library really said when a lookup failed (the agent only saw "lookup failed"), redacted and clipped. */
async function lookupErrors(errorLog: string): Promise<string[]> {
  let text: string;
  try { text = await readFile(errorLog, 'utf8'); } catch { return []; }
  const out: string[] = [];
  for (const line of text.split('\n')) {
    try {
      const row = JSON.parse(line) as { code?: number; stderr?: string };
      out.push(`exit ${row.code ?? '?'}: ${redact(String(row.stderr ?? '')).replace(/\s+/gu, ' ').trim().slice(0, 300)}`);
    } catch { /* blank or torn */ }
  }
  return out.slice(0, 5);
}

/** The warning line for a count of invalid runs (null when there are none); the same wording in `run` and `status`. */
export function invalidWarning(invalid: number, total: number): string | null {
  return invalid === 0 ? null : `${invalid} of ${total} runs are INVALID: the agent ran a command outside its allowed list (a pipe, a redirect or another shell form), so those answers are thrown away and their claims are left out of the pairs`;
}

export function buildPrompt(plan: Plan, claim: Claim, wrapper: string): string {
  const shelf = plan.shelf.map((book) => `- ${book.id}: ${book.title}`).join('\n');
  return `You are a research assistant. A scholar's article makes the claim below, and you must find
the exact page in their library that supports it, so it can be cited.

The scholar's shelf has ${plan.shelf.length} book${plan.shelf.length === 1 ? '' : 's'}:
${shelf}

Claim from the article:
"${claim.text}"

You may only use these two shell commands, in exactly these forms:
${wrapper} toc --source <book id>
${wrapper} read --source <book id> --pages <a>-<b> --text
(toc prints the table of contents: section titles with page ranges and short hints; read prints pages a to b. A single page is --pages <a>, a short list is --pages <a>,<b>.)

Run each command exactly as given, as one plain command, without pipes, redirects, \`;\`, \`&&\`, \`||\`, subshells, \`$(...)\` or backticks, and without head, grep, cut, sed or any other filter after it. A command with any of these is refused, and a refused command invalidates your whole answer: it is thrown away. You never need to filter: a read is already limited to the pages you ask for (at most ${evalLimits.maxPagesPerRead} pages per read), so read the output as it comes.

Rules:
- Start from the table of contents.
- Read pages at most ${evalLimits.maxReads} times in total, and at most ${evalLimits.maxPagesPerRead} pages per read.
- Page numbers are the page numbers these commands show you, not the printed page numbers inside the text.
- Finish with one fenced json block and nothing after it:
\`\`\`json
{"book": "<book id>", "pages": [<best page>, <second>, <third>], "reason": "<one sentence>"}
\`\`\`
List up to ${evalLimits.maxAnswerPages} distinct single pages, best first.
`;
}

function segments(calls: string[]): string[] {
  return calls.flatMap((call) => call.split(/;|&&|\||\n/u)).map((part) => part.trim()).filter(Boolean);
}

function pagesAsked(command: string): number {
  const spec = /--pages[=\s]+["']?([\d,-]+)/u.exec(command)?.[1] ?? '';
  let total = 0;
  for (const part of spec.split(',')) {
    const [first, last] = part.split('-');
    if (first && /^\d+$/u.test(first)) total += last && /^\d+$/u.test(last) ? Number(last) - Number(first) + 1 : 1;
  }
  return total;
}

/** Reads, table-of-contents calls and pages per read, from the commands the agent ran. */
export function deriveBudget(calls: string[], wrapper: string): Pick<Run, 'n_reads' | 'n_toc' | 'pages_per_read' | 'over_budget'> {
  const parts = segments(calls);
  const reads = parts.filter((part) => part.includes(`${wrapper} read`));
  const tocs = parts.filter((part) => part.includes(`${wrapper} toc`));
  const pages = reads.map(pagesAsked);
  return {
    n_reads: reads.length, n_toc: tocs.length, pages_per_read: pages,
    over_budget: reads.length > evalLimits.maxReads || pages.some((count) => count > evalLimits.maxPagesPerRead),
  };
}

const SHELL_META = /[$`;|&<>()\\\n\r]/u;
const BOOK_ID = /^[A-Za-z0-9._#:_-]+$/u;
const PAGE_SPEC = /^\d{1,6}(?:-\d{1,6})?(?:,\d{1,6}(?:-\d{1,6})?)*$/u;

function unquote(token: string): string {
  const first = token[0];
  return token.length >= 2 && (first === "'" || first === '"') && token.endsWith(first) ? token.slice(1, -1) : token;
}

/**
 * Why a command an agent ran is outside its allowed list, or null when it is allowed: exactly
 * `<wrapper> toc --source <id>` or `<wrapper> read --source <id> --pages <spec> [--text]`, one command, no shell
 * metacharacters anywhere, ids and page specs in their plain forms. (Claude Code's own permission matching, which
 * understands shell operators, is the first guard; this is the second, and the only one for Codex.)
 */
export function commandProblem(call: string, wrapper: string): string | null {
  const shell = /^(?:\S*\/)?(?:ba|z)?sh\s+-l?c\s+(['"])([\s\S]*)\1\s*$/u.exec(call.trim());
  const command = (shell ? shell[2] as string : call).trim();
  if (SHELL_META.test(command)) return 'shell metacharacter';
  if (!command.startsWith(`${wrapper} `)) return 'not the library command';
  const tokens = command.slice(wrapper.length).trim().split(/\s+/u).map(unquote);
  const [subcommand, ...rest] = tokens;
  const seen = new Set<string>();
  const values = new Map<string, string>();
  for (let index = 0; index < rest.length; index += 1) {
    const flag = rest[index] as string;
    if (flag === '--text' && subcommand === 'read') { if (seen.has(flag)) return 'repeated option'; seen.add(flag); continue; }
    if (flag !== '--source' && !(flag === '--pages' && subcommand === 'read')) return `option ${flag.slice(0, 20)} is not allowed`;
    const value = rest[index + 1];
    if (value === undefined || seen.has(flag)) return 'missing or repeated option value';
    if (flag === '--source' && !BOOK_ID.test(value)) return 'book id is not plain';
    if (flag === '--pages' && !PAGE_SPEC.test(value)) return 'page list is not plain';
    seen.add(flag);
    values.set(flag, value);
    index += 1;
  }
  if (subcommand === 'toc') return seen.size === 1 && seen.has('--source') ? null : 'toc takes only --source';
  if (subcommand === 'read') return values.has('--source') && values.has('--pages') ? null : 'read needs --source and --pages';
  return 'subcommand is not allowed';
}

/** Plain words for why commands were refused: from the first one that breaks the rule. */
export function invalidReason(commands: string[], wrapper: string): string {
  for (const call of commands) {
    const problem = commandProblem(call, wrapper);
    if (problem === null) continue;
    if (problem === 'shell metacharacter') return 'a pipe, redirect or other shell character was used (commands must be run exactly as given)';
    if (problem === 'not the library command') return 'a command that is not one of the two allowed library commands';
    return `a command that is not allowed (${problem})`;
  }
  return 'a command outside the allowed list';
}

/** A stand-in path for the wrapper that stored commands show as `<wrapper>` (which is itself shell metacharacters), to re-check them. */
const STORED_WRAPPER = '/awlib';

/** One entry per claim with invalid runs, from the runs' recorded violations (route-blind: never says which library). */
export function invalidClaims(runs: Array<Pick<Run, 'claim_id' | 'violations'>>): InvalidClaim[] {
  const byClaim = new Map<string, { runs: number; commands: string[] }>();
  for (const run of runs) {
    if (run.violations.length === 0) continue;
    const entry = byClaim.get(run.claim_id) ?? { runs: 0, commands: [] };
    entry.runs += 1;
    for (const command of run.violations) if (!entry.commands.includes(command)) entry.commands.push(command);
    byClaim.set(run.claim_id, entry);
  }
  return [...byClaim.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([claim_id, entry]) => ({ claim_id, runs: entry.runs, reason: invalidReason(entry.commands.map((command) => command.replaceAll('<wrapper>', STORED_WRAPPER)), STORED_WRAPPER), commands: entry.commands.slice(0, 5) }));
}

/** The commands (clipped, wrapper path hidden) that break the allowed list. */
export function commandViolations(calls: string[], wrapper: string): string[] {
  return calls.filter((call) => commandProblem(call, wrapper) !== null).map((call) => call.replaceAll(wrapper, '<wrapper>').slice(0, 120));
}

/**
 * Characters and (when T2's estimate is present) tokens that ONE locate attempt's lookups returned, from the retrieval ledger:
 * only lookup rows with this run id whose time falls inside the attempt's window. The run id is reused by a later generation
 * (`run --reset`, a replaced plan, another model), so rows of an older generation are never counted.
 */
export async function returnedFor(project: string, runId: string, window: { fromMs: number; toMs: number }): Promise<{ chars: number | null; est: number | null }> {
  let text: string;
  try { text = await readFile(join(project, '.academic-helper', 'retrieval.jsonl'), 'utf8'); } catch { return { chars: null, est: null }; }
  let chars = 0;
  let est = 0;
  let rows = 0;
  let withEstimate = 0;
  for (const line of text.split('\n')) {
    if (!line.includes(runId)) continue;
    try {
      const row = JSON.parse(line) as { row_type?: string; run_id?: string | null; ts?: unknown; primary?: { chars?: unknown; est_tokens?: unknown } };
      if (row.row_type !== 'lookup' || row.run_id !== runId) continue;
      const at = typeof row.ts === 'string' ? Date.parse(row.ts) : Number.NaN;
      if (!(at >= window.fromMs && at <= window.toMs)) continue;
      rows += 1;
      chars += typeof row.primary?.chars === 'number' ? row.primary.chars : 0;
      if (typeof row.primary?.est_tokens === 'number') { est += row.primary.est_tokens; withEstimate += 1; }
    } catch { /* a torn line */ }
  }
  return rows === 0 ? { chars: null, est: null } : { chars, est: withEstimate === rows ? est : null };
}

function claudeArgs(model: string, wrapper: string): string[] {
  return ['-p', '--model', model, '--output-format', 'stream-json', '--verbose', '--setting-sources', 'project',
    '--settings', JSON.stringify({ disableAllHooks: true }), '--strict-mcp-config', '--tools', 'Bash', '--no-session-persistence',
    '--max-turns', String(evalLimits.maxTurns), '--max-budget-usd', String(evalLimits.maxBudgetUsdPerRun),
    '--allowedTools', `Bash(${wrapper} toc:*)`, `Bash(${wrapper} read:*)`];
}

function codexArgs(model: string | null, cwd: string): string[] {
  return ['exec', '--json', '--skip-git-repo-check', '--ephemeral', '--ignore-user-config', '--sandbox', 'read-only', '-C', cwd, ...(model ? ['-m', model] : []), '-'];
}

function engineCommand(engine: Engine, env: NodeJS.ProcessEnv): string[] { return [(engine === 'claude' ? env.AW_EVAL_CLAUDE_COMMAND : env.AW_EVAL_CODEX_COMMAND)?.trim() || engine]; }

/** Bump when the prompt or the allowed commands change: runs made with the old ones are not reused. */
export const PROMPT_VERSION = 'locate-v3';

export function planSha(plan: Plan): string { return sha256(canonicalJson(plan)); }
export function claimSha(claim: Claim): string { return sha256(claim.text.normalize('NFC')); }

/** What a run is bound to: the plan, the claim's text, the route, the engine, the requested model and the prompt version. */
export function fingerprintOf(parts: { plan_sha256: string; claim_sha256: string; claim_id: string; route: Route; engine: Engine; model_requested: string; prompt_version: string }): string {
  return sha256(canonicalJson(parts));
}

export function modelRequested(options: Pick<RunnerOptions, 'engine' | 'model'>): string {
  return options.engine === 'claude' ? (options.model ?? evalLimits.locateModel) : (options.model ?? 'default');
}

export function expectedFingerprint(options: Pick<RunnerOptions, 'engine' | 'model' | 'plan'>, claim: Claim, route: Route): string {
  return fingerprintOf({
    plan_sha256: planSha(options.plan), claim_sha256: claimSha(claim), claim_id: claim.id, route, engine: options.engine,
    model_requested: modelRequested(options), prompt_version: PROMPT_VERSION,
  });
}

async function locateOnce(options: RunnerOptions, claim: Claim, route: Route, group: ChildGroup): Promise<{ run: Omit<Run, 'attempts'>; missing: boolean }> {
  if (group.stopping) throw new LibraryError('exit', 'ERROR library eval run: interrupted');
  const runId = runIdFor(options.plan.eval_id, route, claim.id);
  const tag = `${runId}.${randomBytes(6).toString('hex')}`;
  const base = await realpath(tmpdir());
  const dir = await mkdtemp(join(base, 'aw-eval-'));
  const started = options.now();
  try {
    const cwd = join(dir, 'work');
    const bin = join(dir, 'bin');
    await mkdir(cwd);
    await mkdir(bin);
    const { wrapper, errorLog } = await writeWrapper(bin, { awCommand: options.awCommand, project: options.project, route, runId, claimId: claim.id, env: options.env });
    const prompt = buildPrompt(options.plan, claim, wrapper);
    const requested = modelRequested(options);
    const model = options.engine === 'claude' ? requested : options.model;
    const env: NodeJS.ProcessEnv = { ...options.env, CLAUDE_CODE_DISABLE_CLAUDE_MDS: '1', [RUN_TAG_ENV]: tag };
    for (const key of ['AW_LIBRARY_ROUTE', 'GOOGLE_API_KEY', 'GEMINI_API_KEY']) delete env[key];
    const [file, ...prefix] = engineCommand(options.engine, options.env) as [string, ...string[]];
    let exit;
    let tracker: TreeTracker | undefined;
    // This attempt's own window in the retrieval ledger (real clock: the rows are stamped by the library commands).
    const fromMs = Date.now();
    const attempt: { tag: string; tracker?: TreeTracker } = { tag };
    group.attempts.add(attempt);
    try {
      exit = await runAgent([file, ...prefix], options.engine === 'claude' ? claudeArgs(model as string, wrapper) : codexArgs(model, cwd), {
        input: prompt, cwd, env, timeoutMs: options.runTimeoutMs, maxBuffer: evalLimits.maxBufferBytes, group,
        tracker: (pid) => { tracker = new TreeTracker(pid); attempt.tracker = tracker; tracker.start(); },
      });
    } finally {
      // The agent's group is gone; the library commands `aw` started run in groups of their own: found by the tag, or by the tree followed while the agent ran.
      await tracker?.stop();
      await reapTagged(tag, tracker);
      group.attempts.delete(attempt);
    }
    const parsed: Parsed = parseAgent(options.engine, exit.stdout);
    const answer = parseAnswer(parsed.text, evalLimits.maxAnswerPages);
    const budget = deriveBudget(parsed.calls, wrapper);
    const returned = await returnedFor(options.project, runId, { fromMs, toMs: Date.now() });
    const violations = commandViolations(parsed.calls, wrapper).slice(0, 5);
    let error: string | null = null;
    if (exit.spawnError === 'missing') error = `the ${options.engine} command was not found`;
    else if (exit.spawnError) error = `could not start ${options.engine}: ${exit.spawnError}`;
    else if (exit.timedOut) error = `timed out after ${Math.round(options.runTimeoutMs / 1000)} s`;
    else if (exit.tooLarge) error = 'the agent printed more than the output limit';
    else if (violations.length > 0) error = 'the agent ran a command that is not on its allowed list';
    else if (!answer) error = parsed.stopReason ? `no answer (${parsed.stopReason})` : (exit.code !== 0 ? `exit ${exit.code ?? 'signal'} and no answer: ${exit.stderr.trim().slice(0, 200)}` : 'no parsable answer');
    else if (!options.plan.shelf.some((book) => book.id === answer.book)) error = 'the answer names a book that is not on the shelf';
    const usd = parsed.costUsd;
    await appendUsage(options.project, {
      run_id: runId, step: 'library.eval.locate', provider: options.engine === 'claude' ? 'claude-code' : 'codex', model: parsed.model ?? model ?? 'default',
      input_tokens: parsed.inputTokens, output_tokens: parsed.outputTokens, cost_usd: usd, latency_ms: exit.wallMs, exit: error ? 'ERROR' : 'OK', same_family: false,
    });
    const run: Omit<Run, 'attempts'> = {
      schema: 1, eval_id: options.plan.eval_id, claim_id: claim.id, route, engine: options.engine, model: parsed.model ?? model ?? 'default',
      status: error ? 'error' : 'ok', started_at: started.toISOString(), answer, tool_calls: parsed.calls.map((call) => call.replaceAll(wrapper, '<wrapper>').slice(0, 400)),
      ...budget, permission_denials: parsed.permissionDenials, wall_ms: exit.wallMs, agent_ms: parsed.agentMs, turns: parsed.turns,
      input_tokens: parsed.inputTokens, output_tokens: parsed.outputTokens, cost_usd: usd, returned_chars: returned.chars, returned_est_tokens: returned.est,
      agent_version: parsed.version, error,
      plan_sha256: planSha(options.plan), claim_sha256: claimSha(claim), prompt_version: PROMPT_VERSION, model_requested: requested,
      fingerprint: expectedFingerprint(options, claim, route), violations, lookup_errors: await lookupErrors(errorLog),
    };
    return { run, missing: exit.spawnError === 'missing' };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

/** Returned text over two attempts: an attempt with no rows adds nothing; one whose rows lack an estimate makes the estimate unknown. */
function sumReturned(a: Pick<Run, 'returned_chars' | 'returned_est_tokens'>, b: Pick<Run, 'returned_chars' | 'returned_est_tokens'>): { chars: number | null; est: number | null } {
  if (a.returned_chars === null && b.returned_chars === null) return { chars: null, est: null };
  const missing = (x: Pick<Run, 'returned_chars' | 'returned_est_tokens'>): boolean => x.returned_chars !== null && x.returned_est_tokens === null;
  return { chars: (a.returned_chars ?? 0) + (b.returned_chars ?? 0), est: missing(a) || missing(b) ? null : (a.returned_est_tokens ?? 0) + (b.returned_est_tokens ?? 0) };
}

/** One claim on one route: up to two attempts, and the totals of time, tokens and cost over both. */
export async function locate(options: RunnerOptions, claim: Claim, route: Route, group: ChildGroup): Promise<Run> {
  let total: Run | null = null;
  let violations: string[] = [];
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    const { run, missing } = await locateOnce(options, claim, route, group);
    if (missing) throw new LibraryError('config', `ERROR library eval run: the ${options.engine} command was not found. The evaluation needs ${options.engine === 'claude' ? 'Claude Code' : 'Codex'} installed on this computer (it cannot run in Cowork).`);
    // A command outside the allowed list on ANY attempt invalidates the run for good: a clean retry never hides it.
    violations = [...new Set([...violations, ...run.violations])].slice(0, 10);
    total = total === null ? { ...run, attempts: 1 } : {
      ...run, attempts: attempt, wall_ms: total.wall_ms + run.wall_ms, input_tokens: total.input_tokens + run.input_tokens, output_tokens: total.output_tokens + run.output_tokens,
      cost_usd: total.cost_usd === null && run.cost_usd === null ? null : (total.cost_usd ?? 0) + (run.cost_usd ?? 0),
      // Each attempt measured its own window; the run's figure is the total over its attempts.
      returned_chars: sumReturned(total, run).chars,
      returned_est_tokens: sumReturned(total, run).est,
      agent_ms: total.agent_ms === null && run.agent_ms === null ? null : (total.agent_ms ?? 0) + (run.agent_ms ?? 0),
    };
    total.violations = violations;
    if (violations.length > 0) {
      total.status = 'error';
      total.error = 'the agent ran a command that is not on its allowed list';
      break;
    }
    if (run.status === 'ok') break;
  }
  return total as Run;
}

/**
 * Run every (claim, route) that has no good run file yet, `parallel` at a time. Resumable: a claim already located
 * (status ok) is skipped; a failed one is tried again (twice) on the next run. Interrupts and fatal errors kill every
 * agent's process group before the error leaves.
 */
export async function runAll(options: RunnerOptions): Promise<RunSummary> {
  // Runs, pairs and judgments are one generation: once pairs exist, runs are never overwritten (a new eval id, or `run --reset`, starts again).
  if (existsSync(options.paths.pairs)) {
    throw new LibraryError('usage', 'ERROR library eval run: pairs already exist for this evaluation, so its runs cannot change. Start a new evaluation with another --eval id, or run again with --reset (the old pairs, judgments and runs are archived first).');
  }
  const jobs: Array<{ claim: Claim; route: Route }> = [];
  let skipped = 0;
  let invalid = 0;
  const invalidSeen: Array<Pick<Run, 'claim_id' | 'violations'>> = [];
  for (const claim of options.plan.claims) {
    for (const route of options.routes) {
      const existing = await readJson(runFile(options.paths, claim.id, route));
      // Reused only when it finished AND is bound to this very plan, claim text, route, engine, model and prompt.
      const current = existing !== null && validate('run', existing).length === 0 && (existing as Run).fingerprint === expectedFingerprint(options, claim, route);
      // A run that ran a forbidden command stays invalid: it is not tried again.
      if (current && (existing as Run).violations.length > 0) { invalid += 1; invalidSeen.push(existing as Run); }
      else if (current && (existing as Run).status === 'ok') skipped += 1;
      else jobs.push({ claim, route });
    }
  }
  const summary: RunSummary = { planned: options.plan.claims.length * options.routes.length, done: 0, skipped, failed: 0, invalid, cost_usd: 0, invalid_runs: [] };
  const group = new ChildGroup();
  const stop = (): void => group.killAll();
  let fatal: unknown = null;
  let interrupted = false;
  // An interrupt stops the agents, waits for the bounded cleanup of everything they started, then exits with the signal's code.
  const onSignal = (signal: NodeJS.Signals): void => {
    if (interrupted) return;
    interrupted = true;
    fatal = new LibraryError('exit', `ERROR library eval run: interrupted by ${signal}`);
    void group.reapAll().finally(() => process.exit(128 + (osConstants.signals[signal] ?? 15)));
  };
  process.once('SIGINT', onSignal);
  process.once('SIGTERM', onSignal);
  process.once('exit', stop);
  let next = 0;
  const worker = async (): Promise<void> => {
    for (;;) {
      if (fatal !== null) return;
      const job = jobs[next];
      next += 1;
      if (!job) return;
      try {
        const run = await locate(options, job.claim, job.route, group);
        await writeJson(runFile(options.paths, job.claim.id, job.route), run);
        summary.cost_usd += run.cost_usd ?? 0;
        if (run.violations.length > 0) { summary.invalid += 1; invalidSeen.push(run); }
        else if (run.status === 'ok') summary.done += 1;
        else summary.failed += 1;
        options.progress(`located ${summary.done + summary.failed + summary.invalid + skipped} of ${summary.planned}`);
      } catch (error) { if (fatal === null) fatal = error; group.killAll(); return; }
    }
  };
  try {
    await Promise.all(Array.from({ length: Math.max(1, Math.min(options.parallel, jobs.length || 1)) }, () => worker()));
  } finally {
    process.removeListener('SIGINT', onSignal);
    process.removeListener('SIGTERM', onSignal);
    process.removeListener('exit', stop);
    group.killAll();
  }
  // The interrupt handler is cleaning up and will end the program with the signal's code: nothing may return or throw first.
  if (interrupted) await new Promise<never>(() => undefined);
  if (fatal !== null) throw fatal;
  summary.cost_usd = Math.round(summary.cost_usd * 10000) / 10000;
  summary.invalid_runs = invalidClaims(invalidSeen);
  return summary;
}
