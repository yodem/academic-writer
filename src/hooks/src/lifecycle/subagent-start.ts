import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { HookInput, HookResult } from '../types.js';
import { recordActivity } from '../lib/activity.js';

interface SubagentStartInput extends HookInput {
  agent_type?: string; // the field Claude Code sends (2.1.302)
  agent_id?: string;
  subagent_type?: string;
  subagentType?: string;
}

interface Thresholds {
  rewriteCycles?: { max?: number };
}

export function subagentStart(input: SubagentStartInput): HookResult {
  const projectDir = input.project_dir ?? process.env['CLAUDE_PROJECT_DIR'] ?? '.';

  // Hard gate: only inject in academic-writer projects.
  if (!existsSync(join(projectDir, '.academic-helper', 'profile.md'))) {
    return { continue: true, suppressOutput: true };
  }

  const subagentType = input.agent_type ?? input.subagent_type ?? input.subagentType ?? '';
  // Activity record: every subagent, whatever its type. Nothing is written without an active run.
  recordActivity(projectDir, 'subagent_start', { ...(subagentType ? { agent: subagentType } : {}) }, { pluginRoot: input.plugin_root });

  // Only inject for the auditor subagent — others have their own context.
  if (subagentType !== 'auditor' && subagentType !== 'academic-writer:auditor') {
    return { continue: true, suppressOutput: true };
  }

  // Read thresholds.json so the auditor knows the current cutoffs.
  // thresholds.json ships at the plugin root, not in the project's .academic-helper/.
  const pluginRoot = input.plugin_root ?? process.env['CLAUDE_PLUGIN_ROOT'];
  let thresholdNote = '';
  if (pluginRoot) {
    const thresholdsPath = join(pluginRoot, 'thresholds.json');
    if (existsSync(thresholdsPath)) {
      try {
        const raw = readFileSync(thresholdsPath, 'utf-8');
        const t = JSON.parse(raw) as Thresholds;
        thresholdNote = `\nCurrent thresholds: max rewrite cycles ${t.rewriteCycles?.max}.`;
      } catch {
        // ignore parse errors; missing thresholds is non-fatal
      }
    }
  }

  const rules = [
    'AUDITOR CONTEXT (injected by SubagentStart hook):',
    '- Verify every citation against the canonical sources.json registry.',
    '- A citation passes only when title, author and page match; year when the citation style carries one.',
    '- Mark [NEEDS REVIEW: <field>] when a field is missing or low-confidence.',
    '- Use WebSearch for external verification only when the registry has no entry.',
    '- Validate WebSearch results: title (exact), author, year (±1), page range — anything weaker = [NEEDS REVIEW: external_verification].',
    thresholdNote,
  ].filter(Boolean).join('\n');

  return {
    continue: true,
    hookSpecificOutput: {
      hookEventName: 'SubagentStart',
      additionalContext: rules,
    },
  };
}
