import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { LibraryError } from './types.ts';
import { parseSourcePageMap, type RoutePages, type SourcePageMap } from './pages.ts';

export type SourceRecord = { id: string; pageMap?: SourcePageMap; warning?: string };

export function stripFragment(id: string): string {
  const index = id.indexOf('#');
  return index >= 0 ? id.slice(0, index) : id;
}

/** The source's record in `.academic-helper/sources.json` (an array, or `{sources: [...]}`), or undefined. */
export function findSource(project: string, sourceId: string): SourceRecord | undefined {
  const file = join(project, '.academic-helper', 'sources.json');
  if (!existsSync(file)) return undefined;
  let raw: unknown;
  try { raw = JSON.parse(readFileSync(file, 'utf8')); } catch { return undefined; }
  const list: unknown = Array.isArray(raw) ? raw : (raw as { sources?: unknown } | null)?.sources;
  if (!Array.isArray(list)) return undefined;
  const base = stripFragment(sourceId);
  const records = list.filter((entry): entry is Record<string, unknown> => typeof entry === 'object' && entry !== null);
  const idOf = (entry: Record<string, unknown>): string => String(entry.sourceId ?? entry.id ?? '');
  const hit = records.find((entry) => idOf(entry) === sourceId) ?? records.find((entry) => stripFragment(idOf(entry)) === base);
  if (!hit) return undefined;
  const parsed = parseSourcePageMap(hit.pageMap);
  return { id: idOf(hit), ...(parsed.map ? { pageMap: parsed.map } : {}), ...(parsed.warning ? { warning: parsed.warning } : {}) };
}

export type ShelfPages = 'identity' | 'auto' | RoutePages;
export type ShelfEntry = { book: string; pages: ShelfPages };
export type Shelf = { books: string[] | null; map: Map<string, ShelfEntry> };

/**
 * The PageIndex shelf: `{"books": [...ids], "map": {"<trove id>": {"book": "<library id>", "pages": "identity" | {"pagemap": [...]}}}}`
 * or a bare id list. A map entry without `pages` asks the library (`pilib meta`). A map without `books` limits the
 * shelf to the mapped books.
 *
 * No shelf configured (`path` null) means no restriction. A shelf that IS configured but missing, unreadable or
 * malformed is a config error: falling back to "no restriction" would silently expose the whole catalog.
 */
export function loadShelf(path: string | null): Shelf {
  if (!path) return { books: null, map: new Map() };
  const bad = (why: string): LibraryError => new LibraryError('config', `ERROR library: the PageIndex shelf ${path} ${why}; fix it or remove "pageindex.shelf" from library.json`);
  if (!existsSync(path)) throw bad('does not exist');
  let raw: unknown;
  try { raw = JSON.parse(readFileSync(path, 'utf8')); }
  catch (error) { throw bad(error instanceof SyntaxError ? 'is not valid JSON' : 'cannot be read'); }
  const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every((entry) => typeof entry === 'string');
  const record = typeof raw === 'object' && raw !== null && !Array.isArray(raw) ? raw as { books?: unknown; map?: unknown } : undefined;
  if (!Array.isArray(raw) && !record) throw bad('must be a list of book ids or an object with "books" and/or "map"');
  const books: unknown = Array.isArray(raw) ? raw : record?.books;
  const mapRaw: unknown = record?.map;
  if (books !== undefined && !strings(books)) throw bad('has a "books" list that is not a list of book id strings');
  if (mapRaw !== undefined && (typeof mapRaw !== 'object' || mapRaw === null || Array.isArray(mapRaw))) throw bad('has a "map" that is not an object');
  if (books === undefined && mapRaw === undefined) throw bad('has neither "books" nor "map"');
  const map = new Map<string, ShelfEntry>();
  for (const [source, value] of Object.entries((mapRaw ?? {}) as Record<string, unknown>)) {
    const entry = typeof value === 'object' && value !== null ? value as { book?: unknown; pages?: unknown } : undefined;
    if (!entry || typeof entry.book !== 'string' || !entry.book) throw bad(`has a map entry "${source}" without a "book" id`);
    let pages: ShelfPages = 'auto';
    if (entry.pages === 'identity') pages = 'identity';
    else if (typeof entry.pages === 'object' && entry.pages !== null) {
      const pagemap = (entry.pages as { pagemap?: unknown }).pagemap;
      if (!Array.isArray(pagemap) || !pagemap.every((n) => Number.isInteger(n))) throw bad(`has a map entry "${source}" whose pagemap is not a list of whole numbers`);
      pages = { kind: 'pagemap', pdfToTrove: pagemap as number[] };
    } else if (entry.pages !== undefined) throw bad(`has a map entry "${source}" with an unknown "pages" value`);
    map.set(source, { book: entry.book, pages });
  }
  return { books: strings(books) ? books : [...new Set([...map.values()].map((entry) => entry.book))], map };
}
