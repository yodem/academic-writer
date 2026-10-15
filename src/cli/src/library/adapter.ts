import { randomBytes } from 'node:crypto';
import thresholds from '../../../thresholds.json' with { type: 'json' };
import { PageIndexBackend, TroveBackend } from './backends.ts';
import { loadLibraryConfig, profileTroveEnabled, type LibraryConfig } from './config.ts';
import { formatPageRanges, parsePageSpec, printedToTrove, relabelPages, routeToTrovePage, troveToRoutePages, type RoutePages } from './pages.ts';
import { findSource, loadShelf, stripFragment, type Shelf } from './registry.ts';
import { LibraryError, errorMessage, type BookInfo, type LibraryBackend, type RouteName, type TocEntry } from './types.ts';

const limits = thresholds.library;

export type ResolvedBook = { book: string; pages: RoutePages };
export type ReadRequest = { source: string; pages?: string; printed?: string; all?: boolean };
export type ReadOutput = {
  lookup_id: string;
  op: 'read';
  source_id: string;
  route: RouteName;
  mode: LibraryConfig['route'];
  /** "disabled" until the shadow worker exists (T2) or when shadowing is off; "none" for a single route. */
  shadow_status: 'none' | 'disabled';
  request: { printed: string | null; trove_pages: string };
  printed_pages: number[] | null;
  title: string | null;
  page_count: number | null;
  pages: Array<{ trove_page: number; text: string; route_pages: number[] }>;
  missing_pages: number[];
  latency_ms: number;
  chars: number;
  /** Primary route's raw output, for callers that parse the route's own format (kept out of the JSON the CLI prints). */
  raw?: string;
};

export function newLookupId(): string { return `lk_${Date.now().toString(36)}${randomBytes(4).toString('hex')}`; }

export class Library {
  readonly config: LibraryConfig;
  private readonly trove: TroveBackend;
  private readonly pageindex: PageIndexBackend;
  private shelfCache: Shelf | undefined;
  private readonly resolved = new Map<string, ResolvedBook>();

  constructor(readonly project: string, private readonly env: NodeJS.ProcessEnv = process.env) {
    this.config = loadLibraryConfig(project, env);
    const override = Number(env.AW_LIBRARY_TIMEOUT_MS);
    this.override = Number.isFinite(override) && override > 0 ? override : undefined;
    this.trove = this.makeTrove(this.override ?? limits.timeoutMs.primary);
    this.pageindex = this.makePageIndex(this.override ?? limits.timeoutMs.primary);
  }

  /** AW_LIBRARY_TIMEOUT_MS replaces every timeout (test and troubleshooting seam; the defaults live in thresholds.json). */
  private readonly override: number | undefined;
  private makeTrove(timeoutMs: number): TroveBackend { return new TroveBackend({ command: this.config.troveCommand, env: this.env, timeoutMs }); }
  private makePageIndex(timeoutMs: number): PageIndexBackend { return new PageIndexBackend({ command: this.config.pageindexCommand, env: this.env, timeoutMs }); }

  private get shelf(): Shelf {
    this.shelfCache ??= loadShelf(this.config.shelfPath);
    return this.shelfCache;
  }

  backend(route: RouteName): LibraryBackend { return route === 'trove' ? this.trove : this.pageindex; }

  private statusFor(): 'none' | 'disabled' { return this.config.route === 'both' ? 'disabled' : 'none'; }

  /** Which route book and page space a canonical source id means on `route`. Unknown PageIndex mappings fail loud. */
  async resolveBook(route: RouteName, source: string): Promise<ResolvedBook> {
    const id = stripFragment(source);
    if (route === 'trove') return { book: id, pages: { kind: 'identity' } };
    const cached = this.resolved.get(id);
    if (cached) return cached;
    const found = await this.resolvePageIndex(id);
    this.resolved.set(id, found);
    return found;
  }

