#!/usr/bin/env node
import { build } from 'esbuild';
import { mkdirSync } from 'node:fs';

mkdirSync('./dist', { recursive: true });

await build({
  entryPoints: ['./src/index.ts'],
  outfile: './dist/index.js',
  bundle: true,
  format: 'esm',
  platform: 'node',
  target: 'node20',
  minify: false,
  // dist/index.js is now committed and shipped to users (see .gitignore and
  // scripts/build-mcp.sh) — a sourcemap has zero runtime value there, adds
  // ~380KB of dead weight, and is one more file a repo-privacy scan has to
  // clear. Local debugging can still pass `sourcemap: true` here temporarily.
  sourcemap: false,
  // Fully self-contained bundle: @modelcontextprotocol/sdk and @google/genai are
  // inlined rather than external, so dist/index.js has zero runtime dependency on
  // node_modules being present alongside it (see scripts/check-mcp-dist.sh, which
  // proves this by running dist/index.js alone with no ancestor node_modules).
  // google-auth-library (pulled in via @google/genai) does `require('child_process')`
  // etc. internally; esbuild's ESM output otherwise throws "Dynamic require of
  // ... is not supported" for that. The banner below is the standard fix: it
  // shims a real `require` into the ESM module scope via node:module's
  // createRequire, so those dynamic requires resolve against the bundle's own
  // inlined modules at runtime. (CJS output was also tried instead of this shim;
  // it broke `import.meta.url` resolution used elsewhere in this server, so ESM +
  // shim is what's shipped.)
  external: [],
  loader: { '.md': 'text' },
  banner: {
    js: [
      '#!/usr/bin/env node',
      "import { createRequire as __cr } from 'node:module';",
      'const require = __cr(import.meta.url);',
    ].join('\n'),
  },
});

console.log('Built dist/index.js');
