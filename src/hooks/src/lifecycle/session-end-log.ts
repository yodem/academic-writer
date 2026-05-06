import { existsSync, appendFileSync } from 'node:fs';
import { join } from 'node:path';
import type { HookInput, HookResult } from '../types.js';
import { getProfilePath } from '../lib/profile.js';

export function sessionEndLog(input: HookInput): HookResult {
  const projectDir = input.project_dir ?? process.env['CLAUDE_PROJECT_DIR'] ?? '.';

  // Hard gate: only log in projects that already have an academic-writer profile.
  // Never create .academic-helper or its logs/ subdir — that's the setup skill's job.
  if (!existsSync(getProfilePath(projectDir))) {
    return { continue: true, suppressOutput: true };
  }

  const logsDir = join(projectDir, '.academic-helper', 'logs');
  if (!existsSync(logsDir)) {
    // Profile exists but logs/ was never created — skip silently rather than create it.
    return { continue: true, suppressOutput: true };
  }

  try {
    const now = new Date();
    const dateStr = now.toISOString().split('T')[0];
    const timeStr = now.toISOString().split('T')[1].split('.')[0];
    const logFile = join(logsDir, `${dateStr}.log`);

    const sessionId = input.session_id ?? 'unknown';

    const entry = [
      '',
      `--- Session End: ${timeStr} (${sessionId}) ---`,
      `Timestamp: ${now.toISOString()}`,
      '---',
      '',
    ].join('\n');

    appendFileSync(logFile, entry, 'utf-8');
  } catch {
    // Silent failure — logging should never block the session
  }

  return { continue: true, suppressOutput: true };
}
