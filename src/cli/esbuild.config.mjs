import { build } from 'esbuild';
import { mkdir, chmod } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const outfile = fileURLToPath(new URL('../../plugins/academic-writer/bin/aw', import.meta.url));
const entryPoint = fileURLToPath(new URL('./src/main.ts', import.meta.url));
await mkdir(fileURLToPath(new URL('../../plugins/academic-writer/bin/', import.meta.url)), { recursive: true });
await build({ entryPoints: [entryPoint], outfile, bundle: true, platform: 'node', target: 'node20', format: 'esm', banner: { js: "#!/usr/bin/env node\n// ESM bundle: give bundled CommonJS deps a real require (else 'Dynamic require of child_process').\nimport { createRequire as __awCreateRequire } from 'node:module'; const require = __awCreateRequire(import.meta.url);" }, loader: { '.md': 'text' } });
await chmod(outfile, 0o755);
