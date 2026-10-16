import { appendFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

export type SessionEnvValues = { googleApiKey?: string; jevApiKey?: string; pageindexCommand?: string; pluginData?: string };

// An unset userConfig option can arrive as the literal placeholder text (observed for skills in
// docs/refactor/runtime-facts.md); never export a placeholder as a key.
function usable(v: string | undefined): v is string { return !!v && v.trim() !== '' && !v.includes('${user_config.'); }

/**
 * A plugin option as the hook process sees it. Claude Code hands every option to hooks as CLAUDE_PLUGIN_OPTION_<UPPER_KEY>; the
 * hooks.json command must not interpolate ${user_config.*} (Claude Code 2.1.300 refuses a shell-form command that does). The
 * USER_CONFIG_<UPPER_KEY> name is the older bridge and stays as a fallback. Example: pageindex_command arrives as
 * CLAUDE_PLUGIN_OPTION_PAGEINDEX_COMMAND and leaves as AW_PAGEINDEX_COMMAND.
 */
export function pluginOption(key: string, env: NodeJS.ProcessEnv = process.env): string | undefined {
  const upper = key.toUpperCase();
  return [env[`CLAUDE_PLUGIN_OPTION_${upper}`], env[`USER_CONFIG_${upper}`]].find(usable);
}

export function sessionEnv(projectDir: string, envFile: string | undefined, values: SessionEnvValues): void {
  if (!existsSync(join(projectDir, '.academic-helper', 'profile.md')) || !envFile) return;
  const lines: string[] = [];
  const googleApiKey = 'googleApiKey' in values ? values.googleApiKey : pluginOption('google_api_key');
  const jevApiKey = 'jevApiKey' in values ? values.jevApiKey : pluginOption('jev_api_key');
  if (usable(googleApiKey)) lines.push(`export GOOGLE_API_KEY='${shellQuote(googleApiKey)}'`);
  if (usable(jevApiKey)) lines.push(`export JEV_API_KEY='${shellQuote(jevApiKey)}'`);
  // Not a secret: how to start the optional PageIndex library (read by `aw library`).
  const pageindex = 'pageindexCommand' in values ? values.pageindexCommand : pluginOption('pageindex_command');
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
