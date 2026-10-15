import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
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
 * or a bare id list. A map entry without `pages` asks the library (`pilib meta`).
 */
export function loadShelf(path: string | null): Shelf {
  const empty: Shelf = { books: null, map: new Map() };
  if (!path || !existsSync(path)) return empty;
  let raw: unknown;
  try { raw = JSON.parse(readFileSync(path, 'utf8')); } catch { return empty; }
  const books = Array.isArray(raw) ? raw : (raw as { books?: unknown } | null)?.books;
  const mapRaw = Array.isArray(raw) ? undefined : (raw as { map?: unknown } | null)?.map;
  const map = new Map<string, ShelfEntry>();
  if (mapRaw && typeof mapRaw === 'object') {
    for (const [source, value] of Object.entries(mapRaw as Record<string, unknown>)) {
      if (typeof value !== 'object' || value === null) continue;
      const entry = value as { book?: unknown; pages?: unknown };
      if (typeof entry.book !== 'string' || !entry.book) continue;
      let pages: ShelfPages = 'auto';
      if (entry.pages === 'identity') pages = 'identity';
      else if (typeof entry.pages === 'object' && entry.pages !== null) {
        const pagemap = (entry.pages as { pagemap?: unknown }).pagemap;
        if (Array.isArray(pagemap) && pagemap.every((n) => Number.isInteger(n))) pages = { kind: 'pagemap', pdfToTrove: pagemap as number[] };
      }
      map.set(source, { book: entry.book, pages });
    }
  }
  return { books: Array.isArray(books) ? books.filter((b): b is string => typeof b === 'string') : null, map };
}
