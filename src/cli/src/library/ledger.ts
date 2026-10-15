import { createHash } from 'node:crypto';
import { appendFile, mkdir, readFile, readdir, rename, rm, stat, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import retrievalSchema from '../../../schemas/retrieval-row.schema.json' with { type: 'json' };
import thresholds from '../../../thresholds.json' with { type: 'json' };
import { checkSchema, type JsonSchema } from './jsonschema.ts';
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
};

export type SupportsReason = 'covered' | 'not_covered' | 'no_quote' | 'shadow_missing' | 'shadow_pending';

export type VerdictRow = {
  row_type: 'verdict';
  schema: 1;
  ts: string;
  lookup_id: string;
  run_id: string | null;
  paragraph_id: string | null;
  verdict: 'PASS' | 'FAIL';
  corrected_page: number | null;
  shadow_supports: boolean | null;
  shadow_supports_reason: SupportsReason;
  primary_route: RouteName | null;
  mode: RouteMode | null;
  settled?: boolean;
};

export type RetrievalRow = LookupRow | ShadowRow | VerdictRow;

export function nowIso(): string { return new Date().toISOString(); }

/** 16 hex characters of the SHA-256 of `text`: enough to tell two page texts apart, nothing to read back. */
export function textSha(text: string): string { return createHash('sha256').update(text, 'utf8').digest('hex').slice(0, 16); }

/** One line, no newlines, short enough for a ledger row. */
export function clipError(message: string): string {
  return message.replace(/\s+/gu, ' ').trim().slice(0, limits.ledger.maxErrorChars);
}

export function ledgerPath(project: string): string { return join(project, RETRIEVAL_FILE); }
export function retrievalDir(project: string): string { return join(project, RETRIEVAL_DIR); }
export function spoolDir(project: string): string { return join(retrievalDir(project), 'spool'); }

async function isDirectory(path: string): Promise<boolean> {
  try { return (await stat(path)).isDirectory(); } catch { return false; }
}

/** Whether `project` is an article project (has `.academic-helper/`); the ledger never makes that folder. */
export function hasProjectFolder(project: string): Promise<boolean> { return isDirectory(join(project, '.academic-helper')); }

export type AppendResult = { ok: true } | { ok: false; reason: string };

/** Check the row against the schema and append it as one line. Never throws; a refused row is reported, not fatal. */
export async function appendRow(project: string, row: RetrievalRow): Promise<AppendResult> {
  try {
    if (!(await hasProjectFolder(project))) return { ok: false, reason: 'no .academic-helper folder in this project' };
    const problems = checkSchema(retrievalSchema as JsonSchema, row);
    if (problems.length > 0) return { ok: false, reason: `row does not match the schema (${problems[0]})` };
    const line = `${JSON.stringify(row)}\n`;
    if (Buffer.byteLength(line, 'utf8') > limits.ledger.maxRowBytes) return { ok: false, reason: 'row is larger than the ledger allows' };
    await appendFile(ledgerPath(project), line, 'utf8');
    return { ok: true };
  } catch (error) {
    return { ok: false, reason: error instanceof Error ? error.message : String(error) };
  }
}

/** Every valid row in the ledger, in file order. Lines that are not valid rows are counted, not returned. */
export async function readRows(project: string): Promise<{ rows: RetrievalRow[]; invalid: number }> {
  let text: string;
  try { text = await readFile(ledgerPath(project), 'utf8'); } catch { return { rows: [], invalid: 0 }; }
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
  let text: string;
  try { text = await readFile(ledgerPath(project), 'utf8'); } catch { return []; }
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

export function spoolFile(project: string, lookupId: string, kind: 'primary' | 'shadow'): string { return join(spoolDir(project), `${lookupId}.${kind}.json`); }

/** Write a spool file whole (temp name, then rename), so a reader never sees half a file. Never throws. */
export async function writeSpool(project: string, file: string, value: unknown): Promise<boolean> {
  try {
    if (!(await hasProjectFolder(project))) return false;
    await mkdir(spoolDir(project), { recursive: true });
    const temp = `${file}.${process.pid}.tmp`;
    await writeFile(temp, JSON.stringify(value), 'utf8');
    await rename(temp, file);
    return true;
  } catch { return false; }
}

export async function readSpool(file: string): Promise<SpooledPages | null> {
  try {
    const parsed: unknown = JSON.parse(await readFile(file, 'utf8'));
    if (typeof parsed !== 'object' || parsed === null || !Array.isArray((parsed as SpooledPages).pages)) return null;
    return parsed as SpooledPages;
  } catch { return null; }
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
    const dir = spoolDir(project);
    const cutoff = now - limits.spool.ttlHours * 3600 * 1000;
    for (const name of await readdir(dir)) {
      const file = join(dir, name);
      try { if ((await stat(file)).mtimeMs < cutoff) await rm(file, { force: true }); } catch { /* gone already */ }
    }
  } catch { /* no spool folder yet */ }
}
