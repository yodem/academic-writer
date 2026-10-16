import { createHash } from 'node:crypto';
import { constants } from 'node:fs';
import { lstat, mkdir, open, readFile, readdir, realpath, rename, rm, stat } from 'node:fs/promises';
import { basename, dirname, join, sep } from 'node:path';
import retrievalSchema from '../../../schemas/retrieval-row.schema.json' with { type: 'json' };
import thresholds from '../../../thresholds.json' with { type: 'json' };
import { checkSchema, type JsonSchema } from './jsonschema.ts';
import { redact } from './redact.ts';
import type { RouteMode, RouteName } from './types.ts';

const limits = thresholds.library;

/**
 * The retrieval ledger: `.academic-helper/retrieval.jsonl`, one JSON line per event, append-only, metadata
 * only (ids, pages, sizes, hashes; never source text). It records what happened so routes can be compared;
 * nothing in the writing pipeline reads it to decide anything. It never creates `.academic-helper/` itself.
 */
export const RETRIEVAL_FILE = join('.academic-helper', 'retrieval.jsonl');
export const RETRIEVAL_DIR = join('.academic-helper', 'retrieval');

export type LookupOp = 'list' | 'toc' | 'read' | 'get';

/** The only basis a token figure in the ledger has: characters divided by a ratio, never a tokenizer count. */
export type TokensBasis = 'estimate';
export const TOKENS_BASIS: TokensBasis = 'estimate';

export type RouteCall = {
  route: RouteName;
  ok: boolean;
  route_pages: string | null;
  latency_ms: number;
  bytes: number;
  chars: number;
  text_sha: string | null;
  error: string | null;
  error_code: string | null;
  /** Estimated tokens of the text this call returned (see estimateTokens); absent on failed calls and on rows written before 0.17.0. */
  est_tokens?: number;
  tokens_basis?: TokensBasis;
};

export type Agreement = { rate: number | null; compared: number; agreed: number; pages: Array<{ page: number; jaccard: number; agree: boolean }> };

export type LookupRow = {
  row_type: 'lookup';
  schema: 1;
  ts: string;
  lookup_id: string;
  run_id: string | null;
  claim_id: string | null;
  op: LookupOp;
  source_id: string | null;
  mode: RouteMode;
  route_primary: RouteName;
  book_by_route: { trove: string | null; pageindex: string | null };
  request: { printed: string | null; trove_pages: string | null };
  primary: RouteCall;
  shadow_status: string;
};

export type ShadowRow = {
  row_type: 'shadow';
  schema: 1;
  ts: string;
  lookup_id: string;
  run_id: string | null;
  route: RouteName;
  ok: boolean;
  book: string | null;
  route_pages: string | null;
  latency_ms: number;
  bytes: number;
  chars: number;
  text_sha: string | null;
  error: string | null;
  error_code: string | null;
  timed_out: boolean;
  agree: Agreement | null;
  est_tokens?: number;
  tokens_basis?: TokensBasis;
};

export type SupportsReason = 'covered' | 'not_covered' | 'no_quote' | 'shadow_missing' | 'shadow_pending';

export type VerdictRow = {
  row_type: 'verdict';
  schema: 1;
  ts: string;
  lookup_id: string;
  run_id: string | null;
  paragraph_id: string | null;
  /** When `aw library verdict` was invoked (epoch nanoseconds, as a string). With `pid` and `nonce` it orders the verdicts of one citation. */
  verdict_at: string;
  pid: number;
  nonce: string;
  verdict: 'PASS' | 'FAIL';
  corrected_page: number | null;
  shadow_supports: boolean | null;
  shadow_supports_reason: SupportsReason;
  primary_route: RouteName | null;
  mode: RouteMode | null;
  settled?: boolean;
};

export type RetrievalRow = LookupRow | ShadowRow | VerdictRow;

/**
 * Order two verdicts of one citation: by the time `aw library verdict` was invoked, then pid, then nonce.
 * The ledger needs no lock for this: each row carries its own key, so rows may be appended in any order
 * (several processes, a late settle) and the newest verdict is still the one with the highest key.
 * Positive when `a` is newer than `b`.
 */
export function compareVerdictKeys(a: Pick<VerdictRow, 'verdict_at' | 'pid' | 'nonce'>, b: Pick<VerdictRow, 'verdict_at' | 'pid' | 'nonce'>): number {
  const left = BigInt(a.verdict_at);
  const right = BigInt(b.verdict_at);
  if (left !== right) return left > right ? 1 : -1;
  if (a.pid !== b.pid) return a.pid > b.pid ? 1 : -1;
  return a.nonce === b.nonce ? 0 : (a.nonce > b.nonce ? 1 : -1);
}

export function nowIso(): string { return new Date().toISOString(); }

/** 16 hex characters of the SHA-256 of `text`: enough to tell two page texts apart, nothing to read back. */
export function textSha(text: string): string { return createHash('sha256').update(text, 'utf8').digest('hex').slice(0, 16); }

