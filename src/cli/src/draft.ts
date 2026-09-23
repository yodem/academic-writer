import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { callGemini } from './gemini.ts';
import { decide } from './decide.ts';
import { projectDir } from './paths.ts';
import { AwError, Budget, budgetFor } from './ledger.ts';
import { voiceBundle } from './voice.ts';
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
export type DraftAllOptions = { runId: string; unit?: string; feedbackFile?: string };

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
// A gershayim (״) with a Hebrew letter on both sides is an abbreviation
// mark (e.g. רמב״ם), never a quotation delimiter -- filter those out before
// pairing the rest as open/close quote marks.
function isAbbreviationGershayim(text: string, index: number): boolean {
  const prev = text[index - 1];
  const next = text[index + 1];
  return Boolean(prev && next && HEBREW_LETTER.test(prev) && HEBREW_LETTER.test(next));
}

function pairDelimiters(text: string, char: string, filterAbbreviation: boolean): string[] {
  const positions: number[] = [];
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] !== char) continue;
    if (filterAbbreviation && isAbbreviationGershayim(text, index)) continue;
    positions.push(index);
  }
  const spans: string[] = [];
  for (let index = 0; index + 1 < positions.length; index += 2) {
    spans.push(text.slice(positions[index]! + 1, positions[index + 1]));
  }
  return spans;
}

function extractQuotedSpans(text: string): string[] {
  const gershayim = pairDelimiters(text, '״', true); // ״…״
  const curly = [...text.matchAll(/“([^“”]+)”/g)].map((m) => m[1]!); // "…"
  const straight = pairDelimiters(text, '"', false); // "…"
  return [...gershayim, ...curly, ...straight].filter((span) => span.trim().length > 0);
}

function countOccurrences(haystack: string, needle: string): number {
  if (!needle) return 0;
  return haystack.split(needle).length - 1;
}

function runGates(unit: OutlineUnit, text: string, paragraphs: string[], ctx: { sourceKeys: Set<string>; evidenceQuotes: string[]; styleWords: StyleWords }): { gate: string; detail: string } | null {
  const citations = extractCitationKeys(text);
  const badCitation = citations.find((key) => !ctx.sourceKeys.has(key));
  if (badCitation !== undefined) return { gate: 'citation-not-in-sources', detail: badCitation };

  const pool = ctx.evidenceQuotes.map(normalize).filter(Boolean);
  for (const quote of extractQuotedSpans(text)) {
    const needle = normalize(quote);
    if (!needle) continue;
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
    const words = text.split(/\s+/).filter(Boolean).length;
    const bounds = thresholds.writerUnit as { minWords: number; maxWords: number };
    if (words < bounds.minWords || words > bounds.maxWords) {
      return { gate: 'word-bounds', detail: `${words} words (bounds ${bounds.minWords}-${bounds.maxWords})` };
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

async function realGenerate(unit: OutlineUnit, predecessors: Predecessor[], ctx: { outline: Outline; voice: VoiceBundle; evidenceQuotes: string[]; feedback?: string; budget: Budget; runId: string }): Promise<string> {
  const system = fillTemplate(DRAFT_PROMPT, {
    thesis: ctx.outline.thesis ?? '',
    unit_id: unit.id,
    unit_role: roleOf(unit),
    unit_claim: unit.claim ?? '',
    unit_plan: JSON.stringify(unit.paragraphs ?? [], null, 2),
    outline_summary: JSON.stringify(flatten(ctx.outline).map((u) => ({ id: u.id, claim: u.claim ?? '' })), null, 2),
    evidence_passages: ctx.evidenceQuotes.length ? ctx.evidenceQuotes.map((q, i) => `${i + 1}. ${q}`).join('\n') : '(none)',
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

export async function draftAll(outline: Outline, options: DraftAllOptions): Promise<DraftAllResult> {
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
  const sourceKeys = loadSourceKeys();
  const feedback = options.feedbackFile && existsSync(options.feedbackFile) ? readFileSync(options.feedbackFile, 'utf8') : undefined;
  const budget = new Budget(options.runId, budgetFor('write'));

  const drafted: string[] = [];
  const failures: DraftFailure[] = [];
  const audit: AuditItem[] = [];

  for (const unit of targetUnits) {
    const role = roleOf(unit);
    const predecessors: Predecessor[] = role === 'body'
      ? (unit.dependsOn ?? []).filter((id) => draftedText.has(id)).map((id) => ({ id, text: draftedText.get(id)! }))
      : bodyUnits.filter((u) => draftedText.has(u.id)).map((u) => ({ id: u.id, text: draftedText.get(u.id)! }));

    const evidenceQuotes = stubs.evidenceQuotes ?? evidenceQuotesFor(unit);
    const generate: GenFn = stubs.gen ?? ((u, preds) => realGenerate(u, preds, { outline, voice, evidenceQuotes, feedback, budget, runId: options.runId }));

    const text = await generate(unit, predecessors);
    draftedText.set(unit.id, text);
    writeDraft(unit.id, text);
    drafted.push(unit.id);

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

    const failure = runGates(unit, text, paragraphs, { sourceKeys, evidenceQuotes, styleWords: voice.styleWords });
    if (failure) failures.push({ unit: unit.id, gate: failure.gate, detail: failure.detail });
  }

  return { drafted, failures, audit };
}
