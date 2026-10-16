import { createHash, randomBytes } from 'node:crypto';
import { existsSync, lstatSync, realpathSync } from 'node:fs';
import { appendFile, chmod, lstat, mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { dirname, join, sep } from 'node:path';
import ledgerSchema from '../../../../schemas/ledger-row.schema.json' with { type: 'json' };
import judgmentsSchema from '../../../../schemas/library-eval-judgments.schema.json' with { type: 'json' };
import mappingSchema from '../../../../schemas/library-eval-mapping.schema.json' with { type: 'json' };
import pairsSchema from '../../../../schemas/library-eval-pairs.schema.json' with { type: 'json' };
import planSchema from '../../../../schemas/library-eval-plan.schema.json' with { type: 'json' };
import runSchema from '../../../../schemas/library-eval-run.schema.json' with { type: 'json' };
import type { LedgerRow } from '../../ledger.ts';
import { checkSchema, type JsonSchema } from '../jsonschema.ts';
import { LibraryError } from '../types.ts';

export const EVAL_ROOT = join('.academic-helper', 'library-eval');
/** Letters, digits and hyphens: safe in a run id, a file name and a shell word. */
export const EVAL_ID = /^[A-Za-z0-9][A-Za-z0-9-]{0,39}$/u;

export type EvalPaths = {
  root: string; plan: string; runsDir: string; pairs: string; sealedDir: string; mapping: string;
  judgments: string; reportJson: string; reportMd: string; judgeHtml: string;
};

/**
 * The evaluation's folders must be real folders inside the project's real `.academic-helper`: nothing from
 * `library-eval` down may be a symlink (a link would send the plan, the sealed key or the runs somewhere else), and the
 * project's own `.academic-helper` must resolve to a place inside the project. Folders not made yet are fine.
 * Known limit (as for the retrieval ledger): a folder swapped for a link between this check and a later write is not caught.
 */
export function guardEvalDirs(project: string, evalId: string): void {
  const refuse = (what: string): never => { throw new LibraryError('config', `ERROR library eval: ${what}; refusing to use it`); };
  let real: string;
  try { real = realpathSync(project); } catch { return refuse('the project folder cannot be resolved'); }
  const helper = join(project, '.academic-helper');
  if (!existsSync(helper)) return;
  let helperReal: string;
  try { helperReal = realpathSync(helper); } catch { return refuse('.academic-helper cannot be resolved'); }
  if (helperReal !== real && !helperReal.startsWith(`${real}${sep}`)) refuse('.academic-helper points outside the project');
  const evalRoot = join(helperReal, 'library-eval', evalId);
  for (const dir of [join(helperReal, 'library-eval'), evalRoot, join(evalRoot, 'runs'), join(evalRoot, 'sealed')]) {
    let info;
    try { info = lstatSync(dir); } catch { continue; }
    if (info.isSymbolicLink()) refuse(`${dir.slice(helperReal.length + 1)} is a symbolic link`);
    if (!info.isDirectory()) refuse(`${dir.slice(helperReal.length + 1)} is not a folder`);
  }
}

export function evalPaths(project: string, evalId: string): EvalPaths {
  if (!EVAL_ID.test(evalId)) throw new LibraryError('usage', 'ERROR library eval: --eval must be a plain id (letters, digits and hyphens, up to 40)');
  guardEvalDirs(project, evalId);
  const root = join(project, EVAL_ROOT, evalId);
  return {
    root, plan: join(root, 'plan.json'), runsDir: join(root, 'runs'), pairs: join(root, 'pairs.json'),
    sealedDir: join(root, 'sealed'), mapping: join(root, 'sealed', 'mapping.json'), judgments: join(root, 'judgments.json'),
    reportJson: join(root, 'report.json'), reportMd: join(root, 'report.md'), judgeHtml: join(root, 'judge.html'),
  };
}

export function runFile(paths: EvalPaths, claimId: string, route: string): string { return join(paths.runsDir, `${claimId}-${route}.json`); }

export function requireProject(project: string): void {
  if (!existsSync(join(project, '.academic-helper'))) {
    throw new LibraryError('config', 'ERROR library eval: this folder has no .academic-helper folder, so it is not an article project; open the article folder first');
  }
}

export function sha256(data: string | Buffer): string { return createHash('sha256').update(data).digest('hex'); }
export function newNonce(): string { return randomBytes(32).toString('hex'); }

/** JSON with every object's keys sorted, so a hash does not depend on the order a file was written in. */
export function canonicalJson(value: unknown): string {
  const sort = (item: unknown): unknown => {
    if (Array.isArray(item)) return item.map(sort);
    if (typeof item === 'object' && item !== null) {
      return Object.fromEntries(Object.entries(item as Record<string, unknown>).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)).map(([key, inner]) => [key, sort(inner)]));
    }
    return item;
  };
  return JSON.stringify(sort(value));
}

