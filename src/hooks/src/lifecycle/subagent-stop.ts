import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { HookInput, HookResult } from '../types.js';
import { recordActivity, type ActivityFields } from '../lib/activity.js';

// Fields confirmed on Claude Code 2.1.302 (spike, 2026-10-18): SubagentStop carries agent_id, agent_type,
// agent_transcript_path, last_assistant_message, stop_hook_active, cwd, session_id, transcript_path.
export interface SubagentStopInput extends HookInput {
  agent_type?: string;
  agent_id?: string;
  agent_transcript_path?: string;
  last_assistant_message?: string;
  subagent_type?: string;
  cwd?: string;
}

const AUDITOR_TYPES = new Set(['auditor', 'academic-writer:auditor']);

function lastAssistantText(transcriptPath: string | undefined): string | undefined {
  if (!transcriptPath || !existsSync(transcriptPath)) return undefined;
  let last: string | undefined;
  try {
    for (const line of readFileSync(transcriptPath, 'utf-8').split('\n')) {
      if (!line.trim()) continue;
      try {
        const row = JSON.parse(line) as { type?: string; role?: string; message?: { role?: string; content?: unknown } };
        const role = row.message?.role ?? row.role ?? row.type;
        if (role !== 'assistant') continue;
        const content = row.message?.content;
        if (typeof content === 'string') last = content;
        else if (Array.isArray(content)) {
          const text = content.filter((part): part is { type: string; text: string } => typeof part === 'object' && part !== null && (part as { type?: unknown }).type === 'text' && typeof (part as { text?: unknown }).text === 'string').map((part) => part.text).join('\n');
          if (text) last = text;
        }
      } catch {
        // skip an unreadable transcript line
      }
    }
  } catch {
    return undefined;
  }
  return last;
}

function verdictOf(value: unknown): 'PASS' | 'FAIL' | 'PARTIAL' | 'unknown' {
  return value === 'PASS' || value === 'FAIL' || value === 'PARTIAL' ? value : 'unknown';
}

/** One entry per `results[]` item; a single `unknown` verdict when the text holds no usable json block. */
export function auditVerdicts(text: string | undefined): ActivityFields[] {
  const unknown: ActivityFields[] = [{ verdict: 'unknown', reason: 'auditor result could not be read' }];
  if (!text) return unknown;
  const blocks = [...text.matchAll(/```json\s*([\s\S]*?)```/g)];
  if (blocks.length !== 1) return unknown;
  try {
    const parsed = JSON.parse(blocks[0]![1]!) as { results?: unknown };
    if (!parsed || !Array.isArray(parsed.results) || parsed.results.length === 0) return unknown;
    return parsed.results.map((entry): ActivityFields => {
      const row = (typeof entry === 'object' && entry !== null ? entry : {}) as { paragraphIndex?: unknown; paragraph?: unknown; verdict?: unknown; feedback?: unknown };
      const index = typeof row.paragraphIndex === 'number' ? row.paragraphIndex : row.paragraph;
      return {
        step: 'audit',
        ...(typeof index === 'number' && Number.isInteger(index) && index >= 0 ? { paragraph: index } : {}),
        verdict: verdictOf(row.verdict),
        ...(typeof row.feedback === 'string' && row.feedback ? { reason: row.feedback.slice(0, 300) } : {}),
      };
    });
  } catch {
    return unknown;
  }
}

function statusFallback(projectDir: string): string | undefined {
  const root = process.env['CLAUDE_PLUGIN_ROOT'];
  if (!root) return undefined;
  try {
    const out = execFileSync(join(root, 'bin', 'aw'), ['--project-dir', projectDir, 'activity', 'show', '--latest'], { encoding: 'utf-8', timeout: 2000, stdio: ['ignore', 'pipe', 'ignore'] });
    return out.split('\n')[0]?.trim() || undefined;
  } catch {
    return undefined;
  }
}

export function subagentStop(input: SubagentStopInput): HookResult {
  const projectDir = input.project_dir ?? process.env['CLAUDE_PROJECT_DIR'] ?? input.cwd ?? '.';
  // Hard gate: only record in academic-writer projects.
  if (!existsSync(join(projectDir, '.academic-helper', 'profile.md'))) {
    return { continue: true, suppressOutput: true };
  }
  const agent = input.agent_type ?? input.subagent_type ?? '';
  const options = { pluginRoot: input.plugin_root };
  let wrote = false;
  if (AUDITOR_TYPES.has(agent)) {
    const text = input.last_assistant_message ?? lastAssistantText(input.agent_transcript_path);
    for (const fields of auditVerdicts(text)) wrote = recordActivity(projectDir, 'audit_verdict', { ...fields, agent }, options) || wrote;
  }
  wrote = recordActivity(projectDir, 'subagent_stop', { ...(agent ? { agent } : {}) }, options) || wrote;

  // Without the mod pane there is no live view, so say where the run stands in one line.
  if (wrote && !process.env['CLAUDE_CODE_ENABLE_FUNCTION_HOOKS']) {
    const line = statusFallback(projectDir);
    if (line) return { continue: true, systemMessage: line };
  }
  return { continue: true, suppressOutput: true };
}
