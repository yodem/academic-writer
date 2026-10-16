import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { appendUsage, readJson, runFile, validate, writeJson, type EvalPaths } from './files.ts';
import { ChildGroup, parseAgent, parseAnswer, runAgent, type Parsed } from './agent.ts';
import { evalLimits } from './limits.ts';
import { LibraryError } from '../types.ts';
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

export type RunSummary = { planned: number; done: number; skipped: number; failed: number; cost_usd: number };

const MAX_ATTEMPTS = 2;

function quote(value: string): string { return `'${value.replace(/'/gu, `'\\''`)}'`; }

export function runIdFor(evalId: string, route: Route, claimId: string): string { return `${evalId}-${route}-${claimId}`; }

/**
 * The one door an agent gets to the library: a shell script that runs `aw library <toc|read ...>` for ONE route
 * (AW_LIBRARY_ROUTE forces it and turns the shadow off) and stamps every call with the run and claim ids, so the
 * retrieval ledger can be joined to this run. Agents see the same two commands whichever route stands behind them.
 */
export function wrapperScript(options: { awCommand: string[]; project: string; route: Route; runId: string; claimId: string; env: NodeJS.ProcessEnv }): string {
  const exported = Object.entries(options.env)
    .filter(([key, value]) => value !== undefined && (key === 'PATH' || (key.startsWith('AW_') && key !== 'AW_LIBRARY_ROUTE')))
    .map(([key, value]) => `${key}=${quote(String(value))}; export ${key}`);
  return [
    '#!/bin/sh',
    ...exported,
    `AW_LIBRARY_ROUTE=${quote(options.route)}; export AW_LIBRARY_ROUTE`,
    `exec ${options.awCommand.map(quote).join(' ')} --project-dir ${quote(options.project)} library "$@" --run ${quote(options.runId)} --claim ${quote(options.claimId)}`,
    '',
  ].join('\n');
}

export function buildPrompt(plan: Plan, claim: Claim, wrapper: string): string {
  const shelf = plan.shelf.map((book) => `- ${book.id}: ${book.title}`).join('\n');
  return `You are a research assistant. A scholar's article makes the claim below, and you must find
the exact page in their library that supports it, so it can be cited.

The scholar's shelf has ${plan.shelf.length} book${plan.shelf.length === 1 ? '' : 's'}:
${shelf}

Claim from the article:
"${claim.text}"

You may only use these shell commands:
${wrapper} toc --source <book id>   # table of contents: section titles with page ranges and short hints
${wrapper} read --source <book id> --pages <a>-<b> --text   # read pages a to b

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

/** Codex cannot be given an allow-list, so check afterwards: every command must be the wrapper (alone or inside `sh -c`). */
export function offListCommands(calls: string[], wrapper: string): string[] {
  const unwrap = (call: string): string => {
    const match = /^(?:\S*\/)?(?:ba|z)?sh\s+-l?c\s+(['"])([\s\S]*)\1\s*$/u.exec(call.trim());
    return (match ? match[2] as string : call).trim();
  };
  return calls.filter((call) => segments([unwrap(call)]).some((part) => !part.startsWith(wrapper)));
}

/** Characters and (when T2's estimate is present) tokens that this run's lookups returned, from the retrieval ledger. */
export async function returnedFor(project: string, runId: string): Promise<{ chars: number | null; est: number | null }> {
  let text: string;
  try { text = await readFile(join(project, '.academic-helper', 'retrieval.jsonl'), 'utf8'); } catch { return { chars: null, est: null }; }
  let chars = 0;
  let est = 0;
  let rows = 0;
  let withEstimate = 0;
  for (const line of text.split('\n')) {
    if (!line.includes(runId)) continue;
    try {
      const row = JSON.parse(line) as { row_type?: string; run_id?: string | null; primary?: { chars?: unknown; est_tokens?: unknown } };
      if (row.row_type !== 'lookup' || row.run_id !== runId) continue;
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

async function locateOnce(options: RunnerOptions, claim: Claim, route: Route, group: ChildGroup): Promise<{ run: Omit<Run, 'attempts'>; missing: boolean }> {
  const runId = runIdFor(options.plan.eval_id, route, claim.id);
  const base = await realpath(tmpdir());
  const dir = await mkdtemp(join(base, 'aw-eval-'));
  const started = options.now();
  try {
    const cwd = join(dir, 'work');
    const bin = join(dir, 'bin');
    await mkdir(cwd);
    await mkdir(bin);
    const wrapper = join(bin, 'awlib');
    await writeFile(wrapper, wrapperScript({ awCommand: options.awCommand, project: options.project, route, runId, claimId: claim.id, env: options.env }), { mode: 0o700 });
    const prompt = buildPrompt(options.plan, claim, wrapper);
    const model = options.engine === 'claude' ? (options.model ?? evalLimits.locateModel) : options.model;
    const env: NodeJS.ProcessEnv = { ...options.env, CLAUDE_CODE_DISABLE_CLAUDE_MDS: '1' };
    for (const key of ['AW_LIBRARY_ROUTE', 'GOOGLE_API_KEY', 'GEMINI_API_KEY']) delete env[key];
    const [file, ...prefix] = engineCommand(options.engine, options.env) as [string, ...string[]];
    const exit = await runAgent([file, ...prefix], options.engine === 'claude' ? claudeArgs(model as string, wrapper) : codexArgs(model, cwd), {
      input: prompt, cwd, env, timeoutMs: options.runTimeoutMs, maxBuffer: evalLimits.maxBufferBytes, group,
    });
    const parsed: Parsed = parseAgent(options.engine, exit.stdout);
    const answer = parseAnswer(parsed.text, evalLimits.maxAnswerPages);
    const budget = deriveBudget(parsed.calls, wrapper);
    const returned = await returnedFor(options.project, runId);
    const offList = options.engine === 'codex' ? offListCommands(parsed.calls, wrapper) : [];
    let error: string | null = null;
    if (exit.spawnError === 'missing') error = `the ${options.engine} command was not found`;
    else if (exit.spawnError) error = `could not start ${options.engine}: ${exit.spawnError}`;
    else if (exit.timedOut) error = `timed out after ${Math.round(options.runTimeoutMs / 1000)} s`;
    else if (exit.tooLarge) error = 'the agent printed more than the output limit';
    else if (offList.length > 0) error = 'the agent ran a command that is not on its allowed list';
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
    };
    return { run, missing: exit.spawnError === 'missing' };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

/** One claim on one route: up to two attempts, and the totals of time, tokens and cost over both. */
export async function locate(options: RunnerOptions, claim: Claim, route: Route, group: ChildGroup): Promise<Run> {
  let total: Run | null = null;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    const { run, missing } = await locateOnce(options, claim, route, group);
    if (missing) throw new LibraryError('config', `ERROR library eval run: the ${options.engine} command was not found. The evaluation needs ${options.engine === 'claude' ? 'Claude Code' : 'Codex'} installed on this computer (it cannot run in Cowork).`);
    total = total === null ? { ...run, attempts: 1 } : {
      ...run, attempts: attempt, wall_ms: total.wall_ms + run.wall_ms, input_tokens: total.input_tokens + run.input_tokens, output_tokens: total.output_tokens + run.output_tokens,
      cost_usd: total.cost_usd === null && run.cost_usd === null ? null : (total.cost_usd ?? 0) + (run.cost_usd ?? 0),
      agent_ms: total.agent_ms === null && run.agent_ms === null ? null : (total.agent_ms ?? 0) + (run.agent_ms ?? 0),
    };
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
  const jobs: Array<{ claim: Claim; route: Route }> = [];
  let skipped = 0;
  for (const claim of options.plan.claims) {
    for (const route of options.routes) {
      const existing = await readJson(runFile(options.paths, claim.id, route));
      if (existing !== null && validate('run', existing).length === 0 && (existing as Run).status === 'ok') skipped += 1;
      else jobs.push({ claim, route });
    }
  }
  const summary: RunSummary = { planned: options.plan.claims.length * options.routes.length, done: 0, skipped, failed: 0, cost_usd: 0 };
  const group = new ChildGroup();
  const stop = (): void => group.killAll();
  const onSignal = (signal: NodeJS.Signals): void => { stop(); process.kill(process.pid, signal); };
  process.once('SIGINT', onSignal);
  process.once('SIGTERM', onSignal);
  process.once('exit', stop);
  let fatal: unknown = null;
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
        if (run.status === 'ok') summary.done += 1; else summary.failed += 1;
        options.progress(`located ${summary.done + summary.failed + skipped} of ${summary.planned}`);
      } catch (error) { fatal = error; group.killAll(); return; }
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
  if (fatal !== null) throw fatal;
  summary.cost_usd = Math.round(summary.cost_usd * 10000) / 10000;
  return summary;
}
