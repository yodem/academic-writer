import { existsSync, readFileSync } from 'node:fs';
import { isAbsolute, relative, resolve } from 'node:path';
import thresholds from '../../../thresholds.json' with { type: 'json' };
import { LibraryError, type CanonicalPage, type PageText } from './types.ts';

/**
 * Page spaces. The canonical page is the Trove page (sequential, H1 = page break). A citation names a
 * printed page, which a source's `pageMap` turns into a Trove page. PageIndex pages are PDF pages; a book
 * rendered from Trove carries a `pdf_to_trove` list, a book exported from Trove has the same pages.
 */
export type SourcePageMap =
  | { kind: 'identity' }
  | { kind: 'offset'; trove_minus_printed: number }
  | { kind: 'crosswalk'; file: string; volume?: number; stored_minus_printed?: number };

export type RoutePages = { kind: 'identity' } | { kind: 'pagemap'; pdfToTrove: number[] };

const maxRequestPages = thresholds.library.maxRequestPages;

/** "7-9,12" -> [7,8,9,12] (sorted, unique); "all" -> 'all'. */
export function parsePageSpec(spec: string): number[] | 'all' {
  const text = spec.trim();
  if (text === 'all') return 'all';
  const out = new Set<number>();
  for (const part of text.split(',')) {
    const piece = part.trim();
    if (!piece) continue;
    const match = piece.match(/^(\d+)(?:\s*-\s*(\d+))?$/u);
    if (!match) throw new LibraryError('usage', `ERROR library: bad page list "${spec}" (use 7, 7-9, 7-9,12 or all)`);
    const low = Number(match[1]);
    const high = Number(match[2] ?? match[1]);
    if (low < 1 || high < low) throw new LibraryError('usage', `ERROR library: bad page range "${piece}"`);
    if (out.size + (high - low + 1) > maxRequestPages) throw new LibraryError('usage', `ERROR library: more than ${maxRequestPages} pages requested; use all`);
    for (let page = low; page <= high; page += 1) out.add(page);
  }
  if (out.size === 0) throw new LibraryError('usage', 'ERROR library: no pages requested');
  return [...out].sort((a, b) => a - b);
}

/** [7,8,9,12] -> "7-9,12". */
export function formatPageRanges(pages: number[]): string {
  const sorted = [...new Set(pages)].sort((a, b) => a - b);
  const parts: string[] = [];
  for (let index = 0; index < sorted.length;) {
    let end = index;
    while (end + 1 < sorted.length && sorted[end + 1] === (sorted[end] as number) + 1) end += 1;
    parts.push(end === index ? String(sorted[index]) : `${sorted[index]}-${sorted[end]}`);
    index = end + 1;
  }
  return parts.join(',');
}

const BANNER = /^[─—-]{2}\s*Page\s+(\d+)\s*[─—-]{2}\s*$/u;

/**
 * Parse `── Page N ──` output (Trove `items read` and `pilib read` share it). Lines before the first banner
 * are a header (title, "ID | N pages") that is returned separately.
 */
export function parseBanners(output: string): { header: string[]; pageCount: number | null; pages: PageText[] } {
  const header: string[] = [];
  const pages: PageText[] = [];
  let current: { page: number; lines: string[] } | undefined;
  for (const line of output.split('\n')) {
    const banner = line.match(BANNER);
    if (banner) {
      if (current) pages.push({ page: current.page, text: current.lines.join('\n').replace(/\s+$/u, '') });
      current = { page: Number(banner[1]), lines: [] };
    } else if (current) current.lines.push(line);
    else header.push(line);
  }
  if (current) pages.push({ page: current.page, text: current.lines.join('\n').replace(/\s+$/u, '') });
  const count = header.join('\n').match(/\|\s*(\d+)\s+pages?\b/iu);
  return { header: header.filter((line) => line.trim() && !/^[─=\-\s]+$/u.test(line)), pageCount: count ? Number(count[1]) : null, pages };
}

/** Read the structured `pageMap` of a sources.json record. Free-text legacy values are ignored with a warning. */
export function parseSourcePageMap(raw: unknown): { map?: SourcePageMap; warning?: string } {
  if (raw === undefined || raw === null) return {};
  if (typeof raw !== 'object' || Array.isArray(raw)) return { warning: 'pageMap is free text; use {"kind":"identity"|"offset"|"crosswalk"} (ignored)' };
  const record = raw as Record<string, unknown>;
  if (record.kind === 'identity') return { map: { kind: 'identity' } };
  if (record.kind === 'offset' && Number.isInteger(record.trove_minus_printed)) return { map: { kind: 'offset', trove_minus_printed: record.trove_minus_printed as number } };
  if (record.kind === 'crosswalk' && typeof record.file === 'string' && record.file) {
    const volume = Number.isInteger(record.volume) ? record.volume as number : undefined;
    const shift = Number.isInteger(record.stored_minus_printed) ? record.stored_minus_printed as number : undefined;
    return { map: { kind: 'crosswalk', file: record.file, ...(volume !== undefined ? { volume } : {}), ...(shift !== undefined ? { stored_minus_printed: shift } : {}) } };
  }
  return { warning: 'pageMap has an unknown shape (ignored)' };
}

