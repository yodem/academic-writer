import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { chmodSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import thresholds from '../../thresholds.json' with { type: 'json' };
import { runLibraryCli } from '../src/library/cli.ts';
import { childEnv, friendlyInstallError, geminiKeyFrom, installPaths, installedCommand, readInstalled, readPinned, resolveHome, runInstall, runUninstall, takeLock, type InstallOptions } from '../src/library/install.ts';
import { choosePython, discoverPythons, parseVersion, venvPython } from '../src/library/python-discovery.ts';
import { LibraryError } from '../src/library/types.ts';
import { setPathArguments } from '../src/paths.ts';

const SECRET = 'AIzaSyFAKEKEYFORTESTS0123456789abcdef';
const COMMIT = thresholds.library.install.pageindexCommit;
// The install lock is an OS advisory lock held by a small real-Python process, so these tests need one real Python 3 (the fake Pythons are node scripts).
const REAL_PYTHON = execFileSync('python3', ['-c', 'import sys; print(sys.executable)'], { encoding: 'utf8' }).trim();

// A fake Python for each version (what `python3.12 -c ...` answers, and what `-m venv` makes) and the fake private Python inside the venv it
// creates (pip, the bootstrap that runs pilib, health). Each call is logged as one JSON line in FAKE_LOG, with which secrets its environment held.
function baseFake(version: string): string {
  return `
const fs = require('node:fs'); const path = require('node:path');
const VERSION = ${JSON.stringify(version)};
const args = process.argv.slice(2);
const log = (extra) => process.env.FAKE_LOG && fs.appendFileSync(process.env.FAKE_LOG, JSON.stringify(Object.assign({ who: 'base-' + VERSION, args, google: process.env.GOOGLE_API_KEY ? 'set' : 'unset', gemini: process.env.GEMINI_API_KEY ? 'set' : 'unset' }, extra || {})) + '\\n');
if (args[0] === '-c' && String(args[1]).includes('fcntl')) { // the install lock: delegate to a real Python
  if (process.env.FAKE_PLANT_VENV && !fs.existsSync(path.join(process.env.FAKE_PLANT_VENV, 'bin', 'python'))) { // another installer finished just before this one got the lock
    fs.mkdirSync(path.join(process.env.FAKE_PLANT_VENV, 'bin'), { recursive: true });
    fs.writeFileSync(path.join(process.env.FAKE_PLANT_VENV, 'bin', 'python'), fs.readFileSync(process.env.FAKE_VENV_SCRIPT, 'utf8').replace('__VERSION__', '3.9.23'), { mode: 0o755 });
  }
  const child = require('node:child_process').spawn(process.env.FAKE_REAL_PYTHON, args, { stdio: 'inherit' });
  child.on('close', (code) => process.exit(code === null ? 1 : code));
} else if (args[0] === '-c') { log(); console.log(VERSION); console.log(process.argv[1]); process.exit(0); }
else if (args[0] === '-m' && args[1] === 'venv') {
  log();
  if (process.env.FAKE_VENV_FAIL) { console.error('No module named venv'); process.exit(1); }
  const dir = args[2]; fs.mkdirSync(path.join(dir, 'bin'), { recursive: true });
  const body = fs.readFileSync(process.env.FAKE_VENV_SCRIPT, 'utf8').replace('__VERSION__', VERSION);
  fs.writeFileSync(path.join(dir, 'bin', 'python'), body, { mode: 0o755 });
  process.exit(0);
}
console.error('unexpected: ' + args.join(' ')); process.exit(2);
`;
}
const VENV_FAKE = `
const fs = require('node:fs');
let args = process.argv.slice(2);
if (args[0] === '-c' && String(args[1]).startsWith('import sys; print(')) { console.log('__VERSION__'); console.log(process.argv[1]); process.exit(0); }
const log = (extra) => process.env.FAKE_LOG && fs.appendFileSync(process.env.FAKE_LOG, JSON.stringify(Object.assign({ who: 'venv', args: args.map((a) => a.length > 200 ? a.slice(0, 40) + '...' : a), google: process.env.GOOGLE_API_KEY ? 'set' : 'unset', gemini: process.env.GEMINI_API_KEY ? 'set' : 'unset', jev: process.env.JEV_API_KEY ? 'set' : 'unset', pipNoInput: process.env.PIP_NO_INPUT || '' }, extra || {})) + '\\n');
if (args[0] === '-c' && args[1] === 'pass') { log(); process.exit(0); }
if (args[0] === '-m' && args[1] === 'pip') {
  log();
  if (process.env.FAKE_PIP_FAIL) { console.error(process.env.FAKE_PIP_FAIL); process.exit(1); }
  process.exit(0);
}
if (args[0] === '-c') { const boot = args[1]; args = args.slice(2); log({ boot: boot.length }); }
if (args[0] === 'health') {
  if (process.env.FAKE_NO_HEALTH) { console.error('boom'); process.exit(1); }
  console.log(JSON.stringify({ ok: true, pilib_version: process.env.FAKE_PILIB_VERSION || '1.0.0', python: '3.12.1', tier: process.env.FAKE_TIER || 'structure', pageindex_commit: null, litellm: '1.83.9', pageindex: process.env.FAKE_TIER !== 'core', weasyprint: process.env.FAKE_TIER !== 'core', library: '/x', books: 0 }));
  process.exit(0);
}
console.error('unexpected: ' + args.join(' ')); process.exit(2);
`;

type Fixture = { root: string; bin: string; pluginRoot: string; data: string; home: string; log: string; env: NodeJS.ProcessEnv; options: (extra?: Partial<InstallOptions>) => InstallOptions; calls: () => Array<Record<string, unknown>>; cleanup: () => void };

function sha(text: string): string { return createHash('sha256').update(text).digest('hex'); }

function writeFake(dir: string, name: string, body: string): string {
  mkdirSync(dir, { recursive: true });
  const file = join(dir, name);
  writeFileSync(file, `#!${process.execPath}\n${body}`, 'utf8');
  chmodSync(file, 0o755);
  return file;
}

/** A plugin folder with its own small pinned requirements, a data folder, and fake Pythons on a PATH of their own. */
function fixture(pythons: string[], extra: Record<string, string> = {}): Fixture {
  const root = mkdtempSync(join(tmpdir(), 'aw-install-'));
  const bin = join(root, 'bin');
  const pluginRoot = join(root, 'plugin');
  const source = join(pluginRoot, 'scripts', 'pageindex');
  mkdirSync(source, { recursive: true });
  const core = '# core\nlitellm==1.83.9 --hash=sha256:aaaa\n';
  const structure = '# structure\nlitellm==1.105.1 --hash=sha256:bbbb\n';
  writeFileSync(join(source, 'requirements-core.txt'), core);
  writeFileSync(join(source, 'requirements-structure.txt'), structure);
  const tier = (file: string, text: string, locked: string, requires: string): Record<string, unknown> => ({ requirements: file, requirements_sha256: sha(text), requires_python: requires, locked_with_python: locked, ...(file.includes('structure') ? { system_libraries: { weasyprint: 'pango', macos: 'brew install pango', debian_ubuntu: 'sudo apt install libpango-1.0-0' } } : {}) });
  writeFileSync(join(source, 'PINNED.json'), JSON.stringify({ schema: 1, pilib_version: '1.0.0', pageindex: { commit: COMMIT }, tiers: { core: tier('requirements-core.txt', core, '3.9', '>=3.9'), structure: tier('requirements-structure.txt', structure, '3.10', '>=3.10') } }));
  const venvScript = writeFake(join(root, 'scripts'), 'venv-python.js', VENV_FAKE);
  for (const version of pythons) {
    const [major, minor] = version.split('.');
    writeFake(bin, `python${major}.${minor}`, baseFake(version));
  }
  const log = join(root, 'calls.log');
  const data = join(root, 'data');
  const env: NodeJS.ProcessEnv = { PATH: bin, HOME: root, FAKE_LOG: log, FAKE_VENV_SCRIPT: venvScript, GOOGLE_API_KEY: SECRET, GEMINI_API_KEY: SECRET, JEV_API_KEY: 'jev-secret-value', FAKE_REAL_PYTHON: REAL_PYTHON, ...extra };
  env.AW_LIBRARY_PASS_ENV = ['FAKE_LOG', 'FAKE_VENV_SCRIPT', 'FAKE_REAL_PYTHON', 'FAKE_TIER', 'FAKE_PILIB_VERSION', 'FAKE_PIP_FAIL', 'FAKE_VENV_FAIL', 'FAKE_NO_HEALTH', 'FAKE_PLANT_VENV'].join(',');
  return {
    root, bin, pluginRoot, data, home: join(data, 'pageindex'), log, env,
    options: (more = {}) => ({ dryRun: false, yes: true, dataDir: data, pluginRoot, env, ...more }),
    calls: () => (existsSync(log) ? readFileSync(log, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line) as Record<string, unknown>) : []),
    cleanup: () => rmSync(root, { recursive: true, force: true }),
  };
}

