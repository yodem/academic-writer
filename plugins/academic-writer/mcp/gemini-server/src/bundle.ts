/**
 * Calibration bundle loader. Reads voice / fingerprint / words / anti-AI ref /
 * rubric from the project + plugin dirs, caches per target_language in-memory.
 *
 * Cache lifetime == server process lifetime (~ Claude Code session).
 */
import { readFile } from 'node:fs/promises';
import * as path from 'node:path';
import { bundleLoadFailed, type StructuredError } from './errors.js';

export interface CalibrationBundle {
  voice: string;
  fingerprint: string;
  words: string;
  antiAi: string;
  rubric: string;
  targetLanguage: string;
}

const cache = new Map<string, CalibrationBundle>();

function projectDir(): string {
  return process.env.CLAUDE_PROJECT_DIR ?? process.cwd();
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

/**
 * Pull the JSON block beneath `## Style Fingerprint` from profile.md. The block
 * is fenced with ```json … ```. Returns the JSON-string body, or '' if absent.
 */
function extractStyleFingerprint(profileMd: string): string {
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

async function loadAntiAi(plugin: string, targetLanguage: string): Promise<string> {
  const lc = lang(targetLanguage);
  const candidate = path.join(
    plugin,
    'skills',
    'write',
    'references',
    `anti-ai-patterns-${lc}.md`,
  );
  const primary = await readOptional(candidate);
  if (primary) return primary;
  // Fallback to Hebrew per existing plugin convention.
  const fallback = path.join(
    plugin,
    'skills',
    'write',
    'references',
    'anti-ai-patterns-hebrew.md',
  );
  return await readOptional(fallback);
}

export async function getBundle(targetLanguage: string): Promise<CalibrationBundle> {
  const key = lang(targetLanguage);
  const hit = cache.get(key);
  if (hit) return hit;

  const project = projectDir();
  const plugin = pluginRoot();

  try {
    const [voice, profileMd, words, antiAi, rubric] = await Promise.all([
      readOptional(path.join(project, 'AUTHOR_VOICE.md')),
      readOptional(path.join(project, '.academic-helper', 'profile.md')),
      readOptional(path.join(plugin, 'words.md')),
      loadAntiAi(plugin, key),
      readOptional(
        path.join(plugin, 'skills', 'write', 'references', 'style-fingerprint-rubric.md'),
      ),
    ]);

    const fingerprint = extractStyleFingerprint(profileMd);

    const bundle: CalibrationBundle = {
      voice,
      fingerprint,
      words,
      antiAi,
      rubric,
      targetLanguage: key,
    };
    cache.set(key, bundle);
    return bundle;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw bundleLoadFailed(`Failed to load calibration bundle for ${key}: ${message}`) as unknown as Error;
  }
}

/**
 * Render the calibration bundle into a single markdown block to inject into
 * the system prompt template.
 */
export function renderBundleMarkdown(b: CalibrationBundle): string {
  const sections: string[] = [];
  sections.push(`<!-- target_language: ${b.targetLanguage} -->`);
  if (b.voice) sections.push('## AUTHOR VOICE\n\n' + b.voice);
  if (b.fingerprint)
    sections.push('## STYLE FINGERPRINT (JSON)\n\n```json\n' + b.fingerprint + '\n```');
  if (b.rubric) sections.push('## STYLE FINGERPRINT RUBRIC\n\n' + b.rubric);
  if (b.words) sections.push('## ACADEMIC LINKING WORDS\n\n' + b.words);
  if (b.antiAi) sections.push('## ANTI-AI PATTERNS\n\n' + b.antiAi);
  return sections.join('\n\n---\n\n');
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
