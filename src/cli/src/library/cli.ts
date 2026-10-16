import { Library } from './adapter.ts';
import { runBackfill, type BackfillSelector } from './backfill.ts';
import { PLAIN_ID } from './backends.ts';
import type { LibraryConfig } from './config.ts';
import { runEvalCli } from './eval/cli.ts';
import { childEnv, pilibHealth, readInstalled, readPinned, resolveHome, runInstall, runUninstall, matchesPinned, type Tier } from './install.ts';
import { ensureCanIndex, indexBook, indexOutput, makeIndexer, newRunId, SUMMARY_MODES, type IndexRequest, type SummaryMode } from './index-cmd.ts';
import { formatReport, reportFor } from './report.ts';
import { loadSpec, runShadowWorker, shadowModeFrom, workerSettings } from './shadow.ts';
import { recordVerdict, settlePending } from './verdict.ts';
import { dataDir, projectDirOr } from '../paths.ts';
import { pluginRoot } from '../pi.ts';
import thresholds from '../../../thresholds.json' with { type: 'json' };
import { LibraryError, errorMessage } from './types.ts';

const BOOLEAN_FLAGS = new Set(['--json', '--check', '--text', '--all', '--settle', '--dry-run', '--yes', '--no-fallback', '--no-verify', '--shelf-current', '--skip-existing', '--purge-library']);
const VALUE_FLAGS = new Set(['--source', '--pages', '--printed', '--page', '--run', '--claim', '--lookup', '--verdict', '--corrected-page', '--support-quote', '--paragraph', '--eval',
  '--trove-id', '--book-id', '--summaries', '--max-calls', '--model', '--concurrency', '--tier', '--python', '--ids', '--limit']);

// Ids that an agent writes into a shell command line. Anything else is refused before it is used (a defence in depth:
// the agent single-quotes them too), so an id can never carry a command.
const ID_FLAGS = new Set(['--source', '--lookup', '--paragraph', '--run', '--claim', '--eval', '--trove-id', '--book-id']);

type Parsed = { positional: string[]; flags: Map<string, string | true> };

function parse(argv: string[]): Parsed {
  const positional: string[] = [];
  const flags = new Map<string, string | true>();
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index] as string;
    if (BOOLEAN_FLAGS.has(arg)) flags.set(arg, true);
    else if (VALUE_FLAGS.has(arg)) {
      const value = argv[index + 1];
      if (value === undefined) throw new LibraryError('usage', `ERROR library: ${arg} needs a value`);
      if (ID_FLAGS.has(arg) && !PLAIN_ID.test(value)) throw new LibraryError('usage', `ERROR library: ${arg} must be a plain id (letters, digits and . _ # : - only)`);
      flags.set(arg, value);
      index += 1;
    } else if (arg.startsWith('--')) throw new LibraryError('usage', `ERROR library: unknown option ${arg}`);
    else positional.push(arg);
  }
  return { positional, flags };
}

export type LibraryIo = { out: (text: string) => void; err: (text: string) => void };
const processIo: LibraryIo = { out: (text) => { process.stdout.write(text); }, err: (text) => { process.stderr.write(text); } };

function exitCodeFor(error: unknown): number {
  if (!(error instanceof LibraryError)) return 4;
  if (error.code === 'usage') return 2;
  if (error.code === 'config') return 3;
  return 4;
}

/** POSIX single quotes: nothing inside is expanded by a shell; an embedded ' is written as '\\''. */
export function shellQuote(value: string): string { return `'${value.replace(/'/gu, `'\\''`)}'`; }

function flagText(flags: Map<string, string | true>, name: string): string | undefined {
  const value = flags.get(name);
  return typeof value === 'string' ? value : undefined;
}

function wholeFlag(flags: Map<string, string | true>, name: string, max: number): number | undefined {
  const raw = flagText(flags, name);
  if (raw === undefined) return undefined;
  if (!/^[1-9]\d{0,8}$/u.test(raw) || Number(raw) > max) throw new LibraryError('usage', `ERROR library: ${name} must be a whole number from 1 to ${max}`);
  return Number(raw);
}

function summariesFlag(flags: Map<string, string | true>): SummaryMode {
  const raw = flagText(flags, '--summaries') ?? 'gemini';
  if (!(SUMMARY_MODES as readonly string[]).includes(raw)) throw new LibraryError('usage', 'ERROR library: --summaries must be gemini, hints or none');
  return raw as SummaryMode;
}

function plugin(what: string): string {
  try { return pluginRoot(); } catch { throw new LibraryError('config', `ERROR library ${what}: cannot find the plugin's own folder. Run aw from the plugin (<plugin>/bin/aw).`); }
}

