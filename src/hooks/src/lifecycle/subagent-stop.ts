import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { HookInput, HookResult } from '../types.js';
import { recordActivity, type ActivityFields } from '../lib/activity.js';
import { pluginOption } from './session-env.js';

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

/** The unit (or edited section) an auditor batch covers: `unitId` / `sectionId` in the first user message of its transcript. */
export function auditedUnit(transcriptPath: string | undefined): string | undefined {
  if (!transcriptPath || !existsSync(transcriptPath)) return undefined;
  try {
    for (const line of readFileSync(transcriptPath, 'utf-8').split('\n')) {
      if (!line.trim()) continue;
      let row: { type?: string; role?: string; message?: { role?: string; content?: unknown } };
      try { row = JSON.parse(line) as typeof row; } catch { continue; }
      if ((row.message?.role ?? row.role ?? row.type) !== 'user') continue;
      const content = row.message?.content;
      const text = typeof content === 'string' ? content
        : Array.isArray(content) ? content.map((part) => (typeof part === 'object' && part !== null && typeof (part as { text?: unknown }).text === 'string' ? (part as { text: string }).text : '')).join('\n')
          : '';
      return /["'`]?\b(?:unitId|sectionId)\b["'`]?\s*[:=]\s*["'`]?([A-Za-z0-9][\w.-]*)/.exec(text)?.[1];
    }
  } catch {
    return undefined;
  }
  return undefined;
}

/** What the record keeps of the auditor's feedback: the verdict and how many numbered issues it lists, never its words. */
function reasonOf(verdict: 'PASS' | 'FAIL' | 'PARTIAL' | 'unknown', feedback: unknown): string | undefined {
  if (verdict === 'PASS') return undefined;
  const issues = typeof feedback === 'string' ? (feedback.match(/^\s*\d+[.)]\s/gm) ?? []).length : 0;
  return issues > 0 ? `${verdict}, ${issues} issues` : verdict;
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
      const verdict = verdictOf(row.verdict);
      const reason = reasonOf(verdict, row.feedback);
      return {
        step: 'audit',
        ...(typeof index === 'number' && Number.isInteger(index) && index >= 0 ? { paragraph: index } : {}),
        verdict,
        ...(reason !== undefined ? { reason } : {}),
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
    const unit = auditedUnit(input.agent_transcript_path);
    wrote = recordActivity(projectDir, 'step_start', { step: 'audit', agent }, options) || wrote;
    for (const fields of auditVerdicts(text)) wrote = recordActivity(projectDir, 'audit_verdict', { ...fields, ...(unit ? { unit } : {}), agent }, options) || wrote;
    wrote = recordActivity(projectDir, 'step_end', { step: 'audit', agent }, options) || wrote;
  }
  wrote = recordActivity(projectDir, 'subagent_stop', { ...(agent ? { agent } : {}) }, options) || wrote;

  // Without the mod pane (no function hooks, or the author turned the pane off) there is no live view, so say where the run stands in one line.
  const paneOff = !process.env['CLAUDE_CODE_ENABLE_FUNCTION_HOOKS'] || pluginOption('activity_pane')?.trim().toLowerCase() === 'false';
  if (wrote && paneOff) {
    const line = statusFallback(projectDir);
    if (line) return { continue: true, systemMessage: line };
  }
  return { continue: true, suppressOutput: true };
}
