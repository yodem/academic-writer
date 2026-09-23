import { build } from 'esbuild';
import { mkdir, chmod } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const outfile = fileURLToPath(new URL('../../plugins/academic-writer/bin/aw', import.meta.url));
const entryPoint = fileURLToPath(new URL('./src/main.ts', import.meta.url));
await mkdir(fileURLToPath(new URL('../../plugins/academic-writer/bin/', import.meta.url)), { recursive: true });
await build({ entryPoints: [entryPoint], outfile, bundle: true, platform: 'node', target: 'node20', format: 'esm', banner: { js: '#!/usr/bin/env node' }, loader: { '.md': 'text' } });
await chmod(outfile, 0o755);
