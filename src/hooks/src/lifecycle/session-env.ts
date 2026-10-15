import { appendFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

export type SessionEnvValues = { googleApiKey?: string; jevApiKey?: string; pageindexCommand?: string };

// An unset userConfig option can arrive as the literal placeholder text (observed for skills in
// docs/refactor/runtime-facts.md); never export a placeholder as a key.
function usable(v: string | undefined): v is string { return !!v && v.trim() !== '' && !v.includes('${user_config.'); }

export function sessionEnv(projectDir: string, envFile: string | undefined, values: SessionEnvValues): void {
  if (!existsSync(join(projectDir, '.academic-helper', 'profile.md')) || !envFile) return;
  const lines: string[] = [];
  if (usable(values.googleApiKey)) lines.push(`export GOOGLE_API_KEY='${shellQuote(values.googleApiKey)}'`);
  if (usable(values.jevApiKey)) lines.push(`export JEV_API_KEY='${shellQuote(values.jevApiKey)}'`);
  // Not a secret: how to start the optional PageIndex library (read by `aw library`). The hook entry
  // does not pass it, so an omitted value is read from the hook command's own environment.
  const pageindex = 'pageindexCommand' in values ? values.pageindexCommand : process.env['USER_CONFIG_PAGEINDEX_COMMAND'];
  if (usable(pageindex)) lines.push(`export AW_PAGEINDEX_COMMAND='${shellQuote(pageindex.trim())}'`);
  if (lines.length) appendFileSync(envFile, `${lines.join('\n')}\n`, 'utf8');
}

function shellQuote(value: string): string { return value.replace(/'/g, "'\\''"); }