async function rejects(promise: Promise<unknown>, code: string, pattern?: RegExp): Promise<LibraryError> {
  try { await promise; } catch (error) {
    assert.ok(error instanceof LibraryError, `expected LibraryError, got ${String(error)}`);
    assert.equal(error.code, code, error.message);
    if (pattern) assert.match(error.message, pattern);
    return error;
  }
  assert.fail(`expected a ${code} error`);
}

// ---------------------------------------------------------------- python discovery

test('python discovery finds each interpreter once, whatever it is called, and picks by version and by the lock\'s Python', async () => {
  const fx = fixture(['3.9.23', '3.12.1']);
  try {
    // python3 is the same interpreter as python3.9 under another name
    symlinkSync(join(fx.bin, 'python3.9'), join(fx.bin, 'python3'));
    const found = await discoverPythons(fx.env);
    assert.deepEqual(found.map((info) => info.minorName).sort(), ['3.12', '3.9']);
    assert.deepEqual(parseVersion('3.10.4'), { major: 3, minor: 10, patch: 4 });
    assert.equal(parseVersion('nope'), null);
    const exact = choosePython(found, '3.9', '3.9');
    assert.deepEqual([exact?.python.minorName, exact?.exact], ['3.9', true]);
    const newer = choosePython(found, '3.10', '3.10');
    assert.deepEqual([newer?.python.minorName, newer?.exact], ['3.12', false]);
    assert.equal(choosePython(found, '3.13'), null);
    assert.equal(choosePython([], '3.9'), null);
  } finally { fx.cleanup(); }
});

