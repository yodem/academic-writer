import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { chmodSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { discoverPython, isSupportedPythonVersion, pythonEnv, pythonInvocation, requirePython, resetPythonCache } from '../src/python.ts';

// Fake interpreters are POSIX shell scripts; the Windows CI job runs the shell steps separately.
const skip = process.platform === 'win32';

function fakeBin(files: Record<string, string>): string {
  const dir = mkdtempSync(join(tmpdir(), 'aw-python-'));
  for (const [name, version] of Object.entries(files)) {
    // `exit 0` with a version line, or a failing stub (the Microsoft Store python.exe) when version is empty.
    const body = version ? `#!/bin/sh\necho "${version}"\n` : '#!/bin/sh\necho "Python was not found; run without arguments to install from the Microsoft Store" >&2\nexit 9\n';
    writeFileSync(join(dir, name), body);
    chmodSync(join(dir, name), 0o755);
  }
  return dir;
}
// Only the fake directory and a shell on PATH: a real python3 elsewhere must never answer.
function envFor(dir: string): NodeJS.ProcessEnv { return { PATH: dir }; }

afterEach(() => resetPythonCache());

test('version check: Python 3 at or above the minimum only', () => {
  assert.equal(isSupportedPythonVersion('Python 3.12.1'), true);
  assert.equal(isSupportedPythonVersion('Python 3.9.0'), true);
  assert.equal(isSupportedPythonVersion('Python 3.8.10'), false);
  assert.equal(isSupportedPythonVersion('Python 2.7.18'), false);
  assert.equal(isSupportedPythonVersion(''), false);
});

test('python3 absent, python present: python is used', { skip }, () => {
  const dir = fakeBin({ python: 'Python 3.11.4' });
  assert.deepEqual(discoverPython(envFor(dir)), { command: 'python', args: [] });
});

test('the Store stub as python3 is skipped for a working python', { skip }, () => {
  const dir = fakeBin({ python3: '', python: 'Python 3.12.1' });
  assert.deepEqual(discoverPython(envFor(dir)), { command: 'python', args: [] });
});

test('an obsolete python3 is skipped for a supported python', { skip }, () => {
  const dir = fakeBin({ python3: 'Python 3.6.9', python: 'Python 3.12.1' });
  assert.deepEqual(discoverPython(envFor(dir)), { command: 'python', args: [] });
});

test('only the py launcher: py -3', { skip }, () => {
  const dir = fakeBin({ py: 'Python 3.12.1' });
  assert.deepEqual(discoverPython(envFor(dir)), { command: 'py', args: ['-3'] });
});

test('nothing usable: null, and requirePython says so in one plain line', { skip }, () => {
  const dir = fakeBin({ python3: '', python: 'Python 2.7.18' });
  assert.equal(discoverPython(envFor(dir)), null);
  assert.throws(() => requirePython(envFor(dir)), /ERROR python: Python 3\.9 or newer was not found/u);
});

test('the answer is cached per PATH', { skip }, () => {
  const dir = fakeBin({ python3: 'Python 3.12.1' });
  const first = discoverPython(envFor(dir));
  chmodSync(join(dir, 'python3'), 0o000); // would fail a second probe
  assert.equal(discoverPython(envFor(dir)), first);
  const other = fakeBin({ python: 'Python 3.10.0' });
  assert.deepEqual(discoverPython(envFor(other)), { command: 'python', args: [] });
});

test('invocation puts the launcher arguments before the script', { skip }, () => {
  const dir = fakeBin({ py: 'Python 3.12.1' });
  assert.deepEqual(pythonInvocation('/p/s.py', ['--x'], envFor(dir)), { command: 'py', args: ['-3', '/p/s.py', '--x'] });
});

test('spawned Python gets UTF-8 mode', () => {
  const env = pythonEnv({ PATH: '/x', PYTHONUTF8: '0' });
  assert.equal(env.PYTHONUTF8, '1');
  assert.equal(env.PYTHONIOENCODING, 'utf-8');
  assert.equal(env.PATH, '/x');
});
