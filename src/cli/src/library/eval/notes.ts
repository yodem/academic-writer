import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { PLAIN_ID } from '../backends.ts';
import { evalLimits } from './limits.ts';

/**
 * Footnotes in real articles cite by author and title ("Pedersén, South Palace Archives, 14."), not by source id. This
 * module reads such a note and finds the entry of `.academic-helper/sources.json` it stands for, or says why it cannot.
 * It never guesses: a note that matches no source, or several equally well, is reported as unmatched with the reason.
 */

// ---------------------------------------------------------------- folding: case, diacritics, niqqud, Hebrew final letters

const SPECIAL: Record<string, string> = { 'ø': 'o', 'đ': 'd', 'ł': 'l', 'ß': 'ss', 'æ': 'ae', 'œ': 'oe', 'ı': 'i', 'ð': 'd', 'þ': 'th' };
const FINAL: Record<string, string> = { 'ך': 'כ', 'ם': 'מ', 'ן': 'נ', 'ף': 'פ', 'ץ': 'צ' };

/** Lower case, no combining marks (accents, niqqud, cantillation), no quotes or geresh, Hebrew final letters as plain letters, words split by single spaces. */
export function fold(text: string): string {
  let out = text.normalize('NFKD').toLowerCase().replace(/\p{M}/gu, '');
  out = out.replace(/[׳״'’‘`"“”„]/gu, '');
  out = out.replace(/[øđłßæœıðþ]/gu, (char) => SPECIAL[char] ?? char);
  out = out.replace(/[ךםןףץ]/gu, (char) => FINAL[char] ?? char);
  return out.replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
}

const HEBREW = /^[א-ת]+$/u;
/** Hebrew attaches one-letter prefixes (the, and, in, to, from, that); a note word may carry one or two. */
const PREFIX_LETTERS = new Set(['ו', 'ה', 'ב', 'כ', 'ל', 'מ', 'ש']);

function tokensOf(text: string): string[] { return fold(text).split(' ').filter(Boolean); }

/** The note word equals the wanted word, or is that Hebrew word with up to two prefix letters. */
function sameWord(noteWord: string, wanted: string): boolean {
  if (noteWord === wanted) return true;
  if (!HEBREW.test(noteWord) || !HEBREW.test(wanted) || wanted.length < 3) return false;
  const extra = noteWord.length - wanted.length;
  return extra >= 1 && extra <= 2 && noteWord.endsWith(wanted) && [...noteWord.slice(0, extra)].every((letter) => PREFIX_LETTERS.has(letter));
}

function hasWord(tokens: string[], wanted: string): boolean { return tokens.some((token) => sameWord(token, wanted)); }

function hasSequence(tokens: string[], wanted: string[]): boolean {
  if (wanted.length === 0) return false;
  for (let at = 0; at + wanted.length <= tokens.length; at += 1) {
    if (wanted.every((word, index) => sameWord(tokens[at + index] as string, word))) return true;
  }
  return false;
}

// ---------------------------------------------------------------- the sources a note may stand for

const STOPWORDS = new Set([
  'the', 'and', 'for', 'from', 'with', 'into', 'its', 'their', 'that', 'this', 'les', 'des', 'der', 'die', 'das', 'und', 'von', 'van', 'del', 'della',
  'של', 'את', 'על', 'עם', 'אל', 'מן', 'או', 'גם', 'כי', 'הוא', 'היא', 'זה', 'זאת', 'בין', 'לא', 'אשר',
]);

export type SourceCard = {
  id: string;
  title: string;
  /** Each author's surname as folded words ("van der berg" is three words). */
  surnames: string[][];
  /** Distinctive folded words of the title (no short or common words). */
  titleWords: string[];
  year: string | null;
};

function textOf(value: unknown): string { return typeof value === 'string' ? value : typeof value === 'number' ? String(value) : ''; }

/** Surnames out of an author field: "Last, First", "First Last", "A and B", a list, or {family, given}. */
export function surnamesOf(author: unknown): string[][] {
  const out: string[][] = [];
  const add = (surname: string): void => { const words = tokensOf(surname); if (words.length > 0) out.push(words); };
  if (Array.isArray(author)) { for (const entry of author) out.push(...surnamesOf(entry)); return out; }
  if (typeof author === 'object' && author !== null) {
    const record = author as Record<string, unknown>;
    const family = textOf(record.family ?? record.surname ?? record.last ?? record.lastName);
    if (family) add(family); else out.push(...surnamesOf(textOf(record.name ?? record.literal)));
    return out;
  }
  const text = textOf(author).trim();
  if (!text) return out;
  for (const piece of text.split(/\s+(?:and|&|ו)\s+|\s*;\s*/iu)) {
    const trimmed = piece.trim();
    if (!trimmed) continue;
    if (trimmed.includes(',')) add(trimmed.slice(0, trimmed.indexOf(',')));
    else { const words = trimmed.split(/\s+/u); add(words[words.length - 1] as string); }
  }
  return out;
}

function distinctive(title: string): string[] {
  return [...new Set(tokensOf(title).filter((word) => word.length >= 3 && !STOPWORDS.has(word)))];
}

function listOf(raw: unknown, key: string): Array<Record<string, unknown>> {
  const list: unknown = Array.isArray(raw) ? raw : (raw as Record<string, unknown> | null | undefined)?.[key];
  return Array.isArray(list) ? list.filter((entry): entry is Record<string, unknown> => typeof entry === 'object' && entry !== null) : [];
}

function readQuiet(file: string): unknown {
  if (!existsSync(file)) return undefined;
  try { return JSON.parse(readFileSync(file, 'utf8')); } catch { return undefined; }
}

/** One card per source of `.academic-helper/sources.json` (and, for sources only there, `evidence.json`). */
export function loadSourceCards(project: string): SourceCard[] {
  const dir = join(project, '.academic-helper');
  const cards = new Map<string, SourceCard>();
  const add = (entry: Record<string, unknown>, idKeys: string[], titleKeys: string[]): void => {
    const id = textOf(idKeys.map((key) => entry[key]).find((value) => textOf(value) !== ''));
    if (!id || !PLAIN_ID.test(id) || cards.has(id)) return;
    const titles = titleKeys.map((key) => textOf(entry[key])).filter(Boolean);
    const year = /\b(1[0-9]{3}|20[0-9]{2})\b/u.exec(textOf(entry.year ?? entry.date ?? entry.issued))?.[1] ?? null;
    cards.set(id, {
      id, title: titles[0] ?? id, year,
      surnames: surnamesOf(entry.author ?? entry.authors ?? entry.creators),
      titleWords: [...new Set(titles.flatMap(distinctive))],
    });
  };
  for (const entry of listOf(readQuiet(join(dir, 'sources.json')), 'sources')) add(entry, ['sourceId', 'id'], ['workTitle', 'title', 'shortTitle']);
  for (const entry of listOf(readQuiet(join(dir, 'evidence.json')), 'sources')) add(entry, ['id', 'sourceId'], ['title', 'workTitle', 'shortTitle']);
  return [...cards.values()];
}

// ---------------------------------------------------------------- matching one citation

export type SegmentMatch =
  | { kind: 'source'; card: SourceCard; printed: number[] }
  | { kind: 'ibid'; printed: number[] }
  | { kind: 'unmatched'; reason: string };

const IBID = new Set(['ibid', 'ibidem', 'idem', 'שם', 'שמ']);
const LEAD_IN = new Set(['see', 'also', 'cf', 'compare', 'and', 'ראו', 'וראו', 'ראה', 'השוו', 'השוה', 'וכן']);

/** True when the citation only repeats the previous note ("Ibid., 15", "שם, עמ׳ 34"). */
export function isIbid(segment: string): boolean {
  const tokens = tokensOf(segment);
  let at = 0;
  while (at < tokens.length && LEAD_IN.has(tokens[at] as string)) at += 1;
  const first = tokens[at];
  return first !== undefined && IBID.has(first) && !/\p{L}{3,}/u.test(tokens.slice(at + 1).filter((word) => !['p', 'pp', 'עמ', 'עמוד', 'עמודים', 'page', 'pages'].includes(word)).join(' ').replace(/\d+/gu, ''));
}

const YEAR_LIKE = (value: number): boolean => value >= 1000 && value <= 2100;

function pageRange(first: number, last: number): number[] {
  const pages: number[] = [];
  for (let page = first; page <= Math.max(first, last) && pages.length < evalLimits.maxAnswerPages; page += 1) pages.push(page);
  return pages;
}

const NAMED_PAGE = /(?<![\p{L}\p{N}])(?:pp?\.|pages?|עמ[׳'’]?|עמוד(?:ים)?)\s*(\d{1,5})(?:\s*[-–—]\s*(\d{1,5}))?/iu;
const TRAILING_PAGE = /[,:\s](\d{1,5})(?:\s*[-–—]\s*(\d{1,5}))?\s*[.)\]]*\s*$/u;

/** Printed pages a citation names: "p. 14", "pp. 27–29", "עמ׳ 33", or a bare number closing the note ("…Archives, 14."). A year is never taken for a page. */
export function pagesCited(segment: string, year: string | null): number[] {
  const named = NAMED_PAGE.exec(segment);
  if (named) return pageRange(Number(named[1]), named[2] ? Number(named[2]) : Number(named[1]));
  const trailing = TRAILING_PAGE.exec(segment.trim());
  if (!trailing) return [];
  const first = Number(trailing[1]);
  const last = trailing[2] ? Number(trailing[2]) : first;
  if (YEAR_LIKE(first) && !trailing[2]) return [];
  if (year !== null && String(first) === year) return [];
  return pageRange(first, last);
}

/** Splits a note into its citations ("A, X, 5; B, Y, 7" is two). */
export function segmentsOf(note: string): string[] {
  return note.split(/\s*[;؛]\s*/u).map((piece) => piece.trim()).filter(Boolean);
}

/** Find the source one citation stands for: author surname(s) and distinctive title words (or the year), with ties left unmatched. */
export function matchSegment(cards: SourceCard[], segment: string): SegmentMatch {
  if (isIbid(segment)) return { kind: 'ibid', printed: pagesCited(segment, null) };
  const tokens = tokensOf(segment);
  type Scored = { card: SourceCard; score: number; titleHits: number; yearHit: boolean };
  const byAuthor: SourceCard[] = [];
  const eligible: Scored[] = [];
  for (const card of cards) {
    const authorsHit = card.surnames.filter((surname) => hasSequence(tokens, surname)).length;
    if (authorsHit === 0) continue;
    byAuthor.push(card);
    const titleHits = card.titleWords.filter((word) => hasWord(tokens, word)).length;
    const yearHit = card.year !== null && tokens.includes(card.year);
    if (titleHits === 0 && !yearHit) continue;
    eligible.push({
      card, titleHits, yearHit,
      score: titleHits / Math.max(1, card.titleWords.length) + (yearHit ? 0.5 : 0) + (authorsHit / card.surnames.length) * 0.25,
    });
  }
  if (eligible.length === 0) {
    return { kind: 'unmatched', reason: byAuthor.length === 0
      ? 'no source in sources.json has an author surname that appears in the note'
      : `the author matches ${byAuthor.map((card) => card.id).join(', ')} but no title word or year of it appears in the note` };
  }
  eligible.sort((a, b) => b.score - a.score);
  const [best, second] = eligible as [Scored, ...Scored[]];
  if (second && second.score >= best.score - 1e-9) {
    const tied = eligible.filter((entry) => entry.score >= best.score - 1e-9).map((entry) => entry.card.id);
    return { kind: 'unmatched', reason: `the note matches several sources equally (${tied.join(', ')}); name more of the title` };
  }
  return { kind: 'source', card: best.card, printed: pagesCited(segment, best.card.year) };
}

// ---------------------------------------------------------------- one article: notes in order, with "Ibid."

export type NoteSource = { sourceId: string; title: string; printed: number[] };
export type UnmatchedNote = { unit: string; note: string; text: string; reason: string };
export type NoteResolution = {
  sources: NoteSource[];
  unmatched: Array<{ text: string; reason: string }>;
  /** Some citations of the note matched a source and others did not: the note counts as unresolved (`sources` is empty). */
  partial: boolean;
};

/**
 * Resolves the notes of one draft file in the order they first appear. "Ibid." and "שם" repeat the previous note's single
 * source (and take their own page); with no earlier note, an unmatched earlier note or an earlier note of several sources
 * they stay unmatched. A note with several citations of which only some match is unresolved as a whole, and so is an
 * "Ibid." after it: the matched part alone would be a guess about what the note cites.
 */
export class NoteResolver {
  private previous: { sources: NoteSource[]; reason: string | null } | null = null;
  private readonly seen = new Map<string, NoteResolution>();

  constructor(private readonly cards: SourceCard[]) {}

  /** Record a note that was resolved some other way (by its source id), so a following "Ibid." can repeat it. */
  noteResolvedByKey(key: string, source: NoteSource | null): void {
    this.seen.set(key, { sources: source ? [source] : [], unmatched: [], partial: false });
    this.previous = { sources: source ? [source] : [], reason: source ? null : 'the previous note names no known source' };
  }

  resolve(key: string, text: string): NoteResolution {
    const known = this.seen.get(key);
    if (known) return known;
    const result: NoteResolution = { sources: [], unmatched: [], partial: false };
    const trimmed = text.trim();
    if (!trimmed) result.unmatched.push({ text: '', reason: 'the note has no text to match' });
    for (const segment of segmentsOf(trimmed)) {
      const match = matchSegment(this.cards, segment);
      if (match.kind === 'source') result.sources.push({ sourceId: match.card.id, title: match.card.title, printed: match.printed });
      else if (match.kind === 'unmatched') result.unmatched.push({ text: segment, reason: match.reason });
      else if (this.previous === null) result.unmatched.push({ text: segment, reason: 'Ibid. with no earlier note to repeat' });
      else if (this.previous.reason !== null) result.unmatched.push({ text: segment, reason: `Ibid. repeats the previous note, but ${this.previous.reason}` });
      else if (this.previous.sources.length !== 1) result.unmatched.push({ text: segment, reason: 'Ibid. repeats a previous note that cites several sources, so it does not say which' });
      else result.sources.push({ ...(this.previous.sources[0] as NoteSource), printed: match.printed });
    }
    if (result.sources.length > 0 && result.unmatched.length > 0) {
      const matched = [...new Set(result.sources.map((source) => source.sourceId))].join(', ');
      result.partial = true;
      result.sources = [];
      result.unmatched = result.unmatched.map((item) => ({ text: item.text, reason: `partial match: another citation of this note matched ${matched}, so the whole note is left unresolved; ${item.reason}` }));
    }
    this.seen.set(key, result);
    this.previous = {
      sources: result.sources,
      reason: result.sources.length === 0 ? `the previous note is unmatched (${result.unmatched[0]?.reason ?? 'no text'})` : null,
    };
    return result;
  }
}