/** Write a JSON file whole: a new temp file next to it, then a rename. `mode` is for files that must stay private. */
export async function writeJson(file: string, value: unknown, mode = 0o644): Promise<void> {
  await mkdir(dirname(file), { recursive: true });
  const temp = `${file}.${process.pid}.${randomBytes(4).toString('hex')}.tmp`;
  await writeFile(temp, `${JSON.stringify(value, null, 2)}\n`, { encoding: 'utf8', mode });
  await chmod(temp, mode);
  await rename(temp, file);
}

export async function readJson(file: string): Promise<unknown | null> {
  let text: string;
  try {
    if ((await lstat(file)).isSymbolicLink()) throw new LibraryError('config', `ERROR library eval: ${file} is a symbolic link; refusing to read it`);
    text = await readFile(file, 'utf8');
  } catch (error) { if (error instanceof LibraryError) throw error; return null; }
  try { return JSON.parse(text); } catch { throw new LibraryError('parse', `ERROR library eval: ${file} is not valid JSON`); }
}

const SCHEMAS = { plan: planSchema, run: runSchema, pairs: pairsSchema, judgments: judgmentsSchema, mapping: mappingSchema } as const;
export type SchemaName = keyof typeof SCHEMAS;

/** Problems found (empty means valid). */
export function validate(name: SchemaName, value: unknown): string[] { return checkSchema(SCHEMAS[name] as JsonSchema, value); }
/** Check an import file (definitions.import of the judgments schema). */
export function validateImport(value: unknown): string[] {
  return checkSchema({ $ref: '#/definitions/import' }, value, judgmentsSchema as JsonSchema);
}

export async function readValid<T>(name: SchemaName, file: string, what: string): Promise<T> {
  const value = await readJson(file);
  if (value === null) throw new LibraryError('usage', `ERROR library eval: no ${what} yet (${name === 'plan' ? 'run `aw library eval plan` first' : 'a step before this one has not run'})`);
  const problems = validate(name, value);
  if (problems.length > 0) throw new LibraryError('parse', `ERROR library eval: ${what} is not valid (${problems[0]})`);
  return value as T;
}

export async function removeFile(file: string): Promise<void> { await rm(file, { force: true }); }

/**
 * One row in the plugin's usage ledger, `.academic-helper/runs/<run_id>/usage.jsonl`: the same file and row shape
 * `appendLedger` writes (and `aw ledger show` reads). It is written here with the project passed in, because the
 * eval resolves its project like `aw library` does (no --data-dir needed). A row that fails the schema is dropped.
 */
export async function appendUsage(project: string, row: LedgerRow): Promise<boolean> {
  if (checkSchema(ledgerSchema as JsonSchema, row).length > 0) return false;
  try {
    const dir = join(project, '.academic-helper', 'runs', row.run_id);
    await mkdir(dir, { recursive: true });
    await appendFile(join(dir, 'usage.jsonl'), `${JSON.stringify(row)}\n`, 'utf8');
    return true;
  } catch { return false; }
}