/** Printed pages -> Trove pages, deterministically. Never guesses: a page the map cannot place is an error. */
export function printedToTrove(printed: number[], map: SourcePageMap | undefined, project: string): number[] {
  if (!map) throw new LibraryError('page_map', 'ERROR library: this source has no structured pageMap in sources.json, so --printed cannot be resolved; pass --pages (Trove pages)');
  if (map.kind === 'identity') return printed;
  if (map.kind === 'offset') {
    return printed.map((page) => {
      const trove = page + map.trove_minus_printed;
      if (trove < 1) throw new LibraryError('page_map', `ERROR library: printed page ${page} maps below Trove page 1`);
      return trove;
    });
  }
  const dir = resolve(project, '.academic-helper');
  const file = resolve(dir, map.file);
  const inside = relative(resolve(project), file);
  if (inside.startsWith('..') || isAbsolute(inside)) throw new LibraryError('page_map', 'ERROR library: the crosswalk file must be inside the project folder');
  if (!existsSync(file)) throw new LibraryError('page_map', `ERROR library: crosswalk file not found: ${map.file}`);
  let crosswalk: { volumes?: Array<{ volume?: number; stored_to_ck?: Record<string, number> }> };
  try { crosswalk = JSON.parse(readFileSync(file, 'utf8')) as typeof crosswalk; }
  catch { throw new LibraryError('page_map', `ERROR library: crosswalk file is not valid JSON: ${map.file}`); }
  const wanted = map.volume ?? 1;
  const volume = (crosswalk.volumes ?? []).find((entry) => entry.volume === wanted);
  if (!volume?.stored_to_ck) throw new LibraryError('page_map', `ERROR library: crosswalk has no volume ${wanted}`);
  return printed.map((page) => {
    const stored = page + (map.stored_minus_printed ?? 0);
    const trove = volume.stored_to_ck?.[String(stored)];
    if (!Number.isInteger(trove)) throw new LibraryError('page_map', `ERROR library: printed page ${page} has no Trove page in the crosswalk; pass --pages`);
    return trove as number;
  });
}

/** Trove (canonical) pages -> the route's own pages. `missing` lists Trove pages the route does not have. */
export function troveToRoutePages(trove: number[], routePages: RoutePages): { route: number[]; missing: number[] } {
  if (routePages.kind === 'identity') return { route: trove, missing: [] };
  const byTrove = new Map<number, number[]>();
  routePages.pdfToTrove.forEach((troveNumber, index) => {
    const list = byTrove.get(troveNumber) ?? [];
    list.push(index + 1);
    byTrove.set(troveNumber, list);
  });
  const route: number[] = [];
  const missing: number[] = [];
  for (const page of trove) {
    const found = byTrove.get(page);
    if (found) route.push(...found); else missing.push(page);
  }
  return { route, missing };
}

/** The Trove page of one route page (identity for books that share Trove's pages). Null when out of range. */
export function routeToTrovePage(page: number, routePages: RoutePages): number | null {
  if (routePages.kind === 'identity') return page;
  return routePages.pdfToTrove[page - 1] ?? null;
}

/** Route pages -> canonical pages: many-to-one PDF pages are joined under their Trove page, sorted. */
export function relabelPages(pages: PageText[], routePages: RoutePages): CanonicalPage[] {
  if (routePages.kind === 'identity') return pages.map((entry) => ({ page: entry.page, text: entry.text, routePages: [entry.page] })).sort((a, b) => a.page - b.page);
  const grouped = new Map<number, CanonicalPage>();
  for (const entry of pages) {
    const trove = routeToTrovePage(entry.page, routePages);
    if (trove === null) continue;
    const existing = grouped.get(trove);
    if (existing) { existing.text += `\n${entry.text}`; existing.routePages.push(entry.page); }
    else grouped.set(trove, { page: trove, text: entry.text, routePages: [entry.page] });
  }
  return [...grouped.values()].sort((a, b) => a.page - b.page);
}
