import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import thresholds from '../../../thresholds.json' with { type: 'json' };
import type { LedgerRow } from '../ledger.ts';
import { PLAIN_ID, TroveBackend } from './backends.ts';
import { loadLibraryConfig, type LibraryConfig, type PageindexSource } from './config.ts';
import { appendUsage } from './eval/files.ts';
import { runCommand } from './exec.ts';
import { childEnv, geminiKeyFrom } from './install.ts';
import { redact } from './redact.ts';
import { LibraryError } from './types.ts';

const limits = thresholds.library;
export const INDEX_STEP = 'library.index';

export type SummaryMode = 'gemini' | 'hints' | 'none';
export const SUMMARY_MODES: readonly SummaryMode[] = ['gemini', 'hints', 'none'];

// ---------------------------------------------------------------- one place that knows how to reach the PageIndex command

export type Indexer = {
  project: string;
  config: LibraryConfig;
  /** The PageIndex command (the built-in helper, a wrapper, or pilib on the path). */
  command: string[];
  source: PageindexSource;
  /** The environment aw itself was started with: only read here, never passed on as it is. */
  env: NodeJS.ProcessEnv;
  now: () => Date;
  capable?: Promise<void>;
};

export function makeIndexer(project: string, env: NodeJS.ProcessEnv = process.env, now: () => Date = () => new Date()): Indexer {
  const config = loadLibraryConfig(project, env);
  return { project, config, command: config.pageindexCommand, source: config.pageindexSource, env, now };
}

/**
 * The environment of the PageIndex command. Secrets are removed. The Gemini key goes in (as GEMINI_API_KEY, in this child's
 * environment only) just for the built-in helper writing summaries; a command the researcher supplied (an ssh wrapper) uses
 * whatever key it holds on its own side, so the plugin never forwards one.
 */
export function pageindexEnv(indexer: Indexer, summaries: SummaryMode): NodeJS.ProcessEnv {
  const key = indexer.source === 'installed' && summaries === 'gemini' ? geminiKeyFrom(indexer.env) : null;
  return childEnv(indexer.env, { gemini: key });
}

// ---------------------------------------------------------------- running a command and keeping its stdout even when it fails

export type Captured = { code: number | null; stdout: string; stderr: string; timedOut: boolean; spawnError: string | null };

/** Like runCommand, but a non-zero exit still returns what was printed: pilib's index failures are a JSON object on stdout. */
export function runCapture(command: string[], args: string[], options: { timeoutMs: number; maxBuffer: number; env: NodeJS.ProcessEnv; cwd?: string }): Promise<Captured> {
  const [file, ...prefix] = command;
  if (!file) return Promise.reject(new LibraryError('config', 'ERROR library: empty command'));
  return new Promise<Captured>((resolve) => {
    let settled = false;
    let stdout = '';
    let stderr = '';
    let bytes = 0;
    const posix = process.platform !== 'win32';
    const child = spawn(file, [...prefix, ...args], { stdio: ['ignore', 'pipe', 'pipe'], env: options.env, cwd: options.cwd, detached: posix, windowsHide: true });
    const kill = (): void => { try { if (posix && child.pid) process.kill(-child.pid, 'SIGKILL'); else child.kill('SIGKILL'); } catch { try { child.kill('SIGKILL'); } catch { /* already gone */ } } };
    const done = (value: Captured): void => { if (settled) return; settled = true; clearTimeout(timer); resolve(value); };
    const timer = setTimeout(() => { kill(); child.stdout?.destroy(); child.stderr?.destroy(); done({ code: null, stdout, stderr, timedOut: true, spawnError: null }); }, options.timeoutMs);
    child.stdout?.setEncoding('utf8').on('data', (chunk: string) => {
      bytes += Buffer.byteLength(chunk);
      if (bytes > options.maxBuffer) { kill(); done({ code: null, stdout, stderr: `${stderr}\noutput larger than ${options.maxBuffer} bytes`, timedOut: false, spawnError: null }); return; }
      stdout += chunk;
    });
    child.stderr?.setEncoding('utf8').on('data', (chunk: string) => { if (stderr.length < 8192) stderr += chunk; });
    child.on('error', (error: NodeJS.ErrnoException) => done({ code: null, stdout, stderr, timedOut: false, spawnError: error.code === 'ENOENT' ? `command not found: ${file}` : error.message }));
    child.on('close', (code) => done({ code, stdout, stderr, timedOut: false, spawnError: null }));
  });
}

