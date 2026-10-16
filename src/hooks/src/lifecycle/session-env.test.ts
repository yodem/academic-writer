import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { sessionEnv } from './session-env.js';

test('the Google and Jev keys are read from CLAUDE_PLUGIN_OPTION_*, then the older USER_CONFIG_* names, quoted', () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-session-env-'));
  const names = ['CLAUDE_PLUGIN_OPTION_GOOGLE_API_KEY', 'USER_CONFIG_GOOGLE_API_KEY', 'CLAUDE_PLUGIN_OPTION_JEV_API_KEY', 'USER_CONFIG_JEV_API_KEY'] as const;
  const before = names.map((n) => process.env[n]);
  try {
    mkdirSync(join(root, '.academic-helper'));
    writeFileSync(join(root, '.academic-helper', 'profile.md'), 'profile');
    const envFile = join(root, 'claude.env');
    writeFileSync(envFile, '');
    process.env['CLAUDE_PLUGIN_OPTION_GOOGLE_API_KEY'] = "g'k $HOME; x";
    process.env['USER_CONFIG_GOOGLE_API_KEY'] = 'old';
    process.env['USER_CONFIG_JEV_API_KEY'] = 'jev-old';
    delete process.env['CLAUDE_PLUGIN_OPTION_JEV_API_KEY'];
    sessionEnv(root, envFile, { pageindexCommand: '' });
    assert.equal(readFileSync(envFile, 'utf8'), "export GOOGLE_API_KEY='g'\\''k $HOME; x'\nexport JEV_API_KEY='jev-old'\n");
  } finally {
    names.forEach((n, i) => { const v = before[i]; if (v === undefined) delete process.env[n]; else process.env[n] = v; });
    rmSync(root, { recursive: true, force: true });
  }
});