  private async pagesFromMeta(book: string): Promise<RoutePages | null> {
    const meta = await this.pageindex.meta(book);
    if (!meta) return null;
    return meta.pagemap ? { kind: 'pagemap', pdfToTrove: meta.pagemap } : { kind: 'identity' };
  }

  private async resolvePageIndex(id: string): Promise<ResolvedBook> {
    const shelf = this.shelf;
    const mapped = shelf.map.get(id);
    if (mapped) {
      if (mapped.pages === 'identity') return { book: mapped.book, pages: { kind: 'identity' } };
      if (mapped.pages !== 'auto') return { book: mapped.book, pages: mapped.pages };
      const fromMeta = await this.pagesFromMeta(mapped.book);
      if (!fromMeta) throw new LibraryError('page_map', `ERROR library: cannot tell how PageIndex pages of ${mapped.book} map to Trove pages; add "pages": "identity" or a pagemap to the shelf map`);
      return { book: mapped.book, pages: fromMeta };
    }
    const catalog = await this.pageindex.catalog();
    const onShelf = (book: string): boolean => shelf.books === null || shelf.books.includes(book);
    if (catalog.has(id) && onShelf(id)) return { book: id, pages: (await this.pagesFromMeta(id)) ?? { kind: 'identity' } };
    const candidates = [...catalog.keys()].filter(onShelf);
    if (candidates.length > limits.pageindex.metaScanMax) throw new LibraryError('page_map', `ERROR library: ${id} is not in the shelf map and the shelf has too many books to search; add it to the shelf map`);
    let found: ResolvedBook | undefined;
    let next = 0;
    const worker = async (): Promise<void> => {
      while (next < candidates.length && !found) {
        const book = candidates[next] as string;
        next += 1;
        const meta = await this.pageindex.meta(book);
        if (meta?.trove_id === id) found = { book, pages: meta.pagemap ? { kind: 'pagemap', pdfToTrove: meta.pagemap } : { kind: 'identity' } };
      }
    };
    await Promise.all(Array.from({ length: Math.min(limits.pageindex.metaScanConcurrency, candidates.length) }, worker));
    if (!found) throw new LibraryError('page_map', `ERROR library: ${id} is not on this project's PageIndex shelf`);
    return found;
  }

  /** The answering route's books, as canonical ids (PageIndex books that map to a Trove id show that id). */
  async list(): Promise<{ route: RouteName; mode: LibraryConfig['route']; items: BookInfo[] }> {
    const route = this.config.primary;
    const books = await this.backend(route).list();
    if (route === 'trove') return { route, mode: this.config.route, items: books };
    const shelf = this.shelf;
    const reverse = new Map<string, string>();
    for (const [source, entry] of shelf.map) reverse.set(entry.book, source);
    const visible = books.filter((book) => shelf.books === null || shelf.books.includes(book.id) || reverse.has(book.id));
    return { route, mode: this.config.route, items: visible.map((book) => ({ ...book, id: reverse.get(book.id) ?? book.id })) };
  }

  async toc(source: string): Promise<{ route: RouteName; mode: LibraryConfig['route']; source_id: string; title: string | null; toc: TocEntry[] }> {
    const route = this.config.primary;
    const { book, pages } = await this.resolveBook(route, source);
    const result = await this.backend(route).toc(book);
    const toc = result.toc.flatMap((entry): TocEntry[] => {
      const page = routeToTrovePage(entry.page, pages);
      if (page === null) return [];
      return [{ ...entry, page, endPage: entry.endPage === null ? null : routeToTrovePage(entry.endPage, pages) }];
    });
    return { route, mode: this.config.route, source_id: stripFragment(source), title: result.title ?? null, toc };
  }