test('the private Python is bin/python, or Scripts/python.exe on Windows', () => {
  assert.equal(venvPython('/data/pageindex/venv', 'darwin'), join('/data/pageindex/venv', 'bin', 'python'));
  assert.equal(venvPython('/data/pageindex/venv', 'linux'), join('/data/pageindex/venv', 'bin', 'python'));
  assert.equal(venvPython('C:\\data\\venv', 'win32'), join('C:\\data\\venv', 'Scripts', 'python.exe'));
});

// ---------------------------------------------------------------- the install

test('--dry-run shows the plan (tier, Python, size, steps) and changes nothing', async () => {
  const fx = fixture(['3.12.1']);
  try {
    const plan = await runInstall(fx.options({ dryRun: true, yes: false })) as Record<string, any>;
    assert.deepEqual([plan.ok, plan.dry_run, plan.tier, plan.python.version, plan.approx_size_mb, plan.sends_data_to_google], [true, true, 'structure', '3.12.1', thresholds.library.install.approxSizeMb.structure, false]);
    assert.equal(plan.system_library.name, 'pango');
    assert.match(plan.system_library.macos, /brew install pango/);
    assert.ok(plan.steps.length >= 4);
    assert.ok(!existsSync(fx.data), 'nothing was created');
    assert.deepEqual(fx.calls().filter((call) => call.who === 'venv'), []);
  } finally { fx.cleanup(); }
});

test('without --yes the install refuses, says to ask the researcher first, and creates nothing', async () => {
  const fx = fixture(['3.12.1']);
  try {
    const error = await rejects(runInstall(fx.options({ yes: false })), 'usage', /Ask the researcher first, then run it again with --yes/);
    assert.match(error.message, /about 500 MB/);
    assert.ok(!existsSync(fx.data));
  } finally { fx.cleanup(); }
});

test('a core install on Python 3.9: venv, hashed pip install, health, installed.json; no key or secret reaches any child', async () => {
  const fx = fixture(['3.9.23'], { FAKE_TIER: 'core' });
  try {
    const result = await runInstall(fx.options()) as Record<string, any>;
    assert.deepEqual([result.ok, result.action, result.tier, result.degraded], [true, 'installed', 'core', false]);
    assert.match(result.warnings.join(' '), /No Python 3\.10 or newer was found, so only the basic helper is installed/);
    const paths = installPaths(fx.home);
    assert.ok(existsSync(paths.python) && existsSync(paths.library));
    const record = readInstalled(fx.home);
    assert.deepEqual([record?.tier, record?.pageindex_commit, record?.pilib_version, record?.python], ['core', null, '1.0.0', '3.9.23']);
    assert.equal(record?.requirements_sha256, sha(readFileSync(join(fx.pluginRoot, 'scripts', 'pageindex', 'requirements-core.txt'), 'utf8')));
    const pip = fx.calls().find((call) => call.who === 'venv' && (call.args as string[])[1] === 'pip') as { args: string[]; pipNoInput: string };
    assert.deepEqual(pip.args.slice(0, 5), ['-m', 'pip', 'install', '--quiet', '--require-hashes']);
    assert.ok(pip.args.includes('-r') && pip.args[pip.args.indexOf('-r') + 1]?.endsWith('requirements-core.txt'));
    assert.equal(pip.pipNoInput, '1');
    for (const call of fx.calls()) assert.deepEqual([call.google, call.gemini], ['unset', 'unset'], JSON.stringify(call));
    await (await takeLock(paths.lock, REAL_PYTHON, process.env, 'install'))();  // released: it can be taken again
    assert.ok(!readFileSync(fx.log, 'utf8').includes(SECRET) && !JSON.stringify(result).includes(SECRET));
    assert.deepEqual(installedCommand(fx.home, fx.pluginRoot).slice(0, 2), [paths.python, '-c']);
  } finally { fx.cleanup(); }
});