function lastJson(text: string): Record<string, unknown> | null {
  const line = text.trim().split('\n').filter(Boolean).at(-1);
  if (!line) return null;
  try { const value: unknown = JSON.parse(line); return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null; } catch { return null; }
}

// ---------------------------------------------------------------- plain-language errors (what a researcher reads)

const PLAIN: Record<string, (detail: string) => string> = {
  trove_failed: (detail) => `Trove could not be read for this book${detail ? ` (${detail})` : ''}. The upload to Trove is not affected; try indexing again once Trove answers.`,
  trove_truncated: () => 'Trove would not hand over this whole book in one read, so it cannot be indexed yet. The copy in Trove is fine.',
  no_hinted_toc: () => 'This book has no table of contents with hints, and the structure fallback was switched off, so nothing was indexed.',
  structure_helper_missing: () => 'This book has no table of contents with hints, and the full helper that finds the structure by itself is not installed here. Install the full helper (needs Python 3.10 or newer), or use a computer that has it.',
  core_helper_missing: () => 'The summary helper is not installed. Install the built-in helper, or index without Gemini summaries.',
  missing_key: () => 'No Google (Gemini) key is available for the summaries. Add your Google key in the plugin settings, or index without summaries.',
  call_cap: (detail) => `Stopped at the limit of Gemini calls${detail ? ` (${detail})` : ''}. The summaries written so far are kept; run it again to continue.`,
  model_failed: (detail) => `Gemini did not answer${detail ? ` (${detail})` : ''}. Check the key, the model name and the connection.`,
  bad_input: (detail) => `An option or the book name was not accepted${detail ? `: ${detail}` : ''}.`,
  empty_book: () => 'This book has no pages in Trove, so there is nothing to index.',
  no_toc: () => 'This book has no usable table of contents entries, so no outline could be built.',
  render_failed: (detail) => `The text of this book could not be turned into a PDF for the structure check${detail ? ` (${detail})` : ''}. The Trove copy is fine.`,
  structure_failed: (detail) => `PageIndex stopped while reading the structure of the book${detail ? ` (${detail})` : ''}.`,
  empty_tree: () => 'PageIndex found no structure in this book.',
  busy: () => 'This book is being indexed by another process right now; try again when it finishes.',
  internal: (detail) => `The indexing helper stopped unexpectedly${detail ? ` (${detail})` : ''}. Please report it.`,
  read_back_failed: (detail) => `The book was indexed, but the check afterwards found a problem${detail ? `: ${detail}` : ''}. Trove is not affected; run the index again.`,
};

export function plainFailure(code: string, detail: string): string {
  const clean = redact(detail).replace(/\s+/gu, ' ').trim().slice(0, 240);
  return (PLAIN[code] ?? PLAIN.internal as (detail: string) => string)(clean);
}

const OLD_COMMAND = 'The PageIndex command found here is older than this plugin: it cannot index books (it has no index-trove step) and it cannot read books indexed by the built-in helper. Install the built-in helper (aw library install), or update pilib on the computer that holds your library.';

