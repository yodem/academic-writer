import { readFile } from 'node:fs/promises';
import { LibraryError } from '../types.ts';
import { readJson, readValid, sha256, validate, validateImport, writeJson, type EvalPaths } from './files.ts';
import { mappingCommitment } from './seal.ts';
import type { JudgmentEntry, Judgments, Mapping, Pairs, Verdict } from './types.ts';

const VERDICTS: ReadonlySet<string> = new Set<Verdict>(['A', 'B', 'same', 'neither', 'skip']);

/** The newest entry of each pair (append order decides). */
export function effective(judgments: Judgments | null): Map<string, JudgmentEntry> {
  const latest = new Map<string, JudgmentEntry>();
  for (const entry of judgments?.entries ?? []) latest.set(entry.pair_id, entry);
  return latest;
}

/**
 * Accept the three shapes a judging page may hand back and return the import shape ({judgments: [...]}):
 * the shape itself, a bare list, or a map of pair id to {verdict, note, at} (what a shared-state store keyed by pair holds).
 */
export function normalizeImport(raw: unknown): unknown {
  const toList = (map: Record<string, unknown>): unknown[] => Object.entries(map).map(([pair, value]) => (
    typeof value === 'string' ? { pair_id: pair, verdict: value } : { pair_id: pair, ...(typeof value === 'object' && value !== null ? value as object : {}) }));
  if (Array.isArray(raw)) return { judgments: raw };
  if (typeof raw !== 'object' || raw === null) return raw;
  const object = raw as Record<string, unknown>;
  if (Array.isArray(object.judgments)) return { ...(object.schema === undefined ? {} : { schema: object.schema }), ...(object.eval_id === undefined ? {} : { eval_id: object.eval_id }), judgments: object.judgments };
  if (typeof object.judgments === 'object' && object.judgments !== null) return { ...(object.eval_id === undefined ? {} : { eval_id: object.eval_id }), judgments: toList(object.judgments as Record<string, unknown>) };
  if (Object.keys(object).length > 0 && Object.keys(object).every((key) => /^p[0-9]{2,3}$/u.test(key))) return { judgments: toList(object) };
  return raw;
}

export type CommitmentCheck = { pairs: Pairs; mapping: Mapping; pairsSha: string };

/** Load pairs and the sealed mapping and prove they still belong together (the commitment pairs.json made). */
export async function checkCommitment(paths: EvalPaths): Promise<CommitmentCheck> {
  const pairs = await readValid<Pairs>('pairs', paths.pairs, 'pairs');
  const mapping = await readValid<Mapping>('mapping', paths.mapping, 'sealed mapping');
  if (mappingCommitment(mapping) !== pairs.mapping_sha256) {
    throw new LibraryError('parse', 'ERROR library eval: the sealed mapping does not match the commitment in pairs.json, so it was changed after the pairs were built; refusing to go on');
  }
  const pairsSha = sha256(await readFile(paths.pairs));
  return { pairs, mapping, pairsSha };
}

export type ImportSummary = { eval_id: string; imported: number; unchanged: number; auto_same: number; judged: number; pairs: number; pending: string[] };

/**
 * Store the judge's verdicts. Every pair must be judged (or skipped on purpose), except the pairs whose two options are
 * identical, which are marked `same` automatically; `partial` allows an incomplete import (progress). Unknown pair ids are
 * refused. judgments.json only ever grows: a changed verdict adds an entry and the newest one counts.
 */
export async function importJudgments(options: { paths: EvalPaths; evalId: string; raw: unknown; partial: boolean; now: Date }): Promise<ImportSummary> {
  const { paths } = options;
  const { pairs, pairsSha } = await checkCommitment(paths);
  const input = normalizeImport(options.raw);
  const problems = validateImport(input);
  if (problems.length > 0) throw new LibraryError('usage', `ERROR library eval import: the judgments file is not valid (${problems[0]})`);
  const body = input as { eval_id?: string; judgments: Array<{ pair_id: string; verdict: string; note?: string; at?: string }> };
  if (body.eval_id !== undefined && body.eval_id !== options.evalId) throw new LibraryError('usage', `ERROR library eval import: this file is for evaluation ${body.eval_id}, not ${options.evalId}`);
  const known = new Map(pairs.pairs.map((pair) => [pair.pair_id, pair]));
  const unknown = [...new Set(body.judgments.map((item) => item.pair_id).filter((id) => !known.has(id)))];
  if (unknown.length > 0) throw new LibraryError('usage', `ERROR library eval import: unknown pair id(s): ${unknown.slice(0, 5).join(', ')}`);
  for (const item of body.judgments) if (!VERDICTS.has(item.verdict)) throw new LibraryError('usage', `ERROR library eval import: ${item.pair_id} has an unknown verdict`);

  const existing = await readJson(paths.judgments);
  let judgments: Judgments;
  if (existing === null) judgments = { schema: 1, eval_id: options.evalId, pairs_sha256: pairsSha, mapping_sha256: pairs.mapping_sha256, entries: [] };
  else {
    if (validate('judgments', existing).length > 0) throw new LibraryError('parse', 'ERROR library eval import: judgments.json is not valid');
    judgments = existing as Judgments;
    if (judgments.pairs_sha256 !== pairsSha || judgments.mapping_sha256 !== pairs.mapping_sha256) throw new LibraryError('parse', 'ERROR library eval import: pairs.json changed after judgments were stored; refusing to mix them');
  }
  const importedAt = options.now.toISOString();
  const latest = new Map<string, (typeof body.judgments)[number]>();
  for (const item of body.judgments) latest.set(item.pair_id, item);
  const current = effective(judgments);
  let imported = 0;
  let unchanged = 0;
  const entries = [...judgments.entries];
  for (const [pairId, item] of latest) {
    const before = current.get(pairId);
    const note = (item.note ?? '').normalize('NFC');
    if (before && before.source === 'judge' && before.verdict === item.verdict && before.note === note) { unchanged += 1; continue; }
    const entry: JudgmentEntry = { pair_id: pairId, verdict: item.verdict as Verdict, note, source: 'judge', judged_at: item.at ?? null, imported_at: importedAt };
    entries.push(entry);
    current.set(pairId, entry);
    imported += 1;
  }
  let auto = 0;
  for (const pair of pairs.pairs) {
    if (pair.auto_same && !current.has(pair.pair_id)) {
      const entry: JudgmentEntry = { pair_id: pair.pair_id, verdict: 'same', note: '', source: 'auto', judged_at: null, imported_at: importedAt };
      entries.push(entry);
      current.set(pair.pair_id, entry);
      auto += 1;
    }
  }
  const pending = pairs.pairs.filter((pair) => !current.has(pair.pair_id)).map((pair) => pair.pair_id);
  if (pending.length > 0 && !options.partial) {
    throw new LibraryError('usage', `ERROR library eval import: ${pending.length} pair(s) have no judgment (${pending.slice(0, 6).join(', ')}${pending.length > 6 ? ', ...' : ''}); judge them or mark them skipped, or import with --partial to save progress`);
  }
  const output: Judgments = { ...judgments, entries };
  const checked = validate('judgments', output);
  if (checked.length > 0) throw new LibraryError('usage', `ERROR library eval import: ${checked[0]}`);
  await writeJson(paths.judgments, output);
  return { eval_id: options.evalId, imported, unchanged, auto_same: auto, judged: current.size, pairs: pairs.pairs.length, pending };
}
