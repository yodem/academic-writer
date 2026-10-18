/**
 * Home folder resolver shared by hooks and `aw` (mirror of src/scripts/home.py).
 * Reads only; never writes. No model call.
 */
import { existsSync, readFileSync, statSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

export interface ResolvedProfile {
  values: Record<string, unknown>;
  sections: Record<string, unknown>;
  home: string | null;
  homeMissing: boolean;
}

const DIR_NAME = '.academic-helper';

/** Expand a leading `~` or `~/` like Python's expanduser (`~user` is left alone). */
export function expandUser(p: string, env: NodeJS.ProcessEnv = process.env): string {
  if (p === '~') return env['HOME'] || homedir();
  if (p.startsWith('~/')) return join(env['HOME'] || homedir(), p.slice(2));
  return p;
}

/** ACADEMIC_HOME, then $CLAUDE_PLUGIN_DATA/home.json {"path": ...}, else null. Never throws. */
export function homeDir(env: NodeJS.ProcessEnv = process.env): string | null {
  try {
    const explicit = env['ACADEMIC_HOME'];
    if (explicit) return expandUser(explicit, env);
    const data = env['CLAUDE_PLUGIN_DATA'];
    if (data) {
      const pointer = join(data, 'home.json');
      if (existsSync(pointer)) {
        const parsed: unknown = JSON.parse(readFileSync(pointer, 'utf-8'));
        if (parsed && typeof parsed === 'object') {
          const value = (parsed as Record<string, unknown>)['path'];
          if (typeof value === 'string' && value) return expandUser(value, env);
        }
      }
    }
  } catch {
    return null;
  }
  return null;
}

/** Scalars, `null`, `[]` and `  - item` lists (same rules as src/scripts/home.py). */
export function parseFrontmatter(raw: string): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const fmMatch = raw.match(/^---\n([\s\S]*?)\n---/);
  if (!fmMatch) return out;
  const lines = fmMatch[1].split('\n');
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const kv = line.match(/^([\w-]+): (.+)$/);
    if (kv) {
      const v = kv[2].trim();
      if (v === 'null') out[kv[1]] = null;
      else if (v === '[]') out[kv[1]] = [];
      else out[kv[1]] = v;
      i++;
    } else if (/^[\w-]+:\s*$/.test(line)) {
      const key = line.split(':')[0];
      const items: string[] = [];
      i++;
      while (i < lines.length && lines[i].startsWith('  - ')) {
        items.push(lines[i].slice(4));
        i++;
      }
      out[key] = items;
    } else {
      i++;
    }
  }
  return out;
}

/** `## Heading` + a json block; key = heading lowercased without spaces. Malformed JSON is skipped. */
export function parseSections(raw: string): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const re = /^## ([^\n]+)\n+```json\n([\s\S]*?)\n```/gm;
  let m: RegExpExecArray | null;
  while ((m = re.exec(raw)) !== null) {
    const key = m[1].trim().toLowerCase().replace(/\s+/g, '');
    try {
      out[key] = JSON.parse(m[2]) as unknown;
    } catch {
      // skip malformed JSON blocks
    }
  }
  return out;
}

function readMd(path: string): { values: Record<string, unknown>; sections: Record<string, unknown> } {
  try {
    const raw = readFileSync(path, 'utf-8');
    return { values: parseFrontmatter(raw), sections: parseSections(raw) };
  } catch {
    return { values: {}, sections: {} };
  }
}

function isDir(path: string): boolean {
  try {
    return statSync(path).isDirectory();
  } catch {
    return false;
  }
}

/** home.md values, then the workspace profile.md overrides (frontmatter keys and whole JSON sections). */
export function resolveProfile(workspace: string, env: NodeJS.ProcessEnv = process.env): ResolvedProfile {
  const home = homeDir(env);
  let values: Record<string, unknown> = {};
  let sections: Record<string, unknown> = {};
  let homeMissing = false;
  if (home !== null) {
    if (isDir(home)) {
      const h = readMd(join(home, DIR_NAME, 'home.md'));
      values = h.values;
      sections = h.sections;
    } else {
      homeMissing = true;
    }
  }
  const w = readMd(join(workspace, DIR_NAME, 'profile.md'));
  return {
    values: { ...values, ...w.values },
    sections: { ...sections, ...w.sections },
    home,
    homeMissing,
  };
}