/** The up-front check that the resolved command can index at all. Refuses with a plain message; never changes anything. */
export function ensureCanIndex(indexer: Indexer): Promise<void> {
  indexer.capable ??= (async (): Promise<void> => {
    const result = await runCapture(indexer.command, ['index-trove', '--help'], { timeoutMs: limits.index.probeTimeoutMs, maxBuffer: 1048576, env: pageindexEnv(indexer, 'none'), cwd: indexer.project });
    if (result.code === 0) return;
    if (result.spawnError) {
      const text = indexer.source === 'default'
        ? 'No PageIndex command is set up on this computer. Install the built-in helper (aw library install), or set your own command in the plugin settings.'
        : `The PageIndex command could not be started (${redact(result.spawnError)}). Check the plugin setting or install the built-in helper (aw library install).`;
      throw new LibraryError('config', `ERROR library index: ${text}`);
    }
    if (result.timedOut) throw new LibraryError('timeout', 'ERROR library index: the PageIndex command did not answer in time; check that it is reachable.');
    if (/invalid choice|unrecognized|usage:/iu.test(result.stderr)) throw new LibraryError('config', `ERROR library index: ${OLD_COMMAND}`);
    throw new LibraryError('exit', `ERROR library index: the PageIndex command failed its start-up check (${redact(result.stderr).replace(/\s+/gu, ' ').trim().slice(0, 200)}).`);
  })();
  return indexer.capable;
}

// ---------------------------------------------------------------- one book

export type IndexRequest = {
  troveId: string;
  bookId?: string;
  summaries: SummaryMode;
  noFallback: boolean;
  maxCalls?: number;
  model?: string;
  concurrency?: number;
  dryRun: boolean;
  /** The researcher agreed to a large Gemini bill; without it a run stops at askAboveCalls model calls. */
  yes: boolean;
  /** The usage-ledger run this row belongs to. */
  run: string;
  verify: boolean;
};

export type ReadBack = { ok: boolean; trove_compared: boolean; checks: Record<string, boolean | string>; problems: string[] };

export type IndexOutcome = {
  ok: boolean;
  code: string | null;
  /** Plain words for a person. */
  message: string | null;
  needs_yes: boolean;
  result: Record<string, unknown>;
  read_back: ReadBack | null;
  ledger_recorded: boolean;
};

// The fields of pilib's answer that are passed on. Anything else (a future field, an echo of the environment) never reaches the output.
const RESULT_FIELDS = ['dry_run', 'book_id', 'trove_id', 'title', 'source', 'fallback', 'summaries', 'model', 'n_pages', 'toc_entries', 'hinted_entries', 'nodes', 'nodes_with_summary',
  'summaries_reused', 'summaries_generated', 'summary_failures', 'expected_calls', 'input_chars', 'calls', 'failures', 'prompt_tokens', 'completion_tokens', 'reasoning_tokens', 'cost_usd',
  'cost_unknown_calls', 'call_cap', 'seconds', 'library', 'indexed_at', 'warnings'] as const;

function pick(source: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const field of RESULT_FIELDS) if (field in source) out[field] = source[field];
  if (Array.isArray(out.warnings)) out.warnings = out.warnings.map((entry) => redact(String(entry)).slice(0, 300));
  return out;
}

/** Whitespace squeezed, nothing else changed: a page read back must be Trove's page, letter for letter. */
function squash(text: string): string { return text.replace(/\s+/gu, ' ').trim(); }

function count(value: unknown): number { return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? Math.round(value) : 0; }

/** A fresh usage-ledger run id: `<prefix>-<date and time>-<4 hex digits>` (letters, digits and hyphens only). */
export function newRunId(now: Date, prefix: string = 'index'): string {
  return `${prefix}-${now.toISOString().slice(0, 19).replace(/[-:T]/gu, '')}-${randomBytes(2).toString('hex')}`;
}

/** The effective cap on model calls: the request's (or the default), and without --yes never above askAboveCalls. */
export function callCap(request: Pick<IndexRequest, 'maxCalls' | 'yes' | 'summaries'>): number {
  const wanted = request.maxCalls ?? limits.index.maxCalls;
  return request.summaries === 'gemini' && !request.yes ? Math.min(wanted, limits.index.askAboveCalls) : wanted;
}

