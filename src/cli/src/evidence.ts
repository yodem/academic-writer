import { createHash } from 'node:crypto';
import { appendFileSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { join } from 'node:path';
import { callGemini } from './gemini.ts';
import { appendLedger } from './ledger.ts';
import { dataDir, projectDir } from './paths.ts';
import { routeFor } from './routing.ts';
import { fetchSefaria } from './sefaria.ts';
import evidenceSchema from '../../schemas/evidence.schema.json' with { type: 'json' };

const execFileAsync = promisify(execFile);
type Passage = { id: string; sourceId: string; locator: string; quote: string; gloss: string; relevance: number };
type Source = { id: string; title: string; author: string; role: 'primary' | 'secondary'; isCoreText: boolean };
type ExtractResult = { passages: Passage[] };
type Stubs = { fetchCk: (id: string) => Promise<string>; fetchSefaria: typeof fetchSefaria; extract: (sourceId: string, text: string, intent: string, runId: string) => Promise<ExtractResult> };
type BuildOptions = { sources: string[]; sefaria?: string[]; intent?: string; runId: string };
type BuildResult = { sources: Source[]; passages: Passage[] };
const sourceCache = new Map<string, string>();
const prompt = 'Extract evidence passages from the supplied source for the author thesis. Use only the supplied author intent and source text. The intent JSON contains the thesis and must-use passages. Return passages that support, complicate, or contradict the thesis. Quotes must be exact substrings copied from the source text; never reconstruct, translate, or silently normalize a quote. Include a locator, a concise gloss, and relevance from 0 through 3. Return only useful passages; return an empty array when none qualify.';
const extractionSchema = { type: 'object', required: ['passages'], properties: { passages: evidenceSchema.properties.passages }, additionalProperties: false };
const stubState: { value?: Partial<Stubs> } = {};

export function __stubs(stubs: Partial<Stubs>): void { stubState.value = stubs; }

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
async function fetchCk(id: string): Promise<string> {
  const { stdout } = await execFileAsync('ck', ['items', 'read', `${id}:all`], { maxBuffer: 64 * 1024 * 1024 });
  return stdout;
}
async function extract(sourceId: string, text: string, intent: string, runId: string): Promise<ExtractResult> {
  if (stubState.value?.extract) return stubState.value.extract(sourceId, text, intent, runId);
  const result = await callGemini({
    step: 'evidence.extract', runId, system: prompt,
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
  const tasks = [
    ...options.sources.map(async (id) => {
      const cached = sourceCache.get(id) ?? cachedText(id);
      const text = cached ?? await (stubState.value?.fetchCk ?? fetchCk)(id);
      sourceCache.set(id, text);
      cachePath(id, text);
      return { id, title: id, author: '', role: 'secondary' as const, isCoreText: false, text };
    }),
    ...(options.sefaria ?? []).map(async (reference) => {
      const id = `sefaria:${reference}`;
      const cached = cachedText(id);
      const result = cached === undefined ? await (stubState.value?.fetchSefaria ?? fetchSefaria)(reference) : { title: reference, author: '', text: cached };
      cachePath(id, result.text);
      return { id, title: result.title, author: result.author, role: 'primary' as const, isCoreText: true, text: result.text };
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
      if (source) extracted[index] = { source, result: await extract(source.id, source.text, intent, options.runId) };
    }
  }));
  const sources: Source[] = fetched.map(({ text: _text, ...source }) => source);
  const passages: Passage[] = [];
  for (const { source, result } of extracted) {
    const cachedText = sourceCache.get(source.id) ?? source.text;
    for (const passage of result.passages) {
      if (normalize(cachedText).includes(normalize(passage.quote))) passages.push(passage);
      else event(options.runId, passage, 'quote_not_verbatim');
    }
  }
  const output: BuildResult = { sources, passages };
  const target = join(projectDir(), '.academic-helper', 'evidence.json');
  mkdirSync(join(projectDir(), '.academic-helper'), { recursive: true });
  writeFileSync(target, `${JSON.stringify(output, null, 2)}\n`, 'utf8');
  appendLedger({ run_id: options.runId, step: 'evidence.build', provider: 'code', model: 'code', input_tokens: 0, output_tokens: 0, cost_usd: 0, latency_ms: 0, exit: 'OK', same_family: false });
  return output;
}
