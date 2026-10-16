import { existsSync } from 'node:fs';
import { readFile, rm } from 'node:fs/promises';
import { randomBytes } from 'node:crypto';
import { isAbsolute, join, relative, resolve } from 'node:path';
import { projectDirOr } from '../../paths.ts';
import { LibraryError, errorMessage } from '../types.ts';
import { awCommandFor, makeAwRunner } from './aw.ts';
import { EVAL_ROOT, evalPaths, readJson, writeText, readValid, requireProject, runFile, validate, writeJson } from './files.ts';
import { importJudgments } from './judgments.ts';
import { evalLimits } from './limits.ts';
import { buildPairs, routeLeak } from './pairs.ts';
import { buildPlan } from './plan.ts';
import { archiveGeneration } from './reset.ts';
import { runAll } from './runner.ts';
import { renderMarkdown, unblind } from './unblind.ts';
import type { Engine, EvalIo, Pairs, Plan, Route, Run } from './types.ts';

const BOOLEAN_FLAGS = new Set(['--json', '--stdin', '--force', '--partial', '--no-resolve', '--reset']);
const VALUE_FLAGS = new Set(['--eval', '--article', '--n', '--seed', '--claims', '--routes', '--engine', '--parallel', '--model', '--file', '--out', '--template', '--timeout-s']);
const SUBCOMMANDS = ['plan', 'run', 'pairs', 'page', 'import', 'unblind', 'status'];

type Flags = Map<string, string | true>;

function parse(argv: string[]): Flags {
  const flags: Flags = new Map();
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index] as string;
    if (BOOLEAN_FLAGS.has(arg)) flags.set(arg, true);
    else if (VALUE_FLAGS.has(arg)) {
      const value = argv[index + 1];
      if (value === undefined) throw new LibraryError('usage', `ERROR library eval: ${arg} needs a value`);
      flags.set(arg, value);
      index += 1;
    } else throw new LibraryError('usage', `ERROR library eval: unknown option or argument ${arg}`);
  }
  return flags;
}

function text(flags: Flags, name: string): string | undefined { const value = flags.get(name); return typeof value === 'string' ? value : undefined; }

function wholeNumber(flags: Flags, name: string, fallback: number, max: number): number {
  const raw = text(flags, name);
  if (raw === undefined) return fallback;
  if (!/^[1-9]\d{0,5}$/u.test(raw) || Number(raw) > max) throw new LibraryError('usage', `ERROR library eval: ${name} must be a whole number from 1 to ${max}`);
  return Number(raw);
}

function exitCodeFor(error: unknown): number {
  if (!(error instanceof LibraryError)) return 4;
  if (error.code === 'usage') return 2;
  if (error.code === 'config') return 3;
  return 4;
}

function routesFrom(flags: Flags): Route[] {
  const raw = text(flags, '--routes') ?? 'trove,pageindex';
  const routes = raw.split(',').map((part) => part.trim());
  if (routes.length !== 2 || routes[0] === routes[1] || !routes.every((route): route is Route => route === 'trove' || route === 'pageindex')) {
    throw new LibraryError('usage', 'ERROR library eval: --routes must name both libraries once, for example trove,pageindex');
  }
  return routes as Route[];
}

function engineFrom(flags: Flags): Engine {
  const engine = text(flags, '--engine') ?? 'claude';
  if (engine !== 'claude' && engine !== 'codex') throw new LibraryError('usage', 'ERROR library eval: --engine must be claude or codex');
  return engine;
}

function evalIdFrom(flags: Flags): string {
  const id = text(flags, '--eval');
  if (!id) throw new LibraryError('usage', 'ERROR library eval: --eval <id> is required');
  return id;
}

function newEvalId(project: string, now: Date): string {
  const stamp = now.toISOString().slice(0, 10).replaceAll('-', '');
  for (const letter of 'abcdefghijklmnopqrstuvwxyz') {
    const id = `ev-${stamp}-${letter}`;
    if (!existsSync(join(project, EVAL_ROOT, id))) return id;
  }
  throw new LibraryError('usage', 'ERROR library eval plan: 26 evaluations already exist today; pass --eval <id>');
}

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks).toString('utf8');
}

