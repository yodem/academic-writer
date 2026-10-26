import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { callGemini } from './gemini.ts';
import { decide } from './decide.ts';
import { projectDir } from './paths.ts';
import { AwError, Budget, budgetFor } from './ledger.ts';
import { voiceBundle } from './voice.ts';
import { emit, endRunOnError, startRunOnce, type ActivityFlow } from './activity.ts';
import thresholds from '../../thresholds.json' with { type: 'json' };
import DRAFT_PROMPT from './prompts/write-draft.md';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Role = 'intro' | 'conclusion' | 'body';
export type OutlineParagraph = { move?: string; evidenceIds?: string[]; bridgeTo?: string };
export type OutlineUnit = { id: string; dependsOn?: string[]; role?: string; claim?: string; paragraphs?: OutlineParagraph[]; [key: string]: unknown };
export type OutlineSection = { id: string; title?: string; claim?: string; units?: OutlineUnit[] };
export type Outline = { thesis?: string; units?: OutlineUnit[]; sections?: OutlineSection[]; [key: string]: unknown };

type BannedWord = { word: string; replacement: string | null };
type CappedWord = { word: string; maxPer: 'paragraph' | 'chapter'; max: number; replacement?: string | null };
export type StyleWords = { banned: BannedWord[]; capped: CappedWord[]; filler: string[] };
export type VoiceBundle = { exemplars: unknown[]; pairs: unknown[]; rules: string; styleWords: StyleWords };

export type Predecessor = { id: string; text: string };
type GenFn = (unit: OutlineUnit, predecessors: Predecessor[]) => Promise<string>;
type Stubs = { gen?: GenFn; evidenceQuotes?: string[]; voice?: VoiceBundle };
let stubs: Stubs = {};
export function __stubs(value: Stubs): void { stubs = value; }

export type DraftFailure = { unit: string; gate: string; detail: string };
export type AuditItem = { unit: string; paragraphIndex: number; required: true };
export type DraftAllResult = { drafted: string[]; failures: DraftFailure[]; audit: AuditItem[] };
export type DraftAllOptions = { runId: string; unit?: string; feedbackFile?: string; flow?: ActivityFlow };

const EMPTY_STYLE_WORDS: StyleWords = { banned: [], capped: [], filler: [] };

// ---------------------------------------------------------------------------
// Outline helpers
// ---------------------------------------------------------------------------

function roleOf(unit: OutlineUnit): Role {
  if (unit.role === 'intro' || unit.role === 'conclusion') return unit.role;
  if (unit.id === 'intro') return 'intro';
  if (unit.id === 'conclusion') return 'conclusion';
  return 'body';
}

// The spec test's outline is a flat `{ units: [...] }` list; the real
// outline.json (src/schemas/outline.schema.json) nests units under
// sections. Support both by flattening sections[].units when a top-level
// `units` array is absent.
function flatten(outline: Outline): OutlineUnit[] {
  if (Array.isArray(outline.units)) return outline.units;
  const sections = Array.isArray(outline.sections) ? outline.sections : [];
  return sections.flatMap((section) => (Array.isArray(section.units) ? section.units : []));
}

