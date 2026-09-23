import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname, extname, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { callGemini, type ImagePart } from './gemini.ts';
import { AwError, Budget, budgetFor } from './ledger.ts';
import thresholds from '../../thresholds.json' with { type: 'json' };

export type OcrOptions = { input: string; language: 'he' | 'en' | 'mixed'; runId: string; pages?: string; format?: 'concise' | 'detailed'; out?: string };
type Page = { page_number: number; text: string; is_born_digital: boolean; confidence?: string; notes?: string };
const schema = { type: 'array', items: { type: 'object', required: ['page_number','text','is_born_digital'], properties: { page_number: { type: 'integer' }, text: { type: 'string' }, is_born_digital: { type: 'boolean' }, confidence: { type: 'string', enum: ['high','medium','low'] }, notes: { type: 'string' } } } };
function runScript(name: string, args: string[]): unknown {
  const plugin = resolve(dirname(process.argv[1] ?? ''), '..');
  // OCR helpers moved from the retired MCP server to <plugin>/scripts/ocr/ (T15 integration).
  const script = join(plugin, 'scripts', 'ocr', name);
  const result = spawnSync('python3', [script, ...args], { encoding: 'utf8' });
  if (result.status !== 0) throw new AwError('ERROR', 'ocr', result.stderr.trim() || result.stdout.trim() || `${name} failed`);
  try { return JSON.parse(result.stdout) as unknown; } catch { throw new AwError('ERROR', 'ocr', `${name} returned invalid JSON`); }
}
function prompt(language: OcrOptions['language'], format: OcrOptions['format'], pages: number[]): string {
 const rtl = language !== 'en' ? 'Preserve Hebrew right-to-left reading order. Mixed Hebrew and Latin text should follow human reading order.' : '';
 const detail = format === 'detailed' ? 'Use notes to describe layout, footnotes, tables, and uncertain passages.' : 'Keep notes brief; flag only low-confidence passages.';
 return `Transcribe these scanned academic document pages faithfully. OCR ONLY: do not correct, paraphrase, modernize, or summarize. Preserve paragraph breaks and omit running headers/footers unless they are content. Ignore watermarks. ${rtl}\nLanguage: ${language}; detail: ${format ?? 'concise'}. Images are pages in this order: ${pages.join(', ')}. Return one JSON array entry per page with page_number, text, is_born_digital=false, confidence (high|medium|low), notes. ${detail}`;
}
function stripFence(value: string): string { const match = /```(?:json)?\s*\n([\s\S]*?)\n```/i.exec(value); return match?.[1] ?? value; }
export async function ocrDocument(options: OcrOptions): Promise<{ pages: Page[]; truncated: boolean; truncation_message?: string }> {
 const input = resolve(options.input);
 if (!existsSync(input)) throw new AwError('ERROR', 'ocr', `input does not exist: ${input}`);
 const isDir = statSync(input).isDirectory();
 const imageFiles = isDir ? readdirSync(input).filter((name) => /\.(png|jpe?g|webp|tiff?)$/i.test(name)).sort().map((name) => join(input, name)) : [];
 let pages: Page[] = [];
 let truncated = false;
 let truncation_message: string | undefined;
 if (!isDir && extname(input).toLowerCase() === '.pdf') {
   const detected = runScript('detect_text_layer.py', options.pages ? [input, '--pages', options.pages] : [input]) as { total_pages: number; pages: Array<{page_number:number;is_born_digital:boolean;text:string}> };
   const selected = detected.pages.slice(0, thresholds.ocr.perCallPageCap);
   truncated = detected.pages.length > selected.length;
   if (truncated) truncation_message = `${selected.length} of ${detected.pages.length} pages processed; rerun with a narrower page range.`;
   pages.push(...selected.filter(p => p.is_born_digital).map(p => ({ page_number:p.page_number,text:p.text,is_born_digital:true,confidence:'high',notes:'' })));
   const scans = selected.filter(p => !p.is_born_digital).map(p => p.page_number);
   for (let offset=0; offset<scans.length; offset+=thresholds.ocr.geminiBatchSize) {
     const batch = scans.slice(offset,offset+thresholds.ocr.geminiBatchSize);
     const raster = runScript('rasterize_pages.py',[input,'--pages',batch.join(',')]) as {temp_dir:string;pages:Array<{page_number:number;png_path:string}>};
     try {
       const parts: ImagePart[] = raster.pages.map(p => ({inlineData:{mimeType:'image/png',data:readFileSync(p.png_path).toString('base64')}}));
       const result = await callGemini({step:'ocr',system:prompt(options.language,options.format,batch),parts:[...parts,prompt(options.language,options.format,batch)],responseSchema:schema,runId:options.runId,budget:new Budget(options.runId,budgetFor('write'))});
       const parsed = JSON.parse(stripFence(result.text)) as Page[];
       if (!Array.isArray(parsed) || parsed.some(p => typeof p.page_number !== 'number' || typeof p.text !== 'string')) throw new AwError('ERROR','ocr','invalid OCR page response');
       pages.push(...parsed);
     } finally { const fs = await import('node:fs/promises'); await fs.rm(raster.temp_dir,{recursive:true,force:true}); }
   }
 } else {
   const files = imageFiles.length ? imageFiles : [input];
   if (isDir && files.length === 0) throw new AwError('ERROR', 'ocr', 'directory contains no supported image files');
   for(let index=0; index<Math.min(files.length,thresholds.ocr.perCallPageCap); index++) {
     const file=files[index];
     const mime= /\.jpe?g$/i.test(file) ? 'image/jpeg' : /\.webp$/i.test(file) ? 'image/webp' : /\.tiff?$/i.test(file) ? 'image/tiff' : 'image/png';
     const result=await callGemini({step:'ocr',system:prompt(options.language,options.format,[index+1]),parts:[{inlineData:{mimeType:mime,data:readFileSync(file).toString('base64')}},prompt(options.language,options.format,[index+1])],responseSchema:schema,runId:options.runId,budget:new Budget(options.runId,budgetFor('write'))});
     const parsed=JSON.parse(stripFence(result.text)) as Page[]; pages.push(...parsed);
   }
   truncated=files.length>pages.length;
   if(truncated) truncation_message=`${pages.length} of ${files.length} images processed.`;
 }
 pages.sort((a,b)=>a.page_number-b.page_number);
 const output={pages,truncated,...(truncation_message?{truncation_message}:{})};
 if(options.out) writeFileSync(options.out, pages.map(p=>p.text).join('\n\n'),'utf8');
 return output;
}
