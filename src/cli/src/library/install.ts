import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { existsSync, lstatSync, readFileSync, realpathSync } from 'node:fs';
import { mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { z } from 'zod';
import thresholds from '../../../thresholds.json' with { type: 'json' };
import { allowedEnv, type EnvKind } from './backends.ts';
import { runCommand } from './exec.ts';
import { atLeast, choosePython, discoverPythons, probePython, venvPython, type PythonInfo } from './python-discovery.ts';
import { LibraryError } from './types.ts';

const install = thresholds.library.install;

export type Tier = 'core' | 'structure';

/** Where the built-in PageIndex helper lives inside the plugin's data folder. */
export type InstallPaths = { home: string; venv: string; python: string; library: string; installed: string; lock: string };

export function installPaths(home: string): InstallPaths {
  const venv = join(home, 'venv');
  return { home, venv, python: venvPython(venv), library: join(home, 'library'), installed: join(home, 'installed.json'), lock: join(home, 'install.lock') };
}

/**
 * The folder of the built-in helper: AW_PAGEINDEX_HOME (the SessionStart hook sets it once the helper is installed),
 * else `<data folder>/pageindex` (`--data-dir`), else `$CLAUDE_PLUGIN_DATA/pageindex`. Null when none of them is known.
 */
export function resolveHome(env: NodeJS.ProcessEnv, dataDirectory: string | null | undefined): string | null {
  const named = env.AW_PAGEINDEX_HOME?.trim();
  if (named) return resolve(named);
  if (dataDirectory) return join(resolve(dataDirectory), 'pageindex');
  const plugin = env.CLAUDE_PLUGIN_DATA?.trim();
  return plugin ? join(resolve(plugin), 'pageindex') : null;
}

// ---------------------------------------------------------------- what the plugin pins (PINNED.json)

const tierSchema = z.object({
  requirements: z.string().min(1),
  requirements_sha256: z.string().regex(/^[0-9a-f]{64}$/u),
  requires_python: z.string().min(1),
  locked_with_python: z.string().min(1),
  system_libraries: z.object({ macos: z.string().optional(), debian_ubuntu: z.string().optional() }).passthrough().optional(),
}).passthrough();

const pinnedSchema = z.object({
  schema: z.literal(1),
  pilib_version: z.string().min(1),
  pageindex: z.object({ commit: z.string().regex(/^[0-9a-f]{40}$/u) }).passthrough(),
  tiers: z.object({ core: tierSchema, structure: tierSchema }),
}).passthrough();
export type Pinned = z.infer<typeof pinnedSchema>;

/** The folder holding pilib, PINNED.json and the requirements files. */
export function pilibSource(root: string): string { return join(root, 'scripts', 'pageindex'); }

export function readPinned(root: string): Pinned {
  const file = join(pilibSource(root), 'PINNED.json');
  let raw: unknown;
  try { raw = JSON.parse(readFileSync(file, 'utf8')); }
  catch { throw new LibraryError('config', 'ERROR library install: this copy of the plugin has no PageIndex helper files (scripts/pageindex/PINNED.json is missing or unreadable). Update or reinstall the plugin.'); }
  const parsed = pinnedSchema.safeParse(raw);
  if (!parsed.success) throw new LibraryError('config', `ERROR library install: scripts/pageindex/PINNED.json is not valid (${parsed.error.issues[0]?.path.join('.') ?? 'file'}). Update or reinstall the plugin.`);
  if (parsed.data.pageindex.commit !== install.pageindexCommit) {
    throw new LibraryError('config', 'ERROR library install: the pinned PageIndex version in PINNED.json does not match the plugin settings. Update or reinstall the plugin.');
  }
  return parsed.data;
}

// ---------------------------------------------------------------- what is installed (installed.json)

const installedSchema = z.object({
  schema: z.literal(1),
  tier: z.enum(['core', 'structure']),
  requested_tier: z.enum(['core', 'structure']).optional(),
  python: z.string(),
  pageindex_commit: z.string().nullable(),
  requirements_sha256: z.string(),
  pilib_version: z.string(),
  litellm: z.string().nullable().optional(),
  installed_at: z.string(),
}).passthrough();
export type Installed = z.infer<typeof installedSchema>;

/** installed.json, or null when it is missing or unreadable (an unreadable record means "not installed"). */
export function readInstalled(home: string): Installed | null {
  try {
    const parsed = installedSchema.safeParse(JSON.parse(readFileSync(installPaths(home).installed, 'utf8')));
    return parsed.success ? parsed.data : null;
  } catch { return null; }
}

/** The helper is usable only when its record exists and the private Python it names is still there. */
export function isInstalled(home: string): boolean {
  return readInstalled(home) !== null && existsSync(installPaths(home).python);
}

/** Python that starts pilib from the plugin's own copy of it: no PYTHONPATH or environment needed, so the command is plain words. */
export function bootstrapCode(source: string, library: string): string {
  // JSON strings are valid Python string literals, whatever characters the folder names hold.
  return `import os, sys, runpy; sys.path.insert(0, ${JSON.stringify(source)}); os.environ["AW_LIBRARY"] = ${JSON.stringify(library)}; runpy.run_module("pilib", run_name="__main__")`;
}

/** The command that runs the installed pilib: `<venv python> -c <bootstrap>`, with pilib's own arguments after it. */
export function installedCommand(home: string, pluginRootDir: string): string[] {
  const paths = installPaths(home);
  return [paths.python, '-c', bootstrapCode(pilibSource(pluginRootDir), paths.library)];
}

/** Does the record still match what this version of the plugin pins? False means an update is available. */
export function matchesPinned(installed: Installed, pinned: Pinned): boolean {
  const tier = pinned.tiers[installed.tier];
  return installed.requirements_sha256 === tier.requirements_sha256
    && installed.pilib_version === pinned.pilib_version
    && (installed.tier === 'core' || installed.pageindex_commit === pinned.pageindex.commit);
}

// ---------------------------------------------------------------- the environment of a child

/**
 * The environment of a command the plugin starts: the allow-list of allowedEnv (no keys, tokens or secrets), plus, when `gemini` names a key, that key
 * as GEMINI_API_KEY (LiteLLM's name) in this child's environment only, never in an argument. Only the built-in helper that writes the summaries gets it.
 */
export function childEnv(env: NodeJS.ProcessEnv, options: { gemini?: string | null; kind?: EnvKind } = {}): NodeJS.ProcessEnv {
  const clean = allowedEnv(env, options.kind ?? 'pageindex');
  if (options.gemini) clean.GEMINI_API_KEY = options.gemini;
  return clean;
}

/** The Gemini key the plugin holds: the one it was given as GOOGLE_API_KEY, else the researcher's own GEMINI_API_KEY. */
export function geminiKeyFrom(env: NodeJS.ProcessEnv): string | null {
  for (const name of ['GOOGLE_API_KEY', 'GEMINI_API_KEY']) {
    const value = env[name]?.trim();
    if (value && !value.includes('${user_config.')) return value;
  }
  return null;
}

// ---------------------------------------------------------------- plain words for what can go wrong

/** One short plain sentence for a pip or venv failure, from the start of what the command printed. */
export function friendlyInstallError(step: string, text: string): string {
  const lower = text.toLowerCase();
  if (/externally-managed-environment/u.test(lower)) return 'this Python refuses to install packages by itself; point --python at a normal Python (python.org or Homebrew)';
  if (/(could not resolve|name or service not known|temporary failure in name|connection (?:error|refused|reset|timed out)|network is unreachable|max retries exceeded|read timed out)/u.test(lower)) return 'the download did not work: check the internet connection and try again';
  if (/ssl|certificate/u.test(lower)) return 'a secure download failed (certificate problem): check the network or proxy and try again';
  if (/(hashes are required|do not match the hashes|hash mismatch|expected sha256)/u.test(lower)) return 'a downloaded file did not match its expected checksum, so nothing was kept: try again, and report it if it repeats';
  if (/no matching distribution|could not find a version/u.test(lower)) return 'a required package has no version for this Python: try a different Python with --python';
  if (/(no module named venv|ensurepip is not available)/u.test(lower)) return 'this Python cannot make a private folder (the venv module is missing): install the full Python from python.org or Homebrew';
  if (/(no space left|disk quota)/u.test(lower)) return 'the disk is full';
  if (/(permission denied|operation not permitted)/u.test(lower)) return 'the plugin could not write to its data folder (permission denied)';
  if (/failed building wheel|error: subprocess-exited|microsoft visual c\+\+/u.test(lower)) return 'a package could not be built on this computer: try a different Python with --python';
  const line = text.split('\n').map((entry) => entry.trim()).filter((entry) => /^(error|fatal)/iu.test(entry)).at(-1) ?? text.split('\n').map((entry) => entry.trim()).find(Boolean) ?? '';
  return `${step} did not finish${line ? ` (${line.slice(0, 160)})` : ''}`;
}

function stepFailure(step: string, error: unknown): LibraryError {
  if (error instanceof LibraryError) {
    if (error.code === 'timeout') return new LibraryError('timeout', `ERROR library install: ${step} took too long and was stopped. Try again; a slow connection can need a second run.`);
    if (error.code === 'spawn') return new LibraryError('spawn', `ERROR library install: could not start ${step}: ${error.message.replace(/^ERROR library: /u, '')}`);
    return new LibraryError('exit', `ERROR library install: ${friendlyInstallError(step, `${error.stderr}\n${error.message}`)}.`, error.stderr);
  }
  return new LibraryError('exit', `ERROR library install: ${step} failed`);
}

// ---------------------------------------------------------------- the install itself

export type InstallOptions = {
  tier?: Tier;
  dryRun: boolean;
  yes: boolean;
  /** A Python the researcher chose (`--python`). */
  python?: string;
  /** The plugin's data folder (`--data-dir`), or null. */
  dataDir: string | null;
  pluginRoot: string;
  env: NodeJS.ProcessEnv;
  now?: () => Date;
};

type Chosen = { tier: Tier; requested: Tier | null; python: PythonInfo; exact: boolean; notes: string[] };

async function chooseTier(options: InstallOptions, pinned: Pinned): Promise<Chosen> {
  const found = await discoverPythons(childEnv(options.env), options.python ? [options.python] : []);
  if (options.python && !found.some((info) => info.command === options.python)) {
    throw new LibraryError('usage', `ERROR library install: ${options.python} is not a Python 3 that runs on this computer`);
  }
  const usable = options.python ? found.filter((info) => info.command === options.python) : found;
  const structure = choosePython(usable, install.minPython, pinned.tiers.structure.locked_with_python);
  const core = choosePython(usable, install.minPythonCore, pinned.tiers.core.locked_with_python);
  const notes: string[] = [];
  if (options.tier === 'structure') {
    if (!structure) throw new LibraryError('config', `ERROR library install: the full helper (for books with no table of contents) needs Python ${install.minPython} or newer, and none was found. Install a newer Python (python.org or Homebrew) and run this again, or install the basic helper with --tier core.`);
    return { tier: 'structure', requested: 'structure', python: structure.python, exact: structure.exact, notes };
  }
  if (options.tier === 'core' || !structure) {
    if (!core) throw new LibraryError('config', `ERROR library install: no Python ${install.minPythonCore} or newer was found on this computer. Install Python from python.org (or Homebrew) and run this again.`);
    if (options.tier === undefined) notes.push(`No Python ${install.minPython} or newer was found, so only the basic helper is installed: it indexes books that have a table of contents. A book without one needs a newer Python (run the install again afterwards) or a computer that has it.`);
    return { tier: 'core', requested: options.tier ?? null, python: core.python, exact: core.exact, notes };
  }
  return { tier: 'structure', requested: null, python: structure.python, exact: structure.exact, notes };
}

function requirementsFile(root: string, pinned: Pinned, tier: Tier): string { return join(pilibSource(root), pinned.tiers[tier].requirements); }

async function sha256File(file: string): Promise<string> { return createHash('sha256').update(await readFile(file)).digest('hex'); }

// The install lock is an OS advisory lock (flock, or msvcrt on Windows) held on an open file by a small Python process that lives as long as
// the install or uninstall does. The kernel drops it when that process ends, however it ends, so there is no lock file to go stale or to take over;
// the file itself is never deleted. Node has no flock of its own, and the install already needs a Python.
const LOCK_SCRIPT = [
  'import os, sys',
  'fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o600)',
  'try:',
  '    if os.name == "nt":',
  '        import msvcrt',
  '        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)',
  '    else:',
  '        import fcntl',
  '        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)',
  'except OSError:',
  '    print("busy", flush=True)',
  '    sys.exit(3)',
  'print("locked", flush=True)',
  'sys.stdin.read()',
].join('\n');

/** Take the per-folder install lock without waiting. Returns the release function; contention is a plain "busy" error. */
export async function takeLock(file: string, python: string, env: NodeJS.ProcessEnv, what: 'install' | 'uninstall'): Promise<() => Promise<void>> {
  const child = spawn(python, ['-c', LOCK_SCRIPT, file], { stdio: ['pipe', 'pipe', 'ignore'], env: childEnv(env), windowsHide: true });
  let closed = false;
  const closing = new Promise<void>((done) => { child.once('close', () => { closed = true; done(); }); });
  const answer = await new Promise<string>((settle) => {
    let text = '';
    const timer = setTimeout(() => { settle('timeout'); }, install.probeTimeoutMs);
    child.stdout?.setEncoding('utf8').on('data', (chunk: string) => { text += chunk; if (text.includes('\n')) { clearTimeout(timer); settle(text.trim()); } });
    child.once('error', () => { clearTimeout(timer); settle('error'); });
    child.once('close', () => { clearTimeout(timer); settle(text.trim() || 'closed'); });
  });
  const release = async (): Promise<void> => {
    if (closed) return;
    child.stdin?.end();
    const killer = setTimeout(() => { child.kill('SIGKILL'); }, 3000);
    await closing;
    clearTimeout(killer);
  };
  if (answer === 'locked') return release;
  child.kill('SIGKILL');
  if (answer === 'busy') throw new LibraryError('exit', `ERROR library ${what}: another install or uninstall is already running; wait for it to finish.`);
  throw new LibraryError('config', `ERROR library ${what}: could not take the install lock (the Python at ${python} did not start properly). Try another with --python.`);
}

/**
 * The helper's folder must be exactly <plugin data folder>/pageindex once real paths are resolved, and neither it nor anything this code deletes
 * or builds in may be a symbolic link: a link could send a delete (or an install) to another place.
 */
function guardHome(home: string, dataRoot: string | null | undefined, what: 'install' | 'uninstall'): void {
  const refuse = (why: string): LibraryError => new LibraryError('config', `ERROR library ${what}: ${why}`);
  if (!dataRoot) throw refuse('the plugin\'s data folder is not known (pass --data-dir <folder>), so the helper folder cannot be checked; nothing was touched.');
  let root: string;
  try { root = realpathSync(resolve(dataRoot)); } catch { throw refuse(`the plugin's data folder ${dataRoot} cannot be resolved; nothing was touched.`); }
  const expected = join(root, 'pageindex');
  let actual: string;
  if (existsSync(home) || isLink(home)) {
    if (isLink(home)) throw refuse(`${home} is a symbolic link; refusing to use it.`);
    actual = realpathSync(home);
  } else {
    try { actual = join(realpathSync(dirname(home)), basename(home)); } catch { actual = resolve(home); }
  }
  if (actual !== expected) throw refuse(`${home} is not the plugin's own helper folder (${expected}); nothing was touched.`);
  for (const path of [installPaths(home).venv, installPaths(home).library, installPaths(home).installed]) {
    if (isLink(path)) throw refuse(`${path} is a symbolic link; refusing to use it.`);
  }
}

/** Write a file by temp name + rename, so a reader sees the old record or the new one, never half of one. */
async function writeAtomic(file: string, text: string): Promise<void> {
  const temp = `${file}.${process.pid}.tmp`;
  try {
    await writeFile(temp, text, 'utf8');
    await rename(temp, file);
  } catch (error) { await rm(temp, { force: true }); throw error; }
}

type Health = { ok: boolean; tier: string; python: string; litellm: string | null; pilib_version: string; weasyprint: boolean; pageindex: boolean; pageindex_commit: string | null };

/** `pilib health` through a command (no --require: that exits 1 and hides the answer). Null when it fails or prints no JSON. */
export async function pilibHealth(command: string[], env: NodeJS.ProcessEnv, timeoutMs: number = install.healthTimeoutMs): Promise<Health | null> {
  try {
    const out = await runCommand(command, ['health'], { timeoutMs, maxBuffer: 1048576, env });
    const parsed = JSON.parse(out.trim().split('\n').at(-1) ?? '') as Partial<Health>;
    if (typeof parsed.tier !== 'string' || typeof parsed.pilib_version !== 'string') return null;
    return { ok: parsed.ok === true, tier: parsed.tier, python: String(parsed.python ?? ''), litellm: typeof parsed.litellm === 'string' ? parsed.litellm : null, pilib_version: parsed.pilib_version, weasyprint: parsed.weasyprint === true, pageindex: parsed.pageindex === true, pageindex_commit: typeof parsed.pageindex_commit === 'string' ? parsed.pageindex_commit : null };
  } catch { return null; }
}

function homeFor(options: InstallOptions): string {
  const home = resolveHome(options.env, options.dataDir);
  if (!home) throw new LibraryError('config', 'ERROR library install: the plugin\'s data folder is not known. Run this through the plugin (it passes --data-dir), or pass --data-dir <folder>.');
  return home;
}

/**
 * `aw library install [--tier core|structure] [--dry-run] [--yes] [--python PATH]`. The skill asks the researcher first; this
 * refuses to change anything without --yes. Returns the JSON to print.
 */
export async function runInstall(options: InstallOptions): Promise<Record<string, unknown>> {
  const pinned = readPinned(options.pluginRoot);
  const home = homeFor(options);
  const paths = installPaths(home);
  const chosen = await chooseTier(options, pinned);
  const requirements = requirementsFile(options.pluginRoot, pinned, chosen.tier);
  if (!existsSync(requirements)) throw new LibraryError('config', 'ERROR library install: the plugin is missing its requirements file; update or reinstall the plugin.');
  const expected = pinned.tiers[chosen.tier].requirements_sha256;
  if (await sha256File(requirements) !== expected) throw new LibraryError('config', 'ERROR library install: the requirements file does not match the one the plugin pins (its checksum differs); update or reinstall the plugin.');
  const system = chosen.tier === 'structure' ? pinned.tiers.structure.system_libraries : undefined;
  const warnings = [...chosen.notes];
  if (!chosen.exact) warnings.push(`The packages were locked with Python ${pinned.tiers[chosen.tier].locked_with_python}; this computer uses ${chosen.python.minorName}. The install checks that it works afterwards.`);
  // A private Python folder made earlier may be too old for this tier (a basic install under Python 3.9, then the full helper): it is rebuilt.
  let rebuild: string | null = null;
  if (existsSync(paths.python)) {
    const minimum = chosen.tier === 'structure' ? install.minPython : install.minPythonCore;
    const existing = await probePython(paths.python, childEnv(options.env));
    if (!existing) rebuild = 'the existing private Python folder no longer starts';
    else if (!atLeast(existing, minimum)) rebuild = `the existing private Python folder uses Python ${existing.version}, and this tier needs Python ${minimum} or newer`;
  }
  if (rebuild) warnings.push(`${rebuild[0]?.toUpperCase()}${rebuild.slice(1)}, so it will be removed and rebuilt with Python ${chosen.python.version}. The indexed books are kept.`);
  const plan = {
    rebuild_venv: rebuild !== null, rebuild_reason: rebuild,
    tier: chosen.tier, requested_tier: chosen.requested, python: { path: chosen.python.path, version: chosen.python.version },
    home, venv: paths.venv, library: paths.library, requirements: pinned.tiers[chosen.tier].requirements,
    approx_size_mb: install.approxSizeMb[chosen.tier], sends_data_to_google: false,
    steps: ['create a private Python folder (venv)', 'install the pinned packages with checked hashes (pip --require-hashes)', 'check that the helper starts (pilib health)', 'write installed.json'],
    ...(system ? { system_library: { name: 'pango', macos: system.macos ?? null, debian_ubuntu: system.debian_ubuntu ?? null, note: 'Needed to turn the text of a book without a table of contents into a PDF. Without it the helper stays at the basic tier.' } } : {}),
    warnings,
  };
  if (options.dryRun) return { ok: true, dry_run: true, ...plan };
  if (!options.yes) {
    throw new LibraryError('usage', `ERROR library install: this adds about ${install.approxSizeMb[chosen.tier]} MB of Python packages to ${home}. Ask the researcher first, then run it again with --yes. (--dry-run shows the plan without changing anything.)`);
  }

  const dataRoot = options.dataDir ?? options.env.CLAUDE_PLUGIN_DATA ?? null;
  if (dataRoot) await mkdir(resolve(dataRoot), { recursive: true });
  guardHome(home, dataRoot, 'install');
  await mkdir(home, { recursive: true });
  const release = await takeLock(paths.lock, chosen.python.path, options.env, 'install');
  let created = false;
  // A private Python folder made by this run and not finished is removed: no half install is left behind. One that was there before stays.
  const abandon = async (): Promise<void> => { if (created) await rm(paths.venv, { recursive: true, force: true }); };
  try {
    const env = { ...childEnv(options.env, { kind: 'install' }), PIP_DISABLE_PIP_VERSION_CHECK: '1', PIP_NO_INPUT: '1', PYTHONNOUSERSITE: '1' };
    const command = installedCommand(home, options.pluginRoot);
    const existing = readInstalled(home);
    if (!rebuild && existing && existing.tier === chosen.tier && matchesPinned(existing, pinned) && existsSync(paths.python)) {
      const health = await pilibHealth(command, env);
      if (health && health.tier === chosen.tier) return { ok: true, action: 'already_installed', ...plan, tier: health.tier, installed_at: existing.installed_at, notes: ['Already installed and up to date.'] };
    }
    if (rebuild) {
      // The record described the folder that is going away; the indexed books (library/) are not touched.
      await rm(paths.installed, { force: true });
      await rm(paths.venv, { recursive: true, force: true });
    }
    if (!existsSync(paths.python)) {
      try { await runCommand([chosen.python.path], ['-m', 'venv', paths.venv], { timeoutMs: install.venvTimeoutMs, maxBuffer: 1048576, env }); created = true; }
      catch (error) { await rm(paths.venv, { recursive: true, force: true }); throw stepFailure('creating the private Python folder', error); }
    }
    try {
      await runCommand([paths.python], ['-m', 'pip', 'install', '--quiet', '--require-hashes', '--no-input', '--disable-pip-version-check', '-r', requirements], { timeoutMs: install.pipTimeoutMs, maxBuffer: 16777216, env });
    } catch (error) { throw stepFailure('installing the packages', error); }
    await mkdir(paths.library, { recursive: true });
    const health = await pilibHealth(command, env);
    if (!health) throw new LibraryError('exit', 'ERROR library install: the packages installed, but the helper does not start. Run `aw library install --dry-run` to see which Python was used, and try another with --python.');
    if (health.tier !== 'core' && health.tier !== 'structure') throw new LibraryError('exit', 'ERROR library install: the packages installed, but the summary helper (LiteLLM) cannot be loaded. Try another Python with --python.');
    const degraded = chosen.tier === 'structure' && health.tier !== 'structure';
    if (degraded) warnings.push(`The full helper could not start (${health.weasyprint ? 'PageIndex did not load' : 'the PDF library WeasyPrint did not load'}), so the basic helper is ready and books with no table of contents are not covered yet.${system?.macos && process.platform === 'darwin' ? ` On a Mac, run: ${system.macos}, then run this install again.` : system?.debian_ubuntu && process.platform === 'linux' ? ` On Linux, run: ${system.debian_ubuntu}, then run this install again.` : ' Install the pango system library, then run this install again.'}`);
    // The Python recorded is the one the private folder really runs.
    const real = await probePython(paths.python, env);
    const record: Installed = {
      schema: 1, tier: health.tier === 'structure' ? 'structure' : 'core', requested_tier: chosen.tier, python: real?.version ?? chosen.python.version,
      pageindex_commit: health.tier === 'structure' ? pinned.pageindex.commit : null, requirements_sha256: expected,
      pilib_version: health.pilib_version, litellm: health.litellm, installed_at: (options.now ?? ((): Date => new Date()))().toISOString(),
    };
    // A degraded structure install keeps the structure lock's hash, so a later run sees it is not complete and tries again.
    if (degraded) record.requirements_sha256 = pinned.tiers.core.requirements_sha256;
    await writeAtomic(paths.installed, `${JSON.stringify(record, null, 2)}\n`);
    return { ok: true, action: 'installed', ...plan, tier: record.tier, degraded, pilib_version: record.pilib_version, litellm: record.litellm ?? null, installed_at: record.installed_at, warnings };
  } catch (error) {
    await abandon();
    throw error;
  } finally { await release(); }
}

// ---------------------------------------------------------------- uninstall

/**
 * `aw library uninstall --yes [--purge-library]`: removes the private Python folder and the record; the indexed books stay unless asked.
 * Takes the same lock as install, and deletes only inside <plugin data folder>/pageindex (real paths, no symbolic links).
 */
export async function runUninstall(options: { yes: boolean; purgeLibrary: boolean; dataDir: string | null; env: NodeJS.ProcessEnv }): Promise<Record<string, unknown>> {
  const home = resolveHome(options.env, options.dataDir);
  if (!home) throw new LibraryError('config', 'ERROR library uninstall: the plugin\'s data folder is not known. Pass --data-dir <folder>.');
  guardHome(home, options.dataDir ?? options.env.CLAUDE_PLUGIN_DATA ?? null, 'uninstall');
  const paths = installPaths(home);
  if (!options.yes) {
    throw new LibraryError('usage', `ERROR library uninstall: this removes the helper's private Python folder${options.purgeLibrary ? ' and every indexed book' : ' (the indexed books are kept)'} in ${home}. Ask the researcher first, then run it again with --yes.`);
  }
  if (!existsSync(home)) return { ok: true, removed: [], library_kept: null, home };
  const python = (await discoverPythons(childEnv(options.env)))[0]?.path ?? (process.platform !== 'win32' && existsSync(paths.python) ? paths.python : null);
  if (!python) throw new LibraryError('config', 'ERROR library uninstall: no Python was found to hold the install lock, so nothing was removed. Install Python, or remove the folder by hand.');
  const release = await takeLock(paths.lock, python, options.env, 'uninstall');
  try {
    const present = [paths.venv, paths.installed, ...(options.purgeLibrary ? [paths.library] : [])].filter((path) => existsSync(path));
    for (const path of present) await rm(path, { recursive: true, force: true });
    return { ok: true, removed: present.map((path) => basename(path)), library_kept: options.purgeLibrary ? null : (existsSync(paths.library) ? paths.library : null), home };
  } finally { await release(); }
}

function isLink(path: string): boolean {
  try { return lstatSync(path).isSymbolicLink(); } catch { return false; }
}
