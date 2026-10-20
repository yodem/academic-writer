import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, extname, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { allowedEnv } from './library/backends.ts';
import { callGemini, type ImagePart } from './gemini.ts';
import { AwError, Budget, budgetFor } from './ledger.ts';
import thresholds from '../../thresholds.json' with { type: 'json' };

export type Engine = 'gemini' | 'claude' | 'local' | 'surya';
export type OcrOptions = { input: string; language: 'he' | 'en' | 'mixed'; runId: string; pages?: string; format?: 'concise' | 'detailed'; out?: string; engine?: Engine | 'auto' };
type Page = { page_number: number; text: string; is_born_digital: boolean; confidence?: string; notes?: string; dpi?: number; engine?: Engine };
type Scan = { page_number: number; png: string; dpi?: number };
const schema = { type: 'array', items: { type: 'object', required: ['page_number','text','is_born_digital'], properties: { page_number: { type: 'integer' }, text: { type: 'string' }, is_born_digital: { type: 'boolean' }, confidence: { type: 'string', enum: ['high','medium','low'] }, notes: { type: 'string' } } } };
const cfg = thresholds.ocr;
function runScript(name: string, args: string[]): unknown {
  const plugin = resolve(dirname(process.argv[1] ?? ''), '..');
  // OCR helpers moved from the retired MCP server to <plugin>/scripts/ocr/ (T15 integration).
  const script = join(plugin, 'scripts', 'ocr', name);
  const result = spawnSync('python3', [script, ...args], { encoding: 'utf8', env: allowedEnv(process.env, 'script') });
  if (result.status !== 0) throw new AwError('ERROR', 'ocr', result.stderr.trim() || result.stdout.trim() || `${name} failed`);
  try { return JSON.parse(result.stdout) as unknown; } catch { throw new AwError('ERROR', 'ocr', `${name} returned invalid JSON`); }
}
function prompt(language: OcrOptions['language'], format: OcrOptions['format'], pages: number[]): string {
 const rtl = language !== 'en' ? 'Preserve Hebrew right-to-left reading order. Mixed Hebrew and Latin text should follow human reading order.' : '';
 const detail = format === 'detailed' ? 'Use notes to describe layout, footnotes, tables, and uncertain passages.' : 'Keep notes brief; flag only low-confidence passages.';
 return `Transcribe these scanned academic document pages faithfully. OCR ONLY: do not correct, paraphrase, modernize, or summarize. Preserve paragraph breaks and omit running headers/footers unless they are content. Ignore watermarks. ${rtl}\nLanguage: ${language}; detail: ${format ?? 'concise'}. Images are pages in this order: ${pages.join(', ')}. Return one JSON array entry per page with page_number, text, is_born_digital=false, confidence (high|medium|low), notes. ${detail}`;
}
// Same instruction as the 2026-10-20 bake-off, where Claude and Gemini were scored with it.
const PLAIN_PROMPT = 'Transcribe all text on this page image exactly as printed, in the natural reading order of the page. Include running heads, page numbers and footnotes (footnotes after the main text). Keep the original spelling, vowel points (niqqud) and punctuation. Do not correct, modernize, translate, summarize or add any commentary. Mark an illegible word as [?]. Output plain text only, no markdown.';
const GEMINI_REFUSAL = /RECITATION|SAFETY|PROHIBITED_CONTENT|BLOCKLIST|SPII|IMAGE_SAFETY/;
// Claude's output filter, as it read on 2026-10-20; any other error result (auth, quota, service) fails the run
const CLAUDE_REFUSAL = /content filtering|Output blocked/i;
// Sonnet 5.5 sometimes answers a full book page with a polite summary instead of the text (2 of 59 pages, 2026-10-20)
const SOFT_REFUSAL = /I can(?:no|['’])t (?:transcribe|reproduce)|copyrighted text/i;
function stripFence(value: string): string { const match = /```(?:json)?\s*\n([\s\S]*?)\n```/i.exec(value); return match?.[1] ?? value; }

/** Which programs exist on this computer; replaceable in tests. */
let probe = (cmd: string): boolean => spawnSync(cmd, [cmd === 'surya_ocr' ? '--help' : '--version'], { encoding: 'utf8' }).status === 0;
export function __setProbe(fn: (cmd: string) => boolean): void { probe = fn; }

/** Letters and spaces only, without vowel points or cantillation: the bake-off's normalization (bin/score.py). */
function lettersOnly(text: string): string {
  return text.normalize('NFC').replace(/[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]/g, '').replace(/\[\?\]/g, ' ')
    .replace(/[\u05be-]/g, ' ').replace(/[\u0591-\u05c7]/g, '').replace(/[^\p{L}\p{M}\s]/gu, ' ').toLowerCase().replace(/\s+/g, ' ').trim();
}
/** 2·LCS / (|a| + |b|): rapidfuzz's fuzz.ratio, the agreement measured in the bake-off. */
function similarity(a: string, b: string): number {
  if (!a.length && !b.length) return 1;
  let prev = new Uint32Array(b.length + 1), cur = new Uint32Array(b.length + 1);
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) cur[j] = a[i - 1] === b[j - 1] ? prev[j - 1] + 1 : Math.max(prev[j], cur[j - 1]);
    [prev, cur] = [cur, prev];
  }
  return (2 * prev[b.length]) / (a.length + b.length);
}

