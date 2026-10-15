// Shared types for `aw library`: one adapter in front of the Trove and PageIndex routes.
export type RouteName = 'trove' | 'pageindex';
export type RouteMode = RouteName | 'both';

/** One page of text. `page` is the page number in the space the producer works in (route or canonical). */
export type PageText = { page: number; text: string };
/** A canonical (Trove-numbered) page; `routePages` lists the route pages it was built from. */
export type CanonicalPage = { page: number; text: string; routePages: number[] };
export type BookInfo = { id: string; title: string; author: string; pageCount: number | null };
export type TocEntry = { title: string; page: number; endPage: number | null; level: number };
export type TocResult = { title: string | undefined; toc: TocEntry[] };
export type RawRead = { pages: PageText[]; raw?: string; title?: string; pageCount?: number | null };

/** Backend-level view of one route. `book` is the route's own book id; pages are in the route's own numbering. */
export interface LibraryBackend {
  readonly route: RouteName;
  list(): Promise<BookInfo[]>;
  toc(book: string): Promise<TocResult>;
  read(book: string, pages: number[] | 'all'): Promise<RawRead>;
  title(book: string): Promise<string | undefined>;
}

export type LibraryErrorCode = 'usage' | 'config' | 'spawn' | 'timeout' | 'exit' | 'too_large' | 'parse' | 'page_map' | 'page_missing' | 'lock';

export class LibraryError extends Error {
  readonly code: LibraryErrorCode;
  readonly stderr: string;
  constructor(code: LibraryErrorCode, message: string, stderr = '') {
    super(message);
    this.name = 'LibraryError';
    this.code = code;
    this.stderr = stderr;
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
