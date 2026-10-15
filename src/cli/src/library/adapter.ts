import { randomBytes } from 'node:crypto';
import thresholds from '../../../thresholds.json' with { type: 'json' };
import { PageIndexBackend, TroveBackend } from './backends.ts';
import type { CommandScope } from './exec.ts';
import { loadLibraryConfig, profileTroveEnabled, type LibraryConfig } from './config.ts';
import { appendRow, clipError, nowIso, spoolFile, spoolValue, textSha, writeSpool, type LookupOp, type LookupRow } from './ledger.ts';
import { noShadow, startShadow, workerSettings, type RouteResult, type ShadowHandle, type ShadowMode, type ShadowRunner, type ShadowSpec } from './shadow.ts';
import { formatPageRanges, parsePageSpec, printedToTrove, relabelPages, routeToTrovePage, splitComplete, troveToRoutePages, type RoutePages } from './pages.ts';
import { findSource, loadShelf, stripFragment, type Shelf } from './registry.ts';
import { LibraryError, errorMessage, type BookInfo, type CanonicalPage, type LibraryBackend, type RawRead, type RouteName, type TocEntry } from './types.ts';

const limits = thresholds.library;

export type ResolvedBook = { book: string; pages: RoutePages };
export type ReadRequest = {
  source: string;
  pages?: string;
  printed?: string;
  all?: boolean;
  /** Which command asked, for the ledger: `get` is a whole-book read. */
  op?: 'read' | 'get';
  /** The write/edit run and the paragraph this lookup serves, for the ledger. */
  run?: string;
  claim?: string;
};
/** Options of a Library. `shadow` defaults to off here; the aw library command turns it on (detached). */
export type LibraryOptions = { shadow?: ShadowMode; timeoutMs?: number; /** The commands of this Library stop together (the shadow worker's scope). */ scope?: CommandScope };
type Ids = { run?: string; claim?: string };
export type ReadOutput = {
  lookup_id: string;
  op: 'read';
  source_id: string;
  route: RouteName;
  mode: LibraryConfig['route'];
  /** none (single route), disabled (both, shadow off), pending (the other route is running quietly) or skipped:<why>. */
  shadow_status: string;
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

export class Library implements ShadowRunner {
  readonly config: LibraryConfig;
  private readonly trove: TroveBackend;
  private readonly pageindex: PageIndexBackend;
  private shelfCache: Shelf | undefined;
  private readonly resolved = new Map<string, ResolvedBook>();

  private readonly shadowMode: ShadowMode;
  private readonly scope: CommandScope | undefined;

  constructor(readonly project: string, private readonly env: NodeJS.ProcessEnv = process.env, options: LibraryOptions = {}) {
    this.config = loadLibraryConfig(project, env);
    const override = Number(env.AW_LIBRARY_TIMEOUT_MS);
    this.override = Number.isFinite(override) && override > 0 ? override : undefined;
    this.shadowMode = options.shadow ?? 'off';
    this.scope = options.scope;
    const timeoutMs = options.timeoutMs ?? this.override ?? limits.timeoutMs.primary;
    this.trove = this.makeTrove(timeoutMs);
    this.pageindex = this.makePageIndex(timeoutMs);
  }

  /** AW_LIBRARY_TIMEOUT_MS replaces every timeout (test and troubleshooting seam; the defaults live in thresholds.json). */
  private readonly override: number | undefined;
  private makeTrove(timeoutMs: number): TroveBackend { return new TroveBackend({ command: this.config.troveCommand, env: this.env, timeoutMs, cwd: this.project, scope: this.scope }); }
  private makePageIndex(timeoutMs: number): PageIndexBackend { return new PageIndexBackend({ command: this.config.pageindexCommand, env: this.env, timeoutMs, cwd: this.project, scope: this.scope }); }

  private get shelf(): Shelf {
    this.shelfCache ??= loadShelf(this.config.shelfPath);
    return this.shelfCache;
  }

  backend(route: RouteName): LibraryBackend { return route === 'trove' ? this.trove : this.pageindex; }

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

  private async listVia(route: RouteName): Promise<BookInfo[]> {
    const books = await this.backend(route).list();
    if (route === 'trove') return books;
    const shelf = this.shelf;
    const reverse = new Map<string, string>();
    for (const [source, entry] of shelf.map) reverse.set(entry.book, source);
    const visible = books.filter((book) => shelf.books === null || shelf.books.includes(book.id) || reverse.has(book.id));
    return visible.map((book) => ({ ...book, id: reverse.get(book.id) ?? book.id }));
  }

  private async tocVia(route: RouteName, source: string): Promise<{ book: string; title: string | null; toc: TocEntry[] }> {
    const { book, pages } = await this.resolveBook(route, source);
    const result = await this.backend(route).toc(book);
    const toc = result.toc.flatMap((entry): TocEntry[] => {
      const page = routeToTrovePage(entry.page, pages);
      if (page === null) return [];
      return [{ ...entry, page, endPage: entry.endPage === null ? null : routeToTrovePage(entry.endPage, pages) }];
    });
    return { book, title: result.title ?? null, toc };
  }

  /** One route's answer for a page request, in canonical (Trove) page numbers. Used by the answering path and by the shadow. */
  private async fetchPages(route: RouteName, source: string, wanted: number[] | 'all'): Promise<{ book: string; routePages: RoutePages; raw: RawRead; canonical: CanonicalPage[]; missing: number[] }> {
    const wantedAll = wanted === 'all';
    const { book, pages: routePages } = await this.resolveBook(route, source);
    let routeWanted: number[] | 'all' = 'all';
    let missing: number[] = [];
    if (!wantedAll) {
      const mapped = troveToRoutePages(wanted, routePages);
      routeWanted = mapped.route;
      missing = mapped.missing;
    }
    const backend = this.backend(route);
    const raw = routeWanted === 'all' || routeWanted.length > 0 ? await backend.read(book, routeWanted) : { pages: [] };
    const split = splitComplete(relabelPages(raw.pages, routePages), routePages);
    const canonical = split.complete;
    if (!wantedAll) {
      const have = new Set(canonical.map((page) => page.page));
      missing = [...new Set([...missing, ...wanted.filter((page) => !have.has(page))])].sort((a, b) => a - b);
      if (canonical.length === 0) throw new LibraryError('page_missing', `ERROR library read: ${route} has none of the requested pages of ${source} (missing ${missing.join(',')})`);
    }
    // A whole-book read has no requested list: every canonical page the book's pagemap has must be whole.
    if (wantedAll && routePages.kind === 'pagemap') {
      const have = new Set(canonical.map((page) => page.page));
      missing = [...new Set(routePages.pdfToTrove)].filter((page) => !have.has(page)).sort((a, b) => a - b);
    }
    return { book, routePages, raw, canonical, missing };
  }

  // ------------------------------------------------------------ ledger and shadow

  /** The shadow for one lookup, started before the answering route is asked so the two overlap. Never throws, never waits for the worker. */
  private async launch(op: 'list' | 'toc' | 'read', source: string | null, pages: number[] | 'all' | null, ids: Ids, lookupId: string): Promise<ShadowHandle> {
    const secondary = this.config.secondary;
    if (!secondary) return noShadow('none');
    if (!this.config.shadowEnabled || this.shadowMode === 'off') return noShadow('disabled');
    if (!limits.shadow.ops.includes(op)) return noShadow('skipped:op');
    if (Array.isArray(pages) && pages.length > limits.shadow.readAllMaxPages) return noShadow('skipped:too_many_pages');
    const spec: Omit<ShadowSpec, 'slot' | 'slot_nonce'> = { v: 1, lookup_id: lookupId, run_id: ids.run ?? null, claim_id: ids.claim ?? null, op, route: secondary, project: this.project, source, pages };
    return startShadow(spec, this.shadowMode, this.env, this);
  }

  /** Whether a whole-book read may still be shadowed once its size is known (never before: the size comes from the answer). */
  private wholeBookGate(): string | null {
    if (!this.config.secondary) return 'none';
    if (!this.config.shadowEnabled || this.shadowMode === 'off') return 'disabled';
    if (!limits.shadow.ops.includes('read')) return 'skipped:op';
    return null;
  }

  private async spoolPrimary(lookupId: string, ok: boolean, pages: Array<{ page: number; text: string }>): Promise<void> {
    await writeSpool(this.project, spoolFile(this.project, lookupId, 'primary'), spoolValue(lookupId, { ok }, pages));
  }

  private async writeLookup(p: {
    lookupId: string; op: LookupOp; source: string | null; ids: Ids; request: LookupRow['request']; book: string | null;
    ok: boolean; routePages: string | null; latencyMs: number; bytes: number; chars: number; sha: string | null; error: unknown; shadowStatus: string;
  }): Promise<void> {
    const route = this.config.primary;
    const row: LookupRow = {
      row_type: 'lookup',
      schema: 1,
      ts: nowIso(),
      lookup_id: p.lookupId,
      run_id: p.ids.run ?? null,
      claim_id: p.ids.claim ?? null,
      op: p.op,
      source_id: p.source,
      mode: this.config.route,
      route_primary: route,
      book_by_route: { trove: route === 'trove' ? p.book : null, pageindex: route === 'pageindex' ? p.book : null },
      request: p.request,
      primary: {
        route,
        ok: p.ok,
        route_pages: p.routePages,
        latency_ms: p.latencyMs,
        bytes: p.bytes,
        chars: p.chars,
        text_sha: p.sha,
        error: p.ok ? null : clipError(errorMessage(p.error)),
        error_code: p.ok ? null : (p.error instanceof LibraryError ? p.error.code : 'error'),
      },
      shadow_status: p.shadowStatus,
    };
    await appendRow(this.project, row);
  }

  /** The ShadowRunner side: the same request on the other route, under the shadow timeout instead of the primary one; the worker records the outcome. */
  runShadow(spec: ShadowSpec, scope?: CommandScope): Promise<RouteResult> {
    return new Library(this.project, this.env, { shadow: 'off', timeoutMs: workerSettings(this.env).timeoutMs, scope }).shadowCall(spec);
  }

  private async shadowCall(spec: ShadowSpec): Promise<RouteResult> {
    if (spec.op === 'list') return summarizeText(null, JSON.stringify(await this.listVia(spec.route)));
    if (spec.op === 'toc') {
      const result = await this.tocVia(spec.route, spec.source ?? '');
      return summarizeText(result.book, JSON.stringify(result.toc));
    }
    const got = await this.fetchPages(spec.route, spec.source ?? '', spec.pages ?? 'all');
    const text = got.canonical.map((page) => page.text).join('\n');
    return {
      book: got.book,
      route_pages: formatPageRanges(got.canonical.flatMap((page) => page.routePages)) || null,
      bytes: Buffer.byteLength(text, 'utf8'),
      chars: text.length,
      text_sha: textSha(text),
      pages: got.canonical.map((page) => ({ page: page.page, text: page.text })),
    };
  }

  /** A lookup that has no page text (list, toc): ask the answering route, record the lookup, let the shadow settle. */
  private async tracked<T>(op: 'list' | 'toc', source: string | null, ids: Ids, work: (route: RouteName) => Promise<{ value: T; book: string | null; text: string }>): Promise<T> {
    const lookupId = newLookupId();
    const handle = await this.launch(op, source, null, ids, lookupId);
    const started = Date.now();
    const base = { lookupId, op, source, ids, request: { printed: null, trove_pages: null }, shadowStatus: handle.status };
    try {
      const { value, book, text } = await work(this.config.primary);
      await this.writeLookup({ ...base, book, ok: true, routePages: null, latencyMs: Date.now() - started, bytes: Buffer.byteLength(text, 'utf8'), chars: text.length, sha: textSha(text), error: null });
      await handle.settle();
      return value;
    } catch (error) {
      await this.writeLookup({ ...base, book: null, ok: false, routePages: null, latencyMs: Date.now() - started, bytes: 0, chars: 0, sha: null, error });
      await handle.settle();
      throw error;
    }
  }

  /** The answering route's books, as canonical ids (PageIndex books that map to a Trove id show that id). */
  async list(ids: Ids = {}): Promise<{ route: RouteName; mode: LibraryConfig['route']; items: BookInfo[] }> {
    return this.tracked('list', null, ids, async (route) => {
      const items = await this.listVia(route);
      return { value: { route, mode: this.config.route, items }, book: null, text: JSON.stringify(items) };
    });
  }

  async toc(source: string, ids: Ids = {}): Promise<{ route: RouteName; mode: LibraryConfig['route']; source_id: string; title: string | null; toc: TocEntry[] }> {
    return this.tracked('toc', stripFragment(source), ids, async (route) => {
      const result = await this.tocVia(route, source);
      return { value: { route, mode: this.config.route, source_id: stripFragment(source), title: result.title, toc: result.toc }, book: result.book, text: JSON.stringify(result.toc) };
    });
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
    const ids: Ids = { run: request.run, claim: request.claim };
    const lookupId = newLookupId();
    const ledgerRequest = { printed: request.printed ?? null, trove_pages: wantedAll ? 'all' : formatPageRanges(wanted as number[]) };
    // Explicit pages: the shadow starts now and overlaps the answering route. A whole book is only shadowed once its size is known.
    const gate = wantedAll ? this.wholeBookGate() : null;
    let handle = wantedAll ? noShadow(gate ?? 'skipped:primary_failed') : await this.launch('read', source, wanted, ids, lookupId);
    const started = Date.now();
    const op: LookupOp = request.op ?? 'read';
    try {
      const got = await this.fetchPages(route, source, wanted);
      const { raw, canonical, routePages, missing } = got;
      const plain = canonical.map((page) => ({ page: page.page, text: page.text }));
      const title = raw.title ?? await this.backend(route).title(got.book);
      const chars = canonical.reduce((sum, page) => sum + page.text.length, 0);
      if (wantedAll && gate === null) {
        if (canonical.length > limits.shadow.readAllMaxPages) handle = noShadow('skipped:read_all');
        else {
          await this.spoolPrimary(lookupId, true, plain);
          handle = await this.launch('read', source, canonical.map((page) => page.page), ids, lookupId);
        }
      } else if (handle.status === 'pending') await this.spoolPrimary(lookupId, true, plain);
      const text = canonical.map((page) => page.text).join('\n');
      const latencyMs = Date.now() - started;
      await this.writeLookup({
        lookupId, op, source, ids, request: ledgerRequest, book: got.book, ok: true,
        routePages: formatPageRanges(canonical.flatMap((page) => page.routePages)) || null,
        latencyMs, bytes: Buffer.byteLength(text, 'utf8'), chars, sha: textSha(text), error: null, shadowStatus: handle.status,
      });
      const output: ReadOutput = {
        lookup_id: lookupId,
        op: 'read',
        source_id: source,
        route,
        mode: this.config.route,
        shadow_status: handle.status,
        request: ledgerRequest,
        printed_pages: printedPages,
        title: title ?? null,
        page_count: raw.pageCount ?? null,
        pages: canonical.map((page) => ({ trove_page: page.page, text: page.text, route_pages: page.routePages })),
        missing_pages: missing,
        latency_ms: latencyMs,
        chars,
        ...(raw.raw !== undefined && routePages.kind === 'identity' ? { raw: raw.raw } : {}),
      };
      await handle.settle();
      return output;
    } catch (error) {
      if (handle.status === 'pending') await this.spoolPrimary(lookupId, false, []);
      await this.writeLookup({ lookupId, op, source, ids, request: ledgerRequest, book: null, ok: false, routePages: null, latencyMs: Date.now() - started, bytes: 0, chars: 0, sha: null, error, shadowStatus: handle.status });
      await handle.settle();
      throw error;
    }
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

function summarizeText(book: string | null, text: string): RouteResult {
  return { book, route_pages: null, bytes: Buffer.byteLength(text, 'utf8'), chars: text.length, text_sha: textSha(text) };
}
