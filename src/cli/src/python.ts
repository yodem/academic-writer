import { spawnSync } from 'node:child_process';

/**
 * The one place the `aw` CLI finds a Python 3 for the plugin's own scripts. It follows bin/aw-python: try
 * python3, python, then the Windows launcher `py -3`; a candidate counts only when `--version` exits 0 and
 * prints Python 3.<minor> with minor at least MIN_PYTHON_MINOR (the same minimum as MIN_PYTHON in
 * scripts/setup_checks.py). That skips the Microsoft Store stub Windows ships as python.exe.
 */
export type PythonCommand = { command: string; args: string[] };

export const MIN_PYTHON_MINOR = 9;
const CANDIDATES: PythonCommand[] = [
  { command: 'python3', args: [] },
  { command: 'python', args: [] },
  { command: 'py', args: ['-3'] },
];
const PROBE_TIMEOUT_MS = 15000;

/** True when `--version` output names Python 3 at the minimum minor or newer. */
export function isSupportedPythonVersion(output: string): boolean {
  const match = output.match(/Python 3\.(\d+)/u);
  return match !== null && Number(match[1]) >= MIN_PYTHON_MINOR;
}

/** UTF-8 mode for the child: Hebrew text files must read and write the same on Windows as elsewhere. */
export function pythonEnv(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  return { ...env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' };
}

const cache = new Map<string, PythonCommand | null>();

/** Forget what was found (tests change PATH between cases). */
export function resetPythonCache(): void { cache.clear(); }

function pathKey(env: NodeJS.ProcessEnv): string { return env.PATH ?? env.Path ?? ''; }

/** The first working Python 3 on this PATH, or null. The answer is cached per PATH value. */
export function discoverPython(env: NodeJS.ProcessEnv = process.env): PythonCommand | null {
  const key = pathKey(env);
  if (cache.has(key)) return cache.get(key) ?? null;
  let found: PythonCommand | null = null;
  for (const candidate of CANDIDATES) {
    const result = spawnSync(candidate.command, [...candidate.args, '--version'], { encoding: 'utf8', env, timeout: PROBE_TIMEOUT_MS, windowsHide: true });
    if (result.error || result.status !== 0) continue;
    if (isSupportedPythonVersion(`${result.stdout ?? ''}${result.stderr ?? ''}`)) { found = candidate; break; }
  }
  cache.set(key, found);
  return found;
}

/** Like discoverPython, but a plain error line when there is none. */
export function requirePython(env: NodeJS.ProcessEnv = process.env): PythonCommand {
  const found = discoverPython(env);
  if (!found) throw new Error(`ERROR python: Python 3.${MIN_PYTHON_MINOR} or newer was not found on this computer. Run /academic-writer:setup to install it.`);
  return found;
}

/** The program and arguments that run `script` (with its own arguments) under the discovered Python. */
export function pythonInvocation(script: string, args: string[], env: NodeJS.ProcessEnv = process.env): { command: string; args: string[] } {
  const python = requirePython(env);
  return { command: python.command, args: [...python.args, script, ...args] };
}
