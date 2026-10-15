import { Library } from './adapter.ts';
import { projectDirOr } from '../paths.ts';
import { LibraryError, errorMessage } from './types.ts';

const BOOLEAN_FLAGS = new Set(['--json', '--check', '--text', '--all']);
const VALUE_FLAGS = new Set(['--source', '--pages', '--printed', '--page', '--run', '--claim']);

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

/**
 * `aw library <status|list|toc|read|get>`: one adapter over the Trove and PageIndex routes. Everything
 * prints JSON on stdout (read also takes --text for the plain page layout). Exit codes: 0 ok, 2 usage,
 * 3 config, 4 the answering route failed (there is no fallback to the other route).
 */
export async function runLibraryCli(argv: string[], io: LibraryIo = processIo): Promise<number> {
  const print = (value: unknown): void => io.out(`${JSON.stringify(value)}\n`);
  const [subcommand, ...rest] = argv;
  try {
    const { positional, flags } = parse(rest);
    const library = new Library(projectDirOr());
    const source = flags.get('--source');
    const requireSource = (): string => {
      if (typeof source !== 'string' || !source) throw new LibraryError('usage', `ERROR library ${subcommand}: --source <id> is required`);
      return source;
    };
    if (subcommand === 'status') {
      print(await library.status(flags.has('--check')));
    } else if (subcommand === 'list') {
      print(await library.list());
    } else if (subcommand === 'toc') {
      print(await library.toc(requireSource()));
    } else if (subcommand === 'read' || subcommand === 'get') {
      const all = flags.has('--all') || positional.includes('all');
      const page = flags.get('--page');
      const output = await library.read({
        source: requireSource(),
        all: all || (subcommand === 'get' && typeof page !== 'string' && typeof flags.get('--pages') !== 'string' && typeof flags.get('--printed') !== 'string'),
        pages: typeof flags.get('--pages') === 'string' ? flags.get('--pages') as string : (typeof page === 'string' ? page : undefined),
        printed: typeof flags.get('--printed') === 'string' ? flags.get('--printed') as string : undefined,
      });
      const { raw: _raw, ...visible } = output;
      if (flags.has('--text')) io.out(`${output.pages.map((entry) => `── Page ${entry.trove_page} ──\n${entry.text}`).join('\n')}\n`);
      else print(visible);
    } else {
      throw new LibraryError('usage', 'ERROR library: expected aw library status|list|toc|read|get');
    }
    return 0;
  } catch (error) {
    io.err(`${errorMessage(error)}\n`);
    return exitCodeFor(error);
  }
}
