import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { HookInput, HookResult } from '../types.js';

interface SubagentStartInput extends HookInput {
  subagent_type?: string;
  subagentType?: string;
}

interface Thresholds {
  antiAi?: { passThreshold?: number; maxScore?: number };
  rewriteCycles?: { max?: number };
}

export function subagentStart(input: SubagentStartInput): HookResult {
  const projectDir = input.project_dir ?? process.env['CLAUDE_PROJECT_DIR'] ?? '.';

  // Hard gate: only inject in academic-writer projects.
  if (!existsSync(join(projectDir, '.academic-helper', 'profile.md'))) {
    return { continue: true, suppressOutput: true };
  }

  const subagentType = input.subagent_type ?? input.subagentType ?? '';
  // Only inject for the auditor subagent — others have their own context.
  if (subagentType !== 'auditor' && subagentType !== 'academic-writer:auditor') {
    return { continue: true, suppressOutput: true };
  }

  // Read thresholds.json so the auditor knows the current cutoffs.
  const thresholdsPath = join(projectDir, '.academic-helper', 'thresholds.json');
  let thresholdNote = '';
  if (existsSync(thresholdsPath)) {
    try {
      const raw = readFileSync(thresholdsPath, 'utf-8');
      const t = JSON.parse(raw) as Thresholds;
      thresholdNote = `\nCurrent thresholds: anti-AI ${t.antiAi?.passThreshold}/${t.antiAi?.maxScore}, max rewrite cycles ${t.rewriteCycles?.max}.`;
    } catch {
      // ignore parse errors; missing thresholds is non-fatal
    }
  }

  const rules = [
    'AUDITOR CONTEXT (injected by SubagentStart hook):',
    '- Verify every citation against the canonical sources.json registry.',
    '- A citation passes only when title, author, year, and page all match.',
    '- Mark [NEEDS REVIEW: <field>] when a field is missing or low-confidence.',
    '- Use WebSearch for external verification only when the registry has no entry.',
    '- Validate WebSearch results: title (exact), author, year (±1), page range — anything weaker = [NEEDS REVIEW: external_verification].',
    '- Final output must be a single VERDICT line: PASS or FAIL with reasons.',
    thresholdNote,
  ].filter(Boolean).join('\n');

  return {
    continue: true,
    systemMessage: rules,
  };
}