// Kahn's algorithm over dependsOn, restricted to body units. A dangling
// dependsOn id outside the body-unit set (e.g. a stray reference to
// 'intro') is ignored for ordering purposes -- intro/conclusion are always
// drafted last regardless of what they declare.
function topoSort(units: OutlineUnit[]): OutlineUnit[] {
  const byId = new Map(units.map((unit) => [unit.id, unit]));
  const indegree = new Map(units.map((unit) => [unit.id, 0]));
  const dependents = new Map<string, string[]>();
  for (const unit of units) {
    for (const dep of unit.dependsOn ?? []) {
      if (!byId.has(dep)) continue;
      indegree.set(unit.id, (indegree.get(unit.id) ?? 0) + 1);
      dependents.set(dep, [...(dependents.get(dep) ?? []), unit.id]);
    }
  }
  const queue = units.filter((unit) => (indegree.get(unit.id) ?? 0) === 0).map((unit) => unit.id);
  const order: OutlineUnit[] = [];
  const seen = new Set<string>();
  while (queue.length) {
    const id = queue.shift();
    if (id === undefined || seen.has(id)) continue;
    seen.add(id);
    const unit = byId.get(id);
    if (unit) order.push(unit);
    for (const next of dependents.get(id) ?? []) {
      indegree.set(next, (indegree.get(next) ?? 1) - 1);
      if ((indegree.get(next) ?? 0) <= 0) queue.push(next);
    }
  }
  if (order.length !== units.length) {
    const stuck = units.filter((unit) => !seen.has(unit.id)).map((unit) => unit.id);
    throw new AwError('ERROR', 'write.draft', `cycle detected in dependsOn: ${stuck.join(', ')}`);
  }
  return order;
}

// ---------------------------------------------------------------------------
// Text analysis: citations, quotes, style words, word bounds
// ---------------------------------------------------------------------------

function normalize(value: string): string {
  return value.normalize('NFC').replace(/\s+/gu, ' ').trim();
}

function splitParagraphs(text: string): string[] {
  return text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
}

// Footnote citation keys: `[^sourceId]` markers and `[^sourceId]:` definitions
// both match; a definition necessarily also cites a real sourceId.
function extractCitationKeys(text: string): string[] {
  const keys = new Set<string>();
  const re = /\[\^([^\]]+)\]/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text))) keys.add(match[1]!);
  return [...keys];
}

const HEBREW_LETTER = /[א-ת]/;
// A gershayim (״) or a straight double quote (") with a Hebrew letter on both sides is an abbreviation
// or numeral mark (e.g. רמב״ם, תשכ"ב), never a quotation delimiter -- filter those out before
// pairing the rest as open/close quote marks. Hebrew quotations are written with a straight " (author
// decision 2026-10-26); gershayim is accepted here only so older drafts still pair correctly.
function isAbbreviationMark(text: string, index: number): boolean {
  const prev = text[index - 1];
  const next = text[index + 1];
  // An acronym's gershayim precede exactly ONE final letter (רמב״ם, ז״ל, ע״י). A quote opened after a
  // prefix letter (ה"יש מאין", ה״יש מאין״) has a longer word after it and IS a delimiter; treating it as an
  // acronym broke the pairing of every later quote (live rehearsal 2026-09-23).
  const after = text[index + 2];
  return Boolean(prev && next && HEBREW_LETTER.test(prev) && HEBREW_LETTER.test(next) && !(after && HEBREW_LETTER.test(after)));
}

const PREFIX_LETTERS = 'והבכלמש';
const MAX_AMBIGUOUS_MARKS = 12;