/** The reader the author named with --engine; `auto` goes page by page through readAuto instead. */
export function chooseEngine(requested: Exclude<Engine, 'surya'>): { engine: Engine; reason: string } {
  const hasKey = (process.env.GOOGLE_API_KEY ?? '').trim() !== '';
  if (requested === 'gemini') { if (!hasKey) throw new AwError('ERROR', 'ocr', 'engine gemini needs a Google API key (GOOGLE_API_KEY)'); return { engine: 'gemini', reason: 'requested' }; }
  if (requested === 'claude') { if (!probe('claude')) throw new AwError('ERROR', 'ocr', 'engine claude needs the claude program on PATH'); return { engine: 'claude', reason: 'requested' }; }
  if (!probe('tesseract')) throw new AwError('ERROR', 'ocr', 'engine local needs tesseract installed');
  return { engine: 'local', reason: 'requested' };
}

/** Native resolution of the largest image on a scanned page, from pdfimages; undefined if unknown. */
function nativeDpi(pdf: string, page: number): number | undefined {
  const out = spawnSync('pdfimages', ['-list', '-f', String(page), '-l', String(page), pdf], { encoding: 'utf8' });
  if (out.status !== 0) return undefined;
  const rows = out.stdout.split('\n').slice(2).map((l) => l.trim().split(/\s+/)).filter((r) => r.length > 12);
  const big = rows.sort((a, b) => Number(b[3]) * Number(b[4]) - Number(a[3]) * Number(a[4]))[0];
  const dpi = big ? Number(big[12]) : NaN;
  return Number.isFinite(dpi) && dpi > 0 ? dpi : undefined;
}
function lowResNote(engine: Engine | 'none', dpi: number | undefined): string {
  if (engine === 'gemini' || engine === 'none' || dpi === undefined || dpi >= cfg.lowResDpi) return '';
  return `low resolution (${dpi} dpi): in the bake-off Gemini read pages under ${cfg.lowResDpi} dpi more accurately; verify against the image`;
}