test('the structure tier needs Python 3.10: with 3.12 it installs (and notes the lock\'s Python), with only 3.9 it refuses and offers the basic helper', async () => {
  const modern = fixture(['3.9.23', '3.12.1']);
  const old = fixture(['3.9.23']);
  try {
    const result = await runInstall(modern.options({ tier: 'structure' })) as Record<string, any>;
    assert.deepEqual([result.tier, result.degraded, result.python.version], ['structure', false, '3.12.1']);
    assert.match(result.warnings.join(' '), /locked with Python 3\.10; this computer uses 3\.12/);
    assert.deepEqual([readInstalled(modern.home)?.tier, readInstalled(modern.home)?.pageindex_commit], ['structure', COMMIT]);
    await rejects(runInstall(old.options({ tier: 'structure' })), 'config', /needs Python 3\.10 or newer.*--tier core/s);
    assert.ok(!existsSync(old.data));
    const none = fixture([]);
    try { await rejects(runInstall(none.options({ tier: 'core' })), 'config', /no Python 3\.9 or newer/); }
    finally { none.cleanup(); }
  } finally { modern.cleanup(); old.cleanup(); }
});

test('without --tier the best available tier is chosen: structure when Python 3.10 exists, else core', async () => {
  const modern = fixture(['3.11.4']);
  const old = fixture(['3.9.23'], { FAKE_TIER: 'core' });
  try {
    assert.equal(((await runInstall(modern.options({ dryRun: true, yes: false }))) as Record<string, any>).tier, 'structure');
    assert.equal(((await runInstall(old.options({ dryRun: true, yes: false }))) as Record<string, any>).tier, 'core');
  } finally { modern.cleanup(); old.cleanup(); }
});

test('a structure install whose PDF library does not load is reported as the basic helper, with the system library to install', async () => {
  const fx = fixture(['3.12.1'], { FAKE_TIER: 'core' });
  try {
    const result = await runInstall(fx.options({ tier: 'structure' })) as Record<string, any>;
    assert.deepEqual([result.ok, result.degraded, result.tier], [true, true, 'core']);
    assert.match(result.warnings.join(' '), /WeasyPrint did not load/);
    assert.match(result.warnings.join(' '), /pango/);
    const record = readInstalled(fx.home);
    assert.deepEqual([record?.tier, record?.requested_tier], ['core', 'structure']);
    // asking for the structure tier again is not "already installed": it tries again
    fx.env.FAKE_TIER = 'structure';
    const again = await runInstall(fx.options({ tier: 'structure' })) as Record<string, any>;
    assert.deepEqual([again.action, again.tier, again.degraded], ['installed', 'structure', false]);
  } finally { fx.cleanup(); }
});

test('a second install is a no-op (no pip) until the plugin pins something new', async () => {
  const fx = fixture(['3.12.1']);
  try {
    await runInstall(fx.options());
    const second = await runInstall(fx.options()) as Record<string, any>;
    assert.equal(second.action, 'already_installed');
    assert.equal(fx.calls().filter((call) => call.who === 'venv' && (call.args as string[])[1] === 'pip').length, 1);
    // the plugin now pins another pilib version: the record no longer matches, so pip runs again
    const pinnedFile = join(fx.pluginRoot, 'scripts', 'pageindex', 'PINNED.json');
    writeFileSync(pinnedFile, readFileSync(pinnedFile, 'utf8').replace('"pilib_version":"1.0.0"', '"pilib_version":"1.1.0"'));
    fx.env.FAKE_PILIB_VERSION = '1.1.0';
    const third = await runInstall(fx.options()) as Record<string, any>;
    assert.equal(third.action, 'installed');
    assert.equal(fx.calls().filter((call) => call.who === 'venv' && (call.args as string[])[1] === 'pip').length, 2);
  } finally { fx.cleanup(); }
});

