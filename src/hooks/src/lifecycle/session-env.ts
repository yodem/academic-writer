import { appendFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

export type SessionEnvValues = { googleApiKey?: string; jevApiKey?: string; pageindexCommand?: string; pluginData?: string };

// An unset userConfig option can arrive as the literal placeholder text (observed for skills in
// docs/refactor/runtime-facts.md); never export a placeholder as a key.
function usable(v: string | undefined): v is string { return !!v && v.trim() !== '' && !v.includes('${user_config.'); }

export function sessionEnv(projectDir: string, envFile: string | undefined, values: SessionEnvValues): void {
  if (!existsSync(join(projectDir, '.academic-helper', 'profile.md')) || !envFile) return;
  const lines: string[] = [];
  if (usable(values.googleApiKey)) lines.push(`export GOOGLE_API_KEY='${shellQuote(values.googleApiKey)}'`);
  if (usable(values.jevApiKey)) lines.push(`export JEV_API_KEY='${shellQuote(values.jevApiKey)}'`);
  // Not a secret: how to start the optional PageIndex library (read by `aw library`). Claude Code hands
  // plugin options to hook processes as CLAUDE_PLUGIN_OPTION_<KEY>, so the value never passes through
  // the shell-form hook command (a ${user_config.*} there would be re-parsed by the shell). The
  // USER_CONFIG_ name is the older bridge and stays as a fallback.
  const pageindex = 'pageindexCommand' in values
    ? values.pageindexCommand
    : [process.env['CLAUDE_PLUGIN_OPTION_PAGEINDEX_COMMAND'], process.env['USER_CONFIG_PAGEINDEX_COMMAND']].find(usable);
  if (usable(pageindex)) lines.push(`export AW_PAGEINDEX_COMMAND='${shellQuote(pageindex.trim())}'`);
  // The built-in PageIndex helper (`aw library install`) lives in <plugin data>/pageindex. Not a secret: it tells `aw library` where to
  // look, because the Bash tool gets no CLAUDE_PLUGIN_DATA. Exported only once installed.json exists, so nothing changes for a researcher
  // who never installed it. A command the researcher supplied (AW_PAGEINDEX_COMMAND) still wins: aw decides, this only says where the helper is.
  const data = 'pluginData' in values ? values.pluginData : process.env['CLAUDE_PLUGIN_DATA'];
  if (usable(data)) {
    const home = join(data.trim(), 'pageindex');
    if (existsSync(join(home, 'installed.json'))) lines.push(`export AW_PAGEINDEX_HOME='${shellQuote(home)}'`);
  }
  if (lines.length) appendFileSync(envFile, `${lines.join('\n')}\n`, 'utf8');
}

function shellQuote(value: string): string { return value.replace(/'/g, "'\\''"); }
