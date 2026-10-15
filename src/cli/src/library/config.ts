import { existsSync, readFileSync } from 'node:fs';
import { isAbsolute, join, resolve } from 'node:path';
import { z } from 'zod';
import { splitCommand } from './exec.ts';
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
  /** Absolute path of the shelf file, or null. */
  shelfPath: string | null;
  shadowEnabled: boolean;
};

function commandFrom(value: string | string[] | undefined, fallback: string): string[] {
  if (Array.isArray(value)) return value;
  if (typeof value === 'string' && value.trim()) return splitCommand(value);
  return [fallback];
}

/** Read `.academic-helper/library.json` (absent means Trove only) and resolve the two command lines. */
export function loadLibraryConfig(project: string, env: NodeJS.ProcessEnv = process.env): LibraryConfig {
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
  return {
    configured: parsed !== undefined,
    route,
    primary,
    secondary,
    troveCommand: commandFrom(env.AW_TROVE_COMMAND?.trim(), DEFAULT_TROVE_COMMAND),
    pageindexCommand: envPageindex ? splitCommand(envPageindex) : commandFrom(parsed?.pageindex?.command, DEFAULT_PAGEINDEX_COMMAND),
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
