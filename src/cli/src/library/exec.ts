import { spawn } from 'node:child_process';
import { LibraryError } from './types.ts';

export type RunOptions = { timeoutMs: number; maxBuffer: number; env?: NodeJS.ProcessEnv; cwd?: string };

const STDERR_KEEP = 8192;

/**
 * Run `command` (a word list, never a shell string) with `args` and return its stdout.
 * The promise settles at the deadline even when the process ignores the signal or a grandchild holds the
 * pipe open (a wrapper script that sleeps), so a wedged route can never hold the caller past `timeoutMs`.
 */
export function runCommand(command: string[], args: string[], options: RunOptions): Promise<string> {
  const [file, ...prefix] = command;
  if (!file) return Promise.reject(new LibraryError('config', 'ERROR library: empty command'));
  const label = file.split('/').pop() ?? file;
  return new Promise<string>((resolve, reject) => {
    let settled = false;
    const chunks: Buffer[] = [];
    let size = 0;
    let stderr = '';
    const posix = process.platform !== 'win32';
    const child = spawn(file, [...prefix, ...args], { stdio: ['ignore', 'pipe', 'pipe'], env: options.env, cwd: options.cwd, detached: posix, windowsHide: true });
    const killTree = (): void => {
      try { if (posix && child.pid) process.kill(-child.pid, 'SIGKILL'); else child.kill('SIGKILL'); } catch { try { child.kill('SIGKILL'); } catch { /* already gone */ } }
    };
    const finish = (fn: () => void): void => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      fn();
    };
    const timer = setTimeout(() => {
      finish(() => {
        killTree();
        child.stdout?.destroy();
        child.stderr?.destroy();
        reject(new LibraryError('timeout', `ERROR library: ${label} did not answer within ${options.timeoutMs} ms`));
      });
    }, options.timeoutMs);
    child.stdout?.on('data', (chunk: Buffer) => {
      size += chunk.length;
      if (size > options.maxBuffer) {
        finish(() => { killTree(); reject(new LibraryError('too_large', `ERROR library: ${label} output is larger than ${options.maxBuffer} bytes`)); });
        return;
      }
      chunks.push(chunk);
    });
    child.stderr?.on('data', (chunk: Buffer) => { if (stderr.length < STDERR_KEEP) stderr += chunk.toString('utf8'); });
    child.on('error', (error: NodeJS.ErrnoException) => {
      finish(() => reject(new LibraryError('spawn', error.code === 'ENOENT' ? `ERROR library: command not found: ${file}` : `ERROR library: could not start ${label}: ${error.message}`)));
    });
    child.on('close', (code) => {
      finish(() => {
        if (code === 0) resolve(Buffer.concat(chunks).toString('utf8'));
        else reject(new LibraryError('exit', `ERROR library: ${label} exited with code ${code ?? 'signal'}: ${stderr.trim().slice(0, 300)}`, stderr));
      });
    });
  });
}

/** Split a command setting into words without a shell: whitespace separates, single or double quotes group. */
export function splitCommand(text: string): string[] {
  const words: string[] = [];
  let current = '';
  let quote: '"' | "'" | null = null;
  let started = false;
  for (const char of text) {
    if (quote) {
      if (char === quote) quote = null; else current += char;
    } else if (char === '"' || char === "'") { quote = char; started = true; }
    else if (/\s/u.test(char)) { if (started) { words.push(current); current = ''; started = false; } }
    else { current += char; started = true; }
  }
  if (quote) throw new LibraryError('config', 'ERROR library: unbalanced quote in the command setting');
  if (started) words.push(current);
  return words;
}
