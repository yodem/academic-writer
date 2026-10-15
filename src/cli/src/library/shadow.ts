import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { mkdir, open, readFile, realpath, rm, stat } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { z } from 'zod';
import thresholds from '../../../thresholds.json' with { type: 'json' };
import { CommandScope } from './exec.ts';
import {
  appendRow, clipError, containedDir, hasProjectFolder, nowIso, readSpool, removeSpool, spoolFile, spoolValue, sweepSpool, writeSpool,
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
  lookup_id: z.string().regex(/^[A-Za-z0-9_-]{1,80}$/u),
  run_id: z.string().nullable(),
  claim_id: z.string().nullable(),
  op: z.enum(['list', 'toc', 'read']),
  route: z.enum(['trove', 'pageindex']),
  project: z.string().min(1),
  source: z.string().nullable(),
  pages: z.union([z.literal('all'), z.array(z.number().int().min(1)), z.null()]),
  /** The worker slot this lookup holds (released when the worker ends), or null for none. */
  slot: z.number().int().min(0).nullable(),
  /** The token of that slot: only its holder may claim or release it. */
  slot_nonce: z.string().regex(/^[0-9a-f]{16,64}$/u).nullable().optional(),
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

/** Runs the shadow's request; every command it starts belongs to `scope`, so the worker can stop them all. */
export interface ShadowRunner { runShadow(spec: ShadowSpec, scope?: CommandScope): Promise<RouteResult> }

export type ShadowHandle = { status: string; settle: () => Promise<void> };
/** A shadow that did not start (or is not wanted); `status` says why. */
export const noShadow = (status: string): ShadowHandle => ({ status, settle: async () => undefined });
const idle = noShadow;

export type WorkerSettings = { timeoutMs: number; primaryWaitMs: number };

function positive(value: string | undefined): number | undefined {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : undefined;
}

export function workerSettings(env: NodeJS.ProcessEnv): WorkerSettings {
  return {
    timeoutMs: positive(env.AW_LIBRARY_SHADOW_TIMEOUT_MS) ?? limits.timeoutMs.shadow,
    primaryWaitMs: positive(env.AW_LIBRARY_TIMEOUT_MS) ?? limits.timeoutMs.primary,
  };
}

function sleep(ms: number): Promise<void> { return new Promise((resolveSleep) => { setTimeout(resolveSleep, ms); }); }

// ---------------------------------------------------------------- slots (how many workers may run at once)

/**
 * A fixed set of slot files, `slot-0.lock` .. `slot-<max-1>.lock`, each made with an exclusive create
 * (O_EXCL) that writes the holder's token: its pid, a random nonce and the time. The limit holds because
 * two lookups can never create the same file. Ownership is by token: claim and release act only on a slot
 * that still holds the caller's nonce, so a late parent or worker can never free or overwrite a slot that
 * has since passed to someone else. A slot is reaped only when its recorded pid is dead (or nobody released
 * it for shadow.lockStaleMs), the token is re-read right before unlinking, and reaping is serialised by a
 * `.reap` folder.
 */
export type Slot = { slot: number; nonce: string };
type SlotToken = { pid: number; nonce: string; ts: string };

const slotFile = (dir: string, slot: number): string => join(dir, `slot-${slot}.lock`);

function pidAlive(pid: number): boolean {
  try { process.kill(pid, 0); return true; } catch (error) { return (error as NodeJS.ErrnoException).code === 'EPERM'; }
}

async function readToken(file: string): Promise<SlotToken | null> {
  try {
    const parsed: unknown = JSON.parse(await readFile(file, 'utf8'));
    const record = typeof parsed === 'object' && parsed !== null ? parsed as Partial<SlotToken> : {};
    return typeof record.pid === 'number' && typeof record.nonce === 'string' ? { pid: record.pid, nonce: record.nonce, ts: String(record.ts ?? '') } : null;
  } catch { return null; }
}

async function slotIsStale(file: string, now: number): Promise<SlotToken | 'unreadable' | null> {
  try {
    const age = now - (await stat(file)).mtimeMs;
    const token = await readToken(file);
    if (age > limits.shadow.lockStaleMs) return token ?? 'unreadable';
    if (age < limits.shadow.reapGraceMs || !token) return null;
    return pidAlive(token.pid) ? null : token;
  } catch { return null; }
}

// Accepted limit: between re-reading a stale slot's token and unlinking it, a slot can change hands, so under
// an unlucky interleaving one extra worker may run for a short while. maxConcurrent is a soft load cap for
// best-effort background shadows; the worst case never touches the answering route's result or the
// ledger's correctness.
async function reapSlots(dir: string): Promise<void> {
  const guard = join(dir, '.reap');
  try {
    await mkdir(guard);
  } catch {
    // Someone else is reaping; a reaper that died leaves the guard behind, so an old guard is cleared.
    try { if (Date.now() - (await stat(guard)).mtimeMs > limits.shadow.reapGraceMs * 5) await rm(guard, { recursive: true, force: true }); } catch { /* gone */ }
    return;
  }
  try {
    const now = Date.now();
    for (let slot = 0; slot < limits.shadow.maxConcurrent; slot += 1) {
      const file = slotFile(dir, slot);
      const judged = await slotIsStale(file, now);
      if (judged === null) continue;
      // Re-read the token just before unlinking: if the slot changed hands since, leave it alone.
      const current = await readToken(file);
      if (judged === 'unreadable' ? current === null : current?.nonce === judged.nonce) await rm(file, { force: true });
    }
  } finally { await rm(guard, { recursive: true, force: true }); }
}

/** Take a free worker slot, or null when all of shadow.maxConcurrent are held (or the project folder is not usable). */
export async function acquireSlot(project: string): Promise<Slot | null> {
  try {
    const dir = await containedDir(project, ['retrieval', 'active'], true);
    if (!dir) return null;
    await reapSlots(dir);
    const nonce = randomBytes(12).toString('hex');
    for (let slot = 0; slot < limits.shadow.maxConcurrent; slot += 1) {
      try {
        const handle = await open(slotFile(dir, slot), 'wx', 0o644);
        try { await handle.writeFile(JSON.stringify({ pid: process.pid, nonce, ts: nowIso() } satisfies SlotToken), 'utf8'); } finally { await handle.close(); }
        return { slot, nonce };
      } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'EEXIST') return null; }
    }
    return null;
  } catch { return null; }
}

