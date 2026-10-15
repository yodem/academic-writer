import { spawn } from 'node:child_process';
import { mkdir, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import { join, resolve, sep } from 'node:path';
import { z } from 'zod';
import thresholds from '../../../thresholds.json' with { type: 'json' };
import { killLiveCommands } from './exec.ts';
import {
  appendRow, clipError, hasProjectFolder, nowIso, readSpool, retrievalDir, RETRIEVAL_DIR, spoolFile, spoolValue, sweepSpool, writeSpool,
  type Agreement, type ShadowRow, type SpooledPages,
} from './ledger.ts';
import { jaccard } from './textmatch.ts';
import { LibraryError, type RouteName } from './types.ts';

const limits = thresholds.library;

/**
 * The shadow: the other route runs quietly on the same request. In `detached` mode (the real one) it is a
 * background worker process that the answering path never waits for and never reads from; `inline` runs the
 * same work in-process after the answer is ready (for tests); `off` runs nothing. Whatever the shadow does,
 * the answer, its exit code and its timing are the answering route's alone.
 */
export type ShadowMode = 'off' | 'inline' | 'detached';

/** AW_LIBRARY_SHADOW=off|inline|detached picks the mode (a test and troubleshooting seam); detached otherwise. */
export function shadowModeFrom(env: NodeJS.ProcessEnv, fallback: ShadowMode = 'detached'): ShadowMode {
  const value = env.AW_LIBRARY_SHADOW?.trim();
  return value === 'off' || value === 'inline' || value === 'detached' ? value : fallback;
}

export const shadowSpecSchema = z.object({
  v: z.literal(1),
  lookup_id: z.string().min(1).max(80),
  run_id: z.string().nullable(),
  claim_id: z.string().nullable(),
  op: z.enum(['list', 'toc', 'read']),
  route: z.enum(['trove', 'pageindex']),
  project: z.string().min(1),
  source: z.string().nullable(),
  pages: z.union([z.literal('all'), z.array(z.number().int().min(1)), z.null()]),
}).strict();
export type ShadowSpec = z.infer<typeof shadowSpecSchema>;

/** What one route call returned, as the ledger records it (and the page texts, for a read). */
export type RouteResult = {
  book: string | null;
  route_pages: string | null;
  bytes: number;
  chars: number;
  text_sha: string | null;
  pages?: Array<{ page: number; text: string }>;
};

export interface ShadowRunner { runShadow(spec: ShadowSpec): Promise<RouteResult> }

export type ShadowHandle = { status: string; settle: () => Promise<void> };
const idle = (status: string): ShadowHandle => ({ status, settle: async () => undefined });

/** killLive: the worker owns its whole process, so at the deadline it may stop every command still running. */
export type WorkerSettings = { timeoutMs: number; primaryWaitMs: number; killLive: boolean };

function positive(value: string | undefined): number | undefined {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : undefined;
}

export function workerSettings(env: NodeJS.ProcessEnv, killLive = false): WorkerSettings {
  return {
    timeoutMs: positive(env.AW_LIBRARY_SHADOW_TIMEOUT_MS) ?? limits.timeoutMs.shadow,
    primaryWaitMs: positive(env.AW_LIBRARY_TIMEOUT_MS) ?? limits.timeoutMs.primary,
    killLive,
  };
}

function sleep(ms: number): Promise<void> { return new Promise((resolveSleep) => { setTimeout(resolveSleep, ms); }); }

// ---------------------------------------------------------------- slots (how many workers may run at once)

const activeDir = (project: string): string => join(retrievalDir(project), 'active');
const lockFile = (project: string, lookupId: string): string => join(activeDir(project), `${lookupId}.lock`);

/** Workers that have started and not reported back; a slot nobody released for shadow.lockStaleMs is dropped. */
async function liveWorkers(project: string, now: number = Date.now()): Promise<number> {
  let count = 0;
  try {
    for (const name of await readdir(activeDir(project))) {
      const file = join(activeDir(project), name);
      try {
        if (now - (await stat(file)).mtimeMs > limits.shadow.lockStaleMs) await rm(file, { force: true });
        else count += 1;
      } catch { /* released meanwhile */ }
    }
  } catch { /* no slots folder yet */ }
  return count;
}

// ---------------------------------------------------------------- starting a shadow (foreground)

/**
 * Start the shadow for one lookup and return at once. Never throws and never waits for the worker: the cost
 * to the caller is one small file write and one spawn. `status` goes into the lookup row.
 */
export async function startShadow(spec: ShadowSpec, mode: ShadowMode, env: NodeJS.ProcessEnv, runner: ShadowRunner): Promise<ShadowHandle> {
  if (mode === 'off') return idle('disabled');
  try {
    if (!(await hasProjectFolder(spec.project))) return idle('skipped:no_project_dir');
    if (mode === 'inline') return { status: 'pending', settle: () => runShadowWorker(spec, runner, workerSettings(env)) };
    if (await liveWorkers(spec.project) >= limits.shadow.maxConcurrent) return idle('skipped:busy');
    const entry = process.argv[1];
    if (!entry) return idle('skipped:spawn_failed');
    const specPath = join(retrievalDir(spec.project), `spec-${spec.lookup_id}.json`);
    try {
      await mkdir(activeDir(spec.project), { recursive: true });
      await writeFile(specPath, JSON.stringify(spec), 'utf8');
      await writeFile(lockFile(spec.project, spec.lookup_id), '', 'utf8');
      const child = spawn(process.execPath, [entry, 'library', '_shadow', specPath], { detached: true, stdio: 'ignore', windowsHide: true, env });
      child.on('error', () => undefined);
      child.unref();
    } catch (error) {
      await rm(specPath, { force: true });
      await rm(lockFile(spec.project, spec.lookup_id), { force: true });
      throw error;
    }
    return idle('pending');
  } catch {
    return idle('skipped:spawn_failed');
  }
}

// ---------------------------------------------------------------- the worker (background)

/** Read a worker spec file and delete it. The file must sit in the project's own retrieval folder. */
export async function loadSpec(path: string): Promise<ShadowSpec | null> {
  try {
    const parsed = shadowSpecSchema.safeParse(JSON.parse(await readFile(path, 'utf8')));
    if (!parsed.success) return null;
    const inside = resolve(path).startsWith(`${resolve(parsed.data.project, RETRIEVAL_DIR)}${sep}`);
    return inside ? parsed.data : null;
  } catch { return null; } finally {
    await rm(path, { force: true });
  }
}

const round3 = (value: number): number => Math.round(value * 1000) / 1000;

/** Page by page word overlap of the answering route's text with the shadow's, on the shared (Trove) page numbers. */
export function compareRoutes(primary: SpooledPages, shadowPages: Array<{ page: number; text: string }>): Agreement | null {
  if (primary.ok === false || primary.too_large) return null;
  const shadowByPage = new Map(shadowPages.map((entry) => [entry.page, entry.text]));
  const entries = primary.pages.map((entry) => {
    const other = shadowByPage.get(entry.page);
    const overlap = other === undefined ? 0 : jaccard(entry.text, other);
    return { page: entry.page, jaccard: round3(overlap), agree: other !== undefined && overlap >= limits.agree.jaccardMin };
  });
  const agreed = entries.filter((entry) => entry.agree).length;
  return { rate: entries.length === 0 ? null : round3(agreed / entries.length), compared: entries.length, agreed, pages: entries.slice(0, limits.ledger.maxAgreePages) };
}

async function waitForPrimary(spec: ShadowSpec, started: number, settings: WorkerSettings): Promise<SpooledPages | null> {
  const file = spoolFile(spec.project, spec.lookup_id, 'primary');
  for (;;) {
    const found = await readSpool(file);
    if (found) return found;
    if (Date.now() - started >= settings.primaryWaitMs) return null;
    await sleep(limits.shadow.pollMs);
  }
}

/**
 * The shadow worker body: make the same request on the other route, keep its page text in the spool, compare
 * it with the answering route's text and write one `shadow` row. Never throws; a hang is cut off at the
 * shadow timeout and recorded as `timed_out`.
 */
export async function runShadowWorker(spec: ShadowSpec, runner: ShadowRunner, settings: WorkerSettings): Promise<void> {
  const started = Date.now();
  let result: RouteResult | null = null;
  let failure: unknown = null;
  let timedOut = false;
  let timer: NodeJS.Timeout | undefined;
  try {
    await sweepSpool(spec.project);
    const call = runner.runShadow(spec);
    call.catch(() => undefined);
    const deadline = new Promise<'timeout'>((resolveDeadline) => { timer = setTimeout(() => { resolveDeadline('timeout'); }, settings.timeoutMs); });
    try {
      const outcome = await Promise.race([call, deadline]);
      if (outcome === 'timeout') { timedOut = true; if (settings.killLive) killLiveCommands(); } else result = outcome;
    } catch (error) {
      failure = error;
      timedOut = error instanceof LibraryError && error.code === 'timeout';
    }
    clearTimeout(timer);
    const latency = Date.now() - started;
    let agree: Agreement | null = null;
    if (spec.op === 'read' && result?.pages) {
      await writeSpool(spec.project, spoolFile(spec.project, spec.lookup_id, 'shadow'), spoolValue(spec.lookup_id, { route: spec.route, ok: true }, result.pages));
      const primary = await waitForPrimary(spec, started, settings);
      agree = primary ? compareRoutes(primary, result.pages) : null;
    }
    const code = failure instanceof LibraryError ? failure.code : (failure ? 'error' : null);
    const row: ShadowRow = {
      row_type: 'shadow',
      schema: 1,
      ts: nowIso(),
      lookup_id: spec.lookup_id,
      run_id: spec.run_id,
      route: spec.route,
      ok: result !== null,
      book: result?.book ?? null,
      route_pages: result?.route_pages ?? null,
      latency_ms: latency,
      bytes: result?.bytes ?? 0,
      chars: result?.chars ?? 0,
      text_sha: result?.text_sha ?? null,
      error: result ? null : clipError(timedOut && !failure ? `${spec.route} did not answer within ${settings.timeoutMs} ms` : (failure instanceof Error ? failure.message : String(failure ?? 'no answer'))),
      error_code: result ? null : (timedOut ? 'timeout' : code),
      timed_out: timedOut,
      agree,
    };
    await appendRow(spec.project, row);
  } catch {
    // The shadow can never fail the caller, and has nobody to tell: its row is simply missing.
  } finally {
    clearTimeout(timer);
    await rm(lockFile(spec.project, spec.lookup_id), { force: true });
    await rm(spoolFile(spec.project, spec.lookup_id, 'primary'), { force: true });
  }
}
