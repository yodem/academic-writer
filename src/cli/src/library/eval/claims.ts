import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { PLAIN_ID } from '../backends.ts';
import { printedToTrove } from '../pages.ts';
import { findSource, stripFragment } from '../registry.ts';
import { evalLimits } from './limits.ts';

// ---------------------------------------------------------------- reading a draft

export type DraftSentence = { text: string; keys: string[]; paragraphId: string; order: number };
export type ParsedDraft = { sentences: DraftSentence[]; definitions: Map<string, string> };

const DEFINITION = /^\[\^([^\]]+)\]:\s*(.*)$/u;
const MARKER = /\[\^([^\]]+)\]/gu;
const ABBREVIATIONS = new Set(['e.g', 'i.e', 'cf', 'ca', 'vol', 'no', 'ed', 'eds', 'pp', 'p', 'vs', 'etc', 'fig', 'ch', 'esp', 'trans', 'et al', 'al']);

function normalise(text: string): string { return text.normalize('NFC').replace(/\s+/gu, ' ').trim(); }

function wordBefore(text: string, index: number): string {
  let start = index;
  while (start > 0 && /[\p{L}.]/u.test(text[start - 1] as string)) start -= 1;
  return text.slice(start, index).toLowerCase();
}

/** Split a paragraph into sentences. A footnote marker after the full stop stays with the sentence it follows. */
export function splitSentences(paragraph: string): string[] {
  const out: string[] = [];
  let start = 0;
  let index = 0;
  while (index < paragraph.length) {
    const char = paragraph[index] as string;
    if (!'.!?׃'.includes(char)) { index += 1; continue; }
    let end = index + 1;
    for (;;) {
      const marker = /^\[\^[^\]]+\]/u.exec(paragraph.slice(end));
      if (marker) { end += marker[0].length; continue; }
      if (end < paragraph.length && /[.!?׃"”’'״)]/u.test(paragraph[end] as string)) { end += 1; continue; }
      break;
    }
    const atBreak = end >= paragraph.length || /\s/u.test(paragraph[end] as string);
    const word = char === '.' && end === index + 1 ? wordBefore(paragraph, index) : '';
    const abbreviation = word !== '' && (word.length === 1 || ABBREVIATIONS.has(word));
    if (atBreak && !abbreviation) {
      out.push(paragraph.slice(start, end));
      start = end;
    }
    index = end;
  }
  if (start < paragraph.length) out.push(paragraph.slice(start));
  return out.map((piece) => piece.trim()).filter(Boolean);
}

/**
 * The cited-sentence view of one draft file. Paragraphs are the blank-line blocks that are not headings and not
 * footnote definitions, numbered from 1 (`<unit>_p_<n>`, the id the auditor records). A sentence is kept when it
 * carries at least one `[^key]` marker.
 */
export function parseDraft(markdown: string, unitId: string): ParsedDraft {
  const definitions = new Map<string, string>();
  const sentences: DraftSentence[] = [];
  let paragraphNumber = 0;
  let order = 0;
  for (const block of markdown.split(/\n\s*\n/u)) {
    const lines: string[] = [];
    for (const line of block.split('\n')) {
      const match = DEFINITION.exec(line.trim());
      if (match) definitions.set(match[1] as string, normalise(match[2] ?? ''));
      else lines.push(line);
    }
    const body = normalise(lines.join(' '));
    if (!body || body.startsWith('#')) continue;
    paragraphNumber += 1;
    for (const piece of splitSentences(body)) {
      const keys = [...new Set([...piece.matchAll(MARKER)].map((match) => match[1] as string))];
      if (keys.length === 0) continue;
      const text = normalise(piece.replace(MARKER, ' ')).replace(/\s+([.,;:!?׃])/gu, '$1');
      order += 1;
      sentences.push({ text, keys, paragraphId: `${unitId}_p_${paragraphNumber}`, order });
    }
  }
  return { sentences, definitions };
}

export function wordCount(text: string): number { return text.split(/\s+/u).filter((word) => /[\p{L}\p{N}]/u.test(word)).length; }

// ---------------------------------------------------------------- the registry (sources.json / evidence.json)

export type Registry = {
  loaded: boolean;
  sources: Map<string, string>;
  passages: Map<string, { sourceId: string; locator: string }>;
};

function readJsonQuiet(file: string): unknown {
  if (!existsSync(file)) return undefined;
  try { return JSON.parse(readFileSync(file, 'utf8')); } catch { return undefined; }
}

function listOf(raw: unknown, key: string): Array<Record<string, unknown>> {
  const list: unknown = Array.isArray(raw) ? raw : (raw as Record<string, unknown> | null | undefined)?.[key];
  return Array.isArray(list) ? list.filter((entry): entry is Record<string, unknown> => typeof entry === 'object' && entry !== null) : [];
}

export function loadRegistry(project: string): Registry {
  const registry: Registry = { loaded: false, sources: new Map(), passages: new Map() };
  const dir = join(project, '.academic-helper');
  const sources = readJsonQuiet(join(dir, 'sources.json'));
  const evidence = readJsonQuiet(join(dir, 'evidence.json'));
  for (const entry of listOf(sources, 'sources')) {
    const id = String(entry.sourceId ?? entry.id ?? '');
    if (id) { registry.sources.set(id, String(entry.workTitle ?? entry.title ?? id)); registry.loaded = true; }
  }
  for (const entry of listOf(evidence, 'sources')) {
    const id = String(entry.id ?? entry.sourceId ?? '');
    if (id && !registry.sources.has(id)) { registry.sources.set(id, String(entry.title ?? entry.workTitle ?? id)); registry.loaded = true; }
  }
  for (const entry of listOf(evidence, 'passages')) {
    if (typeof entry.id === 'string' && typeof entry.sourceId === 'string') {
      registry.passages.set(entry.id, { sourceId: entry.sourceId, locator: typeof entry.locator === 'string' ? entry.locator : '' });
      registry.loaded = true;
    }
  }
  return registry;
}

export type ResolvedKey = { sourceId: string; title: string; printed: number[]; trove: number[] };

const PRINTED_PAGE = /(?<![\p{L}\p{N}])(?:pp?\.|pages?|עמ[׳'’]?|עמוד(?:ים)?)\s*(\d{1,5})(?:\s*[-–—]\s*(\d{1,5}))?/iu;

/** Page numbers named in a citation text ("p. 12", "pp. 12-14", "עמ׳ 12"); at most `limit` of them. */
export function pagesNamedIn(text: string, limit = evalLimits.maxAnswerPages): number[] {
  const match = PRINTED_PAGE.exec(text);
  if (!match) return [];
  const first = Number(match[1]);
  const last = match[2] ? Number(match[2]) : first;
  const pages: number[] = [];
  for (let page = first; page <= Math.max(first, last) && pages.length < limit; page += 1) pages.push(page);
  return pages;
}

/** Trove pages and printed pages a passage locator names: "Page 12 (orig. 5)" is Trove page 12, printed 5. */
function fromLocator(locator: string): { trove: number[]; printed: number[] } {
  const trove = /^\s*Page\s+(\d{1,6})\b/iu.exec(locator);
  const original = /\borig\.?\s*(\d{1,6})/iu.exec(locator);
  if (trove) return { trove: [Number(trove[1])], printed: original ? [Number(original[1])] : [] };
  return { trove: [], printed: pagesNamedIn(locator) };
}

/** Which source a footnote key stands for, its title and the pages the citation names; null when it names none we know. */
export function resolveKey(project: string, registry: Registry, key: string, definitions: Map<string, string>): ResolvedKey | null {
  const passage = registry.passages.get(key);
  const sourceId = passage ? passage.sourceId : key;
  const known = registry.sources.has(sourceId) ? sourceId : [...registry.sources.keys()].find((id) => stripFragment(id) === stripFragment(sourceId));
  if (registry.loaded && !known) return null;
  if (!registry.loaded && !PLAIN_ID.test(sourceId)) return null;
  const id = known ?? sourceId;
  if (!PLAIN_ID.test(id)) return null;
  const title = registry.sources.get(id) ?? id;
  let trove: number[] = [];
  let printed: number[] = [];
  if (passage) ({ trove, printed } = fromLocator(passage.locator));
  if (trove.length === 0 && printed.length === 0) printed = pagesNamedIn(definitions.get(key) ?? '');
  if (trove.length === 0 && printed.length > 0) {
    const map = findSource(project, id)?.pageMap;
    if (map) { try { trove = printedToTrove(printed, map, project); } catch { trove = []; } }
  }
  return { sourceId: id, title, printed, trove };
}

// ---------------------------------------------------------------- the article's files

/** Draft files of an article: one markdown file, or the .md files of a folder (sorted by name). */
export function draftFiles(path: string): Array<{ file: string; unit: string }> {
  const unitOf = (file: string): string => (file.split('/').pop() ?? file).replace(/\.md$/iu, '');
  if (!existsSync(path)) return [];
  if (!readdirSafe(path)) return [{ file: path, unit: unitOf(path) }];
  return (readdirSafe(path) ?? []).filter((name) => name.toLowerCase().endsWith('.md')).sort().map((name) => ({ file: join(path, name), unit: unitOf(name) }));
}

function readdirSafe(path: string): string[] | null {
  try { return readdirSync(path); } catch { return null; }
}