async function readGemini(scans: Scan[], options: OcrOptions): Promise<Page[]> {
  const pages: Page[] = [];
  for (let offset = 0; offset < scans.length; offset += cfg.geminiBatchSize) {
    const batch = scans.slice(offset, offset + cfg.geminiBatchSize);
    const numbers = batch.map((s) => s.page_number);
    const parts: ImagePart[] = batch.map((s) => ({ inlineData: { mimeType: mimeOf(s.png), data: readFileSync(s.png).toString('base64') } }));
    let result: Awaited<ReturnType<typeof callGemini>>;
    try {
      result = await callGemini({ step: 'ocr', system: prompt(options.language, options.format, numbers), parts: [...parts, prompt(options.language, options.format, numbers)], responseSchema: schema, runId: options.runId, budget: new Budget(options.runId, budgetFor('write')) });
    } catch (error) {
      // callGemini throws on a non-STOP finish; a content refusal is a result for these pages, anything else stays an error
      const message = error instanceof Error ? error.message : '';
      const refusal = GEMINI_REFUSAL.exec(message)?.[0];
      if (!refusal) throw error;
      pages.push(...numbers.map((n) => ({ page_number: n, text: '', is_born_digital: false, confidence: 'low', notes: `blocked: Gemini refused this page (${refusal}); not substituted from another engine` })));
      continue;
    }
    const parsed = JSON.parse(stripFence(result.text)) as Page[];
    if (!Array.isArray(parsed) || parsed.some((p) => typeof p.page_number !== 'number' || typeof p.text !== 'string')) throw new AwError('ERROR', 'ocr', 'invalid OCR page response');
    // a single image is page 1 to the model; give it the scan's own page number
    if (batch.length === 1 && parsed.length === 1) parsed[0].page_number = batch[0].page_number;
    for (const p of parsed) if (!p.text.trim()) { p.confidence = 'low'; p.notes = 'blocked: Gemini returned no text (copyright/recitation block); not substituted from another engine'; }
    pages.push(...parsed);
  }
  return pages;
}

function readClaude(scan: Scan, language: OcrOptions['language']): Page & { refused?: boolean } {
  const message = { type: 'user', message: { role: 'user', content: [
    { type: 'image', source: { type: 'base64', media_type: mimeOf(scan.png), data: readFileSync(scan.png).toString('base64') } },
    { type: 'text', text: language === 'en' ? PLAIN_PROMPT : `${PLAIN_PROMPT} Hebrew columns read right to left.` }] } };
  // Isolated: no user settings, hooks, plugins, MCP servers or tools, so the call costs about image plus prompt.
  const run = spawnSync('claude', ['-p', '--model', cfg.claudeModel, '--setting-sources', '', '--strict-mcp-config', '--tools', '',
    '--system-prompt', 'You are a precise OCR transcription engine.', '--input-format', 'stream-json', '--output-format', 'stream-json',
    '--verbose', '--no-session-persistence'], { input: `${JSON.stringify(message)}\n`, encoding: 'utf8', cwd: tmpdir(), env: { ...process.env, ENABLE_CLAUDEAI_MCP_SERVERS: 'false' }, maxBuffer: 64 * 1024 * 1024, timeout: 900_000 });
  const line = (run.stdout ?? '').split('\n').find((l) => l.includes('"type":"result"'));
  if (!line) throw new AwError('ERROR', 'ocr', `claude produced no result: ${(run.stderr || run.stdout || '').slice(-300)}`);
  const result = JSON.parse(line) as { result?: string; is_error?: boolean };
  if (result.is_error) {
    if (!CLAUDE_REFUSAL.test(result.result ?? '')) throw new AwError('ERROR', 'ocr', `claude failed: ${(result.result ?? '').slice(0, 200)}`);
    // Claude's output filter blocks whole pages of well-known texts (the vocalized Bible in the bake-off).
    return { page_number: scan.page_number, text: '', is_born_digital: false, confidence: 'low', refused: true, notes: `blocked by Claude: ${(result.result ?? '').slice(0, 120)}; ask before sending this page to another engine` };
  }
  return { page_number: scan.page_number, text: result.result ?? '', is_born_digital: false, confidence: 'medium', notes: '' };
}