// A quotation opens before a letter, digit, opening bracket or ellipsis, after a non-letter or after a word
// of one or two prefix letters (ב"תשורי", וב"ב"); it closes after a non-space and before a non-letter. An acronym-shaped mark that could also
// open a quotation (ב"ה, ש"ס, or the one-letter quotation ב"א") is ambiguous; any other acronym-shaped
// mark (רמב"ם, ז"ל, תשכ"ב) is always an acronym.
function canOpen(text: string, index: number): boolean {
  const next = text[index + 1];
  if (!next || !/[\p{L}\p{N}(\[\u2018'\u2026]/u.test(next)) return false;
  let start = index;
  while (start > 0 && /\p{L}/u.test(text[start - 1]!)) start -= 1;
  const cluster = text.slice(start, index);
  return !cluster || (cluster.length <= 2 && [...cluster].every((letter) => PREFIX_LETTERS.includes(letter)));
}

function canClose(text: string, index: number): boolean {
  const prev = text[index - 1]; const next = text[index + 1];
  return Boolean(prev) && !/\s/u.test(prev!) && (!next || !/\p{L}/u.test(next));
}

// Curly quotes nest by direction, so they are parsed as a stack: every “…” span, outer and inner, is checked
// (the outer span keeps the inner marks, so a long outer quotation is never hidden behind a short inner one),
// and a stray “ or ” makes the quotes uncheckable.
function curlySpans(text: string): string[] | null {
  const open: number[] = []; const spans: string[] = [];
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] === '\u201C') open.push(index);
    else if (text[index] === '\u201D') {
      const start = open.pop();
      if (start === undefined) return null;
      spans.push(text.slice(start + 1, index));
    }
  }
  return open.length ? null : spans;
}

type Reading = { spans: string[] };

// The plausible readings of one quote character: every assignment of the ambiguous marks (acronym or
// quotation mark) is tried -- just one when there are none -- and kept only when the marks pair up and
// every pair can open and close where it sits. A same-character nested quotation ("א "ב" ג") has a
// closing mark before a letter, so it admits no plausible reading and the gate fails closed.
function readings(text: string, char: string): Reading[] | null {
  const sure: number[] = []; const ambiguous: number[] = [];
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] !== char) continue;
    if (!isAbbreviationMark(text, index)) sure.push(index);
    else if (canOpen(text, index)) ambiguous.push(index);
  }
  const spansOf = (marks: number[]): string[] => {
    const spans: string[] = [];
    for (let index = 0; index + 1 < marks.length; index += 2) spans.push(text.slice(marks[index]! + 1, marks[index + 1]));
    return spans;
  };
  if (ambiguous.length > MAX_AMBIGUOUS_MARKS) return null;
  const plausible: Reading[] = [];
  for (let mask = 0; mask < 1 << ambiguous.length; mask += 1) {
    const marks = [...sure, ...ambiguous.filter((_, bit) => (mask >> bit) & 1)].sort((a, b) => a - b);
    if (marks.length % 2 === 1) continue;
    // A mark that could both open and close ("(", ")") lets a nested reading hide behind a flat one, so a
    // reading that relies on one is not checkable.
    if (marks.some((mark) => canOpen(text, mark) && canClose(text, mark))) continue;
    let ok = true;
    for (let index = 0; ok && index + 1 < marks.length; index += 2) ok = canOpen(text, marks[index]!) && canClose(text, marks[index + 1]!);
    if (ok) plausible.push({ spans: spansOf(marks) });
  }
  return plausible.length ? plausible : null;
}

// Every plausible reading must pass the evidence gate; when the marks admit no plausible reading the
// quotes cannot be checked, and the gate fails closed rather than letting an unsupported quotation through.
function extractQuotedSpans(text: string): { spans: string[]; unbalanced: boolean } {
  const curly = curlySpans(text); // “…” (Latin-script quotations)
  const spans: string[] = [...(curly ?? [])];
  let unbalanced = curly === null;
  for (const char of ['״', '"']) { // ״…״ (older style) and "…" (Hebrew quotations)
    const found = readings(text, char);
    if (!found) unbalanced = true;
    else for (const reading of found) spans.push(...reading.spans);
  }
  return { spans: spans.filter((span) => span.trim().length > 0), unbalanced };
}

function countOccurrences(haystack: string, needle: string): number {
  if (!needle) return 0;
  return haystack.split(needle).length - 1;
}