  async read(request: ReadRequest): Promise<ReadOutput> {
    const route = this.config.primary;
    const source = stripFragment(request.source);
    let printedPages: number[] | null = null;
    let wanted: number[] | 'all';
    if (request.all) wanted = 'all';
    else if (request.pages !== undefined) wanted = parsePageSpec(request.pages);
    else if (request.printed !== undefined) {
      const printed = parsePageSpec(request.printed);
      if (printed === 'all') throw new LibraryError('usage', 'ERROR library: --printed needs page numbers, not all');
      printedPages = printed;
      const record = findSource(this.project, request.source);
      try { wanted = printedToTrove(printed, record?.pageMap, this.project); }
      catch (error) {
        if (error instanceof LibraryError && error.code === 'page_map') throw new LibraryError('usage', `${error.message}${record?.warning ? ` (${record.warning})` : ''}`);
        throw error;
      }
    } else throw new LibraryError('usage', 'ERROR library read: give --pages A-B, --printed A-B or all');
    const wantedAll = wanted === 'all';
    const started = Date.now();
    const { book, pages: routePages } = await this.resolveBook(route, source);
    let routeWanted: number[] | 'all' = 'all';
    let missing: number[] = [];
    if (!wantedAll) {
      const mapped = troveToRoutePages(wanted as number[], routePages);
      routeWanted = mapped.route;
      missing = mapped.missing;
    }
    const backend = this.backend(route);
    const raw = routeWanted === 'all' || routeWanted.length > 0 ? await backend.read(book, routeWanted) : { pages: [] };
    const canonical = relabelPages(raw.pages, routePages);
    if (!wantedAll) {
      const have = new Set(canonical.map((page) => page.page));
      missing = [...new Set([...missing, ...(wanted as number[]).filter((page) => !have.has(page))])].sort((a, b) => a - b);
      if (canonical.length === 0) throw new LibraryError('page_missing', `ERROR library read: ${route} has none of the requested pages of ${source} (missing ${missing.join(',')})`);
    }
    const title = raw.title ?? await backend.title(book);
    const chars = canonical.reduce((sum, page) => sum + page.text.length, 0);
    return {
      lookup_id: newLookupId(),
      op: 'read',
      source_id: source,
      route,
      mode: this.config.route,
      shadow_status: this.statusFor(),
      request: { printed: request.printed ?? null, trove_pages: wantedAll ? 'all' : formatPageRanges(wanted as number[]) },
      printed_pages: printedPages,
      title: title ?? null,
      page_count: raw.pageCount ?? null,
      pages: canonical.map((page) => ({ trove_page: page.page, text: page.text, route_pages: page.routePages })),
      missing_pages: missing,
      latency_ms: Date.now() - started,
      chars,
      ...(raw.raw !== undefined && routePages.kind === 'identity' ? { raw: raw.raw } : {}),
    };
  }

  /** Report: the route setting, whether the answering route is usable, and with `check` one cheap list per route. */
  async status(check: boolean): Promise<Record<string, unknown>> {
    const { config } = this;
    const troveEnabled = profileTroveEnabled(this.project);
    const enabled = config.primary === 'pageindex' ? true : troveEnabled !== false;
    const word = (command: string[]): string => (command[0] ?? '').split('/').pop() ?? '';
    const report: Record<string, unknown> = {
      route: config.route,
      primary: config.primary,
      secondary: config.secondary,
      configured: config.configured,
      enabled,
      shadow: { enabled: config.shadowEnabled },
      shelf: config.shelfPath !== null,
      commands: { trove: word(config.troveCommand), pageindex: word(config.pageindexCommand) },
    };
    if (check) {
      const probe = async (route: RouteName): Promise<Record<string, unknown>> => {
        const started = Date.now();
        try {
          const timeoutMs = this.override ?? limits.timeoutMs.check;
          const items = await (route === 'trove' ? this.makeTrove(timeoutMs) : this.makePageIndex(timeoutMs)).list();
          return { ok: true, latency_ms: Date.now() - started, count: items.length, error: null };
        } catch (error) { return { ok: false, latency_ms: Date.now() - started, count: null, error: errorMessage(error) }; }
      };
      const routes: Record<string, unknown> = {};
      for (const route of [config.primary, config.secondary]) if (route) routes[route] = await probe(route);
      report.check = routes;
    }
    return report;
  }
}
