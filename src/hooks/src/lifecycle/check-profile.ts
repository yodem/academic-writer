import type { HookInput, HookResult } from '../types.js';
import { getProfileDirPath, getProfilePath } from '../lib/profile.js';
import { existsSync } from 'node:fs';

export function checkProfile(input: HookInput): HookResult {
  const projectDir = input.project_dir ?? process.env['CLAUDE_PROJECT_DIR'] ?? '.';
  const dirExists = existsSync(getProfileDirPath(projectDir));
  const profileExists = existsSync(getProfilePath(projectDir));

  if (dirExists && !profileExists) {
    // Folder exists but no profile → show warning
    return {
      continue: true,
      systemMessage:
        'Academic Writer: No profile found. Run /academic-writer:setup or /academic-writer:init to create one.',
    };
  }

  return { continue: true, suppressOutput: true };
}
