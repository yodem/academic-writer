import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { ProfileData } from '../types.js';

const PROFILE_DIR = '.academic-helper';
const PROFILE_RELATIVE_PATH = '.academic-helper/profile.md';

export function getProfileDirPath(projectDir: string): string {
  return join(projectDir, PROFILE_DIR);
}

export function getProfilePath(projectDir: string): string {
  return join(projectDir, PROFILE_RELATIVE_PATH);
}

function parseProfileMd(raw: string): ProfileData | null {
  try {
    const profile: Record<string, unknown> = {};

    // Extract YAML frontmatter between first --- and second ---
    const fmMatch = raw.match(/^---\n([\s\S]*?)\n---/);
    if (fmMatch) {
      const fmLines = fmMatch[1].split('\n');
      let i = 0;
      while (i < fmLines.length) {
        const line = fmLines[i];
        const kvMatch = line.match(/^([\w-]+): (.+)$/);
        if (kvMatch) {
          const [, key, value] = kvMatch;
          const v = value.trim();
          if (v === 'null') profile[key] = null;
          else if (v === '[]') profile[key] = [];
          else profile[key] = v;
          i++;
        } else if (/^[\w-]+:\s*$/.test(line)) {
          const key = line.split(':')[0];
          const items: string[] = [];
          i++;
          while (i < fmLines.length && fmLines[i].startsWith('  - ')) {
            items.push(fmLines[i].slice(4));
            i++;
          }
          profile[key] = items;
        } else {
          i++;
        }
      }
    }

    // Extract JSON code blocks by section heading
    const sectionRe = /^## ([^\n]+)\n+```json\n([\s\S]*?)\n```/gm;
    let m: RegExpExecArray | null;
    while ((m = sectionRe.exec(raw)) !== null) {
      const heading = m[1].trim().toLowerCase().replace(/\s+/g, '');
      try {
        const parsed: unknown = JSON.parse(m[2]);
        switch (heading) {
          case 'tools': profile['tools'] = parsed; break;
          case 'stylefingerprint': profile['styleFingerprint'] = parsed; break;
          case 'sources': profile['sources'] = parsed; break;
          case 'articlestructure': profile['articleStructure'] = parsed; break;
          case 'outputformatpreferences': profile['outputFormatPreferences'] = parsed; break;
        }
      } catch {
        // skip malformed JSON blocks
      }
    }

    return profile as unknown as ProfileData;
  } catch {
    return null;
  }
}

export function loadProfile(projectDir: string): ProfileData | null {
  const profilePath = getProfilePath(projectDir);
  if (!existsSync(profilePath)) return null;
  try {
    const raw = readFileSync(profilePath, 'utf-8');
    return parseProfileMd(raw);
  } catch {
    return null;
  }
}