function readLocal(scan: Scan, language: OcrOptions['language']): Page {
  const langs = language === 'en' ? 'eng' : 'heb+eng';
  const run = spawnSync('tesseract', [scan.png, '-', '-l', langs], { encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 });
  if (run.status !== 0) throw new AwError('ERROR', 'ocr', `tesseract failed: ${run.stderr.slice(-300)}`);
  return { page_number: scan.page_number, text: run.stdout, is_born_digital: false, confidence: 'low', notes: 'Tesseract: OCR, not image-verified (2-5% letter error on Hebrew scans, more on vowel marks)' };
}

/** Surya OCR 2, when the author has installed it (`surya_ocr`, with their own inference settings). */
function readSurya(scan: Scan): Page {
  const dir = mkdtempSync(join(tmpdir(), 'aw-surya-'));
  try {
    const run = spawnSync('surya_ocr', [scan.png, '--output_dir', dir], { encoding: 'utf8', env: process.env, maxBuffer: 16 * 1024 * 1024, timeout: 1_800_000 });
    const file = readdirSync(dir).map((d) => join(dir, d, 'results.json')).find((f) => existsSync(f));
    if (run.status !== 0 || !file) throw new AwError('ERROR', 'ocr', `surya_ocr failed: ${(run.stderr || run.stdout || '').slice(-300)}`);
    const results = JSON.parse(readFileSync(file, 'utf8')) as Record<string, Array<{ blocks: Array<{ html?: string; skipped?: boolean; reading_order?: number }> }>>;
    const blocks = (Object.values(results)[0]?.[0]?.blocks ?? []).filter((b) => !b.skipped).sort((a, b) => (a.reading_order ?? 0) - (b.reading_order ?? 0));
    return { page_number: scan.page_number, text: blocks.map((b) => (b.html ?? '').replace(/<[^>]+>/g, '')).join('\n'), is_born_digital: false, confidence: 'medium', notes: '' };
  } finally { rmSync(dir, { recursive: true, force: true }); }
}

type Available = { surya: boolean; tesseract: boolean; claude: boolean; gemini: boolean };
function available(): Available {
  return { surya: probe('surya_ocr'), tesseract: probe('tesseract'), claude: probe('claude'), gemini: (process.env.GOOGLE_API_KEY ?? '').trim() !== '' };
}
function withNote(page: Page, note: string, confidence?: string): Page {
  if (!note) return page;
  return { ...page, notes: page.notes ? `${page.notes}; ${note}` : note, ...(confidence ? { confidence } : {}) };
}

/**
 * The cheapest reader that matched Gemini in the 2026-10-20 bake-off (round 3), page by page:
 * 1. free: Surya and Tesseract both read the page; Surya's text is kept when the two agree at
 *    ocr.freeAgreeMin (no page that passed read worse than Gemini);
 * 2. Claude on the subscription (ocr.claudeModel), unless the page is under ocr.lowResDpi and Gemini is available;
 * 3. Gemini, for pages Claude refused or answered much shorter than the free reading, and low-resolution pages;
 * 4. with neither model, the best free reading, marked low confidence.
 */