function runGates(unit: OutlineUnit, text: string, paragraphs: string[], ctx: { sourceKeys: Set<string>; evidenceQuotes: string[]; styleWords: StyleWords; quoteCheckText?: string }): { gate: string; detail: string } | null {
  const citations = extractCitationKeys(text);
  const badCitation = citations.find((key) => !ctx.sourceKeys.has(key));
  if (badCitation !== undefined) return { gate: 'citation-not-in-sources', detail: badCitation };

  const quoteText = ctx.quoteCheckText ?? text;
  const leftover = quoteText.match(/⟦Q:([^⟧\s]+)⟧/u);
  if (leftover) return { gate: 'quote-not-in-evidence', detail: `unknown quote placeholder ${leftover[1]}` };
  const pool = ctx.evidenceQuotes.map(normalize).filter(Boolean);
  const termMaxWords = (thresholds.paragraph as { quotedTermMaxWords?: number }).quotedTermMaxWords ?? 0;
  const quoted = extractQuotedSpans(quoteText);
  if (quoted.unbalanced) return { gate: 'quote-not-in-evidence', detail: 'quotation marks cannot be paired, so the quotations cannot be checked against the evidence: balance every opening " with a closing one, put a quotation inside a quotation in single quotes (\'…\'), and bring source wording through ⟦Q:ID⟧ placeholders' };
  for (const quote of quoted.spans) {
    const needle = normalize(quote);
    if (!needle) continue;
    // A short span in quotation marks is a term or phrase ("יש מאין"), not a source quotation.
    if (needle.split(' ').length <= termMaxWords) continue;
    if (!pool.some((passage) => passage.includes(needle))) return { gate: 'quote-not-in-evidence', detail: quote.slice(0, 80) };
  }

  for (const banned of ctx.styleWords.banned) {
    if (text.includes(banned.word)) return { gate: 'style-banned', detail: banned.word };
  }
  for (const capped of ctx.styleWords.capped) {
    if (capped.maxPer === 'chapter') {
      const count = countOccurrences(text, capped.word);
      if (count > capped.max) return { gate: 'style-capped', detail: `"${capped.word}" x${count} > ${capped.max}/chapter` };
    } else {
      for (const paragraph of paragraphs) {
        const count = countOccurrences(paragraph, capped.word);
        if (count > capped.max) return { gate: 'style-capped', detail: `"${capped.word}" x${count} > ${capped.max}/paragraph` };
      }
    }
  }

  // Word bounds only apply to units whose outline entry actually describes a
  // paragraph plan -- a unit the outline doesn't shape this way (e.g. the
  // flat test fixture's units) has no basis for a min/max word judgement.
  if (Array.isArray(unit.paragraphs)) {
    // Count the author's prose: code-inserted verbatim quotes (a placeholder = one word) do not count.
    const words = (ctx.quoteCheckText ?? text).split(/\s+/).filter(Boolean).length;
    // Bounds scale with the planned paragraph count (writerUnit min/max size the architect's units).
    const para = thresholds.paragraph as { wordFloor: number; wordCeiling: number; wordCeilingIntroConclusionBonus: number };
    const n = Math.max(1, unit.paragraphs.length);
    const bonus = unit.role === 'intro' || unit.role === 'conclusion' ? para.wordCeilingIntroConclusionBonus : 0;
    const bounds = { minWords: n * para.wordFloor, maxWords: n * (para.wordCeiling + bonus) };
    if (words < bounds.minWords || words > bounds.maxWords) {
      return { gate: 'word-bounds', detail: `${words} words (bounds ${bounds.minWords}-${bounds.maxWords} for ${n} planned paragraph(s))` };
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Prompt building + real generation
// ---------------------------------------------------------------------------

function fillTemplate(template: string, vars: Record<string, string>): string {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key: string) => vars[key] ?? '');
}

function languageDirective(thesis: string): string {
  return HEBREW_LETTER.test(thesis)
    ? 'כתוב את היחידה הזו בעברית בלבד. אל תתרגם ואל תערבב שפות.'
    : 'Write this unit only in English. Do not translate or mix languages.';
}

async function realGenerate(unit: OutlineUnit, predecessors: Predecessor[], ctx: { outline: Outline; voice: VoiceBundle; evidenceQuotes: string[]; passagesText: string; feedback?: string; budget: Budget; runId: string }): Promise<string> {
  const system = fillTemplate(DRAFT_PROMPT, {
    thesis: ctx.outline.thesis ?? '',
    unit_id: unit.id,
    unit_role: roleOf(unit),
    unit_claim: unit.claim ?? '',
    unit_plan: JSON.stringify(unit.paragraphs ?? [], null, 2),
    outline_summary: JSON.stringify(flatten(ctx.outline).map((u) => ({ id: u.id, claim: u.claim ?? '' })), null, 2),
    evidence_passages: ctx.passagesText,
    predecessor_text: predecessors.length ? predecessors.map((p) => `### ${p.id}\n${p.text}`).join('\n\n') : '(none — this is the first unit)',
    voice_exemplars: JSON.stringify(ctx.voice.exemplars, null, 2),
    voice_pairs: JSON.stringify(ctx.voice.pairs, null, 2),
    voice_rules: ctx.voice.rules,
    feedback: ctx.feedback ?? '(none — first draft of this unit)',
    language_directive: languageDirective(ctx.outline.thesis ?? ''),
  });
  const result = await callGemini({ step: 'write.draft', system, parts: ['Draft the unit now. Return plain prose only.'], runId: ctx.runId, budget: ctx.budget });
  return result.text;
}

// ---------------------------------------------------------------------------
// Artifact loading (real, non-stubbed path only)
// ---------------------------------------------------------------------------

function draftDir(): string { return join(projectDir(), '.academic-helper', 'drafts'); }
function draftPath(unitId: string): string { return join(draftDir(), `${unitId}.md`); }
function writeDraft(unitId: string, text: string): void {
  mkdirSync(draftDir(), { recursive: true });
  writeFileSync(draftPath(unitId), text, 'utf8');
}

function loadSourceKeys(): Set<string> {
  const path = join(projectDir(), '.academic-helper', 'sources.json');
  if (!existsSync(path)) return new Set();
  try {
    const raw = JSON.parse(readFileSync(path, 'utf8')) as unknown;
    const list: unknown[] = Array.isArray(raw) ? raw : Array.isArray((raw as { sources?: unknown[] })?.sources) ? (raw as { sources: unknown[] }).sources : [];
    return new Set(list.map((entry) => {
      const source = entry as { sourceId?: string; id?: string };
      return String(source.sourceId ?? source.id ?? '');
    }).filter(Boolean));
  } catch { return new Set(); }
}

function withPassageKeys(given: Set<string>): Set<string> {
  // evidence.json (aw evidence build) also lists its sources; the new flow may have no sources.json
  // at all (live rehearsal 2026-09-23: every unit failed citation-not-in-sources for that reason).
  const sourceKeys = new Set(given);
  const path = join(projectDir(), '.academic-helper', 'evidence.json');
  if (!existsSync(path)) return sourceKeys;
  try {
    const raw = JSON.parse(readFileSync(path, 'utf8')) as { sources?: { id: string }[]; passages?: { id: string; sourceId: string }[] };
    for (const source of raw.sources ?? []) sourceKeys.add(source.id);
    const keys = new Set(sourceKeys);
    for (const passage of raw.passages ?? []) if (sourceKeys.has(passage.sourceId)) keys.add(passage.id);
    return keys;
  } catch { return sourceKeys; }
}

type EvidencePassage = { id: string; sourceId: string; locator?: string; quote: string; gloss?: string };
// The drafter must see each passage's id, source and locator: rendered as a bare numbered list
// ("1. quote") the model cited [^1], which no gate can resolve (live run 2026-09-23).
function evidencePassagesFor(unit: OutlineUnit): EvidencePassage[] {
  const path = join(projectDir(), '.academic-helper', 'evidence.json');
  if (!existsSync(path)) return [];
  try {
    const raw = JSON.parse(readFileSync(path, 'utf8')) as { passages?: EvidencePassage[] };
    const ids = new Set((unit.paragraphs ?? []).flatMap((p) => p.evidenceIds ?? []));
    return (raw.passages ?? []).filter((passage) => ids.size === 0 || ids.has(passage.id));
  } catch { return []; }
}

export function renderPassages(passages: EvidencePassage[]): string {
  return passages.length
    ? passages.map((p) => `[${p.id}] source=${p.sourceId}${p.locator ? ` locator=${p.locator}` : ''}\n  quote: ${p.quote}${p.gloss ? `\n  gloss: ${p.gloss}` : ''}`).join('\n')
    : '(none)';
}

function quoteIndex(): Map<string, string> {
  const path = join(projectDir(), '.academic-helper', 'evidence.json');
  if (!existsSync(path)) return new Map();
  try {
    const raw = JSON.parse(readFileSync(path, 'utf8')) as { passages?: { id: string; quote: string }[] };
    return new Map((raw.passages ?? []).map((p) => [p.id, p.quote]));
  } catch { return new Map(); }
}

// ⟦Q:id⟧ -> "verbatim quote" with a straight double quote (Hebrew) or “quote” with curly quotes
// (Latin script); gershayim (״) is an abbreviation mark, never a quotation mark. An unknown id is
// left in place so the quote gate reports it instead of silently dropping it.
export function substituteQuotes(text: string, quotes: Map<string, string>): string {
  return text.replace(/⟦Q:([^⟧\s]+)⟧([.,;:]?)/gu, (whole, id: string, after: string) => {
    const quote = quotes.get(id);
    if (quote === undefined) return whole;
    // When the sentence punctuation follows the placeholder, drop the quote's own final mark so the
    // result is `...".` and not `....".` (live rehearsal 2026-09-23).
    const body = after ? quote.replace(/[.,;:]+\s*$/u, '') : quote;
    return (/[\u0590-\u05FF]/u.test(body) ? `"${body}"` : `\u201C${body}\u201D`) + after;
  });
}

// Footnote definitions for passage keys are rendered by code from evidence.json: `[^id]: Author, Title,
// locator.` The model's own definitions were glosses with an English "Page 3" (live rehearsal).
export function renderFootnotes(text: string, meta: Map<string, { author: string; title: string; locator: string }>): string {
  return text.replace(/^\[\^([^\]]+)\]:.*$/gmu, (line, key: string) => {
    const m = meta.get(key);
    if (!m) return line;
    const locator = m.locator.replace(/^Page\s+(\d+).*$/iu, 'עמ׳ $1');
    return `[^${key}]: ${[m.author, m.title, locator].filter(Boolean).join(', ')}.`;
  });
}