async function recordUsage(indexer: Indexer, request: IndexRequest, result: Record<string, unknown>, ok: boolean, code: string | null, wallMs: number): Promise<boolean> {
  const calls = count(result.calls);
  const unpriced = count(result.cost_unknown_calls);
  const cost = typeof result.cost_usd === 'number' && result.cost_usd >= 0 && !(calls > 0 && unpriced >= calls) ? result.cost_usd : null;
  const model = typeof result.model === 'string' && result.model ? result.model : (request.summaries === 'gemini' ? (request.model ?? limits.index.summaryModel) : 'none');
  const seconds = typeof result.seconds === 'number' ? result.seconds * 1000 : wallMs;
  const row: LedgerRow = {
    run_id: request.run, step: INDEX_STEP, provider: request.summaries === 'gemini' ? 'gemini' : 'pilib', model,
    input_tokens: count(result.prompt_tokens), output_tokens: count(result.completion_tokens), cost_usd: cost,
    latency_ms: Math.max(0, Math.round(Math.max(seconds, wallMs))), exit: ok ? 'OK' : (code === 'call_cap' ? 'CAP_REACHED' : 'ERROR'), same_family: false,
  };
  return appendUsage(indexer.project, row);
}

/**
 * Index one Trove book through the PageIndex command and prove it: read the book back (meta, tree, pages 1..N against Trove)
 * and append a usage-ledger row. Never throws for a problem with the book (it returns a failed outcome); throws LibraryError
 * only when the command cannot run at all (usage 2, config 3).
 */
export async function indexBook(indexer: Indexer, request: IndexRequest): Promise<IndexOutcome> {
  if (!PLAIN_ID.test(request.troveId)) throw new LibraryError('usage', 'ERROR library index: --trove-id must be a plain id (letters, digits and . _ # : - only)');
  if (request.bookId !== undefined && !PLAIN_ID.test(request.bookId)) throw new LibraryError('usage', 'ERROR library index: --book-id must be a plain id (letters, digits and . _ # : - only)');
  if (!SUMMARY_MODES.includes(request.summaries)) throw new LibraryError('usage', 'ERROR library index: --summaries must be gemini, hints or none');
  if (request.model !== undefined && !/^[A-Za-z0-9._/:-]{1,80}$/u.test(request.model)) throw new LibraryError('usage', 'ERROR library index: --model must be a plain model name');
  await ensureCanIndex(indexer);
  // The Gemini key goes only to the real indexing call: not the start-up probe, the read-back or a dry run.
  const env = pageindexEnv(indexer, request.dryRun ? 'none' : request.summaries);
  // Fail before any call when the built-in helper has no key to give: the helper would fail the same way, after reading Trove.
  if (request.summaries === 'gemini' && indexer.source === 'installed' && !request.dryRun && geminiKeyFrom(indexer.env) === null) {
    return { ok: false, code: 'missing_key', message: plainFailure('missing_key', ''), needs_yes: false, result: { trove_id: request.troveId }, read_back: null, ledger_recorded: false };
  }
  const cap = callCap(request);
  const args = ['index-trove', request.troveId, '--summaries', request.summaries, '--max-calls', String(cap),
    ...(request.bookId ? ['--book-id', request.bookId] : []), ...(request.noFallback ? ['--no-fallback'] : []),
    ...(request.model ? ['--model', request.model] : []), ...(request.concurrency ? ['--concurrency', String(request.concurrency)] : []), ...(request.dryRun ? ['--dry-run'] : [])];
  const started = Date.now();
  const captured = await runCapture(indexer.command, args, { timeoutMs: limits.index.timeoutMs, maxBuffer: limits.maxBufferBytes, env, cwd: indexer.project });
  const wall = Date.now() - started;
  if (captured.timedOut) throw new LibraryError('timeout', `ERROR library index: the PageIndex command did not finish within ${Math.round(limits.index.timeoutMs / 60000)} minutes and was stopped. The Trove copy is fine; run it again to continue (summaries already written are kept).`);
  if (captured.spawnError) throw new LibraryError('config', `ERROR library index: the PageIndex command could not be started (${redact(captured.spawnError)}).`);
  const answer = lastJson(captured.stdout);
  if (answer === null) {
    if (/invalid choice|unrecognized/iu.test(captured.stderr)) throw new LibraryError('config', `ERROR library index: ${OLD_COMMAND}`);
    const tail = redact(captured.stderr).replace(/\s+/gu, ' ').trim().slice(-200);
    return { ok: false, code: 'internal', message: plainFailure('internal', tail || `exit ${captured.code ?? 'signal'}`), needs_yes: false, result: { trove_id: request.troveId }, read_back: null, ledger_recorded: false };
  }
  const result = pick(answer);
  if (answer.ok !== true || captured.code !== 0) {
    const code = typeof answer.code === 'string' ? answer.code : 'internal';
    const ledger = request.dryRun ? false : await recordUsage(indexer, request, answer, false, code, wall);
    const needsYes = code === 'call_cap' && !request.yes && request.summaries === 'gemini' && cap === limits.index.askAboveCalls;
    const detail = typeof answer.error === 'string' ? answer.error : '';
    const base = plainFailure(code, code === 'call_cap' ? `${cap} calls` : detail);
    return { ok: false, code, message: needsYes ? `${base} This book needs more than ${limits.index.askAboveCalls} Gemini calls: ask the researcher, then run it again with --yes.` : base, needs_yes: needsYes, result: { ...pick(answer), trove_id: request.troveId }, read_back: null, ledger_recorded: ledger };
  }
  if (request.dryRun) return { ok: true, code: null, message: null, needs_yes: false, result, read_back: null, ledger_recorded: false };
  const readBack = request.verify ? await verifyBook(indexer, request, result) : null;
  const ledger = await recordUsage(indexer, request, answer, readBack === null || readBack.ok, readBack && !readBack.ok ? 'read_back_failed' : null, wall);
  if (readBack && !readBack.ok) return { ok: false, code: 'read_back_failed', message: plainFailure('read_back_failed', readBack.problems.join('; ')), needs_yes: false, result, read_back: readBack, ledger_recorded: ledger };
  return { ok: true, code: null, message: null, needs_yes: false, result, read_back: readBack, ledger_recorded: ledger };
}

