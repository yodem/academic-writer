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
