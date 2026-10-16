import { realpathSync } from 'node:fs';
import { join } from 'node:path';
import thresholds from '../../../thresholds.json' with { type: 'json' };
import { runCommand } from './exec.ts';

/** One Python interpreter found on this computer. `minor` is the "3.10" style name used to match a lock file. */
export type PythonInfo = { command: string; path: string; version: string; major: number; minor: number; minorName: string };

/** The names tried, newest first. `python3` and `python` come last: they may be any version. */
export const PYTHON_CANDIDATES = ['python3.13', 'python3.12', 'python3.11', 'python3.10', 'python3.9', 'python3', 'python'];

const PROBE_CODE = 'import sys; print("%d.%d.%d" % sys.version_info[:3]); print(sys.executable)';

/** "3.10.4" or "3.10" to numbers; null when the text is not a version. */
export function parseVersion(text: string): { major: number; minor: number; patch: number } | null {
  const match = text.trim().match(/^(\d+)\.(\d+)(?:\.(\d+))?/u);
  if (!match) return null;
  return { major: Number(match[1]), minor: Number(match[2]), patch: Number(match[3] ?? 0) };
}

/** True when `have` (major.minor) is at least `need` (major.minor). */
export function atLeast(have: { major: number; minor: number }, need: string): boolean {
  const wanted = parseVersion(need);
  if (!wanted) return false;
  return have.major > wanted.major || (have.major === wanted.major && have.minor >= wanted.minor);
}

/** Ask one command what Python it is. Null when it does not exist, is not Python 3 or does not answer. */
export async function probePython(command: string, env: NodeJS.ProcessEnv | undefined, timeoutMs: number = thresholds.library.install.probeTimeoutMs): Promise<PythonInfo | null> {
  let out: string;
  try { out = await runCommand([command], ['-c', PROBE_CODE], { timeoutMs, maxBuffer: 65536, env }); }
  catch { return null; }
  const [versionLine, pathLine] = out.split('\n').map((line) => line.trim());
  const version = parseVersion(versionLine ?? '');
  if (!version || version.major !== 3 || !pathLine) return null;
  return { command, path: pathLine, version: `${version.major}.${version.minor}.${version.patch}`, major: version.major, minor: version.minor, minorName: `${version.major}.${version.minor}` };
}

function realOrSame(path: string): string {
  try { return realpathSync(path); } catch { return path; }
}

/**
 * Every different Python 3 on this computer: the names in PYTHON_CANDIDATES, then `extra` (a path the
 * researcher or `--python` named). Two names for one interpreter count once.
 */
export async function discoverPythons(env: NodeJS.ProcessEnv | undefined, extra: string[] = []): Promise<PythonInfo[]> {
  const found: PythonInfo[] = [];
  const seen = new Set<string>();
  const probes = await Promise.all([...extra, ...PYTHON_CANDIDATES].map((name) => probePython(name, env)));
  for (const info of probes) {
    if (!info) continue;
    const key = realOrSame(info.path);
    if (seen.has(key)) continue;
    seen.add(key);
    found.push(info);
  }
  return found;
}

/**
 * The interpreter to build the venv with: at least `minimum`, and the one the lock file was compiled with when there
 * is one (`lockedMinor`, e.g. "3.10"), else the oldest newer one. `exact` says whether the lock's own minor was found.
 */
export function choosePython(found: PythonInfo[], minimum: string, lockedMinor?: string): { python: PythonInfo; exact: boolean } | null {
  const fit = found.filter((info) => atLeast(info, minimum));
  if (fit.length === 0) return null;
  const exact = lockedMinor ? fit.find((info) => info.minorName === lockedMinor) : undefined;
  if (exact) return { python: exact, exact: true };
  const ordered = [...fit].sort((left, right) => left.major - right.major || left.minor - right.minor);
  return { python: ordered[0] as PythonInfo, exact: false };
}

/** The Python inside a venv: `bin/python`, or `Scripts/python.exe` on Windows. */
export function venvPython(venvDir: string, platform: string = process.platform): string {
  return platform === 'win32' ? join(venvDir, 'Scripts', 'python.exe') : join(venvDir, 'bin', 'python');
}
