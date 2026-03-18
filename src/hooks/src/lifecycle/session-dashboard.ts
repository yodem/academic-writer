import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import type { HookInput, HookResult } from '../types.js';
import { loadProfile } from '../lib/profile.js';

export function sessionDashboard(input: HookInput): HookResult {
  const projectDir = input.project_dir ?? process.env['CLAUDE_PROJECT_DIR'] ?? '.';
  const profile = loadProfile(projectDir);

  if (!profile) {
    return { continue: true, suppressOutput: true };
  }

  const lines: string[] = [];
  lines.push('');
  lines.push('╔══════════════════════════════════════════════════╗');
  lines.push('║         ACADEMIC WRITER — SESSION START          ║');
  lines.push('╠══════════════════════════════════════════════════╣');

  // Profile status
  lines.push(`║  Field: ${(profile.fieldOfStudy ?? 'Not set').padEnd(38)}║`);
  lines.push(`║  Language: ${(profile.targetLanguage ?? 'Not set').padEnd(36)}║`);
  lines.push(`║  Citation: ${(profile.citationStyle ?? 'Not set').padEnd(36)}║`);
  lines.push(`║  Fingerprint: ${(profile.styleFingerprint ? 'Loaded' : 'Missing').padEnd(33)}║`);

  // Articles count
  const articlesDir = join(projectDir, 'articles');
  let articleCount = 0;
  if (existsSync(articlesDir)) {
    try {
      const files = readdirSync(articlesDir);
      articleCount = files.filter(f => f.endsWith('.docx')).length;
    } catch {
      // ignore
    }
  }
  lines.push(`║  Articles: ${String(articleCount).padEnd(36)}║`);

  // Source count
  const sourceCount = profile.sources?.length ?? 0;
  lines.push(`║  Sources indexed: ${String(sourceCount).padEnd(29)}║`);

  // Tools status
  const tools = profile.tools ?? {};
  const enabledTools: string[] = [];
  for (const [name, config] of Object.entries(tools)) {
    if (config && typeof config === 'object' && 'enabled' in config && config.enabled) {
      enabledTools.push(name);
    }
  }
  lines.push(`║  Tools: ${(enabledTools.length > 0 ? enabledTools.join(', ') : 'None').substring(0, 38).padEnd(38)}║`);

  // Research brief
  const briefPath = join(projectDir, '.academic-helper', 'research-brief.md');
  if (existsSync(briefPath)) {
    lines.push(`║  Research brief: Available                       ║`);
  }

  // Past articles for learning
  const pastDir = join(projectDir, 'past-articles');
  if (existsSync(pastDir)) {
    try {
      const pastFiles = readdirSync(pastDir);
      const analyzed = profile.analyzedArticles?.length ?? 0;
      const total = pastFiles.filter(f => f.endsWith('.pdf') || f.endsWith('.docx')).length;
      const unanalyzed = total - analyzed;
      if (unanalyzed > 0) {
        lines.push(`║  New past articles: ${String(unanalyzed).padEnd(27)}║`);
        lines.push(`║  → Run /academic-writer-learn to update style    ║`);
      }
    } catch {
      // ignore
    }
  }

  lines.push('╠══════════════════════════════════════════════════╣');
  lines.push('║  /academic-writer        — Write new article     ║');
  lines.push('║  /academic-writer-ideate — Brainstorm ideas      ║');
  lines.push('║  /academic-writer-learn  — Update style          ║');
  lines.push('║  /academic-writer-health — Check integrations    ║');
  lines.push('╚══════════════════════════════════════════════════╝');

  return {
    continue: true,
    systemMessage: lines.join('\n'),
  };
}