/** Record the worker's own pid in a slot this caller holds, so the slot is freed if the worker dies. Does nothing if the slot is not (or no longer) ours. */
export async function claimSlot(project: string, held: Slot, pid: number): Promise<void> {
  try {
    const dir = await containedDir(project, ['retrieval', 'active']);
    if (!dir) return;
    const file = slotFile(dir, held.slot);
    const handle = await open(file, 'r+');
    try {
      const current = await readToken(file);
      if (current?.nonce !== held.nonce) return;
      await handle.truncate(0);
      await handle.writeFile(JSON.stringify({ pid, nonce: held.nonce, ts: nowIso() } satisfies SlotToken), 'utf8');
    } finally { await handle.close(); }
  } catch { /* released already, or no slot */ }
}

/** Free a slot, but only if it still holds this caller's token. */
export async function releaseSlot(project: string, held: Slot | null): Promise<void> {
  if (held === null) return;
  try {
    const dir = await containedDir(project, ['retrieval', 'active']);
    if (!dir) return;
    const file = slotFile(dir, held.slot);
    if ((await readToken(file))?.nonce === held.nonce) await rm(file, { force: true });
  } catch { /* nothing to release */ }
}

/**
 * The program a detached worker runs: the aw that is running now. AW_LIBRARY_WORKER_ENTRY can name another
 * one, but only inside the test runner (node --test sets NODE_TEST_CONTEXT in the real process environment);
 * anywhere else the setting is ignored, so a stray environment value can never change what gets spawned.
 */
export function workerEntry(env: NodeJS.ProcessEnv, argvEntry: string | undefined): string | undefined {
  const override = env.AW_LIBRARY_WORKER_ENTRY?.trim();
  return override && process.env.NODE_TEST_CONTEXT !== undefined ? override : argvEntry;
}

// ---------------------------------------------------------------- starting a shadow (foreground)

/**
 * Start the shadow for one lookup and return at once. Never throws and never waits for the worker: the cost
 * to the caller is one small file write and one spawn. `status` goes into the lookup row.
 */
