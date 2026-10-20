import { existsSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, extname, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { allowedEnv } from './library/backends.ts';
import { callGemini, type ImagePart } from './gemini.ts';
import { AwError, Budget, budgetFor } from './ledger.ts';
import thresholds from '../../thresholds.json' with { type: 'json' };

export type Engine = 'gemini' | 'claude' | 'local';
export type OcrOptions = { input: string; language: 'he' | 'en' | 'mixed'; runId: string; pages?: string; format?: 'concise' | 'detailed'; out?: string; engine?: Engine | 'auto' };
type Page = { page_number: number; text: string; is_born_digital: boolean; confidence?: string; notes?: string; dpi?: number };
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
function stripFence(value: string): string { const match = /```(?:json)?\s*\n([\s\S]*?)\n```/i.exec(value); return match?.[1] ?? value; }

/** Which programs exist on this computer; replaceable in tests. */
let probe = (cmd: string): boolean => spawnSync(cmd, ['--version'], { encoding: 'utf8' }).status === 0;
export function __setProbe(fn: (cmd: string) => boolean): void { probe = fn; }

/**
 * Pick who reads the pages. Order measured in the 2026-10-20 bake-off: Gemini (ties Claude at
 * 100 dpi and up, wins at 75 dpi and on canonical texts Claude refuses), then Claude on the
 * author's subscription, then Tesseract on this computer (free, nothing leaves the machine).
 */
export function chooseEngine(requested: OcrOptions['engine'] = 'auto'): { engine: Engine; reason: string } {
  const hasKey = (process.env.GOOGLE_API_KEY ?? '').trim() !== '';
  if (requested === 'gemini') { if (!hasKey) throw new AwError('ERROR', 'ocr', 'engine gemini needs a Google API key (GOOGLE_API_KEY)'); return { engine: 'gemini', reason: 'requested' }; }
  if (requested === 'claude') { if (!probe('claude')) throw new AwError('ERROR', 'ocr', 'engine claude needs the claude program on PATH'); return { engine: 'claude', reason: 'requested' }; }
  if (requested === 'local') { if (!probe('tesseract')) throw new AwError('ERROR', 'ocr', 'engine local needs tesseract installed'); return { engine: 'local', reason: 'requested' }; }
  if (hasKey) return { engine: 'gemini', reason: 'a Google API key is set (tier 1)' };
  if (probe('claude')) return { engine: 'claude', reason: 'no Google API key; Claude on the subscription (tier 2)' };
  if (probe('tesseract')) return { engine: 'local', reason: 'no Google API key and no claude program; Tesseract on this computer (tier 3)' };
  throw new AwError('ERROR', 'ocr', 'no OCR engine available: set GOOGLE_API_KEY, install Claude Code, or install tesseract');
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
function lowResNote(engine: Engine, dpi: number | undefined): string {
  if (engine === 'gemini' || dpi === undefined || dpi >= cfg.lowResDpi) return '';
  return `low resolution (${dpi} dpi): in the bake-off Gemini read pages under ${cfg.lowResDpi} dpi more accurately; verify against the image`;
}

async function readGemini(scans: Scan[], options: OcrOptions): Promise<Page[]> {
  const pages: Page[] = [];
  for (let offset = 0; offset < scans.length; offset += cfg.geminiBatchSize) {
    const batch = scans.slice(offset, offset + cfg.geminiBatchSize);
    const numbers = batch.map((s) => s.page_number);
    const parts: ImagePart[] = batch.map((s) => ({ inlineData: { mimeType: mimeOf(s.png), data: readFileSync(s.png).toString('base64') } }));
    const result = await callGemini({ step: 'ocr', system: prompt(options.language, options.format, numbers), parts: [...parts, prompt(options.language, options.format, numbers)], responseSchema: schema, runId: options.runId, budget: new Budget(options.runId, budgetFor('write')) });
    const parsed = JSON.parse(stripFence(result.text)) as Page[];
    if (!Array.isArray(parsed) || parsed.some((p) => typeof p.page_number !== 'number' || typeof p.text !== 'string')) throw new AwError('ERROR', 'ocr', 'invalid OCR page response');
    // a single image is page 1 to the model; give it the scan's own page number
    if (batch.length === 1 && parsed.length === 1) parsed[0].page_number = batch[0].page_number;
    for (const p of parsed) if (!p.text.trim()) { p.confidence = 'low'; p.notes = 'blocked: Gemini returned no text (copyright/recitation block); not substituted from another engine'; }
    pages.push(...parsed);
  }
  return pages;
}

function readClaude(scan: Scan, language: OcrOptions['language']): Page {
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
    // Claude's output filter blocks whole pages of well-known texts (the vocalized Bible in the bake-off).
    return { page_number: scan.page_number, text: '', is_born_digital: false, confidence: 'low', notes: `blocked by Claude: ${(result.result ?? '').slice(0, 120)}; ask before sending this page to another engine` };
  }
  return { page_number: scan.page_number, text: result.result ?? '', is_born_digital: false, confidence: 'medium', notes: '' };
}

function readLocal(scan: Scan, language: OcrOptions['language']): Page {
  const langs = language === 'en' ? 'eng' : 'heb+eng';
  const run = spawnSync('tesseract', [scan.png, '-', '-l', langs], { encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 });
  if (run.status !== 0) throw new AwError('ERROR', 'ocr', `tesseract failed: ${run.stderr.slice(-300)}`);
  return { page_number: scan.page_number, text: run.stdout, is_born_digital: false, confidence: 'low', notes: 'Tesseract: OCR, not image-verified (2-5% letter error on Hebrew scans, more on vowel marks)' };
}

function mimeOf(file: string): string { return /\.jpe?g$/i.test(file) ? 'image/jpeg' : /\.webp$/i.test(file) ? 'image/webp' : /\.tiff?$/i.test(file) ? 'image/tiff' : 'image/png'; }

export async function ocrDocument(options: OcrOptions): Promise<{ pages: Page[]; truncated: boolean; truncation_message?: string; engine: Engine; engine_reason: string }> {
 const input = resolve(options.input);
 if (!existsSync(input)) throw new AwError('ERROR', 'ocr', `input does not exist: ${input}`);
 const { engine, reason } = chooseEngine(options.engine);
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
 try {
   const read = engine === 'gemini' ? await readGemini(scans, options)
     : scans.map((s) => (engine === 'claude' ? readClaude(s, options.language) : readLocal(s, options.language)));
   for (const page of read) {
     const scan = scans.find((s) => s.page_number === page.page_number);
     const note = lowResNote(engine, scan?.dpi);
     if (scan?.dpi !== undefined) page.dpi = scan.dpi;
     if (note) { page.notes = page.notes ? `${page.notes}; ${note}` : note; page.confidence = 'low'; }
     pages.push(page);
   }
 } finally { if (rasterDir) rmSync(rasterDir, { recursive: true, force: true }); }
 pages.sort((a,b)=>a.page_number-b.page_number);
 const output = { pages, truncated, ...(truncation_message ? { truncation_message } : {}), engine, engine_reason: reason };
 if (options.out) writeFileSync(options.out, `OCR engine: ${engine}\n\n${pages.map(p=>p.text).join('\n\n')}`, 'utf8');
 return output;
}
export const __test = { lowResNote };
