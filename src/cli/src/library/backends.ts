import thresholds from '../../../thresholds.json' with { type: 'json' };
import { runCommand, type CommandScope } from './exec.ts';
import { formatPageRanges, parseBanners } from './pages.ts';
import { LibraryError, type BookInfo, type LibraryBackend, type PageText, type RawRead, type TocEntry, type TocResult } from './types.ts';

export type BackendOptions = { command: string[]; env?: NodeJS.ProcessEnv; timeoutMs: number; /** Timeout of a whole-book read (`all`); defaults to timeoutMs. */ readAllTimeoutMs?: number; /** The project folder: the child runs there, not in the caller's directory. */ cwd?: string; /** Commands of one lookup that must stop together (the shadow worker). */ scope?: CommandScope };
const limits = thresholds.library;

/**
 * The ids an agent may write into a shell command line (source, lookup, paragraph, run, claim). Ids are checked here, where
 * they enter the system (library listings, evidence building) and again by `aw library` when they come back as arguments.
 */
export const PLAIN_ID = /^[A-Za-z0-9_.#:-]+$/u;
export function isPlainId(id: string): boolean { return PLAIN_ID.test(id); }

export type EnvKind = 'pageindex' | 'trove' | 'install';

const BASE_NAMES = new Set(['PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LANGUAGE', 'TMPDIR', 'TEMP', 'TMP', 'TERM', 'SHELL', 'TZ', 'SSH_AUTH_SOCK',
  'SYSTEMROOT', 'SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'PROGRAMDATA']);
const BASE_PREFIXES = ['LC_', 'XDG_'];
const TROVE_PREFIXES = ['TROVE_', 'CANDLEKEEP_', 'CK_'];
const INSTALL_NAMES = new Set(['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'no_proxy', 'all_proxy', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE']);
// A plugin variable that holds a credential is never passed on by this list (AW_* names are allowed otherwise: AW_LIBRARY_*, AW_PAGEINDEX_HOME, AW_TROVE_COMMAND).
const SECRET_NAME = /(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)/iu;
const VALID_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/u;
/** Names the researcher lists in AW_LIBRARY_PASS_ENV (comma separated) are passed on whatever they are called: an explicit opt-in. */
export const PASS_ENV = 'AW_LIBRARY_PASS_ENV';

/**
 * The environment of a command that `aw library` starts for a lookup or an index run: an allow-list, never the whole environment.
 * The PageIndex command may be an ssh wrapper to another computer, and Trove is a program of its own: neither gets the Gemini key, Claude or
 * OpenAI keys, tokens or secrets that happen to be set where aw runs. A command that needs a variable gets it from its own environment, or the
 * researcher names it in AW_LIBRARY_PASS_ENV.
 */
export function allowedEnv(env: NodeJS.ProcessEnv, kind: EnvKind = 'pageindex'): NodeJS.ProcessEnv {
  const out: NodeJS.ProcessEnv = {};
  const listed = new Set((env[PASS_ENV] ?? '').split(',').map((name) => name.trim()).filter((name) => VALID_NAME.test(name)));
  for (const [name, value] of Object.entries(env)) {
    if (value === undefined) continue;
    const allowed = BASE_NAMES.has(name) || BASE_PREFIXES.some((prefix) => name.startsWith(prefix))
      || (name.startsWith('AW_') && !SECRET_NAME.test(name))
      || (kind === 'trove' && TROVE_PREFIXES.some((prefix) => name.startsWith(prefix)))
      || (kind === 'install' && (INSTALL_NAMES.has(name) || name.startsWith('PIP_')))
      || listed.has(name);
    if (allowed) out[name] = value;
  }
  return out;
}

function parseJson(text: string, what: string): unknown {
  try { return JSON.parse(text); } catch { throw new LibraryError('parse', `ERROR library: ${what} did not return JSON`); }
}
function asRecord(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}
function text(value: unknown): string { return typeof value === 'string' ? value : ''; }
function whole(value: unknown): number | null { return typeof value === 'number' && Number.isInteger(value) ? value : null; }

// The Trove table of contents names the book on the line before `ID: <id>` (the bold-line heuristic
// misreads books whose first bold line is a list number).
export function titleFromToc(toc: string): string | undefined {
  const lines = toc.split('\n').map((l) => l.replace(/^=+|=+$/gu, '').trim()).filter((l) => l && !/^=+$/u.test(l));
  const idLine = lines.findIndex((l) => l.startsWith('ID:'));
  const candidate = idLine > 0 ? lines[idLine - 1] : undefined;
  return candidate?.replace(/^=+\s*|\s*=+$/gu, '').trim() || undefined;
}

/** Trove through its `trove` command line. Pages are Trove pages (the canonical space). */
export class TroveBackend implements LibraryBackend {
  readonly route = 'trove' as const;
  constructor(private readonly options: BackendOptions) {}

  private run(args: string[], timeoutMs: number = this.options.timeoutMs): Promise<string> {
    return runCommand(this.options.command, args, { timeoutMs, maxBuffer: limits.maxBufferBytes, env: this.options.env, cwd: this.options.cwd, scope: this.options.scope });
  }

  /** The active shelf of this project, so a listing is not the whole library. Best effort: no shelf means none. */
  private async activeShelf(): Promise<string | undefined> {
    try {
      const out = (await this.run(['shelf', 'current'])).trim();
      if (!out || /^no active shelf/iu.test(out)) return undefined;
      const named = out.match(/^(?:active shelf|shelf)\s*[:=]\s*(.+)$/imu)?.[1];
      const line = (named ?? out.split('\n')[0] ?? '').trim();
      return line || undefined;
    } catch { return undefined; }
  }

  async list(): Promise<BookInfo[]> {
    const shelf = await this.activeShelf();
    const raw = asRecord(parseJson(await this.run(['items', 'list', ...(shelf ? ['--shelf', shelf] : []), '--json']), 'trove items list'));
    const items = Array.isArray(raw?.items) ? raw.items : [];
    return items.flatMap((item): BookInfo[] => {
      const record = asRecord(item);
      return record && text(record.id) ? [{ id: text(record.id), title: text(record.title), author: text(record.author), pageCount: whole(record.pageCount) }] : [];
    });
  }

  async toc(book: string): Promise<TocResult> {
    const raw = asRecord(parseJson(await this.run(['items', 'toc', book, '--json']), 'trove items toc'));
    const first = Array.isArray(raw?.items) ? asRecord(raw.items[0]) : undefined;
    const entries: TocEntry[] = (Array.isArray(first?.toc) ? first.toc : []).flatMap((entry): TocEntry[] => {
      const record = asRecord(entry);
      const page = whole(record?.page);
      return record && page !== null ? [{ title: text(record.title), page, endPage: null, level: whole(record.level) ?? 1 }] : [];
    });
    return { title: text(first?.title) || await this.title(book), toc: entries };
  }

  async title(book: string): Promise<string | undefined> {
    try { return titleFromToc(await this.run(['items', 'toc', book])); } catch { return undefined; }
  }

  async read(book: string, pages: number[] | 'all'): Promise<RawRead> {
    const args = pages === 'all' ? ['items', 'read', `${book}:all`] : ['items', 'read', book, '--pages', formatPageRanges(pages)];
    const raw = await this.run(args, pages === 'all' ? this.options.readAllTimeoutMs ?? this.options.timeoutMs : this.options.timeoutMs);
    const parsed = parseBanners(raw);
    return { pages: parsed.pages, raw, title: parsed.header[0], pageCount: parsed.pageCount };
  }
}

export type PilibMeta = { book_id: string; title: string; n_pages: number | null; origin: Record<string, unknown>; trove_id: string | null; pagemap: number[] | null };
export type PilibCatalogEntry = { title: string; author: string; n_pages: number | null };

/** PageIndex through a `pilib`-style command. Books are library ids; pages are the library's own pages. */
export class PageIndexBackend implements LibraryBackend {
  readonly route = 'pageindex' as const;
  private catalogCache: Map<string, PilibCatalogEntry> | undefined;
  private readonly metaCache = new Map<string, PilibMeta | null>();
  private jsonRead: boolean | undefined;
  constructor(private readonly options: BackendOptions) {}

  private run(args: string[], timeoutMs: number = this.options.timeoutMs): Promise<string> {
    return runCommand(this.options.command, args, { timeoutMs, maxBuffer: limits.maxBufferBytes, env: this.options.env, cwd: this.options.cwd, scope: this.options.scope });
  }

  async catalog(): Promise<Map<string, PilibCatalogEntry>> {
    if (this.catalogCache) return this.catalogCache;
    const raw = asRecord(parseJson(await this.run(['catalog']), 'pilib catalog')) ?? {};
    const map = new Map<string, PilibCatalogEntry>();
    for (const [id, value] of Object.entries(raw)) {
      const record = asRecord(value);
      if (record) map.set(id, { title: text(record.title), author: text(record.author), n_pages: whole(record.n_pages) });
    }
    this.catalogCache = map;
    return map;
  }

  /** `pilib meta <book>`; null when this pilib has no meta command or the book is unknown. */
  async meta(book: string): Promise<PilibMeta | null> {
    if (this.metaCache.has(book)) return this.metaCache.get(book) ?? null;
    let meta: PilibMeta | null = null;
    try {
      const raw = asRecord(parseJson(await this.run(['meta', book]), 'pilib meta'));
      if (raw) {
        const pagemap = Array.isArray(raw.pagemap) && raw.pagemap.every((n) => Number.isInteger(n)) ? raw.pagemap as number[] : null;
        meta = { book_id: text(raw.book_id) || book, title: text(raw.title), n_pages: whole(raw.n_pages), origin: asRecord(raw.origin) ?? {}, trove_id: text(raw.trove_id) || null, pagemap };
      }
    } catch (error) { if (error instanceof LibraryError && (error.code === 'timeout' || error.code === 'spawn')) throw error; }
    this.metaCache.set(book, meta);
    return meta;
  }

  async list(): Promise<BookInfo[]> {
    return [...(await this.catalog())].map(([id, entry]) => ({ id, title: entry.title, author: entry.author, pageCount: entry.n_pages }));
  }

  async toc(book: string): Promise<TocResult> {
    const raw = asRecord(parseJson(await this.run(['tree', book]), 'pilib tree'));
    const entries: TocEntry[] = [];
    const walk = (nodes: unknown, level: number): void => {
      if (!Array.isArray(nodes)) return;
      for (const node of nodes) {
        const record = asRecord(node);
        const start = whole(record?.start_index);
        if (record && start !== null) entries.push({ title: text(record.title), page: start, endPage: whole(record.end_index), level });
        walk(record?.nodes, level + 1);
      }
    };
    walk(raw?.structure, 1);
    return { title: text(raw?.title) || undefined, toc: entries };
  }

  async title(book: string): Promise<string | undefined> {
    try { return (await this.catalog()).get(book)?.title || undefined; } catch { return undefined; }
  }

  async read(book: string, pages: number[] | 'all'): Promise<RawRead> {
    if (this.jsonRead !== false) {
      try {
        const spec = pages === 'all' ? 'all' : formatPageRanges(pages);
        const raw = asRecord(parseJson(await this.run(['read', book, spec, '--json'], this.readTimeout(pages)), 'pilib read'));
        const list = Array.isArray(raw?.pages) ? raw.pages : undefined;
        if (!list) throw new LibraryError('parse', 'ERROR library: pilib read --json returned no pages');
        this.jsonRead = true;
        return { pages: list.flatMap((entry): PageText[] => {
          const record = asRecord(entry);
          const page = whole(record?.page);
          return record && page !== null ? [{ page, text: text(record.content) }] : [];
        }) };
      } catch (error) {
        // An older pilib rejects --json (argparse exit 2); fall back to its 10-page plain reads.
        const old = error instanceof LibraryError && error.code === 'exit' && /unrecognized arguments/iu.test(error.stderr);
        if (!old) throw error;
        this.jsonRead = false;
      }
    }
    return { pages: await this.readPlain(book, pages) };
  }

  /** A whole-book read gets the longer timeout; page ranges keep the lookup timeout. */
  private readTimeout(pages: number[] | 'all'): number {
    return pages === 'all' ? this.options.readAllTimeoutMs ?? this.options.timeoutMs : this.options.timeoutMs;
  }

  private async readPlain(book: string, pages: number[] | 'all'): Promise<PageText[]> {
    let wanted: number[];
    if (pages === 'all') {
      const count = (await this.catalog()).get(book)?.n_pages ?? (await this.meta(book))?.n_pages ?? null;
      if (count === null) throw new LibraryError('page_map', `ERROR library: PageIndex does not say how many pages ${book} has, so the whole book cannot be read in chunks`);
      wanted = Array.from({ length: count }, (_, index) => index + 1);
    } else wanted = pages;
    const chunkSize = limits.pageindex.readChunkPages;
    const chunks: number[][] = [];
    for (let index = 0; index < wanted.length; index += chunkSize) chunks.push(wanted.slice(index, index + chunkSize));
    const results: PageText[][] = new Array<PageText[]>(chunks.length);
    let next = 0;
    const worker = async (): Promise<void> => {
      while (next < chunks.length) {
        const mine = next;
        next += 1;
        results[mine] = parseBanners(await this.run(['read', book, formatPageRanges(chunks[mine] as number[])], this.readTimeout(pages))).pages;
      }
    };
    await Promise.all(Array.from({ length: Math.min(limits.pageindex.chunkConcurrency, chunks.length) }, worker));
    return results.flat();
  }
}
