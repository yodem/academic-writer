import type { HookInput, HookResult } from '../types.js';
import { getProfilePath } from '../lib/profile.js';
import { existsSync } from 'node:fs';

export function checkProfile(input: HookInput): HookResult {
  const projectDir = input.project_dir ?? process.env['CLAUDE_PROJECT_DIR'] ?? '.';
  const profilePath = getProfilePath(projectDir);

  if (!existsSync(profilePath)) {
    return {
      continue: true,
      systemMessage:
        'Academic Writer: No profile found. Run /academic-writer-init to get set up before writing your first article.',
    };
  }

  return { continue: true, suppressOutput: true };
}
