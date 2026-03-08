import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { ProfileData } from '../types.js';

const PROFILE_RELATIVE_PATH = '.academic-writer/profile.json';

export function getProfilePath(projectDir: string): string {
  return join(projectDir, PROFILE_RELATIVE_PATH);
}

export function loadProfile(projectDir: string): ProfileData | null {
  const profilePath = getProfilePath(projectDir);
  if (!existsSync(profilePath)) return null;
  try {
    const raw = readFileSync(profilePath, 'utf-8');
    return JSON.parse(raw) as ProfileData;
  } catch {
    return null;
  }
}