// ---------------------------------------------------------------- read-back

type TreeNode = { start_index?: unknown; end_index?: unknown; summary?: unknown; prefix_summary?: unknown; nodes?: unknown };

function walkTree(nodes: unknown, visit: (node: TreeNode) => void): void {
  if (!Array.isArray(nodes)) return;
  for (const entry of nodes) {
    if (typeof entry !== 'object' || entry === null) continue;
    visit(entry as TreeNode);
    walkTree((entry as TreeNode).nodes, visit);
  }
}

export async function pilibJson(indexer: Indexer, args: string[]): Promise<Record<string, unknown> | null> {
  try {
    const out = await runCommand(indexer.command, args, { timeoutMs: limits.timeoutMs.primary, maxBuffer: limits.maxBufferBytes, env: pageindexEnv(indexer, 'none'), cwd: indexer.project });
    return lastJson(out);
  } catch { return null; }
}

/**
 * Read the book back through the same command the researcher's articles will use and compare it with what pilib reported and with
 * Trove: the book's record (pages, Trove id), the outline (every range inside the book, every node counted, summaries present), and the first
 * pages (equal to Trove's). Trove not answering here is a note, not a failure: the library may sit on another computer.
 */
export async function verifyBook(indexer: Indexer, request: IndexRequest, result: Record<string, unknown>): Promise<ReadBack> {
  const bookId = typeof result.book_id === 'string' ? result.book_id : (request.bookId ?? request.troveId);
  const problems: string[] = [];
  const checks: Record<string, boolean | string> = {};
  const pages = count(result.n_pages);
  const meta = await pilibJson(indexer, ['meta', bookId]);
  checks.meta = meta !== null && count(meta.n_pages) === pages && (meta.trove_id === undefined || meta.trove_id === null || meta.trove_id === request.troveId);
  if (!checks.meta) problems.push(meta === null ? 'the book cannot be read back from the library' : `the library says ${count(meta.n_pages)} pages, the index run said ${pages}`);
  const tree = await pilibJson(indexer, ['tree', bookId]);
  let nodes = 0;
  let outOfRange = 0;
  let summarised = 0;
  walkTree(tree?.structure, (node) => {
    nodes += 1;
    const start = node.start_index;
    const end = node.end_index;
    if (!(typeof start === 'number' && typeof end === 'number' && Number.isInteger(start) && Number.isInteger(end) && start >= 1 && start <= end && end <= pages)) outOfRange += 1;
    if (String(node.summary ?? node.prefix_summary ?? '').trim()) summarised += 1;
  });
  const shortened = tree !== null && typeof tree.note === 'string';
  checks.tree = tree !== null && nodes > 0 && outOfRange === 0 && (shortened || nodes === count(result.nodes));
  if (tree === null || nodes === 0) problems.push('the outline cannot be read back');
  else {
    if (outOfRange > 0) problems.push(`${outOfRange} outline entries point outside the book`);
    if (!shortened && nodes !== count(result.nodes)) problems.push(`the outline has ${nodes} entries, the index run said ${count(result.nodes)}`);
  }
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];
  if (result.source === 'trove-toc' && warnings.length === 0 && count(result.nodes) !== count(result.toc_entries)) { checks.toc_entries = false; problems.push(`the outline has ${count(result.nodes)} entries but Trove's table of contents has ${count(result.toc_entries)}`); }
  if (result.summaries === 'gemini' || result.summaries === 'hints') {
    // What was read back counts, not what the run claimed; a shortened tree view (a very large book) falls back to the run's own count.
    const have = shortened || nodes === 0 ? count(result.nodes_with_summary) : summarised;
    const of = shortened || nodes === 0 ? count(result.nodes) : nodes;
    const share = of === 0 ? 0 : have / of;
    checks.summaries = `${Math.round(share * 100)}%`;
    if (share < limits.index.minSummaryShare) problems.push(`only ${Math.round(share * 100)}% of the outline entries carry a summary (at least ${Math.round(limits.index.minSummaryShare * 100)}% expected)`);
    if (!shortened && nodes > 0 && Math.abs(summarised - count(result.nodes_with_summary)) > Math.max(1, Math.round(nodes * 0.05))) problems.push('the summaries read back do not match the index run');
  }
  const wanted = Array.from({ length: Math.min(limits.index.verifyPages, pages) }, (_, index) => index + 1);
  const spec = wanted.length === 0 ? '' : `${wanted[0]}-${wanted[wanted.length - 1]}`;
  const read = wanted.length === 0 ? null : await pilibJson(indexer, ['read', bookId, spec, '--json']);
  const got = Array.isArray(read?.pages) ? read.pages as Array<{ page?: unknown; content?: unknown }> : [];
  checks.pages = wanted.length > 0 && got.length === wanted.length && got.every((entry) => typeof entry.content === 'string' && entry.content.trim() !== '');
  if (!checks.pages) problems.push('the first pages cannot be read back from the library');
  let troveCompared = false;
  if (checks.pages && wanted.length > 0) {
    try {
      const trove = new TroveBackend({ command: indexer.config.troveCommand, env: childEnv(indexer.env, { kind: 'trove' }), timeoutMs: limits.timeoutMs.primary, cwd: indexer.project });
      const theirs = await trove.read(request.troveId, wanted);
      troveCompared = true;
      const byPage = new Map(theirs.pages.map((entry) => [entry.page, squash(entry.text)]));
      const same = got.every((entry) => byPage.get(Number(entry.page)) === squash(String(entry.content)));
      checks.trove_pages = same;
      if (!same) problems.push('the first pages in the library differ from the pages in Trove');
    } catch { checks.trove_pages = 'not compared (Trove did not answer here)'; }
  }
  return { ok: problems.length === 0, trove_compared: troveCompared, checks, problems };
}

/** The JSON a successful or failed `aw library index` prints. */
export function indexOutput(indexer: Indexer, outcome: IndexOutcome, request: IndexRequest): Record<string, unknown> {
  return {
    ok: outcome.ok, command: 'library index', ...(outcome.code ? { code: outcome.code } : {}), ...(outcome.message ? { error: outcome.message } : {}),
    ...(outcome.needs_yes ? { needs_yes: true } : {}), ...outcome.result, pageindex_source: indexer.source,
    ...(outcome.read_back ? { read_back: outcome.read_back } : {}),
    ...(request.dryRun ? {} : { ledger: { run_id: request.run, step: INDEX_STEP, recorded: outcome.ledger_recorded } }),
  };
}
