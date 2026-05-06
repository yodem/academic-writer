import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import type { HookInput, HookResult } from '../types.js';

export function notifyStop(input: HookInput): HookResult {
  const projectDir = input.project_dir ?? process.env['CLAUDE_PROJECT_DIR'] ?? '.';

  // Hard gate: only notify in academic-writer projects.
  if (!existsSync(join(projectDir, '.academic-helper', 'profile.md'))) {
    return { continue: true, suppressOutput: true };
  }

  // macOS only — silently no-op elsewhere.
  if (process.platform !== 'darwin') {
    return { continue: true, suppressOutput: true };
  }

  // Use execFile (not exec) — args are passed as an array to osascript,
  // never interpreted by the shell. The script string is a static literal.
  const script = 'display notification "Task complete" with title "Academic Writer" sound name "Glass"';
  execFile('osascript', ['-e', script], { timeout: 2000 }, () => {
    // Silent — never block on notification.
  });

  return { continue: true, suppressOutput: true };
}