test('a pip failure is one plain sentence, leaves no half install and releases the lock', async () => {
  const cases: Array<[string, RegExp]> = [
    ['ERROR: Could not resolve host: pypi.org', /download did not work.*internet connection/s],
    ['ERROR: THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE', /did not match its expected checksum/],
    ['error: externally-managed-environment', /refuses to install packages by itself/],
    ['ERROR: No matching distribution found for litellm', /no version for this Python/],
  ];
  for (const [text, pattern] of cases) {
    const fx = fixture(['3.12.1'], { FAKE_PIP_FAIL: text });
    try {
      const error = await rejects(runInstall(fx.options()), 'exit', pattern);
      assert.match(error.message, /^ERROR library install: /);
      assert.ok(!existsSync(installPaths(fx.home).installed), 'no record of a half install');
      assert.ok(!existsSync(installPaths(fx.home).venv), 'the new private Python folder is removed');
      await (await takeLock(installPaths(fx.home).lock, REAL_PYTHON, process.env, 'install'))();
    } finally { fx.cleanup(); }
  }
  const noVenv = fixture(['3.12.1'], { FAKE_VENV_FAIL: '1' });
  try { await rejects(runInstall(noVenv.options()), 'exit', /venv module is missing/); }
  finally { noVenv.cleanup(); }
  const noHealth = fixture(['3.12.1'], { FAKE_NO_HEALTH: '1' });
  try { await rejects(runInstall(noHealth.options()), 'exit', /the helper does not start/); }
  finally { noHealth.cleanup(); }
});

test('what the plugin pins is checked: a changed requirements file, a missing or inconsistent PINNED.json are refused before anything is made', async () => {
  const fx = fixture(['3.12.1']);
  try {
    const requirements = join(fx.pluginRoot, 'scripts', 'pageindex', 'requirements-structure.txt');
    writeFileSync(requirements, `${readFileSync(requirements, 'utf8')}evil==1.0\n`);
    await rejects(runInstall(fx.options()), 'config', /does not match the one the plugin pins/);
    const pinnedFile = join(fx.pluginRoot, 'scripts', 'pageindex', 'PINNED.json');
    const original = readFileSync(pinnedFile, 'utf8');
    writeFileSync(pinnedFile, original.replace(COMMIT, 'a'.repeat(40)));
    await rejects(runInstall(fx.options()), 'config', /does not match the plugin settings/);
    writeFileSync(pinnedFile, '{nope');
    await rejects(runInstall(fx.options()), 'config', /no PageIndex helper files/);
    rmSync(pinnedFile);
    assert.throws(() => readPinned(fx.pluginRoot), /no PageIndex helper files/);
    assert.ok(!existsSync(fx.data));
  } finally { fx.cleanup(); }
});

test('one install or uninstall at a time: an OS lock held by another process makes both say busy; a leftover lock file is no lock', async () => {
  const fx = fixture(['3.12.1']);
  try {
    mkdirSync(fx.home, { recursive: true });
    const release = await takeLock(installPaths(fx.home).lock, REAL_PYTHON, process.env, 'install');
    try {
      await rejects(runInstall(fx.options()), 'exit', /another install or uninstall is already running/);
      await rejects(runUninstall({ yes: true, purgeLibrary: false, dataDir: fx.data, env: fx.env }), 'exit', /another install or uninstall is already running/);
    } finally { await release(); }
    // the kernel dropped the lock with the process; the file left behind (even one naming a live pid) blocks nobody
    writeFileSync(installPaths(fx.home).lock, `${process.pid}\n`);
    const result = await runInstall(fx.options()) as Record<string, any>;
    assert.equal(result.action, 'installed');
    const again = await takeLock(installPaths(fx.home).lock, REAL_PYTHON, process.env, 'install');
    await again();
  } finally { fx.cleanup(); }
});

test('uninstall waits for nobody: it takes the same lock as install, so it cannot delete a venv an install is using', async () => {
  const fx = fixture(['3.12.1']);
  try {
    await runInstall(fx.options());
    const release = await takeLock(installPaths(fx.home).lock, REAL_PYTHON, process.env, 'install');
    try { await rejects(runUninstall({ yes: true, purgeLibrary: true, dataDir: fx.data, env: fx.env }), 'exit', /busy|already running/); }
    finally { await release(); }
    assert.ok(existsSync(installPaths(fx.home).venv) && readInstalled(fx.home) !== null, 'nothing was deleted while the lock was held');
    await runUninstall({ yes: true, purgeLibrary: false, dataDir: fx.data, env: fx.env });
    assert.ok(!existsSync(installPaths(fx.home).venv));
  } finally { fx.cleanup(); }
});