async function readAuto(scan: Scan, options: OcrOptions, have: Available): Promise<Page> {
  // the free readers are optional: one that fails (no Hebrew data, no GPU) is skipped, and a model reads the page
  const failures: string[] = [];
  const tried = (read: () => Page): Page | undefined => {
    try { return read(); } catch (error) { failures.push((error instanceof Error ? error.message : String(error)).replace(/^ERROR ocr: /, '').slice(0, 200)); return undefined; }
  };
  const tess = have.tesseract ? tried(() => readLocal(scan, options.language)) : undefined;
  const noModel = !have.claude && !have.gemini;
  // Surya alone settles nothing, so without Tesseract it runs only as the last free reading
  const surya = have.surya && (tess || noModel) ? tried(() => readSurya(scan)) : undefined;
  const free: Page | undefined = surya ? { ...surya, engine: 'surya' } : tess;
  const page = await chooseRead();
  return failures.length ? withNote(page, `skipped: ${failures.join('; ')}`) : page;

  async function chooseRead(): Promise<Page> {
    if (surya && tess) {
      const [a, b] = [lettersOnly(surya.text), lettersOnly(tess.text)];
      const agree = a && b ? similarity(a, b) : 0; // two empty readings are not an agreement
      if (agree >= cfg.freeAgreeMin) return { ...surya, engine: 'surya', notes: `free reading: Surya and Tesseract agree (${agree.toFixed(3)})` };
    }
    const lowRes = scan.dpi !== undefined && scan.dpi < cfg.lowResDpi;
    let why = lowRes ? `under ${cfg.lowResDpi} dpi` : '';
    if (have.claude && !(lowRes && have.gemini)) {
      const claude = readClaude(scan, options.language);
      const ref = tess ? lettersOnly(tess.text).length : 0;
      why = claude.refused ? 'Claude refused the page'
        : SOFT_REFUSAL.test(claude.text.slice(0, 300)) ? 'Claude declined to transcribe the page'
        : ref >= cfg.shortAnswerMinChars && lettersOnly(claude.text).length < cfg.shortAnswerRatio * ref ? 'Claude\'s answer is much shorter than the free reading'
        : '';
      delete claude.refused;
      if (!why) return withNote({ ...claude, engine: 'claude' }, lowResNote('claude', scan.dpi), lowRes ? 'low' : undefined);
      if (!have.gemini) {
        const fallback = free ?? { ...claude, text: '' };
        return withNote({ ...fallback, engine: free ? (free.engine ?? 'local') : 'claude' }, `${why}; no Google API key for the Gemini fallback, so this is the free reading: check it against the image`, 'low');
      }
    }
    if (have.gemini) {
      const [page] = await readGemini([scan], options);
      return why ? withNote({ ...page, engine: 'gemini' }, `read by Gemini: ${why}`) : { ...page, engine: 'gemini' };
    }
    if (!free) throw new AwError('ERROR', 'ocr', `page ${scan.page_number}: no reader worked and no Claude or Gemini is available (${failures.join('; ') || 'no free reader installed'})`);
    return withNote({ ...free, engine: free.engine ?? 'local' }, 'no Claude or Gemini available: free reading only', 'low');
  }
}

function mimeOf(file: string): string { return /\.jpe?g$/i.test(file) ? 'image/jpeg' : /\.webp$/i.test(file) ? 'image/webp' : /\.tiff?$/i.test(file) ? 'image/tiff' : 'image/png'; }

function autoReason(have: Available): string {
  const steps = [have.surya && have.tesseract ? 'Surya and Tesseract when they agree' : '', have.claude ? `Claude (${cfg.claudeModel})` : '',
    have.gemini ? 'Gemini for refused, short or low-resolution pages' : '', !have.claude && !have.gemini ? 'free readers only' : ''].filter(Boolean);
  return `cheapest reader that matched Gemini, page by page: ${steps.join(', then ')}`;
}