/**
 * Estimated tokens of `text`: Hebrew letters count 1 token per hebrewCharsPerToken characters, everything else
 * 1 per otherCharsPerToken (both in thresholds.json library.tokens). An ESTIMATE for comparing routes: Claude's
 * tokenizer is not available offline, so this is never a billing figure. Exact counts come from the locating
 * agents' own usage rows (step library.eval.locate).
 */
export function estimateTokens(text: string): number {
  let hebrew = 0;
  for (let index = 0; index < text.length; index += 1) {
    const code = text.charCodeAt(index);
    if ((code >= 0x0590 && code <= 0x05ff) || (code >= 0xfb1d && code <= 0xfb4f)) hebrew += 1;
  }
  const tokens = hebrew / limits.tokens.hebrewCharsPerToken + (text.length - hebrew) / limits.tokens.otherCharsPerToken;
  return Math.ceil(tokens);
}

/** One line, no newlines, credentials hidden, short enough for a ledger row. */
export function clipError(message: string): string {
  // Redact first, on the raw text: line breaks are what end a header value.
  return redact(message).replace(/\s+/gu, ' ').trim().slice(0, limits.ledger.maxErrorChars);
}

export function ledgerPath(project: string): string { return join(project, RETRIEVAL_FILE); }
export function retrievalDir(project: string): string { return join(project, RETRIEVAL_DIR); }
export function spoolDir(project: string): string { return join(retrievalDir(project), 'spool'); }

function inside(root: string, path: string): boolean { return path === root || path.startsWith(`${root}${sep}`); }

/**
 * A folder of this project that is really inside it: `.academic-helper` and then `segments`, each resolved
 * through symlinks and required to stay under the project's real path. With `create`, missing segments are
 * made (never `.academic-helper` itself). Null when anything is missing, is not a folder, or points outside.
 */
export async function containedDir(project: string, segments: string[], create = false): Promise<string | null> {
  try {
    const root = await realpath(project);
    let current = await realpath(join(root, '.academic-helper'));
    if (!inside(root, current) || !(await stat(current)).isDirectory()) return null;
    for (const segment of segments) {
      const next = join(current, segment);
      if (create) await mkdir(next).catch((error: NodeJS.ErrnoException) => { if (error.code !== 'EEXIST') throw error; });
      current = await realpath(next);
      if (!inside(root, current) || !(await stat(current)).isDirectory()) return null;
    }
    return current;
  } catch { return null; }
}

// Known limit (accepted): a folder swapped for a symlink between the realpath check and the write below is
// not caught; only the final component is opened without following links. The plugin's threat model is one
// researcher on a local machine who owns the project folder (CLAUDE.md), so the static symlink cases are
// refused and this race is documented rather than closed with descriptor-relative paths.
/** Whether `project` is an article project (has a real `.academic-helper/` inside it); the ledger never makes that folder. */
export async function hasProjectFolder(project: string): Promise<boolean> { return (await containedDir(project, [])) !== null; }

export type AppendResult = { ok: true } | { ok: false; reason: string };

async function isSymlink(path: string): Promise<boolean> {
  try { return (await lstat(path)).isSymbolicLink(); } catch { return false; }
}

/** The ledger file inside the project, or null when the project folder is missing, escapes the project, or the file is a symlink. */
async function safeLedgerFile(project: string): Promise<string | null> {
  const dir = await containedDir(project, []);
  if (!dir) return null;
  const file = join(dir, basename(RETRIEVAL_FILE));
  return (await isSymlink(file)) ? null : file;
}

/**
 * Check the row against the schema and append it as ONE write on an O_APPEND handle (so rows from the
 * answering path and several workers never interleave). The file is opened without following symlinks.
 * Never throws; a refused row is reported, not fatal.
 */
export async function appendRow(project: string, row: RetrievalRow): Promise<AppendResult> {
  try {
    const file = await safeLedgerFile(project);
    if (!file) return { ok: false, reason: 'no usable .academic-helper folder in this project' };
    const problems = checkSchema(retrievalSchema as JsonSchema, row);
    if (problems.length > 0) return { ok: false, reason: `row does not match the schema (${problems[0]})` };
    const line = Buffer.from(`${JSON.stringify(row)}\n`, 'utf8');
    if (line.length > limits.ledger.maxRowBytes) return { ok: false, reason: 'row is larger than the ledger allows' };
    const handle = await open(file, constants.O_WRONLY | constants.O_APPEND | constants.O_CREAT | (constants.O_NOFOLLOW ?? 0), 0o644);
    try {
      const { bytesWritten } = await handle.write(line, 0, line.length);
      if (bytesWritten !== line.length) return { ok: false, reason: 'the ledger write was cut short' };
    } finally { await handle.close(); }
    return { ok: true };
  } catch (error) {
    return { ok: false, reason: error instanceof Error ? error.message : String(error) };
  }
}

async function readLedgerText(project: string): Promise<string | null> {
  const file = await safeLedgerFile(project);
  if (!file) return null;
  try { return await readFile(file, 'utf8'); } catch { return null; }
}

