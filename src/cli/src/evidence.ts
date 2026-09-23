import { createHash } from 'node:crypto';
import { appendFileSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { join } from 'node:path';
import { callGemini } from './gemini.ts';
import { appendLedger } from './ledger.ts';
import { dataDir, projectDir } from './paths.ts';
import { routeFor } from './routing.ts';
import thresholds from '../../thresholds.json' with { type: 'json' };
import { fetchSefaria } from './sefaria.ts';
import { decide } from './decide.ts';
import evidenceSchema from '../../schemas/evidence.schema.json' with { type: 'json' };

const execFileAsync = promisify(execFile);
type Passage = { id: string; sourceId: string; locator: string; quote: string; gloss: string; relevance: number };
type Source = { id: string; title: string; author: string; role: 'primary' | 'secondary'; isCoreText: boolean };
type ExtractResult = { passages: Passage[] };
type Stubs = { fetchCk: (id: string) => Promise<string>; fetchSefaria: typeof fetchSefaria; extract: (sourceId: string, text: string, intent: string, runId: string) => Promise<ExtractResult> };
type BuildOptions = { sources: string[]; sefaria?: string[]; intent?: string; runId: string };
type BuildResult = { sources: Source[]; passages: Passage[] };
const sourceCache = new Map<string, string>();
const prompt = (min: number, max: number, isCore: boolean): string => [
  'Extract evidence passages from the supplied source for the author thesis. Use only the supplied author intent and source text.',
  'The intent JSON contains the thesis in the author\'s words, the argument moves, the core text id and any must-use passages.',
  `Return between ${min} and ${max} passages that support, complicate, illustrate or contradict the thesis or any of its moves.`,
  isCore ? 'This source IS the author\'s core text: cover it densely. Include every passage that states a position the thesis depends on, every dilemma or argument the author will analyse, and the key definitions.' : 'Prefer passages that bear directly on a move.',
  'Quotes must be exact substrings copied from the source text; never reconstruct, translate, or silently normalize a quote. Keep each quote to one or two sentences.',
  'Include a locator (page/section as given in the text), a concise gloss, and relevance from 0 (tangential) through 3 (central).',
].join(' ');
const extractionSchema = { type: 'object', required: ['passages'], properties: { passages: evidenceSchema.properties.passages }, additionalProperties: false };
const stubState: { value?: Partial<Stubs> } = {};

export function __stubs(stubs: Partial<Stubs>): void { stubState.value = stubs; }

// Passage ids are assigned by code: <source prefix>-<hash of the normalized quote>. Model-chosen ids changed on
// every rebuild (breaking outlines that cite them) and collided across sources ("pass-1"); live rehearsal 2026-09-23.
export function stablePassageId(sourceId: string, quote: string): string {
  const prefix = sourceId.replace(/^sefaria:/u, 's-').replace(/[^\p{L}\p{N}-]/gu, '').slice(0, 8);
  return `${prefix}-${createHash('sha256').update(normalize(quote)).digest('hex').slice(0, 8)}`;
}

function normalize(value: string): string { return value.normalize('NFC').replace(/\s+/gu, ' ').trim(); }
function cachePath(id: string, text: string): string {
  const digest = createHash('sha256').update(text).digest('hex');
  const directory = join(dataDir(), 'sources', `${encodeURIComponent(id)}@${digest}`);
  mkdirSync(directory, { recursive: true });
  writeFileSync(join(directory, 'text.md'), text, 'utf8');
  return join(directory, 'text.md');
}
function cachedText(id: string): string | undefined {
  const root = join(dataDir(), 'sources');
  if (!existsSync(root)) return undefined;
  const prefix = `${encodeURIComponent(id)}@`;
  const entry = readdirSync(root).find((name) => name.startsWith(prefix));
  if (!entry) return undefined;
  const path = join(root, entry, 'text.md');
  return existsSync(path) ? readFileSync(path, 'utf8') : undefined;
}
// `ck items get/read` output opens with the book title as a bold line and an Author section.
export function ckMetadata(text: string): { title?: string; author?: string } {
  const head = text.slice(0, 4000);
  const title = head.match(/\*\*([^*\n]{2,200})\*\*/u)?.[1]?.trim();
  const authorBlock = head.split(/^#+\s*(?:מחבר|Author)[^\n]*$/imu)[1];
  const author = authorBlock?.match(/^\s*[-*]\s+([^·(\n]+)/mu)?.[1]?.trim();
  return { title, author };
}

// The ck table of contents names the book reliably on the line before `ID: <id>`; the bold-line
// heuristic misreads books whose first bold line is a list number (Sefer Yetzirah: "1.").
export function titleFromToc(toc: string): string | undefined {
  const lines = toc.split('\n').map((l) => l.replace(/^=+|=+$/gu, '').trim()).filter((l) => l && !/^=+$/u.test(l));
  const idLine = lines.findIndex((l) => l.startsWith('ID:'));
  const candidate = idLine > 0 ? lines[idLine - 1] : undefined;
  return candidate?.replace(/^=+\s*|\s*=+$/gu, '').trim() || undefined;
}
async function ckTitle(id: string): Promise<string | undefined> {
  try { const { stdout } = await execFileAsync('ck', ['items', 'toc', id], { maxBuffer: 8 * 1024 * 1024 }); return titleFromToc(stdout); } catch { return undefined; }
}

async function fetchCk(id: string): Promise<string> {
  const { stdout } = await execFileAsync('ck', ['items', 'read', `${id}:all`], { maxBuffer: 64 * 1024 * 1024 });
  return stdout;
}
async function extract(sourceId: string, text: string, intent: string, runId: string, isCore = false): Promise<ExtractResult> {
  if (stubState.value?.extract) return stubState.value.extract(sourceId, text, intent, runId);
  const target = (thresholds.evidence.passagesPerSource as Record<'core' | 'other', { min: number; max: number }>)[isCore ? 'core' : 'other'];
  const result = await callGemini({
    step: 'evidence.extract', runId, system: prompt(target.min, target.max, isCore),
    parts: [`Author intent (thesis and must-use passages):\n${intent}`, `Source ${sourceId}:\n${text}`],
    responseSchema: extractionSchema,
  });
  if (typeof result.json !== 'object' || result.json === null || !Array.isArray((result.json as { passages?: unknown }).passages)) {
    throw new Error('ERROR evidence.extract: missing passages');
  }
  return { passages: (result.json as { passages: Passage[] }).passages };
}
function event(runId: string, record: Passage, reason: string): void {
  const path = join(projectDir(), '.academic-helper', 'runs', runId, 'events.jsonl');
  mkdirSync(join(projectDir(), '.academic-helper', 'runs', runId), { recursive: true });
  appendFileSync(path, `${JSON.stringify({ type: 'evidence.quote_dropped', passageId: record.id, sourceId: record.sourceId, reason })}\n`, 'utf8');
}

export async function buildEvidence(options: BuildOptions): Promise<BuildResult> {
  dataDir();
  projectDir();
  const intent = options.intent ? readFileSync(options.intent, 'utf8') : '';
  // The author's intent decides the core text and primary sources (live rehearsal 2026-09-23: every
  // CandleKeep source defaulted to secondary / not-core, and titles were raw ids).
  const intentJson = (() => { try { return JSON.parse(intent) as { coreTextSourceId?: string; primarySources?: string[] }; } catch { return {}; } })();
  const intentCore = intentJson.coreTextSourceId ?? '';
  const primaryIds = new Set(intentJson.primarySources ?? []);
  const tasks = [
    ...options.sources.map(async (id) => {
      const cached = sourceCache.get(id) ?? cachedText(id);
      const text = cached ?? await (stubState.value?.fetchCk ?? fetchCk)(id);
      sourceCache.set(id, text);
      cachePath(id, text);
      const meta = ckMetadata(text);
      const tocTitle = stubState.value?.fetchCk ? undefined : await ckTitle(id);
      const isCoreText = id === intentCore;
      return { id, title: tocTitle ?? meta.title ?? id, author: meta.author ?? '', role: (isCoreText || primaryIds.has(id) ? 'primary' : 'secondary') as 'primary' | 'secondary', isCoreText, text };
    }),
    ...(options.sefaria ?? []).map(async (reference) => {
      const id = `sefaria:${reference}`;
      const cached = cachedText(id);
      const result = cached === undefined ? await (stubState.value?.fetchSefaria ?? fetchSefaria)(reference) : { title: reference, author: '', text: cached };
      cachePath(id, result.text);
      return { id, title: result.title, author: result.author, role: 'primary' as const, isCoreText: id === intentCore, text: result.text };
    }),
  ];
  const fetched = await Promise.all(tasks);
  const extracted: Array<{ source: (typeof fetched)[number]; result: ExtractResult }> = [];
  let next = 0;
  const concurrency = routeFor('evidence.extract').concurrency;
  if (concurrency < 1) throw new Error('ERROR evidence.extract: configured concurrency must be positive');
  await Promise.all(Array.from({ length: Math.min(concurrency, fetched.length) }, async () => {
    while (next < fetched.length) {
      const index = next;
      next += 1;
      const source = fetched[index];
      if (source) extracted[index] = { source, result: await extract(source.id, source.text, intent, options.runId, source.isCoreText) };
    }
  }));
  const sources: Source[] = fetched.map(({ text: _text, ...source }) => source);
  const passages: Passage[] = [];
  for (const { source, result } of extracted) {
    const cachedText = sourceCache.get(source.id) ?? source.text;
    for (const passage of result.passages) {
      // An empty quote "occurs" in every text; reject it before the verbatim check.
      if (!normalize(passage.quote) || !normalize(cachedText).includes(normalize(passage.quote))) { event(options.runId, passage, 'quote_not_verbatim'); continue; }
      // Jev point evidence.relevance (shadow-first): the Gemini relevance is the fallback and,
      // in shadow mode, the answer; Jev's view is logged for later labels (passages the outline uses).
      const rated = await decide({ point: 'evidence.relevance', question: 'How relevant is this passage to the author thesis (0 = not relevant, 3 = central)?',
        options: ['0', '1', '2', '3'], context: JSON.stringify({ thesis: intent, quote: passage.quote, gloss: passage.gloss }), runId: options.runId,
        fallback: async () => String(passage.relevance) });
      const id = stablePassageId(source.id, passage.quote);
      if (passages.some((p) => p.id === id)) continue; // same quote extracted twice
      passages.push({ ...passage, id, relevance: Number(rated.answer) });
    }
  }
  // Rebuilds MERGE into the existing evidence.json: extraction varies run to run, and an outline cites
  // passage ids, so dropping a previously extracted (still verbatim) passage would orphan outline refs
  // (live rehearsal 2026-09-23: 7 of the outline's passages were not re-extracted).
  const previousPath = join(projectDir(), '.academic-helper', 'evidence.json');
  if (existsSync(previousPath)) {
    try {
      const previous = JSON.parse(readFileSync(previousPath, 'utf8')) as BuildResult;
      const texts = new Map(fetched.map((f) => [f.id, normalize(sourceCache.get(f.id) ?? f.text)]));
      for (const p of previous.passages ?? []) {
        if (passages.some((q) => q.id === p.id)) continue;
        const text = texts.get(p.sourceId);
        if (text === undefined || text.includes(normalize(p.quote))) passages.push(p); // keep unless now non-verbatim
      }
      for (const src of previous.sources ?? []) if (!sources.some((x) => x.id === src.id)) sources.push(src);
    } catch { /* unreadable previous file: overwrite */ }
  }
  const output: BuildResult = { sources, passages };
  const target = join(projectDir(), '.academic-helper', 'evidence.json');
  mkdirSync(join(projectDir(), '.academic-helper'), { recursive: true });
  writeFileSync(target, `${JSON.stringify(output, null, 2)}\n`, 'utf8');
  appendLedger({ run_id: options.runId, step: 'evidence.build', provider: 'code', model: 'code', input_tokens: 0, output_tokens: 0, cost_usd: 0, latency_ms: 0, exit: 'OK', same_family: false });
  return output;
}
