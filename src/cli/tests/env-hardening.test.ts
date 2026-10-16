import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chmodSync, existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { allowedEnv } from '../src/library/backends.ts';
import { setPathArguments } from '../src/paths.ts';
import { voiceSync, __setDataDir } from '../src/voice.ts';
import { voicePullEnv } from '../../hooks/src/lifecycle/voice-pull.ts';

const SECRETS = { GEMINI_API_KEY: 'g', GOOGLE_API_KEY: 'g2', OPENAI_API_KEY: 'o', ANTHROPIC_API_KEY: 'a', ANTHROPIC_AUTH_TOKEN: 't', OPENROUTER_API_KEY: 'r',
  CLAUDE_PLUGIN_OPTION_GOOGLE_API_KEY: 'p', AW_JEV_API_KEY: 'j', GITHUB_TOKEN: 'x' };
const BASE = { PATH: '/bin', HOME: '/h', LANG: 'C' };

test('script kind keeps interpreter and plugin variables, never a model key', () => {
  const env = allowedEnv({ ...BASE, ...SECRETS, PYTHONPATH: '/p', VIRTUAL_ENV: '/v', CLAUDE_PLUGIN_ROOT: '/r', CLAUDE_PROJECT_DIR: '/d', AW_FIXED_NOW: 'n' }, 'script');
  assert.deepEqual(Object.keys(env).sort(), ['AW_FIXED_NOW', 'CLAUDE_PLUGIN_ROOT', 'CLAUDE_PROJECT_DIR', 'HOME', 'LANG', 'PATH', 'PYTHONPATH', 'VIRTUAL_ENV']);
});

test('pi kind gets the OpenRouter key and no other model key', () => {
  const env = allowedEnv({ ...BASE, ...SECRETS, PI_HOME: '/pi' }, 'pi');
  assert.deepEqual(Object.keys(env).sort(), ['HOME', 'LANG', 'OPENROUTER_API_KEY', 'PATH', 'PI_HOME']);
});

test('the hook environment for voice pull keeps Trove variables and drops model keys', () => {
  const env = voicePullEnv({ ...BASE, ...SECRETS, TROVE_TOKEN: 't', CK_API_KEY: 'c', CLAUDE_PLUGIN_ROOT: '/r' }, '/proj');
  assert.deepEqual(Object.keys(env).sort(), ['CK_API_KEY', 'CLAUDE_PLUGIN_ROOT', 'HOME', 'LANG', 'PATH', 'TROVE_TOKEN', 'VOICE_PROJECT_ROOT']);
});

test('voice sync starts trove with the allow-listed environment', () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-env-'));
  const bin = join(root, 'bin'); const dump = join(root, 'env.json');
  require_mkdir(bin);
  writeFileSync(join(bin, 'trove'), `#!/bin/sh\nnode -e 'require("fs").writeFileSync(process.argv[1], JSON.stringify(process.env))' ${JSON.stringify(dump)}\necho '{"items":[]}'\n`);
  chmodSync(join(bin, 'trove'), 0o755);
  const data = join(root, 'data'); require_mkdir(join(data, 'voice'));
  writeFileSync(join(data, 'voice/profile.json'), '{"schemaVersion":1,"voiceVersion":"v"}');
  __setDataDir(data);
  require_mkdir(join(root, 'proj/.academic-helper'));
  writeFileSync(join(root, 'proj/.academic-helper/profile.md'), 'author_key: tester\n');
  setPathArguments(['--data-dir', data, '--project-dir', join(root, 'proj')]);
  const saved = { ...process.env };
  Object.assign(process.env, { PATH: `${bin}:${process.env.PATH ?? ''}`, GEMINI_API_KEY: 'g', OPENAI_API_KEY: 'o', TROVE_TOKEN: 't' });
  try { try { voiceSync('pull'); } catch { /* "no Trove voice store found" is expected */ } } finally {
    for (const k of ['GEMINI_API_KEY', 'OPENAI_API_KEY', 'TROVE_TOKEN']) { if (saved[k] === undefined) delete process.env[k]; }
    process.env.PATH = saved.PATH;
  }
  assert.ok(existsSync(dump), 'trove was started');
  const seen = JSON.parse(readFileSync(dump, 'utf8')) as Record<string, string>;
  assert.equal(seen.TROVE_TOKEN, 't');
  assert.equal(seen.GEMINI_API_KEY, undefined);
  assert.equal(seen.OPENAI_API_KEY, undefined);
});

import { mkdirSync } from 'node:fs';
function require_mkdir(path: string): void { mkdirSync(path, { recursive: true }); }
