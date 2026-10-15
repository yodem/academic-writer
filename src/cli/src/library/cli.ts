import { Library } from './adapter.ts';
import { formatReport, reportFor } from './report.ts';
import { loadSpec, runShadowWorker, shadowModeFrom, workerSettings } from './shadow.ts';
import { recordVerdict, settlePending } from './verdict.ts';
import { projectDirOr } from '../paths.ts';
import { LibraryError, errorMessage } from './types.ts';

const BOOLEAN_FLAGS = new Set(['--json', '--check', '--text', '--all', '--settle']);
const VALUE_FLAGS = new Set(['--source', '--pages', '--printed', '--page', '--run', '--claim', '--lookup', '--verdict', '--corrected-page', '--support-quote', '--paragraph']);

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

function flagText(flags: Map<string, string | true>, name: string): string | undefined {
  const value = flags.get(name);
  return typeof value === 'string' ? value : undefined;
}

/**
 * `aw library <status|list|toc|read|get|verdict|report>`: one adapter over the Trove and PageIndex routes,
 * with a retrieval ledger. Everything prints JSON on stdout except `report` (plain words; --json for JSON)
 * and `read --text`. Exit codes: 0 ok, 2 usage, 3 config, 4 the answering route failed (there is no
 * fallback to the other route). `_shadow` is the internal background worker and is not for people.
 */
export async function runLibraryCli(argv: string[], io: LibraryIo = processIo): Promise<number> {
  const print = (value: unknown): void => io.out(`${JSON.stringify(value)}\n`);
  const [subcommand, ...rest] = argv;
  try {
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
      const { row, append } = await recordVerdict(projectDirOr(), {
        lookup, verdict: word, correctedPage: corrected === undefined ? null : Number(corrected),
        quote: flagText(flags, '--support-quote') ?? '', paragraph: flagText(flags, '--paragraph') ?? null, run: flagText(flags, '--run') ?? null,
        page: flagText(flags, '--page') === undefined ? null : Number(flagText(flags, '--page')),
      });
      // A ledger problem never changes the auditor's verdict: say so on stderr and still exit 0.
      if (!append.ok) io.err(`NOTE library verdict: not recorded in the ledger (${append.reason})\n`);
      print({ ok: append.ok, lookup_id: row.lookup_id, verdict: row.verdict, shadow_supports: row.shadow_supports, shadow_supports_reason: row.shadow_supports_reason });
      return 0;
    }
    if (subcommand === 'report') {
      const project = projectDirOr();
      if (flags.has('--settle')) await settlePending(project);
      const report = await reportFor(project, flagText(flags, '--run') ?? null);
      io.out(flags.has('--json') ? `${JSON.stringify(report)}\n` : formatReport(report));
      return 0;
    }
    const library = new Library(projectDirOr(), process.env, { shadow: shadowModeFrom(process.env) });
    const source = flags.get('--source');
    const requireSource = (): string => {
      if (typeof source !== 'string' || !source) throw new LibraryError('usage', `ERROR library ${subcommand}: --source <id> is required`);
      return source;
    };
    if (subcommand === 'status') {
      print(await library.status(flags.has('--check')));
    } else if (subcommand === 'list') {
      print(await library.list({ run: flagText(flags, '--run'), claim: flagText(flags, '--claim') }));
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
      throw new LibraryError('usage', 'ERROR library: expected aw library status|list|toc|read|get|verdict|report');
    }
    return 0;
  } catch (error) {
    io.err(`${errorMessage(error)}\n`);
    return exitCodeFor(error);
  }
}