test('session env appends escaped configured keys only for profiled projects', () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-session-env-'));
  try {
    mkdirSync(join(root, '.academic-helper'));
    writeFileSync(join(root, '.academic-helper', 'profile.md'), 'profile');
    const envFile = join(root, 'claude.env');
    writeFileSync(envFile, 'existing\n');
    sessionEnv(root, envFile, { googleApiKey: "g'key", jevApiKey: 'jev' });
    assert.equal(readFileSync(envFile, 'utf8'), "existing\nexport GOOGLE_API_KEY='g'\\''key'\nexport JEV_API_KEY='jev'\n");
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('an unset option arriving as its literal placeholder is never exported', () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-session-env-'));
  try {
    mkdirSync(join(root, '.academic-helper'));
    writeFileSync(join(root, '.academic-helper', 'profile.md'), 'profile');
    const envFile = join(root, 'claude.env');
    writeFileSync(envFile, '');
    sessionEnv(root, envFile, { googleApiKey: 'real', jevApiKey: '${user_config.jev_api_key}' });
    assert.equal(readFileSync(envFile, 'utf8'), "export GOOGLE_API_KEY='real'\n");
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('the PageIndex command is exported as AW_PAGEINDEX_COMMAND in profiled projects, quoted', () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-session-env-'));
  try {
    mkdirSync(join(root, '.academic-helper'));
    writeFileSync(join(root, '.academic-helper', 'profile.md'), 'profile');
    const envFile = join(root, 'claude.env');
    writeFileSync(envFile, '');
    sessionEnv(root, envFile, { pageindexCommand: ' /path/to/pilib-wrapper --fast ' });
    assert.equal(readFileSync(envFile, 'utf8'), "export AW_PAGEINDEX_COMMAND='/path/to/pilib-wrapper --fast'\n");
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('an unprofiled project, an empty value and a literal placeholder never export the PageIndex command', () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-session-env-'));
  const bare = mkdtempSync(join(tmpdir(), 'aw-session-env-'));
  try {
    mkdirSync(join(root, '.academic-helper'));
    writeFileSync(join(root, '.academic-helper', 'profile.md'), 'profile');
    const envFile = join(root, 'claude.env');
    writeFileSync(envFile, '');
    sessionEnv(root, envFile, { pageindexCommand: '' });
    sessionEnv(root, envFile, { pageindexCommand: '${user_config.pageindex_command}' });
    assert.equal(readFileSync(envFile, 'utf8'), '');
    const bareEnv = join(bare, 'claude.env');
    writeFileSync(bareEnv, '');
    sessionEnv(bare, bareEnv, { pageindexCommand: 'pilib' });
    assert.equal(readFileSync(bareEnv, 'utf8'), '');
  } finally { rmSync(root, { recursive: true, force: true }); rmSync(bare, { recursive: true, force: true }); }
});

test('an omitted PageIndex value is read from CLAUDE_PLUGIN_OPTION_PAGEINDEX_COMMAND, then the older USER_CONFIG_ name', () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-session-env-'));
  const before = process.env['USER_CONFIG_PAGEINDEX_COMMAND'];
  try {
    mkdirSync(join(root, '.academic-helper'));
    writeFileSync(join(root, '.academic-helper', 'profile.md'), 'profile');
    const envFile = join(root, 'claude.env');
    writeFileSync(envFile, '');
    process.env['USER_CONFIG_PAGEINDEX_COMMAND'] = 'pilib';
    sessionEnv(root, envFile, {});
    assert.equal(readFileSync(envFile, 'utf8'), "export AW_PAGEINDEX_COMMAND='pilib'\n");
  } finally {
    if (before === undefined) delete process.env['USER_CONFIG_PAGEINDEX_COMMAND']; else process.env['USER_CONFIG_PAGEINDEX_COMMAND'] = before;
    rmSync(root, { recursive: true, force: true });
  }
});

test('CLAUDE_PLUGIN_OPTION_PAGEINDEX_COMMAND wins over the older USER_CONFIG_ name', () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-session-env-'));
  const before = [process.env['CLAUDE_PLUGIN_OPTION_PAGEINDEX_COMMAND'], process.env['USER_CONFIG_PAGEINDEX_COMMAND']];
  try {
    mkdirSync(join(root, '.academic-helper'));
    writeFileSync(join(root, '.academic-helper', 'profile.md'), 'profile');
    const envFile = join(root, 'claude.env');
    writeFileSync(envFile, '');
    process.env['CLAUDE_PLUGIN_OPTION_PAGEINDEX_COMMAND'] = "/path/to/it's wrapper";
    process.env['USER_CONFIG_PAGEINDEX_COMMAND'] = 'old';
    sessionEnv(root, envFile, {});
    assert.equal(readFileSync(envFile, 'utf8'), "export AW_PAGEINDEX_COMMAND='/path/to/it'\\''s wrapper'\n");
  } finally {
    const names = ['CLAUDE_PLUGIN_OPTION_PAGEINDEX_COMMAND', 'USER_CONFIG_PAGEINDEX_COMMAND'] as const;
    names.forEach((name, i) => { const v = before[i]; if (v === undefined) delete process.env[name]; else process.env[name] = v; });
    rmSync(root, { recursive: true, force: true });
  }
});

test('the built-in PageIndex helper folder is exported as AW_PAGEINDEX_HOME only once installed.json exists, quoted', () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-session-env-'));
  try {
    mkdirSync(join(root, '.academic-helper'));
    writeFileSync(join(root, '.academic-helper', 'profile.md'), 'profile');
    const data = join(root, "data it's");
    mkdirSync(join(data, 'pageindex'), { recursive: true });
    const envFile = join(root, 'claude.env');
    writeFileSync(envFile, '');
    sessionEnv(root, envFile, { pluginData: data });
    assert.equal(readFileSync(envFile, 'utf8'), '', 'not installed: nothing is exported');
    writeFileSync(join(data, 'pageindex', 'installed.json'), '{}');
    sessionEnv(root, envFile, { pluginData: data });
    assert.equal(readFileSync(envFile, 'utf8'), `export AW_PAGEINDEX_HOME='${join(data, 'pageindex').replace(/'/g, "'\\''")}'\n`);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('the helper folder is also exported next to a user-supplied PageIndex command (aw decides which wins), and never in an unprofiled project', () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-session-env-'));
  const bare = mkdtempSync(join(tmpdir(), 'aw-session-env-'));
  try {
    mkdirSync(join(root, '.academic-helper'));
    writeFileSync(join(root, '.academic-helper', 'profile.md'), 'profile');
    mkdirSync(join(root, 'data', 'pageindex'), { recursive: true });
    writeFileSync(join(root, 'data', 'pageindex', 'installed.json'), '{}');
    const envFile = join(root, 'claude.env');
    writeFileSync(envFile, '');
    sessionEnv(root, envFile, { pageindexCommand: 'my-wrapper', pluginData: join(root, 'data') });
    assert.equal(readFileSync(envFile, 'utf8'), `export AW_PAGEINDEX_COMMAND='my-wrapper'\nexport AW_PAGEINDEX_HOME='${join(root, 'data', 'pageindex')}'\n`);
    mkdirSync(join(bare, 'data', 'pageindex'), { recursive: true });
    writeFileSync(join(bare, 'data', 'pageindex', 'installed.json'), '{}');
    const bareEnv = join(bare, 'claude.env');
    writeFileSync(bareEnv, '');
    sessionEnv(bare, bareEnv, { pluginData: join(bare, 'data') });
    assert.equal(readFileSync(bareEnv, 'utf8'), '');
  } finally { rmSync(root, { recursive: true, force: true }); rmSync(bare, { recursive: true, force: true }); }
});

test('an omitted pluginData value is read from CLAUDE_PLUGIN_DATA', () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-session-env-'));
  const before = process.env['CLAUDE_PLUGIN_DATA'];
  try {
    mkdirSync(join(root, '.academic-helper'));
    writeFileSync(join(root, '.academic-helper', 'profile.md'), 'profile');
    mkdirSync(join(root, 'data', 'pageindex'), { recursive: true });
    writeFileSync(join(root, 'data', 'pageindex', 'installed.json'), '{}');
    const envFile = join(root, 'claude.env');
    writeFileSync(envFile, '');
    process.env['CLAUDE_PLUGIN_DATA'] = join(root, 'data');
    sessionEnv(root, envFile, { pageindexCommand: '' });
    assert.equal(readFileSync(envFile, 'utf8'), `export AW_PAGEINDEX_HOME='${join(root, 'data', 'pageindex')}'\n`);
  } finally {
    if (before === undefined) delete process.env['CLAUDE_PLUGIN_DATA']; else process.env['CLAUDE_PLUGIN_DATA'] = before;
    rmSync(root, { recursive: true, force: true });
  }
});