function dataFolder(): string | null {
  try { return dataDir(); } catch { return null; }
}

/** What `status` adds about the PageIndex command: where it came from, what the built-in helper is, and with --check what the command can do. */
async function pageindexStatus(config: LibraryConfig, project: string, env: NodeJS.ProcessEnv, check: boolean): Promise<Record<string, unknown>> {
  const home = config.pageindexHome ?? resolveHome(env, dataFolder());
  const installed = home ? readInstalled(home) : null;
  const warnings: string[] = [];
  let pinned: ReturnType<typeof readPinned> | null = null;
  try { pinned = readPinned(pluginRoot()); } catch { pinned = null; }
  const matches = installed && pinned ? matchesPinned(installed, pinned) : null;
  if (installed && matches === false) warnings.push('The built-in PageIndex helper is older than the one this plugin version pins: run the install again to update it.');
  const info: Record<string, unknown> = {
    pageindex_source: config.pageindexSource,
    pageindex_home: home,
    installed: installed
      ? { installed: true, tier: installed.tier, python: installed.python, pilib_version: installed.pilib_version, pageindex_commit: installed.pageindex_commit, litellm: installed.litellm ?? null, installed_at: installed.installed_at, matches_pinned: matches, pinned_pilib_version: pinned?.pilib_version ?? null }
      : { installed: false },
  };
  if (check) {
    const cleaned = childEnv(env);
    const health = await pilibHealth(config.pageindexCommand, cleaned, thresholds.library.timeoutMs.check);
    let indexTrove = false;
    try { await ensureCanIndex({ project, config, command: config.pageindexCommand, source: config.pageindexSource, env, now: () => new Date() }); indexTrove = true; } catch { indexTrove = false; }
    info.pilib = health
      ? { ok: true, pilib_version: health.pilib_version, tier: health.tier, python: health.python, index_trove: indexTrove }
      : { ok: false, pilib_version: null, tier: null, python: null, index_trove: indexTrove };
    if (!indexTrove) warnings.push('The PageIndex command found here cannot index books (it is older than this plugin, or it is not reachable). It also cannot read books indexed by the built-in helper. Install the built-in helper, or update pilib on the computer that holds your library.');
  }
  info.warnings = warnings;
  return info;
}

/**
 * `aw library <status|list|toc|read|get|verdict|report|install|uninstall|index|backfill|eval>`: one adapter over the Trove and PageIndex
 * routes, with a retrieval ledger, plus the built-in PageIndex helper (install, index, backfill) and the blind evaluation (eval).
 * Everything prints JSON on stdout except `report` (plain words; --json for JSON) and `read --text`. Exit codes: 0 ok, 2 usage, 3 config,
 * 4 the answering route (or the index run) failed (there is no fallback to the other route). `_shadow` is the internal background
 * worker and is not for people.
 */