/**
 * `aw library eval <plan|run|pairs|page|import|unblind|status> --eval <id> ...`: a blind comparison of the two
 * libraries on the claims of an article. Everything under `.academic-helper/library-eval/<eval-id>/`. JSON on stdout
 * (unblind prints the plain-words report; --json for JSON). Exit codes: 0 ok, 2 usage, 3 config, 4 the step failed.
 * The judge sees only pairs.json; the key (sealed/mapping.json) is read by `unblind` alone, after judgments are imported.
 */
export async function runEvalCli(argv: string[], io: EvalIo): Promise<number> {
  const print = (value: unknown): void => io.out(`${JSON.stringify(value)}\n`);
  const [subcommand, ...rest] = argv;
  try {
    if (!subcommand || !SUBCOMMANDS.includes(subcommand)) throw new LibraryError('usage', `ERROR library eval: expected aw library eval ${SUBCOMMANDS.join('|')}`);
    const flags = parse(rest);
    const env = io.env ?? process.env;
    const project = io.project ?? projectDirOr();
    const now = (io.now ?? ((): Date => new Date()))();
    requireProject(project);

    if (subcommand === 'plan') {
      const evalId = text(flags, '--eval') ?? newEvalId(project, now);
      const paths = evalPaths(project, evalId);
      if (existsSync(paths.pairs) || existsSync(paths.judgments)) throw new LibraryError('usage', 'ERROR library eval plan: this evaluation already has pairs; start a new one with another --eval id');
      if (existsSync(paths.plan) && !flags.has('--force')) throw new LibraryError('usage', `ERROR library eval plan: ${evalId} already has a plan (--force replaces it)`);
      const routes = routesFrom(flags);
      const aw = makeAwRunner(project, awCommandFor(io, env), env);
      const plan = await buildPlan({
        project, evalId, article: text(flags, '--article'), n: wholeNumber(flags, '--n', Math.min(12, evalLimits.maxClaims), evalLimits.maxClaims),
        seed: text(flags, '--seed') ?? evalId, routes, claimsFile: text(flags, '--claims'), resolve: !flags.has('--no-resolve'), aw, now,
      });
      if (plan.claims.length === 0) throw new LibraryError('usage', `ERROR library eval plan: no usable claims found (skipped: ${JSON.stringify(plan.skipped)}); check that the draft has footnotes and the sources answer on both libraries`);
      // A replaced plan starts a new evaluation: runs of the old one are removed (they are also bound to the old plan by fingerprint).
      if (flags.has('--force')) await rm(paths.runsDir, { recursive: true, force: true });
      await writeJson(paths.plan, plan);
      print({ eval_id: evalId, claims: plan.claims.length, runs: plan.estimate.runs, estimated_usd: plan.estimate.usd, skipped: plan.skipped, plan: paths.plan });
      return 0;
    }

    const evalId = evalIdFrom(flags);
    const paths = evalPaths(project, evalId);

    if (subcommand === 'run') {
      const plan = await readValid<Plan>('plan', paths.plan, 'plan');
      const timeoutS = text(flags, '--timeout-s');
      const archived = flags.has('--reset') ? await archiveGeneration(paths, now) : null;
      if (archived) io.err(`NOTE library eval run: the old pairs, judgments and runs were moved to ${archived}\n`);
      const summary = await runAll({
        project, paths, plan, engine: engineFrom(flags), model: text(flags, '--model') ?? null,
        parallel: wholeNumber(flags, '--parallel', evalLimits.parallel, 8), routes: plan.routes, awCommand: awCommandFor(io, env), env,
        runTimeoutMs: io.runTimeoutMs ?? (timeoutS ? wholeNumber(flags, '--timeout-s', 1, 7200) * 1000 : evalLimits.runTimeoutMs), now: io.now ?? ((): Date => new Date()),
        progress: (line) => io.err(`${line}\n`),
      });
      print({ eval_id: evalId, ...summary, ...(archived ? { archived } : {}) });
      return 0;
    }

    if (subcommand === 'pairs') {
      const plan = await readValid<Plan>('plan', paths.plan, 'plan');
      const aw = makeAwRunner(project, awCommandFor(io, env), env);
      const { summary } = await buildPairs({ evalId, paths, plan, seed: text(flags, '--seed') ?? randomBytes(32).toString('hex'), aw, now, force: flags.has('--force') });
      print(summary);
      return 0;
    }

    if (subcommand === 'page') {
      const pairs = await readValid<Pairs>('pairs', paths.pairs, 'pairs');
      const template = text(flags, '--template') ?? (env.CLAUDE_PLUGIN_ROOT ? join(env.CLAUDE_PLUGIN_ROOT, 'skills', 'library-eval', 'references', 'judge-page.html') : null);
      if (!template || !existsSync(template)) throw new LibraryError('config', 'ERROR library eval page: no judging page template found; pass --template <file>');
      const html = await readFile(template, 'utf8');
      const slot = /(<script\b[^>]*\bid=["']pairs["'][^>]*>)([\s\S]*?)(<\/script>)/iu;
      if (!slot.test(html)) throw new LibraryError('config', 'ERROR library eval page: the template has no <script type="application/json" id="pairs"> slot');
      if (/trove|page-?index/iu.test(html.replace(slot, '$1$3'))) throw new LibraryError('config', 'ERROR library eval page: the template names a library; the judging page must not');
      const leak = routeLeak(pairs);
      if (leak) throw new LibraryError('config', `ERROR library eval page: pairs.json shows a library name at ${leak}`);
      const payload = JSON.stringify(pairs).replaceAll('<', '\\u003c').replaceAll('\u2028', '\\u2028').replaceAll('\u2029', '\\u2029');
      const out = text(flags, '--out') ? resolve(paths.root, text(flags, '--out') as string) : paths.judgeHtml;
      const inside = relative(paths.root, out);
      if (inside === '' || inside.startsWith('..') || isAbsolute(inside)) throw new LibraryError('usage', 'ERROR library eval page: --out must be a file inside the evaluation folder');
      await writeText(out, html.replace(slot, (_whole, open: string, _body: string, close: string) => `${open}${payload}${close}`));
      print({ eval_id: evalId, out, pairs: pairs.pairs.length });
      return 0;
    }

    if (subcommand === 'import') {
      const file = text(flags, '--file');
      if (!file && !flags.has('--stdin')) throw new LibraryError('usage', 'ERROR library eval import: give --file <judgments.json> or --stdin');
      let raw: unknown;
      try { raw = JSON.parse(file ? await readFile(file, 'utf8') : await (io.stdin ?? readStdin)()); }
      catch { throw new LibraryError('usage', 'ERROR library eval import: the judgments are not valid JSON'); }
      print(await importJudgments({ paths, evalId, raw, partial: flags.has('--partial'), now }));
      return 0;
    }

    if (subcommand === 'unblind') {
      const report = await unblind({ paths, force: flags.has('--force'), now });
      io.out(flags.has('--json') ? `${JSON.stringify(report)}\n` : renderMarkdown(report));
      return 0;
    }

    // status: progress only, no library names and no per-library results.
    const plan = await readJson(paths.plan);
    if (plan === null || validate('plan', plan).length > 0) throw new LibraryError('usage', `ERROR library eval status: no plan for ${evalId}`);
    const typed = plan as Plan;
    let finished = 0;
    let failed = 0;
    for (const claim of typed.claims) {
      for (const route of typed.routes) {
        const run = await readJson(runFile(paths, claim.id, route)) as Run | null;
        if (run && validate('run', run).length === 0) { if (run.status === 'ok') finished += 1; else failed += 1; }
      }
    }
    const pairs = await readJson(paths.pairs) as Pairs | null;
    const judgments = await readJson(paths.judgments) as { entries?: Array<{ pair_id: string }> } | null;
    const judgedIds = new Set((judgments?.entries ?? []).map((entry) => entry.pair_id));
    const built = pairs?.pairs.length ?? 0;
    const unblinded = existsSync(paths.reportJson);
    const stage = unblinded ? 'unblinded' : judgments && judgedIds.size >= built && built > 0 ? 'judged' : pairs ? 'paired' : finished + failed >= typed.claims.length * typed.routes.length ? 'located' : 'planned';
    print({
      eval_id: evalId, stage, claims: typed.claims.length,
      runs: { expected: typed.claims.length * typed.routes.length, finished, failed },
      pairs: { built, identical: pairs?.pairs.filter((pair) => pair.auto_same).length ?? 0 },
      judged: { done: judgedIds.size, of: built }, unblinded,
    });
    return 0;
  } catch (error) {
    io.err(`${errorMessage(error)}\n`);
    return exitCodeFor(error);
  }
}
