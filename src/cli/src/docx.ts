import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { allowedEnv } from './library/backends.ts';
import { emit } from './activity.ts';

type Unit = { id: string };
type Section = { title?: string; units?: Unit[] };
type Outline = { title?: string; thesis?: string; sections?: Section[]; units?: Unit[] };
type Footnote = { after: string; text: string };
type Paragraph = { text: string; footnotes: Footnote[] };

function parseUnit(raw: string, unitId: string): Paragraph[] {
  const definitions = new Map<string, string>();
  const body: string[] = [];
  for (const line of raw.split(/\r?\n/u)) {
    const def = line.match(/^\s*\[\^([^\]]+)\]:\s*(.*?)\s*$/u);
    if (def) definitions.set(def[1]!, def[2]!);
    else body.push(line);
  }
  const paragraphs: Paragraph[] = [];
  for (const part of body.join('\n').split(/\n\s*\n/u).map((p) => p.trim()).filter(Boolean)) {
    const footnotes: Footnote[] = [];
    let text = '';
    const marker = /\[\^([^\]]+)\]/gu;
    let last = 0;
    let match: RegExpExecArray | null;
    while ((match = marker.exec(part))) {
      text += part.slice(last, match.index);
      const key = match[1]!;
      const definition = definitions.get(key);
      if (definition === undefined) throw new Error(`ERROR docx: footnote ${key} has no definition`);
      const prior = text;
      let length = Math.min(12, prior.length);
      let anchor = prior.slice(-length);
      while (length < prior.length && anchor && part.split(anchor).length - 1 !== 1) {
        length += 1;
        anchor = prior.slice(-length);
      }
      if (!anchor || part.split(anchor).length - 1 !== 1) throw new Error(`ERROR docx: footnote ${key} has no unique anchor`);
      footnotes.push({ after: anchor, text: definition });
      last = marker.lastIndex;
    }
    text += part.slice(last);
    paragraphs.push({ text: text.trim(), footnotes });
  }
  return paragraphs;
}

export function assembleArticle(outline: Outline, project: string, runId: string, options: { title?: string; coverFile?: string; abstractFile?: string; formatFile?: string }): { article: Record<string, unknown>; sections: number; paragraphs: number; footnotes: number; words: number } {
  const sections: { title: string; paragraphs: Paragraph[] }[] = [];
  let paragraphCount = 0; let footnoteCount = 0;
  const emit = (sectionTitle: string, units: Unit[]): void => {
    const paragraphs = units.flatMap((unit) => {
      const path = join(project, '.academic-helper', 'drafts', `${unit.id}.md`);
      if (!existsSync(path)) throw new Error(`ERROR docx: missing draft ${unit.id}`);
      return parseUnit(readFileSync(path, 'utf8'), unit.id);
    });
    paragraphCount += paragraphs.length;
    footnoteCount += paragraphs.reduce((sum, p) => sum + p.footnotes.length, 0);
    sections.push({ title: sectionTitle, paragraphs });
  };
  const inputSections = outline.sections ?? [];
  if (inputSections.length) {
    for (const section of inputSections) {
      const units = section.units ?? [];
      const intro = units.filter((u) => u.id === 'intro' || u.id === 'introduction');
      const regular = units.filter((u) => !intro.includes(u) && u.id !== 'conclusion');
      const conclusion = units.filter((u) => u.id === 'conclusion');
      if (intro.length) emit(section.title ?? '', intro);
      if (regular.length) emit(section.title ?? '', regular);
      if (conclusion.length) emit(section.title ?? '', conclusion);
    }
  } else if (outline.units) emit('', outline.units);
  const words = sections.flatMap((s) => s.paragraphs.map((p) => p.text)).join(' ').trim().split(/\s+/u).filter(Boolean).length;
  const article: Record<string, unknown> = { title: options.title ?? outline.title ?? '', thesis: outline.thesis ?? null, sections, totalWords: words };
  for (const [key, path] of [['coverPage', options.coverFile], ['abstract', options.abstractFile], ['format', options.formatFile]] as const) {
    if (path) article[key] = JSON.parse(readFileSync(path, 'utf8')) as unknown;
  }
  return { article, sections: sections.length, paragraphs: paragraphCount, footnotes: footnoteCount, words };
}

export function generateDocx(args: { outlinePath: string; runId: string; out: string; title?: string; coverFile?: string; abstractFile?: string; formatFile?: string; projectDir: string; dataDir: string; pluginRoot: string }): Omit<ReturnType<typeof assembleArticle>, 'article'> {
  void args.dataDir;
  const project = resolve(args.projectDir);
  emit(args.runId, 'write', 'step_start', { step: 'word' }, project);
  try {
    return buildDocx(args, project);
  } catch (error) {
    emit(args.runId, 'write', 'run_end', { exit: 'ERROR', reason: (error instanceof Error ? error.message : 'ERROR docx').slice(0, 300) }, project);
    throw error;
  }
}

function buildDocx(args: Parameters<typeof generateDocx>[0], project: string): Omit<ReturnType<typeof assembleArticle>, 'article'> {
  const outline = JSON.parse(readFileSync(args.outlinePath, 'utf8')) as Outline;
  const result = assembleArticle(outline, resolve(args.projectDir), args.runId, args);
  const runDir = join(args.projectDir, '.academic-helper', 'runs', args.runId);
  mkdirSync(runDir, { recursive: true });
  const jsonPath = join(runDir, 'article.json');
  writeFileSync(jsonPath, `${JSON.stringify(result.article, null, 2)}\n`, 'utf8');
  const script = join(args.pluginRoot, 'scripts', 'generate-docx.py');
  const child = spawnSync('python3', [script, '--input', jsonPath, '--output', args.out], { stdio: 'inherit', env: allowedEnv(process.env, 'script') });
  if (child.error) throw new Error(`ERROR docx: ${child.error.message}`);
  if (child.status !== 0) throw new Error(`ERROR docx: generate-docx.py exited ${child.status ?? 1}`);
  emit(args.runId, 'write', 'file_written', { step: 'word', path: args.out }, project);
  emit(args.runId, 'write', 'step_end', { step: 'word' }, project);
  emit(args.runId, 'write', 'run_end', { exit: 'OK' }, project);
  return { sections: result.sections, paragraphs: result.paragraphs, footnotes: result.footnotes, words: result.words };
}

export function docxSummary(value: ReturnType<typeof generateDocx>, out: string): string { return JSON.stringify({ docx: out, ...value }); }