export async function runLibraryCli(argv: string[], io: LibraryIo = processIo): Promise<number> {
  const print = (value: unknown): void => io.out(`${JSON.stringify(value)}\n`);
  const [subcommand, ...rest] = argv;
  try {
    // The evaluation has its own flags and its own exit codes (the same four).
    if (subcommand === 'eval') return await runEvalCli(rest, { out: io.out, err: io.err });
    const { positional, flags } = parse(rest);
    if (subcommand === '_shadow') {
      // The detached worker: it has nobody to report to, so it always exits 0 and its result is a ledger row.
      const spec = positional[0] ? await loadSpec(positional[0]) : null;
      if (spec) await runShadowWorker(spec, new Library(spec.project, process.env), workerSettings(process.env));
      return 0;
    }
    if (subcommand === 'verdict') {
      const lookup = flagText(flags, '--lookup');
      const word = flagText(flags, '--verdict')?.toUpperCase();
      if (!lookup) throw new LibraryError('usage', 'ERROR library verdict: --lookup <id> is required (the lookup_id from aw library read)');
      if (word !== 'PASS' && word !== 'FAIL') throw new LibraryError('usage', 'ERROR library verdict: --verdict must be PASS or FAIL');
      const corrected = flagText(flags, '--corrected-page');
      if (corrected !== undefined && !/^[1-9]\d{0,5}$/u.test(corrected)) throw new LibraryError('usage', 'ERROR library verdict: --corrected-page must be a page number');
      const cited = flagText(flags, '--page');
      if (cited !== undefined && !/^[1-9]\d{0,5}$/u.test(cited)) throw new LibraryError('usage', 'ERROR library verdict: --page must be a page number');
      const quote = flagText(flags, '--support-quote') ?? '';
      const paragraph = flagText(flags, '--paragraph') ?? null;
      const { row, append } = await recordVerdict(projectDirOr(), {
        lookup, verdict: word, correctedPage: corrected === undefined ? null : Number(corrected),
        quote, paragraph, run: flagText(flags, '--run') ?? null,
        page: cited === undefined ? null : Number(cited),
      });
      // A ledger problem never changes the auditor's verdict: say so on stderr, with the command to try again, and still exit 0.
      if (!append.ok) {
        // For a person to read and run, never for a program to execute: every argument is single-quoted (a ' becomes '\''),
        // so the quote text (which comes from untrusted page text) cannot expand or run anything in a shell.
        const args: Array<[string, string]> = [['--lookup', lookup], ['--verdict', word],
          ...(corrected === undefined ? [] : [['--corrected-page', corrected] as [string, string]]), ...(cited === undefined ? [] : [['--page', cited] as [string, string]]),
          ['--support-quote', quote], ...(paragraph === null ? [] : [['--paragraph', paragraph] as [string, string]]),
          ...(flagText(flags, '--run') === undefined ? [] : [['--run', flagText(flags, '--run') as string] as [string, string]])];
        const retry = `aw library verdict ${args.map(([name, value]) => `${name} ${shellQuote(value)}`).join(' ')}`;
        io.err(`NOTE library verdict: not recorded in the ledger (${append.reason}). This is a hint for a person, not for a program: to record it, run:\n  ${retry}\n`);
      }
      print({ ok: append.ok, lookup_id: row.lookup_id, verdict: row.verdict, shadow_supports: row.shadow_supports, shadow_supports_reason: row.shadow_supports_reason });
      return 0;
    }
    if (subcommand === 'report') {
      const project = projectDirOr();
      if (flags.has('--settle')) await settlePending(project);
      const report = await reportFor(project, flagText(flags, '--run') ?? null, { eval: flagText(flags, '--eval') ?? null });
      io.out(flags.has('--json') ? `${JSON.stringify(report)}\n` : formatReport(report));
      return 0;
    }
    if (subcommand === 'install') {
      const tier = flagText(flags, '--tier');
      if (tier !== undefined && tier !== 'core' && tier !== 'structure') throw new LibraryError('usage', 'ERROR library install: --tier must be core or structure');
      const python = flagText(flags, '--python');
      if (python !== undefined && (python.startsWith('-') || python.trim() === '')) throw new LibraryError('usage', 'ERROR library install: --python must be the path of a Python program');
      print(await runInstall({ tier: tier as Tier | undefined, dryRun: flags.has('--dry-run'), yes: flags.has('--yes'), python, dataDir: dataFolder(), pluginRoot: plugin('install'), env: process.env }));
      return 0;
    }
    if (subcommand === 'uninstall') {
      print(await runUninstall({ yes: flags.has('--yes'), purgeLibrary: flags.has('--purge-library'), dataDir: dataFolder(), env: process.env }));
      return 0;
    }
    if (subcommand === 'index') {
      const troveId = flagText(flags, '--trove-id');
      if (!troveId) throw new LibraryError('usage', 'ERROR library index: --trove-id <id> is required (the Trove item to index)');
      const project = projectDirOr();
      const indexer = makeIndexer(project, process.env);
      const request: IndexRequest = {
        troveId, bookId: flagText(flags, '--book-id'), summaries: summariesFlag(flags), noFallback: flags.has('--no-fallback'),
        maxCalls: wholeFlag(flags, '--max-calls', thresholds.library.index.maxCalls), model: flagText(flags, '--model'), concurrency: wholeFlag(flags, '--concurrency', 64),
        dryRun: flags.has('--dry-run'), yes: flags.has('--yes'), run: flagText(flags, '--run') ?? newRunId(indexer.now()), verify: !flags.has('--no-verify'),
      };
      const outcome = await indexBook(indexer, request);
      print(indexOutput(indexer, outcome, request));
      if (!outcome.ok) { io.err(`ERROR library index: ${outcome.message ?? 'the book was not indexed'}\n`); return 4; }
      return 0;
    }
    if (subcommand === 'backfill') {
      const project = projectDirOr();
      const ids = flagText(flags, '--ids');
      const picked = [ids !== undefined, flags.has('--all'), flags.has('--shelf-current')].filter(Boolean).length;
      if (picked !== 1) throw new LibraryError('usage', 'ERROR library backfill: choose which books: --shelf-current (the active Trove shelf), --ids a,b,c, or --all (the whole library)');
      let selector: BackfillSelector = { kind: 'all' };
      if (ids !== undefined) {
        const list = ids.split(',').map((id) => id.trim()).filter(Boolean);
        if (list.length === 0 || !list.every((id) => PLAIN_ID.test(id))) throw new LibraryError('usage', 'ERROR library backfill: --ids must be a comma-separated list of plain ids (letters, digits and . _ # : - only)');
        selector = { kind: 'ids', ids: list };
      } else if (flags.has('--shelf-current')) selector = { kind: 'shelf' };
      const indexer = makeIndexer(project, process.env);
      const { output, exit } = await runBackfill(indexer, {
        selector, limit: wholeFlag(flags, '--limit', 100000), skipExisting: flags.has('--skip-existing'), dryRun: flags.has('--dry-run'), yes: flags.has('--yes'),
        summaries: summariesFlag(flags), noFallback: flags.has('--no-fallback'), maxCalls: wholeFlag(flags, '--max-calls', thresholds.library.index.maxCalls), model: flagText(flags, '--model'),
        run: flagText(flags, '--run') ?? newRunId(indexer.now(), 'backfill'), verify: !flags.has('--no-verify'),
      });
      print(output);
      if (exit !== 0 && typeof output.error === 'string') io.err(`ERROR library backfill: ${output.error}\n`);
      return exit;
    }
    const library = new Library(projectDirOr(), process.env, { shadow: shadowModeFrom(process.env) });
    const source = flags.get('--source');
    const requireSource = (): string => {
      if (typeof source !== 'string' || !source) throw new LibraryError('usage', `ERROR library ${subcommand}: --source <id> is required`);
      return source;
    };
    if (subcommand === 'status') {
      print({ ...await library.status(flags.has('--check')), ...await pageindexStatus(library.config, projectDirOr(), process.env, flags.has('--check')) });
    } else if (subcommand === 'list') {
      const listed = await library.list({ run: flagText(flags, '--run'), claim: flagText(flags, '--claim') });
      if (listed.skipped_invalid_ids > 0) io.err(`NOTE library list: ${listed.skipped_invalid_ids} entries skipped: their ids are not plain (letters, digits and . _ # : - only), so they cannot be used as sources\n`);
      print(listed);
    } else if (subcommand === 'toc') {
      print(await library.toc(requireSource(), { run: flagText(flags, '--run'), claim: flagText(flags, '--claim') }));
    } else if (subcommand === 'read' || subcommand === 'get') {
      const all = flags.has('--all') || positional.includes('all');
      const page = flags.get('--page');
      const output = await library.read({
        source: requireSource(),
        all: all || (subcommand === 'get' && typeof page !== 'string' && typeof flags.get('--pages') !== 'string' && typeof flags.get('--printed') !== 'string'),
        pages: typeof flags.get('--pages') === 'string' ? flags.get('--pages') as string : (typeof page === 'string' ? page : undefined),
        printed: typeof flags.get('--printed') === 'string' ? flags.get('--printed') as string : undefined,
        op: subcommand,
        run: flagText(flags, '--run'),
        claim: flagText(flags, '--claim'),
      });
      const { raw: _raw, ...visible } = output;
      if (flags.has('--text')) io.out(`${output.pages.map((entry) => `── Page ${entry.trove_page} ──\n${entry.text}`).join('\n')}\n`);
      else print(visible);
    } else {
      throw new LibraryError('usage', 'ERROR library: expected aw library status|list|toc|read|get|verdict|report|install|uninstall|index|backfill|eval');
    }
    return 0;
  } catch (error) {
    io.err(`${errorMessage(error)}\n`);
    return exitCodeFor(error);
  }
}