/** Every valid row in the ledger, in file order. Lines that are not valid rows are counted, not returned. */
export async function readRows(project: string): Promise<{ rows: RetrievalRow[]; invalid: number }> {
  const text = await readLedgerText(project);
  if (text === null) return { rows: [], invalid: 0 };
  const rows: RetrievalRow[] = [];
  let invalid = 0;
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try {
      const parsed: unknown = JSON.parse(line);
      if (checkSchema(retrievalSchema as JsonSchema, parsed).length === 0) rows.push(parsed as RetrievalRow);
      else invalid += 1;
    } catch { invalid += 1; }
  }
  return { rows, invalid };
}

/** The raw ledger lines that mention `lookupId`, parsed; a cheap way to look for one lookup's rows without validating the whole file. */
export async function rowsForLookup(project: string, lookupId: string): Promise<RetrievalRow[]> {
  const text = await readLedgerText(project);
  if (text === null) return [];
  const found: RetrievalRow[] = [];
  for (const line of text.split('\n')) {
    if (!line.includes(lookupId)) continue;
    try {
      const parsed = JSON.parse(line) as RetrievalRow;
      if (parsed.lookup_id === lookupId) found.push(parsed);
    } catch { /* a torn line is ignored */ }
  }
  return found;
}

// ---------------------------------------------------------------- spool

export type SpooledPages = { lookup_id: string; route?: RouteName; ok?: boolean; too_large?: boolean; pages: Array<{ page: number; text: string }> };

/** The nominal spool file of a lookup; reads and writes go through the contained spool folder, using only the file's name. */
export function spoolFile(project: string, lookupId: string, kind: 'primary' | 'shadow'): string { return join(spoolDir(project), `${lookupId}.${kind}.json`); }

/** Write a spool file whole (new temp name, then rename), inside the project's real spool folder. Never throws. */
export async function writeSpool(project: string, file: string, value: unknown): Promise<boolean> {
  try {
    if (dirname(file) !== spoolDir(project)) return false;
    const dir = await containedDir(project, ['retrieval', 'spool'], true);
    if (!dir) return false;
    const target = join(dir, basename(file));
    const temp = `${target}.${process.pid}.${Date.now().toString(36)}.tmp`;
    const handle = await open(temp, 'wx', 0o644);
    try { await handle.writeFile(JSON.stringify(value), 'utf8'); } finally { await handle.close(); }
    await rename(temp, target);
    return true;
  } catch { return false; }
}

/** A JSON file from the project's real spool folder (never through a symlink); throws when it is missing or not JSON. */
export async function readSpoolJson(project: string, file: string): Promise<unknown> {
  const dir = await containedDir(project, ['retrieval', 'spool']);
  if (!dir) throw new Error('no spool folder');
  const target = join(dir, basename(file));
  if (await isSymlink(target)) throw new Error('spool file is a symlink');
  return JSON.parse(await readFile(target, 'utf8'));
}

export async function readSpool(project: string, file: string): Promise<SpooledPages | null> {
  try {
    const parsed = await readSpoolJson(project, file);
    if (typeof parsed !== 'object' || parsed === null || !Array.isArray((parsed as SpooledPages).pages)) return null;
    return parsed as SpooledPages;
  } catch { return null; }
}

/** Files in the project's real spool folder whose names pass `keep`. */
export async function listSpool(project: string, keep: (name: string) => boolean): Promise<string[]> {
  const dir = await containedDir(project, ['retrieval', 'spool']);
  if (!dir) return [];
  try { return (await readdir(dir)).filter(keep).map((name) => join(spoolDir(project), name)); } catch { return []; }
}

export async function removeSpool(project: string, file: string): Promise<void> {
  const dir = await containedDir(project, ['retrieval', 'spool']);
  if (dir) await rm(join(dir, basename(file)), { force: true });
}

/** Page texts as a spool value, or the size marker when they would be larger than spool.maxBytes. */
export function spoolValue(lookupId: string, extra: { route?: RouteName; ok?: boolean }, pages: Array<{ page: number; text: string }>): SpooledPages {
  const size = pages.reduce((sum, page) => sum + Buffer.byteLength(page.text, 'utf8'), 0);
  if (size > limits.spool.maxBytes) return { lookup_id: lookupId, ...extra, too_large: true, pages: [] };
  return { lookup_id: lookupId, ...extra, pages };
}

/** Delete spool files older than spool.ttlHours. Never throws. */
export async function sweepSpool(project: string, now: number = Date.now()): Promise<void> {
  try {
    const dir = await containedDir(project, ['retrieval', 'spool']);
    if (!dir) return;
    const cutoff = now - limits.spool.ttlHours * 3600 * 1000;
    for (const name of await readdir(dir)) {
      const file = join(dir, name);
      try { if ((await lstat(file)).mtimeMs < cutoff) await rm(file, { force: true }); } catch { /* gone already */ }
    }
  } catch { /* no spool folder yet */ }
}
