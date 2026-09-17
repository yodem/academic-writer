/**
 * Calibration bundle loader. Reads the author's voice, style fingerprint, real
 * voice exemplars and the language reference lists from the project + plugin
 * dirs.
 *
 * Cached per (project dir, target_language) and invalidated when the author's
 * own files change, so an AUTHOR_VOICE.md edit made mid-session reaches the
 * next Gemini call instead of waiting for a server restart.
 *
 * What is deliberately NOT loaded (2026-09-15 prompt review):
 *   - `words.md`: no such file ships with the plugin, so the section was always
 *     empty while the prompt told Gemini to use "approved linking words from
 *     words.md".
 *   - the style-fingerprint scoring rubric: it only served Gemini's
 *     self-review scores, which returned a flat maximum on every paragraph of
 *     28 recorded calls and gated nothing.
 */
import { readFile, stat } from 'node:fs/promises';
import * as path from 'node:path';
import { bundleLoadFailed, type StructuredError } from './errors.js';

export interface CalibrationBundle {
  voice: string;
  fingerprint: string;
  /** Real paragraphs (or, failing that, sentences) written by the author. */
  exemplars: string[];
  exemplarSource: 'voice-exemplars.md' | 'fingerprint' | 'none';
  antiAi: string;
  positiveTerminology: string;
  targetLanguage: string;
}

interface CacheEntry {
  signature: string;
  bundle: CalibrationBundle;
}

const cache = new Map<string, CacheEntry>();

function projectDir(): string {
  return process.env.CLAUDE_PROJECT_DIR || process.cwd();
}

function pluginRoot(): string {
  // Fall back to walking up from compiled dist path if env var missing.
  const fromEnv = process.env.CLAUDE_PLUGIN_ROOT;
  if (fromEnv) return fromEnv;
  // dist/index.js lives at <plugin>/mcp/gemini-server/dist/index.js
  // plugin root is three levels up.
  return path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', '..', '..');
}

async function readOptional(filePath: string): Promise<string> {
  try {
    return await readFile(filePath, 'utf8');
  } catch {
    return '';
  }
}

async function mtimeOf(filePath: string): Promise<string> {
  try {
    return String((await stat(filePath)).mtimeMs);
  } catch {
    return 'absent';
  }
}

/**
 * Pull the JSON block beneath `## Style Fingerprint` from profile.md. The block
 * is fenced with ```json … ```. Returns the JSON-string body, or '' if absent.
 */
export function extractStyleFingerprint(profileMd: string): string {
  const header = /^##\s+Style Fingerprint\s*$/im;
  const m = header.exec(profileMd);
  if (!m) return '';
  const after = profileMd.slice(m.index + m[0].length);
  const fence = /```(?:json|JSON)?\s*\n([\s\S]*?)\n```/.exec(after);
  return fence ? fence[1].trim() : '';
}

