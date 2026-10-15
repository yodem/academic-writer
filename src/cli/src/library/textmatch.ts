// Word-level text comparison for the retrieval ledger. Two routes return the same page with different
// layout (niqqud, headers, run order), so pages are compared as sets of normalised words, not as strings.
const INVISIBLE = /[​-‏‪-‮⁠-⁩﻿]/gu;
const HEBREW_MARKS = /[֑-ׇֽֿׁׂׅׄ]/gu;
const INWORD_QUOTES = /["'`׳״‘’“”]/gu;

/** NFC, no niqqud or cantillation, no bidi marks, quotes inside words dropped, other punctuation to spaces, lower case. */
export function normalizeText(text: string): string {
  return text
    .normalize('NFC')
    .replace(INVISIBLE, '')
    .replace(HEBREW_MARKS, '')
    .replace(INWORD_QUOTES, '')
    .replace(/[\p{P}\p{S}]+/gu, ' ')
    .toLowerCase()
    .replace(/\s+/gu, ' ')
    .trim();
}

export function tokens(text: string): string[] {
  const normal = normalizeText(text);
  return normal ? normal.split(' ') : [];
}

/** Word overlap of two texts: shared words over all words. Two empty texts count as the same. */
export function jaccard(a: string, b: string): number {
  const left = new Set(tokens(a));
  const right = new Set(tokens(b));
  if (left.size === 0 && right.size === 0) return 1;
  let shared = 0;
  for (const word of left) if (right.has(word)) shared += 1;
  return shared / (left.size + right.size - shared);
}

/** The share of the quote's words found in `text`; 0 when the quote has no words. */
export function coverage(quote: string, text: string): number {
  const wanted = tokens(quote);
  if (wanted.length === 0) return 0;
  const have = new Set(tokens(text));
  return wanted.filter((word) => have.has(word)).length / wanted.length;
}
