import { existsSync } from 'node:fs';
import { join } from 'node:path';
import type { ProfileData } from '../types.js';
import { resolveProfile } from './home.js';

const PROFILE_DIR = '.academic-helper';
const PROFILE_RELATIVE_PATH = '.academic-helper/profile.md';

export function getProfileDirPath(projectDir: string): string {
  return join(projectDir, PROFILE_DIR);
}

export function getProfilePath(projectDir: string): string {
  return join(projectDir, PROFILE_RELATIVE_PATH);
}

const SECTION_KEYS: Record<string, string> = {
  tools: 'tools',
  stylefingerprint: 'styleFingerprint',
  sources: 'sources',
  articlestructure: 'articleStructure',
  outputformatpreferences: 'outputFormatPreferences',
};

export function loadProfile(projectDir: string): ProfileData | null {
  const profilePath = getProfilePath(projectDir);
  if (!existsSync(profilePath)) return null;
  try {
    const resolved = resolveProfile(projectDir);
    const profile: Record<string, unknown> = { ...resolved.values };
    for (const [heading, value] of Object.entries(resolved.sections)) {
      const key = SECTION_KEYS[heading];
      if (key) profile[key] = value;
    }
    if (resolved.homeMissing && resolved.home) profile['homeMissing'] = resolved.home;
    return profile as unknown as ProfileData;
  } catch {
    return null;
  }
}