export async function startShadow(spec: Omit<ShadowSpec, 'slot' | 'slot_nonce'>, mode: ShadowMode, env: NodeJS.ProcessEnv, runner: ShadowRunner): Promise<ShadowHandle> {
  if (mode === 'off') return idle('disabled');
  let slot: Slot | null = null;
  let specPath: string | null = null;
  try {
    if (!(await hasProjectFolder(spec.project))) return idle('skipped:no_project_dir');
    if (mode === 'inline') return { status: 'pending', settle: () => runShadowWorker({ ...spec, slot: null }, runner, workerSettings(env)) };
    const entry = workerEntry(env, process.argv[1] ? resolve(process.argv[1]) : undefined);
    if (!entry) return idle('skipped:spawn_failed');
    slot = await acquireSlot(spec.project);
    if (slot === null) return idle('skipped:busy');
    const dir = await containedDir(spec.project, ['retrieval'], true);
    if (!dir) throw new Error('no retrieval folder');
    specPath = join(dir, `spec-${spec.lookup_id}.json`);
    const handle = await open(specPath, 'wx', 0o644);
    try { await handle.writeFile(JSON.stringify({ ...spec, slot: slot.slot, slot_nonce: slot.nonce }), 'utf8'); } finally { await handle.close(); }
    const child = spawn(process.execPath, [entry, 'library', '_shadow', specPath], { detached: true, stdio: 'ignore', windowsHide: true, env, cwd: spec.project });
    child.on('error', () => undefined);
    child.unref();
    if (child.pid) await claimSlot(spec.project, slot, child.pid);
    return idle('pending');
  } catch {
    if (specPath) await rm(specPath, { force: true });
    await releaseSlot(spec.project, slot);
    return idle('skipped:spawn_failed');
  }
}

// ---------------------------------------------------------------- the worker (background)

/**
 * Read and validate a worker spec file. The file is deleted only when it is a well formed spec that sits
 * in its own project's retrieval folder under its own name (`spec-<lookup_id>.json`); anything else is
 * left exactly as found, so `_shadow <path>` can never remove a file it was merely pointed at.
 */
export async function loadSpec(path: string): Promise<ShadowSpec | null> {
  try {
    const parsed = shadowSpecSchema.safeParse(JSON.parse(await readFile(path, 'utf8')));
    if (!parsed.success) return null;
    const dir = await containedDir(parsed.data.project, ['retrieval']);
    if (!dir) return null;
    const expected = join(dir, `spec-${parsed.data.lookup_id}.json`);
    if ((await realpath(path)) !== expected) return null;
    await rm(expected, { force: true });
    return parsed.data;
  } catch { return null; }
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
    const found = await readSpool(spec.project, file);
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
  const scope = new CommandScope();
  let result: RouteResult | null = null;
  let failure: unknown = null;
  let timedOut = false;
  let timer: NodeJS.Timeout | undefined;
  try {
    await sweepSpool(spec.project);
    const call = runner.runShadow(spec, scope);
    call.catch(() => undefined);
    const deadline = new Promise<'timeout'>((resolveDeadline) => { timer = setTimeout(() => { resolveDeadline('timeout'); }, settings.timeoutMs); });
    try {
      const outcome = await Promise.race([call, deadline]);
      if (outcome === 'timeout') timedOut = true; else result = outcome;
    } catch (error) {
      failure = error;
      timedOut = error instanceof LibraryError && error.code === 'timeout';
    }
    clearTimeout(timer);
    // Once the lookup has timed out, nothing it started may go on: running commands are killed and no new one can begin.
    if (timedOut || scope.aborted) { timedOut = true; scope.abort(); result = null; }
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
      error: result ? null : clipError(timedOut ? `${spec.route} did not answer within ${settings.timeoutMs} ms` : (failure instanceof Error ? failure.message : String(failure ?? 'no answer'))),
      error_code: result ? null : (timedOut ? 'timeout' : code),
      timed_out: timedOut,
      agree,
    };
    await appendRow(spec.project, row);
  } catch {
    // The shadow can never fail the caller, and has nobody to tell: its row is simply missing.
  } finally {
    clearTimeout(timer);
    scope.abort();
    await releaseSlot(spec.project, spec.slot === null || !spec.slot_nonce ? null : { slot: spec.slot, nonce: spec.slot_nonce });
    await removeSpool(spec.project, spoolFile(spec.project, spec.lookup_id, 'primary'));
  }
}