function lang(t: string): string {
  return (t || 'hebrew').toLowerCase().trim();
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

function at(obj: unknown, dotted: string): unknown {
  let cur: unknown = obj;
  for (const key of dotted.split('.')) {
    if (typeof cur !== 'object' || cur === null) return undefined;
    cur = (cur as Record<string, unknown>)[key];
  }
  return cur;
}

function excerptsFromFingerprint(fingerprintJson: string): string[] {
  const fp = parseJson(fingerprintJson);
  for (const p of ['dimensions.representative_excerpts', 'representative_excerpts', 'representativeExcerpts']) {
    const v = at(fp, p);
    if (Array.isArray(v)) {
      return v.filter((s): s is string => typeof s === 'string' && s.trim().length > 0).map((s) => s.trim());
    }
  }
  return [];
}

/**
 * `.academic-helper/voice-exemplars.md` is written by
 * scripts/extract-voice-exemplars.py: optional `#` heading lines, then
 * paragraphs separated by a line containing only `---`.
 */
export function parseExemplarsFile(md: string): string[] {
  return md
    .split(/^\s*---\s*$/m)
    .map((block) => block.split('\n').filter((line) => !/^\s*#/.test(line) && !/^\s*<!--.*-->\s*$/.test(line)).join('\n').trim())
    .filter((block) => block.length > 0);
}

export async function getBundle(targetLanguage: string): Promise<CalibrationBundle> {
  const key = lang(targetLanguage);
  const project = projectDir();
  const plugin = pluginRoot();
  const voicePath = path.join(project, 'AUTHOR_VOICE.md');
  const profilePath = path.join(project, '.academic-helper', 'profile.md');
  const exemplarsPath = path.join(project, '.academic-helper', 'voice-exemplars.md');

  const cacheKey = project + '::' + key;
  const signature = (await Promise.all([voicePath, profilePath, exemplarsPath].map(mtimeOf))).join('|');
  const hit = cache.get(cacheKey);
  if (hit && hit.signature === signature) return hit.bundle;

  try {
    const [voice, profileMd, exemplarsMd, antiAi, positiveTerminology] = await Promise.all([
      readOptional(voicePath),
      readOptional(profilePath),
      readOptional(exemplarsPath),
      loadLanguageReference(plugin, 'anti-ai-patterns', key),
      loadLanguageReference(plugin, 'academic-terminology', key),
    ]);

    const fingerprint = extractStyleFingerprint(profileMd);
    const fileExemplars = parseExemplarsFile(exemplarsMd);
    const fpExemplars = excerptsFromFingerprint(fingerprint);
    const exemplars = fileExemplars.length ? fileExemplars : fpExemplars;

    const bundle: CalibrationBundle = {
      voice,
      fingerprint,
      exemplars,
      exemplarSource: fileExemplars.length ? 'voice-exemplars.md' : fpExemplars.length ? 'fingerprint' : 'none',
      antiAi,
      positiveTerminology,
      targetLanguage: key,
    };
    cache.set(cacheKey, { signature, bundle });
    return bundle;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw bundleLoadFailed(`Failed to load calibration bundle for ${key}: ${message}`) as unknown as Error;
  }
}

async function loadLanguageReference(plugin: string, stem: string, lc: string): Promise<string> {
  const dir = path.join(plugin, 'skills', 'write', 'references');
  const primary = await readOptional(path.join(dir, `${stem}-${lc}.md`));
  if (primary) return primary;
  // Fallback to Hebrew per existing plugin convention.
  return await readOptional(path.join(dir, `${stem}-hebrew.md`));
}

/**
 * Render the calibration bundle for a system prompt.
 *
 * Order matters (Gemini long-context guidance: reference first, the most
 * specific material nearest the task): generic language reference lists
 * first, then the author's own voice profile and fingerprint, then the real
 * exemplars last, so what Gemini reads immediately before the task is the
 * author's actual prose rather than a generic "avoid" list.
 */
export function renderBundleMarkdown(b: CalibrationBundle): string {
  const sections: string[] = [];
  if (b.antiAi) {
    sections.push('<reference_anti_ai_patterns>\nPatterns that make text read as machine-written. Use as a check, not as a style model.\n\n' + b.antiAi + '\n</reference_anti_ai_patterns>');
  }
  if (b.positiveTerminology) {
    sections.push('<reference_academic_terminology>\nGeneral academic-register vocabulary for ' + b.targetLanguage + '. Where it disagrees with the author\'s own usage below, the author wins.\n\n' + b.positiveTerminology + '\n</reference_academic_terminology>');
  }
  if (b.voice) sections.push('<author_voice>\n' + b.voice + '\n</author_voice>');
  if (b.fingerprint) sections.push('<style_fingerprint>\n' + b.fingerprint + '\n</style_fingerprint>');
  if (b.exemplars.length) {
    const kind = b.exemplarSource === 'fingerprint' ? 'sentences' : 'paragraphs';
    sections.push(
      '<voice_examples>\nReal ' + kind + ' written by this author in earlier work. They show the voice to reproduce: rhythm, how a claim is introduced, how a quotation is followed by the author\'s own analysis, where the author says "I" and where the author hedges. Imitate the voice; never reuse their content or wording.\n\n'
      + b.exemplars.map((e, i) => '<example n="' + (i + 1) + '">\n' + e + '\n</example>').join('\n\n')
      + '\n</voice_examples>',
    );
  }
  return sections.join('\n\n');
}

/**
 * Length guidance for the instruction block. Deliberately no numeric target
 * from the fingerprint: fingerprints are mined from the whole past-articles
 * corpus, and on a real one course reflections pulled the mean paragraph to 68
 * words while the author's finished academic papers measure 97-134. The
 * exemplars carry the length; the caller's ceiling is only a maximum.
 */
export function renderStyleTargets(paragraphCeiling?: number): string {
  const lines = ['- Paragraph and sentence length: follow <voice_examples>, varying lengths as the author does.'];
  if (paragraphCeiling) lines.push('- ' + paragraphCeiling + ' words per paragraph is a hard maximum, not a target.');
  return lines.join('\n');
}

/** Test/escape-hatch: forget cached bundles. */
export function clearBundleCache(): void {
  cache.clear();
}

export function isStructuredError(e: unknown): e is StructuredError {
  return (
    typeof e === 'object' &&
    e !== null &&
    'code' in e &&
    typeof (e as { code: unknown }).code === 'string'
  );
}