export async function ocrDocument(options: OcrOptions): Promise<{ pages: Page[]; truncated: boolean; truncation_message?: string; engine: Engine | 'auto' | 'none'; engine_reason: string }> {
 const input = resolve(options.input);
 if (!existsSync(input)) throw new AwError('ERROR', 'ocr', `input does not exist: ${input}`);
 const isDir = statSync(input).isDirectory();
 const imageFiles = isDir ? readdirSync(input).filter((name) => /\.(png|jpe?g|webp|tiff?)$/i.test(name)).sort().map((name) => join(input, name)) : [];
 const pages: Page[] = [];
 let truncated = false;
 let truncation_message: string | undefined;
 const scans: Scan[] = [];
 let rasterDir: string | undefined;
 if (!isDir && extname(input).toLowerCase() === '.pdf') {
   const detected = runScript('detect_text_layer.py', options.pages ? [input, '--pages', options.pages] : [input]) as { total_pages: number; pages: Array<{page_number:number;is_born_digital:boolean;text:string}> };
   const selected = detected.pages.slice(0, cfg.perCallPageCap);
   truncated = detected.pages.length > selected.length;
   if (truncated) truncation_message = `${selected.length} of ${detected.pages.length} pages processed; rerun with a narrower page range.`;
   pages.push(...selected.filter(p => p.is_born_digital).map(p => ({ page_number:p.page_number,text:p.text,is_born_digital:true,confidence:'high',notes:'' })));
   const numbers = selected.filter(p => !p.is_born_digital).map(p => p.page_number);
   if (numbers.length) {
     const raster = runScript('rasterize_pages.py', [input, '--pages', numbers.join(',')]) as { temp_dir: string; pages: Array<{ page_number: number; png_path: string }> };
     rasterDir = raster.temp_dir;
     scans.push(...raster.pages.map((p) => ({ page_number: p.page_number, png: p.png_path, dpi: nativeDpi(input, p.page_number) })));
   }
 } else {
   const files = imageFiles.length ? imageFiles : [input];
   if (isDir && files.length === 0) throw new AwError('ERROR', 'ocr', 'directory contains no supported image files');
   const kept = files.slice(0, cfg.perCallPageCap);
   scans.push(...kept.map((png, index) => ({ page_number: index + 1, png })));
   truncated = files.length > kept.length;
   if (truncated) truncation_message = `${kept.length} of ${files.length} images processed.`;
 }
 // born-digital pages need no engine: choose one only when there is something to read
 const auto = (options.engine ?? 'auto') === 'auto';
 const have = auto && scans.length ? available() : undefined;
 if (have && !have.claude && !have.gemini && !have.tesseract && !have.surya) throw new AwError('ERROR', 'ocr', 'no OCR engine available: install Claude Code, set GOOGLE_API_KEY, or install tesseract');
 const { engine, reason } = !scans.length ? { engine: 'none' as const, reason: 'no scanned pages: text extracted from the PDF text layer' }
   : have ? { engine: 'auto' as const, reason: autoReason(have) } : chooseEngine(options.engine as Exclude<Engine, 'surya'>);
 try {
   const read: Page[] = [];
   if (engine === 'auto' && have) for (const s of scans) read.push(await readAuto(s, options, have));
   else if (engine === 'gemini') read.push(...await readGemini(scans, options));
   else if (engine !== 'none') read.push(...scans.map((s) => (engine === 'claude' ? readClaude(s, options.language) : readLocal(s, options.language))));
   for (const page of read) {
     const scan = scans.find((s) => s.page_number === page.page_number);
     const note = engine === 'auto' ? '' : lowResNote(engine, scan?.dpi);
     if (scan?.dpi !== undefined) page.dpi = scan.dpi;
     if (note) { page.notes = page.notes ? `${page.notes}; ${note}` : note; page.confidence = 'low'; }
     pages.push(page);
   }
 } finally { if (rasterDir) rmSync(rasterDir, { recursive: true, force: true }); }
 pages.sort((a,b)=>a.page_number-b.page_number);
 const output = { pages, truncated, ...(truncation_message ? { truncation_message } : {}), engine, engine_reason: reason };
 // with auto, each scanned page names its own reader in the header, so the saved text keeps who read what
 const byPage = engine === 'auto' ? ` (${pages.filter((p) => p.engine).map((p) => `page ${p.page_number}: ${p.engine}`).join(', ')})` : '';
 if (options.out) writeFileSync(options.out, `OCR engine: ${engine}${byPage}\n\n${pages.map(p=>p.text).join('\n\n')}`, 'utf8');
 return output;
}
export const __test = { lowResNote, lettersOnly, similarity };