function footnoteMeta(): Map<string, { author: string; title: string; locator: string }> {
  const path = join(projectDir(), '.academic-helper', 'evidence.json');
  if (!existsSync(path)) return new Map();
  try {
    const raw = JSON.parse(readFileSync(path, 'utf8')) as { sources?: { id: string; title?: string; author?: string }[]; passages?: { id: string; sourceId: string; locator?: string }[] };
    const src = new Map((raw.sources ?? []).map((x) => [x.id, x]));
    return new Map((raw.passages ?? []).map((p) => [p.id, { author: src.get(p.sourceId)?.author ?? '', title: src.get(p.sourceId)?.title ?? '', locator: p.locator ?? '' }]));
  } catch { return new Map(); }
}

function evidenceQuotesFor(unit: OutlineUnit): string[] {
  const path = join(projectDir(), '.academic-helper', 'evidence.json');
  if (!existsSync(path)) return [];
  try {
    const raw = JSON.parse(readFileSync(path, 'utf8')) as { passages?: { id: string; quote: string }[] };
    const ids = new Set((unit.paragraphs ?? []).flatMap((p) => p.evidenceIds ?? []));
    return (raw.passages ?? []).filter((passage) => ids.size === 0 || ids.has(passage.id)).map((passage) => passage.quote);
  } catch { return []; }
}

