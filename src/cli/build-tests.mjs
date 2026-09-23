#!/usr/bin/env node
// Bundles tests/*.test.ts (and the hook test that exercises the SessionStart key bridge) into
// dist-test/*.test.mjs so `node --test` runs them on any Node >= 20. Plain `node --test *.ts`
// only works on Node versions with type stripping on by default, which this machine's nvm
// Node 22.17 is not. Same pattern as the Gemini server's build-tests.mjs.
import { build } from 'esbuild';
import { readdirSync, mkdirSync, rmSync } from 'node:fs';

rmSync('./dist-test', { recursive: true, force: true });
mkdirSync('./dist-test', { recursive: true });
const entries = readdirSync('./tests').filter((f) => f.endsWith('.test.ts')).map((f) => `./tests/${f}`);
entries.push('../hooks/src/lifecycle/session-env.test.ts');
await build({
  entryPoints: entries, outdir: './dist-test', outExtension: { '.js': '.mjs' }, bundle: true,
  format: 'esm', platform: 'node', target: 'node20', sourcemap: 'inline',
  external: ['@google/genai'], loader: { '.md': 'text' },
});
console.log(`Built ${entries.length} test file(s) into dist-test/`);
