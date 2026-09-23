import { readFileSync, writeFileSync, mkdirSync, existsSync, appendFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { join, resolve } from 'node:path';
import { callGemini } from './gemini.ts';
import { judge } from './judge.ts';
import { decide } from './decide.ts';
import { routeFor } from './routing.ts';
import { Budget, budgetFor } from './ledger.ts';
import { pluginRoot } from './pi.ts';
import findPrompt from './prompts/proofread-find.md';
import verifyPrompt from './prompts/proofread-verify.md';
import memoPrompt from './prompts/proofread-memo.md';

type Change = { id: string; line: number; before: string; after: string | null; class: string; meaningRisk: 'low' | 'medium' | 'high'; mustCatch?: boolean; status?: string; applied?: boolean; skipReason?: string; [key: string]: unknown };
type Chunk = { index: number; id: string; startLine: number; endLine: number; text: string };
type Verdict = { id: string; verdict: 'uphold' | 'refute' };
type Stubs = { find?: (chunk: Chunk) => Promise<Change[]>; verify?: (changes: Change[]) => Promise<Verdict[]>; mustCatch?: () => Promise<Change[]>; memo?: () => Promise<string> };
let stubs: Stubs = {};
export function __stubs(value: Stubs): void { stubs = value; }

const findSchema = { type: 'object', required: ['changes'], properties: { changes: { type: 'array', items: { type: 'object', required: ['id','line','before','after','class','meaningRisk'], properties: { id: { type: 'string' }, line: { type: 'integer' }, before: { type: 'string' }, after: { type: ['string','null'] }, class: { type: 'string' }, meaningRisk: { type: 'string', enum: ['low','medium','high'] } } } } } };
const verifySchema = { type: 'object', required: ['verdicts'], properties: { verdicts: { type: 'array', items: { type: 'object', required: ['id','verdict'], properties: { id: { type: 'string' }, verdict: { type: 'string', enum: ['uphold','refute'] } } } } } };
const prompt = (file: string): string => file === 'proofread-find.md' ? findPrompt : file === 'proofread-verify.md' ? verifyPrompt : memoPrompt;
type ContractChange = { change_id: string; stage: 'mechanical' | 'language'; line: number; type: string; level: 'letter' | 'word' | 'sentence'; before: string; after: string | null; rationale: string; meaningRisk: Change['meaningRisk']; mustCatch?: boolean; applied?: boolean; skipReason?: string | null; refutedBy?: string[] };
function contractChange(change: Change): ContractChange {
  const typeMap: Record<string, string> = { wrong_word: 'word', names_terms: 'word', style_words: 'word', agreement: 'agreement', collocation: 'collocation', syntax: 'syntax', tense: 'tense', register: 'register', punctuation: 'punctuation', typography: 'typography', typo: 'typo' };
  const type = typeMap[change.class] ?? 'word';
  const stage = change.mustCatch || ['typo','punctuation','typography','names_terms','style_words'].includes(change.class) ? 'mechanical' : 'language';
  const skipReason = change.status === 'refuted' ? 'refuted' : change.status === 'triaged-out' || change.after === null ? 'comment-only' : change.status === 'unverified' || change.meaningRisk !== 'low' ? 'meaning-risk' : change.skipReason;
  const applied = typeof change.applied === 'boolean' ? change.applied : skipReason ? false : undefined;
  return { change_id: createHash('sha256').update(`${stage}\0${change.line}\0${change.before}`).digest('hex').slice(0, 12), stage, line: change.line, type, level: ['typo','punctuation','typography'].includes(type) ? 'letter' : type === 'word' ? 'word' : 'sentence', before: change.before, after: change.after, rationale: typeof change.rationale === 'string' ? change.rationale : 'Proofread suggestion; compare with the surrounding context.', meaningRisk: change.meaningRisk, ...(change.mustCatch ? { mustCatch: true } : {}), ...(applied !== undefined ? { applied } : {}), ...(skipReason ? { skipReason } : {}) };
}

export type RunProofreadOptions = { article?: string; chunks?: number | Chunk[]; runId: string; venue?: string; only?: 'mechanical' | 'language' | 'editorial'; out?: string; dataDir?: string; projectDir?: string; voiceRules?: string };
export type ProofreadResult = { changes: Change[]; memo: string; proofed: string; report: string };

async function command(bin: string, args: string[], cwd?: string): Promise<string> {
  return await new Promise((resolvePromise, reject) => {
    const child = spawn(bin, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = ''; let stderr = '';
    child.stdout.setEncoding('utf8').on('data', (data: string) => { stdout += data; });
    child.stderr.setEncoding('utf8').on('data', (data: string) => { stderr += data; });
    child.on('error', reject);
    child.on('close', (code) => code === 0 ? resolvePromise(stdout) : reject(new Error(`ERROR proofread: ${stderr || `${bin} exited ${String(code)}`}`)));
  });
}
function importLegacyJev(runId: string, project: string): void {
  const legacyPath = join(project, '.academic-helper', 'jev-shadow.jsonl');
  const marker = join(project, '.academic-helper', 'jev-shadow-imported');
  if (!existsSync(legacyPath) || existsSync(marker)) return;
  const ledgerDir = join(project, '.academic-helper', 'runs', runId);
  mkdirSync(ledgerDir, { recursive: true });
  const rows = readFileSync(legacyPath, 'utf8').split('\n').filter((line) => line.trim());
  for (const line of rows) {
    let evidence: unknown;
    try { evidence = JSON.parse(line) as unknown; } catch { throw new Error('ERROR proofread.risk: invalid legacy Jev shadow row'); }
    appendFileSync(join(ledgerDir, 'jev.jsonl'), `${JSON.stringify({ point: 'proofread.risk', legacyEvidence: evidence, labelSource: 'llm', priorShadow: true })}\n`, 'utf8');
  }
  writeFileSync(marker, 'imported\n', 'utf8');
}
function numberedChunks(chunks: Chunk[]): Chunk[] { return chunks.map((chunk, index) => ({ ...chunk, index, text: chunk.text.split('\n').map((line, offset) => /^L\d+\t/.test(line) ? line : `L${chunk.startLine + offset}\t${line}`).join('\n') })); }
async function mapLimit<T, R>(items: T[], limit: number, operation: (item: T) => Promise<R>): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let cursor = 0;
  const workers = Array.from({ length: limit }, async () => {
    while (cursor < items.length) { const index = cursor++; results[index] = await operation(items[index]!); }
  });
  await Promise.all(workers);
  return results;
}
async function find(chunk: Chunk, options: RunProofreadOptions, budget: Budget): Promise<Change[]> {
  const raw = stubs.find ? await stubs.find(chunk) : (await callGemini({ step: 'proofread.find', system: prompt('proofread-find.md'), parts: [`Chunk ${chunk.index}; absolute lines ${chunk.startLine}-${chunk.endLine}\n${options.voiceRules ?? ''}\n${chunk.text}`], responseSchema: findSchema, runId: options.runId, budget })).json as { changes: Change[] };
  const candidates = Array.isArray(raw) ? raw : raw.changes;
  const kept: Change[] = [];
  for (const candidate of candidates) {
    const decision = await decide({ point: 'proofread.triage', question: 'Is this candidate a genuine proofread error?', options: ['keep','discard'], context: JSON.stringify(candidate), runId: options.runId, fallback: async () => 'keep' });
    if (decision.answer === 'keep') {
      const risk = await decide({ point: 'proofread.risk', question: 'What meaning risk does this candidate carry?', options: ['low','medium','high'], context: JSON.stringify(candidate), runId: options.runId, fallback: async () => candidate.meaningRisk });
      kept.push({ ...candidate, meaningRisk: risk.answer as Change['meaningRisk'] });
    } else kept.push({ ...candidate, status: 'triaged-out' });
  }
  return kept;
}

export async function runProofread(options: RunProofreadOptions): Promise<ProofreadResult> {
  const root = options.article ? pluginRoot() : '';
  const outDir = resolve(options.out ?? '.'); mkdirSync(outDir, { recursive: true });
  const project = options.projectDir ?? process.env.CLAUDE_PROJECT_DIR ?? '';
  if (project) importLegacyJev(options.runId, project);
  const article = options.article ? resolve(options.article) : '';
  const content = article ? readFileSync(article, 'utf8') : '';
  const numbered = Array.isArray(options.chunks) ? numberedChunks(options.chunks) : [];
  const chunks = numbered.length ? numbered : content ? JSON.parse(await command('python3', [join(root, 'scripts/chunk-article.py'), '--input', article, '--numbered'])) as Chunk[] : Array.from({ length: typeof options.chunks === 'number' ? options.chunks : 0 }, (_, index) => ({ id: `chunk-${index}`, index, startLine: index + 1, endLine: index + 1, text: `L${index + 1}\tx` }));
  const budget = new Budget(options.runId, budgetFor('proofread'));
  let deterministic: Change[] = [];
  if (article) {
    const stylesPath = join(options.dataDir ?? process.env.CLAUDE_PLUGIN_DATA ?? '', 'voice', 'style-words.json');
    const termsPath = join(options.projectDir ?? process.env.CLAUDE_PROJECT_DIR ?? '', '.academic-helper', 'terms.json');
    const actualStyles = existsSync(stylesPath) ? stylesPath : join(outDir, '.empty-style-words.json');
    const actualTerms = existsSync(termsPath) ? termsPath : join(outDir, '.empty-terms.json');
    if (actualStyles !== stylesPath) writeFileSync(actualStyles, JSON.stringify({}));
    if (actualTerms !== termsPath) writeFileSync(actualTerms, JSON.stringify({}));
    const tempText = join(outDir, '.proofread-input.md'); writeFileSync(tempText, content);
    const result = await command('python3', [join(root, 'scripts/must-catch.py'), '--text', tempText, '--style-words', actualStyles, '--terms', actualTerms, '--hspell', '--json']);
    deterministic = (JSON.parse(result) as { changes: Change[] }).changes;
  }
  if (stubs.mustCatch) deterministic = await stubs.mustCatch();
  for (const hit of deterministic.filter((change) => change.class === 'style_words')) {
    await decide({ point: 'style.filler', question: 'Is this capped style-word use filler?', options: ['flag','allow'], context: JSON.stringify(hit), runId: options.runId, fallback: async () => 'flag' });
  }
  const voicePath = join(options.dataDir ?? process.env.CLAUDE_PLUGIN_DATA ?? '', 'voice', 'rules.md');
  const voiceRules = options.voiceRules ?? (existsSync(voicePath) ? readFileSync(voicePath, 'utf8') : '');
  const stageOptions = { ...options, voiceRules };
  const found = options.only === 'editorial' ? [] : await mapLimit(chunks, routeFor('proofread.find').concurrency, (chunk) => find(chunk, stageOptions, budget));
  const candidates = found.flat().filter((change) => {
    if (options.only === 'mechanical') return ['typo','punctuation','typography','names_terms','style_words'].includes(change.class);
    if (options.only === 'language') return !['typo','punctuation','typography','names_terms','style_words'].includes(change.class);
    return true;
  });
  const verifiable = candidates.filter((change) => change.status !== 'triaged-out' && (change.meaningRisk === 'low' || (change.meaningRisk === 'medium' && change.class === 'wrong_word')));
  const byChunk = chunks.map((chunk) => ({ chunk, changes: verifiable.filter((change) => change.line >= chunk.startLine && change.line <= chunk.endLine) }));
  const verified = await mapLimit(byChunk.filter((group) => group.changes.length > 0), routeFor('proofread.verify').concurrency, async ({ chunk, changes }) => {
    let verdictPromise: Promise<Map<string, Verdict['verdict']>> | undefined;
    const getVerdicts = (): Promise<Map<string, Verdict['verdict']>> => {
      verdictPromise ??= (async () => {
        const result = stubs.verify ? await stubs.verify(changes) : (await judge({ step: 'proofread.verify', prompt: `${prompt('proofread-verify.md')}\nChunk:\n${chunk.text}\nChanges:\n${JSON.stringify(changes)}`, schema: verifySchema, runId: options.runId, finderProvider: 'gemini', budget })).json as { verdicts: Verdict[] };
        const verdicts = Array.isArray(result) ? result : result.verdicts;
        const map = new Map(verdicts.map((value) => [value.id, value.verdict]));
        if (changes.some((change) => !map.has(change.id))) throw new Error(`ERROR proofread.verify: missing verdict in ${chunk.id}`);
        return map;
      })();
      return verdictPromise;
    };
    return await Promise.all(changes.map(async (change) => {
      const decided = await decide({ point: 'proofread.verify', question: 'Should this proposed correction be applied?', options: ['uphold','refute'], context: JSON.stringify(change), runId: options.runId, fallback: async () => (await getVerdicts()).get(change.id) ?? 'ERROR' });
      if (!['uphold', 'refute'].includes(decided.answer)) throw new Error(`ERROR proofread.verify: invalid verdict for ${change.id}`);
      return { ...change, status: decided.answer === 'refute' ? 'refuted' : 'verified' };
    }));
  });
  const statusMap = new Map(verified.flat().map((change) => [change.id, change]));
  const all: Change[] = [...deterministic.map((change) => ({ ...change, status: 'must-catch', applied: true })), ...candidates.map((change) => statusMap.get(change.id) ?? { ...change, status: 'unverified' })];
  const editorialChecksPath = join(root, 'skills', 'proofread', 'references', 'editorial-checks.md');
  const editorialChecks = article && existsSync(editorialChecksPath) ? readFileSync(editorialChecksPath, 'utf8') : '';
  const venuePath = options.venue && project ? join(project, '.academic-helper', 'venues', `${options.venue}.md`) : '';
  const venueProfile = venuePath && existsSync(venuePath) ? readFileSync(venuePath, 'utf8') : '';
  const memo = stubs.memo ? await stubs.memo() : (await callGemini({ step: 'proofread.memo', system: prompt('proofread-memo.md'), parts: [`Global editorial checks (always apply):\n${editorialChecks}\n\nOptional additive venue profile${options.venue ? ` (${options.venue})` : ''}:\n${venueProfile || 'None available.'}\n\nArticle:\n${content}`], runId: options.runId, budget })).text;
  let proofed = content;
  const changesPath = join(outDir, 'changes.json'); const proofedPath = join(outDir, 'proofed.md'); const reportPath = join(outDir, 'report.md'); const memoPath = join(outDir, 'memo.md');
  const contract = all.map(contractChange);
  writeFileSync(changesPath, JSON.stringify({ stage: 'language', changes: contract }, null, 2));
  if (article) await command('python3', [join(root, 'scripts/gate.py'), 'changes-schema', changesPath, '--json']);
  if (article) {
    const candidateContract = contract.filter((change) => !change.mustCatch);
    if (candidateContract.length) {
      const guardInput = join(outDir, '.proofread-before-guard.json'); const guardOutput = join(outDir, '.proofread-after-guard.json');
      writeFileSync(guardInput, JSON.stringify({ stage: 'language', changes: candidateContract }));
      const guardedText = await command('python3', [join(root, 'scripts/citation-guard.py'), '--changes', guardInput, '--proof-base', article, '--json']);
      writeFileSync(guardOutput, guardedText);
      const guarded = (JSON.parse(guardedText) as { changes: ContractChange[] }).changes;
      const guardedById = new Map(guarded.map((change) => [change.change_id, change]));
      for (let index = 0; index < all.length; index += 1) {
        const guardedChange = guardedById.get(contract[index]!.change_id);
        if (guardedChange?.skipReason === 'citation-guard') all[index] = { ...all[index]!, status: 'protected-span', applied: false, skipReason: 'citation-guard' };
      }
    }
    writeFileSync(proofedPath, content);
    const applicable = all.filter((change) => (change.mustCatch || change.status === 'verified') && change.meaningRisk === 'low' && change.after !== null).map(contractChange);
    const applyPath = join(outDir, '.proofread-applicable.json'); writeFileSync(applyPath, JSON.stringify({ stage: 'language', changes: applicable }));
    if (applicable.length) {
      const appliedText = await command('python3', [join(root, 'scripts/apply-changes.py'), '--changes', applyPath, '--proof-base', article, '--output', proofedPath, '--json']);
      const applied = (JSON.parse(appliedText) as { changes: ContractChange[] }).changes;
      const appliedById = new Map(applied.map((change) => [change.change_id, change]));
      for (let index = 0; index < all.length; index += 1) {
        const change = all[index]!;
        const outcome = appliedById.get(contract[index]!.change_id);
        if (outcome) all[index] = { ...change, applied: outcome.applied, skipReason: outcome.skipReason ?? undefined };
      }
      proofed = readFileSync(proofedPath, 'utf8');
    }
    const finalContract = all.map(contractChange);
    writeFileSync(changesPath, JSON.stringify({ stage: 'language', changes: finalContract }, null, 2));
    if (article.toLowerCase().endsWith('.docx')) {
      const finalTextPath = join(outDir, '.proofread-final-text.txt'); writeFileSync(finalTextPath, proofed);
      await command('python3', [join(root, 'scripts/build-tracked-docx.py'), '--original', article, '--final-text', finalTextPath, '--changes', changesPath, '--output', join(outDir, 'proofed.docx')]);
    }
  } else writeFileSync(proofedPath, proofed);
  writeFileSync(memoPath, memo);
  writeFileSync(reportPath, `# Proofread report\n\n${memo}\n\n${all.length} changes found; ${all.filter((change) => change.status === 'refuted').length} refuted and retained.\n`);
  return { changes: all, memo, proofed, report: reportPath };
}
