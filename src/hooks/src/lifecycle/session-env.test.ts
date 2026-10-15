import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { sessionEnv } from './session-env.js';

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

test('an omitted PageIndex value is read from the hook command environment', () => {
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
