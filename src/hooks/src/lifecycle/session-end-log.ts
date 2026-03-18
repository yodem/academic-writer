import { existsSync, mkdirSync, appendFileSync } from 'node:fs';
import { join } from 'node:path';
import type { HookInput, HookResult } from '../types.js';

export function sessionEndLog(input: HookInput): HookResult {
  const projectDir = input.project_dir ?? process.env['CLAUDE_PROJECT_DIR'] ?? '.';
  const logsDir = join(projectDir, '.academic-helper', 'logs');

  try {
    if (!existsSync(logsDir)) {
      mkdirSync(logsDir, { recursive: true });
    }

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