test('with no data folder the install says so in plain words', async () => {
  const fx = fixture(['3.12.1']);
  try { await rejects(runInstall(fx.options({ dataDir: null })), 'config', /data folder is not known/); }
  finally { fx.cleanup(); }
  assert.equal(resolveHome({}, null), null);
  assert.equal(resolveHome({ CLAUDE_PLUGIN_DATA: '/d' }, null), join('/d', 'pageindex'));
  assert.equal(resolveHome({ CLAUDE_PLUGIN_DATA: '/d', AW_PAGEINDEX_HOME: '/h/pageindex' }, '/x'), '/h/pageindex');
  assert.equal(resolveHome({ CLAUDE_PLUGIN_DATA: '/d' }, '/x'), join('/x', 'pageindex'));
});

// ---------------------------------------------------------------- uninstall

test('uninstall needs --yes, keeps the indexed books unless asked, and only ever deletes the plugin data folder\'s own pageindex folder', async () => {
  const fx = fixture(['3.12.1']);
  try {
    await runInstall(fx.options());
    writeFileSync(join(installPaths(fx.home).library, 'book.txt'), 'kept');
    await rejects(runUninstall({ yes: false, purgeLibrary: false, dataDir: fx.data, env: fx.env }), 'usage', /Ask the researcher first.*--yes/s);
    assert.ok(existsSync(installPaths(fx.home).venv));
    const kept = await runUninstall({ yes: true, purgeLibrary: false, dataDir: fx.data, env: fx.env }) as Record<string, any>;
    assert.deepEqual(kept.removed.sort(), ['installed.json', 'venv']);
    assert.equal(kept.library_kept, installPaths(fx.home).library);
    assert.ok(existsSync(join(installPaths(fx.home).library, 'book.txt')));
    assert.equal(readInstalled(fx.home), null);
    const purged = await runUninstall({ yes: true, purgeLibrary: true, dataDir: fx.data, env: fx.env }) as Record<string, any>;
    assert.deepEqual([purged.removed, purged.library_kept], [['library'], null]);
    const elsewhere = join(fx.root, 'precious');
    mkdirSync(join(elsewhere, 'venv'), { recursive: true });
    // no data folder to hold it against: refuse, whatever AW_PAGEINDEX_HOME says
    await rejects(runUninstall({ yes: true, purgeLibrary: true, dataDir: null, env: { AW_PAGEINDEX_HOME: join(elsewhere, 'pageindex') } }), 'config', /data folder is not known/);
    // a folder named pageindex somewhere else is not the helper's folder
    mkdirSync(join(elsewhere, 'pageindex', 'venv'), { recursive: true });
    await rejects(runUninstall({ yes: true, purgeLibrary: true, dataDir: fx.data, env: { AW_PAGEINDEX_HOME: join(elsewhere, 'pageindex') } }), 'config', /not the plugin's own helper folder/);
    assert.ok(existsSync(join(elsewhere, 'venv')) && existsSync(join(elsewhere, 'pageindex', 'venv')));
  } finally { fx.cleanup(); }
});

test('uninstall and install refuse a pageindex folder (or private Python folder) that is a symbolic link, and delete nothing through it', async () => {
  const fx = fixture(['3.12.1']);
  try {
    const target = join(fx.root, 'precious');
    mkdirSync(join(target, 'venv'), { recursive: true });
    writeFileSync(join(target, 'installed.json'), '{}');
    mkdirSync(fx.data, { recursive: true });
    symlinkSync(target, join(fx.data, 'pageindex'));
    await rejects(runUninstall({ yes: true, purgeLibrary: true, dataDir: fx.data, env: fx.env }), 'config', /symbolic link/);
    await rejects(runInstall(fx.options()), 'config', /symbolic link/);
    assert.ok(existsSync(join(target, 'venv')) && existsSync(join(target, 'installed.json')));
    // a symbolic link inside the folder: the venv
    rmSync(join(fx.data, 'pageindex'));
    mkdirSync(join(fx.data, 'pageindex'));
    symlinkSync(join(target, 'venv'), join(fx.data, 'pageindex', 'venv'));
    await rejects(runUninstall({ yes: true, purgeLibrary: false, dataDir: fx.data, env: fx.env }), 'config', /symbolic link/);
    assert.ok(lstatSync(join(fx.data, 'pageindex', 'venv')).isSymbolicLink());
    // and a data folder that is itself reached through a link is fine as long as pageindex resolves to <data>/pageindex
    const viaLink = join(fx.root, 'data-link');
    symlinkSync(fx.data, viaLink);
    rmSync(join(fx.data, 'pageindex', 'venv'));
    const ok = await runUninstall({ yes: true, purgeLibrary: false, dataDir: viaLink, env: fx.env }) as Record<string, any>;
    assert.equal(ok.ok, true);
  } finally { fx.cleanup(); }
});

test('an existing private Python too old for the tier is rebuilt with a suitable one: --dry-run says so, --yes needed, the indexed books stay', async () => {
  const fx = fixture(['3.9.23', '3.12.1'], { FAKE_TIER: 'core' });
  try {
    await runInstall(fx.options({ tier: 'core' }));
    assert.equal(readInstalled(fx.home)?.python, '3.9.23');
    writeFileSync(join(installPaths(fx.home).library, 'book.txt'), 'kept');
    fx.env.FAKE_TIER = 'structure';
    const plan = await runInstall(fx.options({ tier: 'structure', dryRun: true, yes: false })) as Record<string, any>;
    assert.equal(plan.rebuild_venv, true);
    assert.match(plan.rebuild_reason, /Python 3\.9\.23.*3\.10/);
    assert.match(plan.warnings.join(' '), /removed and rebuilt/);
    assert.ok(existsSync(installPaths(fx.home).venv), 'a dry run changes nothing');
    await rejects(runInstall(fx.options({ tier: 'structure', yes: false })), 'usage', /--yes/);
    const pips = (): Array<Record<string, any>> => fx.calls().filter((call) => call.who === 'venv' && (call.args as string[])[1] === 'pip');
    const before = pips().length;
    const result = await runInstall(fx.options({ tier: 'structure' })) as Record<string, any>;
    assert.deepEqual([result.action, result.tier, result.rebuild_venv], ['installed', 'structure', true]);
    assert.deepEqual([readInstalled(fx.home)?.python, readInstalled(fx.home)?.tier], ['3.12.1', 'structure']);
    assert.equal(pips().length, before + 1);
    assert.ok(fx.calls().some((call) => call.who === 'base-3.12.1' && (call.args as string[])[1] === 'venv'), 'the new private Python folder was made with Python 3.12');
    assert.equal(readFileSync(join(installPaths(fx.home).library, 'book.txt'), 'utf8'), 'kept');
    // a venv that is already new enough is reused
    const reuse = await runInstall(fx.options({ tier: 'structure', dryRun: true, yes: false })) as Record<string, any>;
    assert.equal(reuse.rebuild_venv, false);
  } finally { fx.cleanup(); }
});

test('the venv check is made again once the lock is held: a venv another installer made in between is judged too, not reused blindly', async () => {
  const fx = fixture(['3.9.23', '3.12.1'], { FAKE_TIER: 'structure' });
  try {
    fx.env.FAKE_PLANT_VENV = installPaths(fx.home).venv;
    // at planning time there is no venv, so the plan says nothing about a rebuild ...
    const plan = await runInstall(fx.options({ tier: 'structure', dryRun: true, yes: false })) as Record<string, any>;
    assert.equal(plan.rebuild_venv, false);
    // ... but by the time this installer holds the lock, a Python 3.9 venv is there
    const result = await runInstall(fx.options({ tier: 'structure' })) as Record<string, any>;
    assert.deepEqual([result.action, result.tier, result.rebuild_venv], ['installed', 'structure', true]);
    assert.match(result.rebuild_reason, /Python 3\.9\.23.*3\.10/);
    assert.equal(readInstalled(fx.home)?.python, '3.12.1', 'the packages went into a venv made with the newer Python');
    assert.ok(fx.calls().some((call) => call.who === 'base-3.12.1' && (call.args as string[])[1] === 'venv'));
  } finally { fx.cleanup(); }
});

test('any failure after the private Python folder exists leaves no half install: unknown health tier, library folder, installed.json', async () => {
  const unknown = fixture(['3.12.1'], { FAKE_TIER: 'read' });
  const noLibrary = fixture(['3.12.1']);
  const noRecord = fixture(['3.12.1']);
  try {
    await rejects(runInstall(unknown.options()), 'exit', /summary helper/);
    assert.ok(!existsSync(installPaths(unknown.home).venv) && readInstalled(unknown.home) === null);
    mkdirSync(noLibrary.home, { recursive: true });
    writeFileSync(installPaths(noLibrary.home).library, 'a file where the library folder should be');
    await assert.rejects(runInstall(noLibrary.options()));
    assert.ok(!existsSync(installPaths(noLibrary.home).venv) && readInstalled(noLibrary.home) === null);
    mkdirSync(join(installPaths(noRecord.home).installed, 'blocker'), { recursive: true });
    await assert.rejects(runInstall(noRecord.options()));
    assert.ok(!existsSync(installPaths(noRecord.home).venv), 'the new private Python folder is removed');
    for (const fx of [unknown, noLibrary, noRecord]) assert.ok(fx.calls().length > 0);
    assert.ok(!existsSync(`${installPaths(noRecord.home).installed}.${process.pid}.tmp`), 'no temp file is left');
  } finally { unknown.cleanup(); noLibrary.cleanup(); noRecord.cleanup(); }
});

// ---------------------------------------------------------------- small pure helpers

test('failures of pip and venv are put in plain words', () => {
  assert.match(friendlyInstallError('x', 'ssl: CERTIFICATE_VERIFY_FAILED'), /certificate problem/);
  assert.match(friendlyInstallError('x', 'OSError: [Errno 28] No space left on device'), /disk is full/);
  assert.match(friendlyInstallError('x', 'PermissionError: [Errno 13] Permission denied'), /permission denied/);
  assert.match(friendlyInstallError('installing the packages', 'something odd\nERROR: weird thing'), /installing the packages did not finish \(ERROR: weird thing\)/);
});

test('the child environment never holds a secret unless the Gemini key is handed over by name', () => {
  const base = { PATH: '/bin', GOOGLE_API_KEY: SECRET, GEMINI_API_KEY: 'other', JEV_API_KEY: 'j', HOME: '/h' };
  assert.deepEqual(childEnv(base), { PATH: '/bin', HOME: '/h' });
  assert.deepEqual(childEnv(base, { gemini: SECRET }), { PATH: '/bin', HOME: '/h', GEMINI_API_KEY: SECRET });
  assert.equal(geminiKeyFrom({ GOOGLE_API_KEY: SECRET }), SECRET);
  assert.equal(geminiKeyFrom({ GEMINI_API_KEY: ' k ' }), 'k');
  assert.equal(geminiKeyFrom({ GOOGLE_API_KEY: '${user_config.google_api_key}' }), null);
  assert.equal(geminiKeyFrom({}), null);
});

// ---------------------------------------------------------------- through `aw library`

async function cli(fx: Fixture, ...argv: string[]): Promise<{ code: number; out: string; err: string }> {
  const saved = { ...process.env };
  let out = '';
  let err = '';
  for (const key of Object.keys(process.env)) delete process.env[key];
  Object.assign(process.env, fx.env, { CLAUDE_PLUGIN_ROOT: fx.pluginRoot, CLAUDE_PLUGIN_DATA: fx.data, CLAUDE_PROJECT_DIR: join(fx.root, 'project') });
  setPathArguments(['--project-dir', join(fx.root, 'project')]);
  try {
    const code = await runLibraryCli(argv, { out: (text) => { out += text; }, err: (text) => { err += text; } });
    return { code, out, err };
  } finally {
    for (const key of Object.keys(process.env)) delete process.env[key];
    Object.assign(process.env, saved);
  }
}

test('aw library install: --dry-run exits 0, no --yes exits 2, --yes installs, status then reports the helper and when it is out of date', async () => {
  const fx = fixture(['3.12.1'], { FAKE_TIER: 'structure' });
  mkdirSync(join(fx.root, 'project', '.academic-helper'), { recursive: true });
  try {
    const dry = await cli(fx, 'install', '--dry-run');
    assert.equal(dry.code, 0, dry.err);
    assert.equal(JSON.parse(dry.out).dry_run, true);
    const refused = await cli(fx, 'install');
    assert.equal(refused.code, 2);
    assert.match(refused.err, /--yes/);
    assert.ok(!existsSync(fx.data));
    const done = await cli(fx, 'install', '--yes', '--tier', 'structure');
    assert.equal(done.code, 0, done.err);
    assert.equal(JSON.parse(done.out).tier, 'structure');
    assert.ok(!done.out.includes(SECRET) && !done.err.includes(SECRET));
    const status = JSON.parse((await cli(fx, 'status')).out) as { pageindex_source: string; installed: { installed: boolean; tier: string; matches_pinned: boolean }; warnings: string[] };
    assert.deepEqual([status.pageindex_source, status.installed.installed, status.installed.tier, status.installed.matches_pinned, status.warnings], ['installed', true, 'structure', true, []]);
    const pinnedFile = join(fx.pluginRoot, 'scripts', 'pageindex', 'PINNED.json');
    writeFileSync(pinnedFile, readFileSync(pinnedFile, 'utf8').replace('"pilib_version":"1.0.0"', '"pilib_version":"2.0.0"'));
    const stale = JSON.parse((await cli(fx, 'status')).out) as { installed: { matches_pinned: boolean }; warnings: string[] };
    assert.equal(stale.installed.matches_pinned, false);
    assert.match(stale.warnings.join(' '), /older than the one this plugin version pins/);
    const nothing = await cli(fx, 'uninstall');
    assert.equal(nothing.code, 2);
    const gone = await cli(fx, 'uninstall', '--yes');
    assert.equal(gone.code, 0, gone.err);
    assert.equal(JSON.parse((await cli(fx, 'status')).out).pageindex_source, 'default');
  } finally { fx.cleanup(); }
});
