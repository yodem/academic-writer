import { existsSync, readFileSync } from 'node:fs';
import { basename, dirname, isAbsolute, join, resolve } from 'node:path';
import { z } from 'zod';
import { dataDir } from '../paths.ts';
import { splitCommand } from './exec.ts';
import { installedCommand, isInstalled, resolveHome } from './install.ts';
import { LibraryError, type RouteMode, type RouteName } from './types.ts';

export const LIBRARY_CONFIG_FILE = join('.academic-helper', 'library.json');
export const DEFAULT_PAGEINDEX_COMMAND = 'pilib';
export const DEFAULT_TROVE_COMMAND = 'trove';

// Mirrors src/schemas/library-config.schema.json (a test keeps the two in step).
export const libraryConfigSchema = z.object({
  $schema: z.string().optional(),
  route: z.enum(['trove', 'pageindex', 'both']),
  primary: z.enum(['trove', 'pageindex']).optional(),
  pageindex: z.object({
    command: z.union([z.string().min(1), z.array(z.string().min(1)).min(1)]).optional(),
    shelf: z.string().min(1).optional(),
  }).strict().optional(),
  shadow: z.object({ enabled: z.boolean().optional() }).strict().optional(),
}).strict();

/** Where the PageIndex command came from: the plugin setting (AW_PAGEINDEX_COMMAND), library.json, the built-in helper, or the plain `pilib`. */
export type PageindexSource = 'setting' | 'library.json' | 'installed' | 'default';

export type LibraryConfig = {
  /** false when there is no library.json: the project behaves exactly as before (Trove only, no shadow). */
  configured: boolean;
  route: RouteMode;
  /** The route that answers. */
  primary: RouteName;
  /** The other route when route is both, else null. */
  secondary: RouteName | null;
  troveCommand: string[];
  pageindexCommand: string[];
  /** Which of the four places the PageIndex command came from (order: setting, library.json, installed, default). */
  pageindexSource: PageindexSource;
  /** The built-in helper's folder when it is known (installed or not), else null. */
  pageindexHome: string | null;
  /** Absolute path of the shelf file, or null. */
  shelfPath: string | null;
  shadowEnabled: boolean;
};

function commandFrom(value: string | string[] | undefined, fallback: string): string[] {
  if (Array.isArray(value)) return value;
  if (typeof value === 'string' && value.trim()) return splitCommand(value);
  return [fallback];
}

export type ConfigOptions = {
  /** The plugin's data folder (`--data-dir`); default: the one given on the command line, if any. */
  dataDir?: string | null;
  /** The plugin's own folder, where pilib's source is; default: found from the running binary or CLAUDE_PLUGIN_ROOT. */
  pluginRoot?: string | null;
};

function optionalDataDir(): string | null {
  try { return dataDir(); } catch { return null; }
}

/** The plugin's own folder: `<root>/bin/aw` is the running program, else CLAUDE_PLUGIN_ROOT (Bash tool calls normally do not have it). */
function optionalPluginRoot(env: NodeJS.ProcessEnv): string | null {
  const bin = dirname(resolve(process.argv[1] ?? ''));
  if (basename(bin) === 'bin') return dirname(bin);
  return env.CLAUDE_PLUGIN_ROOT?.trim() || null;
}

/** The command of the built-in helper, or null when it is not installed (or the plugin's own folder cannot be found). */
function installedPageindex(env: NodeJS.ProcessEnv, options: ConfigOptions): { command: string[]; home: string } | null {
  const home = resolveHome(env, options.dataDir === undefined ? optionalDataDir() : options.dataDir);
  if (!home || !isInstalled(home)) return null;
  const root = options.pluginRoot === undefined ? optionalPluginRoot(env) : options.pluginRoot;
  return root ? { command: installedCommand(home, root), home } : null;
}