async function loadVoiceBundle(runId: string): Promise<VoiceBundle> {
  const cfg = thresholds.voice.bundle as { exemplars: number; pairs: number };
  const result = await voiceBundle({ n: cfg.exemplars, pairs: cfg.pairs, runId });
  const parsed = JSON.parse(readFileSync(result.path, 'utf8')) as Partial<VoiceBundle>;
  return { exemplars: parsed.exemplars ?? [], pairs: parsed.pairs ?? [], rules: parsed.rules ?? '', styleWords: parsed.styleWords ?? EMPTY_STYLE_WORDS };
}

async function voiceCheckFallback(paragraph: string, styleWords: StyleWords): Promise<string> {
  const bannedHits = styleWords.banned.filter((b) => paragraph.includes(b.word)).length;
  const fillerHits = styleWords.filler.filter((w) => paragraph.includes(w)).length;
  const cfg = thresholds.styleFingerprint as { passThreshold: number; maxScore: number };
  const score = Math.max(0, cfg.maxScore - bannedHits * 2 - fillerHits);
  return score >= cfg.passThreshold ? 'pass' : 'fail';
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

/** Fixed plain words for a failed gate in activity.jsonl: the record holds verdicts, never the text that failed. */
const GATE_REASON: Record<string, string> = {
  'citation-not-in-sources': 'unknown-source',
  'quote-not-in-evidence': 'quote-not-in-evidence',
  'style-banned': 'banned-word',
  'style-capped': 'word-used-too-often',
  'word-bounds': 'length-out-of-range',
};

export async function draftAll(outline: Outline, options: DraftAllOptions): Promise<DraftAllResult> {
  return endRunOnError(options.runId, options.flow ?? 'write', () => draftUnits(outline, options));
}

async function draftUnits(outline: Outline, options: DraftAllOptions): Promise<DraftAllResult> {
  const allUnits = flatten(outline);
  if (allUnits.length === 0) throw new AwError('ERROR', 'write.draft', 'outline has no units');

  const bodyUnits = allUnits.filter((unit) => roleOf(unit) === 'body');
  const specialUnits = allUnits.filter((unit) => roleOf(unit) !== 'body')
    .sort((a, b) => (roleOf(a) === 'conclusion' ? 1 : 0) - (roleOf(b) === 'conclusion' ? 1 : 0));
  const ordered = [...topoSort(bodyUnits), ...specialUnits];
  const orderedIds = new Set(ordered.map((u) => u.id));
  for (const dep of allUnits.flatMap((u) => u.dependsOn ?? [])) {
    if (dep && !orderedIds.has(dep) && !allUnits.some((u) => u.id === dep)) {
      throw new AwError('ERROR', 'write.draft', `dangling dependency: ${dep}`);
    }
  }

  const targetUnits = options.unit ? ordered.filter((unit) => unit.id === options.unit) : ordered;
  if (options.unit && targetUnits.length === 0) throw new AwError('ERROR', 'write.draft', `unknown unit: ${options.unit}`);

  const draftedText = new Map<string, string>();
  if (options.unit && !stubs.gen) {
    for (const unit of ordered) {
      if (unit.id === options.unit) break;
      if (existsSync(draftPath(unit.id))) draftedText.set(unit.id, readFileSync(draftPath(unit.id), 'utf8'));
    }
  }

  const voice = stubs.voice ?? await loadVoiceBundle(options.runId);
  // A citation key may be a source id (sources.json) or an evidence passage id whose source is
  // known: the drafter cites passages ([^p1]) because that is what it was handed (live run 2026-09-23).
  const sourceKeys = withPassageKeys(loadSourceKeys());
  const feedback = options.feedbackFile && existsSync(options.feedbackFile) ? readFileSync(options.feedbackFile, 'utf8') : undefined;
  const budget = new Budget(options.runId, budgetFor('write'));

  const drafted: string[] = [];
  const failures: DraftFailure[] = [];
  const audit: AuditItem[] = [];

  const flow = options.flow ?? 'write';
  const redrafting = options.unit !== undefined && options.feedbackFile !== undefined;
  // The edit flows have the one step `edit` (FLOW_STEPS in activity.ts); only a write run has draft and redraft.
  const stepName = flow !== 'write' ? 'edit' : redrafting ? 'redraft' : 'draft';
  startRunOnce(options.runId, flow);
  emit(options.runId, flow, 'step_start', { step: stepName });

  for (const unit of targetUnits) {
    const role = roleOf(unit);
    const predecessors: Predecessor[] = role === 'body'
      ? (unit.dependsOn ?? []).filter((id) => draftedText.has(id)).map((id) => ({ id, text: draftedText.get(id)! }))
      : bodyUnits.filter((u) => draftedText.has(u.id)).map((u) => ({ id: u.id, text: draftedText.get(u.id)! }));

    const evidenceQuotes = stubs.evidenceQuotes ?? evidenceQuotesFor(unit);
    const generate: GenFn = stubs.gen ?? ((u, preds) => realGenerate(u, preds, { outline, voice, evidenceQuotes, passagesText: renderPassages(evidencePassagesFor(unit)), feedback, budget, runId: options.runId }));

    // Quotes are inserted by code from evidence.json: the model writes ⟦Q:id⟧ placeholders. This keeps
    // every quote verbatim by construction and avoids Gemini's RECITATION stop on classical sources
    // (live rehearsal 2026-09-23: U3 quoting Ashkenazi/Job aborted with finishReason RECITATION).
    const raw = await generate(unit, predecessors);
    const quotes = quoteIndex();
    const text = renderFootnotes(substituteQuotes(raw, quotes), footnoteMeta());
    // The quote gate checks only quotes the MODEL wrote: code-inserted quotes are verbatim by
    // construction, and their own inner marks (וצא"ל) must not pair with marks in the prose.
    const modelQuotesText = raw.replace(/⟦Q:([^⟧\s]+)⟧/gu, (whole, id: string) => (quotes.has(id) ? '⟨quote⟩' : whole));
    draftedText.set(unit.id, text);
    writeDraft(unit.id, text);
    drafted.push(unit.id);
    if (redrafting) emit(options.runId, flow, 'redraft', { step: stepName, unit: unit.id });
    emit(options.runId, flow, 'unit_drafted', { step: stepName, unit: unit.id });

    const paragraphs = splitParagraphs(text);
    for (let index = 0; index < paragraphs.length; index += 1) {
      const paragraph = paragraphs[index]!;
      // Jev point write.audit_prescreen: logged only. Its answer never gates
      // anything here -- every paragraph is always marked as requiring the
      // Claude citation auditor, in every Jev mode including cascade.
      await decide({
        point: 'write.audit_prescreen',
        question: 'Does this paragraph plausibly contain a citation the auditor should check?',
        options: ['review', 'skip-likely'],
        context: JSON.stringify({ unit: unit.id, paragraphIndex: index, excerpt: paragraph.slice(0, 200) }),
        runId: options.runId,
        fallback: async () => 'review',
      });
      audit.push({ unit: unit.id, paragraphIndex: index, required: true });

      await decide({
        point: 'write.voice_check',
        question: 'Does this paragraph meet the voice/style-fingerprint threshold?',
        options: ['pass', 'fail'],
        context: JSON.stringify({ unit: unit.id, paragraphIndex: index }),
        runId: options.runId,
        fallback: async () => voiceCheckFallback(paragraph, voice.styleWords),
      });
    }

    const failure = runGates(unit, text, paragraphs, { sourceKeys, evidenceQuotes, styleWords: voice.styleWords, quoteCheckText: modelQuotesText });
    if (failure) failures.push({ unit: unit.id, gate: failure.gate, detail: failure.detail });
    emit(options.runId, flow, 'gate', { step: stepName, unit: unit.id, gate: failure ? failure.gate : 'draft-gates', ok: !failure, ...(failure ? { reason: GATE_REASON[failure.gate] ?? 'gate-failed' } : {}) });
  }
  emit(options.runId, flow, 'step_end', { step: stepName });

  return { drafted, failures, audit };
}
