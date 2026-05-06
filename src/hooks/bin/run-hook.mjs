#!/usr/bin/env node
/**
 * CLI Runner for Academic Writer TypeScript Hooks
 *
 * Usage: run-hook.mjs <hook-name>
 * Example: run-hook.mjs lifecycle/session-dashboard
 */

import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { existsSync } from 'node:fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const distDir = join(__dirname, '..', 'dist');

function getBundleName(hookName) {
  const prefix = hookName.split('/')[0];
  const bundleMap = {
    lifecycle: 'lifecycle',
  };
  return bundleMap[prefix] ?? null;
}

async function loadBundle(hookName) {
  const bundleName = getBundleName(hookName);
  if (!bundleName) return null;
  const bundlePath = join(distDir, `${bundleName}.mjs`);
  if (!existsSync(bundlePath)) return null;
  return await import(bundlePath);
}

function normalizeInput(input) {
  if (!input.tool_input && input.toolInput) {
    input.tool_input = input.toolInput;
  }
  if (!input.tool_input) {
    input.tool_input = {};
  }
  input.tool_name = input.tool_name ?? input.toolName ?? '';
  input.session_id = input.session_id ?? input.sessionId ?? process.env.CLAUDE_SESSION_ID ?? '';
  input.project_dir = input.project_dir ?? input.projectDir ?? process.env.CLAUDE_PROJECT_DIR ?? '.';
  return input;
}

const hookName = process.argv[2];

if (!hookName) {
  console.log('{"continue":true,"suppressOutput":true}');
  process.exit(0);
}

// Guard: skip all hooks if .academic-helper/ doesn't exist in the project dir
const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
const academicHelperDir = join(projectDir, '.academic-helper');
if (!existsSync(academicHelperDir)) {
  console.log('{"continue":true,"suppressOutput":true}');
  process.exit(0);
}

let hooks;
try {
  hooks = await loadBundle(hookName);
} catch {
  console.log('{"continue":true,"suppressOutput":true}');
  process.exit(0);
}

if (!hooks) {
  console.log('{"continue":true,"suppressOutput":true}');
  process.exit(0);
}

const hookFn = hooks.hooks?.[hookName];

if (!hookFn) {
  console.log('{"continue":true,"suppressOutput":true}');
  process.exit(0);
}

let input = '';
let stdinClosed = false;

const timeout = setTimeout(() => {
  if (!stdinClosed) {
    stdinClosed = true;
    runHook(normalizeInput({}));
  }
}, 100);

process.stdin.setEncoding('utf8');

process.stdin.on('data', (chunk) => {
  clearTimeout(timeout);
  input += chunk;
});

process.stdin.on('end', () => {
  clearTimeout(timeout);
  if (!stdinClosed) {
    stdinClosed = true;
    try {
      const parsedInput = input.trim() ? JSON.parse(input) : {};
      runHook(normalizeInput(parsedInput));
    } catch (err) {
      console.log(JSON.stringify({
        continue: true,
        systemMessage: `Hook input parse error: ${err.message}`,
      }));
    }
  }
});

process.stdin.on('error', () => {
  clearTimeout(timeout);
  if (!stdinClosed) {
    stdinClosed = true;
    runHook(normalizeInput({}));
  }
});

async function runHook(parsedInput) {
  try {
    const result = await hookFn(parsedInput);
    console.log(JSON.stringify(result));
  } catch (err) {
    console.log(JSON.stringify({
      continue: true,
      systemMessage: `Hook error (${hookName}): ${err.message}`,
    }));
  }
}