/**
 * Read `.academic-helper/library.json` (absent means Trove only) and resolve the two command lines. The PageIndex command comes from
 * the first of: AW_PAGEINDEX_COMMAND (the plugin setting), library.json `pageindex.command`, the built-in helper (when installed), `pilib`.
 * A command the researcher supplied always wins, so a local install is never used by surprise.
 */
export function loadLibraryConfig(project: string, env: NodeJS.ProcessEnv = process.env, options: ConfigOptions = {}): LibraryConfig {
  const file = join(project, LIBRARY_CONFIG_FILE);
  let parsed: z.infer<typeof libraryConfigSchema> | undefined;
  if (existsSync(file)) {
    let json: unknown;
    try { json = JSON.parse(readFileSync(file, 'utf8')); }
    catch { throw new LibraryError('config', `ERROR library: ${LIBRARY_CONFIG_FILE} is not valid JSON`); }
    const result = libraryConfigSchema.safeParse(json);
    if (!result.success) {
      const issue = result.error.issues[0];
      throw new LibraryError('config', `ERROR library: ${LIBRARY_CONFIG_FILE} is not valid (${issue?.path.join('.') || 'file'}: ${issue?.message ?? 'unknown problem'})`);
    }
    parsed = result.data;
  }
  const route: RouteMode = parsed?.route ?? 'trove';
  if (route !== 'both' && parsed?.primary && parsed.primary !== route) {
    throw new LibraryError('config', `ERROR library: ${LIBRARY_CONFIG_FILE} says route "${route}" but primary "${parsed.primary}"; drop primary or use route "both"`);
  }
  const primary: RouteName = route === 'both' ? (parsed?.primary ?? 'trove') : route;
  const secondary: RouteName | null = route === 'both' ? (primary === 'trove' ? 'pageindex' : 'trove') : null;
  const envPageindex = env.AW_PAGEINDEX_COMMAND?.trim();
  const shelf = parsed?.pageindex?.shelf;
  const fromFile = parsed?.pageindex?.command;
  let pageindexCommand: string[];
  let pageindexSource: PageindexSource;
  let pageindexHome = resolveHome(env, options.dataDir === undefined ? optionalDataDir() : options.dataDir);
  if (envPageindex) { pageindexCommand = splitCommand(envPageindex); pageindexSource = 'setting'; }
  else if (fromFile !== undefined && (Array.isArray(fromFile) || fromFile.trim())) { pageindexCommand = commandFrom(fromFile, DEFAULT_PAGEINDEX_COMMAND); pageindexSource = 'library.json'; }
  else {
    const installed = installedPageindex(env, options);
    if (installed) { pageindexCommand = installed.command; pageindexSource = 'installed'; pageindexHome = installed.home; }
    else { pageindexCommand = [DEFAULT_PAGEINDEX_COMMAND]; pageindexSource = 'default'; }
  }
  return {
    configured: parsed !== undefined,
    route,
    primary,
    secondary,
    troveCommand: commandFrom(env.AW_TROVE_COMMAND?.trim(), DEFAULT_TROVE_COMMAND),
    pageindexCommand,
    pageindexSource,
    pageindexHome,
    shelfPath: shelf ? (isAbsolute(shelf) ? shelf : resolve(project, shelf)) : null,
    shadowEnabled: route === 'both' && (parsed?.shadow?.enabled ?? true),
  };
}

/** `tools.trove.enabled` (older profiles: `tools.candlekeep.enabled`) from the profile's fenced `## Tools` JSON. Null when unknown. */
export function profileTroveEnabled(project: string): boolean | null {
  const file = join(project, '.academic-helper', 'profile.md');
  if (!existsSync(file)) return null;
  const match = readFileSync(file, 'utf8').match(/^## Tools\s*\n+```json\n([\s\S]*?)\n```/mu);
  if (!match?.[1]) return null;
  try {
    const tools = JSON.parse(match[1]) as Record<string, { enabled?: unknown } | undefined>;
    const entry = tools.trove ?? tools.candlekeep;
    return typeof entry?.enabled === 'boolean' ? entry.enabled : null;
  } catch { return null; }
}
