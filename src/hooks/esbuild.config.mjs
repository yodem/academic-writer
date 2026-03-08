#!/usr/bin/env node
/**
 * esbuild configuration for Academic Writer hooks
 * Simplified from OrchestKit — only lifecycle bundle needed
 */

import { build } from 'esbuild';
import { writeFileSync, mkdirSync } from 'node:fs';

const entryPoints = {
  lifecycle: './src/entries/lifecycle.ts',
};

const commonBuildOptions = {
  bundle: true,
  format: 'esm',
  platform: 'node',
  target: 'node20',
  minify: true,
  sourcemap: true,
  metafile: true,
  external: [],
};

async function main() {
  mkdirSync('./dist', { recursive: true });

  const startTime = Date.now();
  const stats = {
    generatedAt: new Date().toISOString(),
    buildTimeMs: 0,
    bundles: {},
    totalSize: 0,
  };

  console.log('Building Academic Writer hooks...\n');

  for (const [name, entryPoint] of Object.entries(entryPoints)) {
    const outfile = `./dist/${name}.mjs`;
    const result = await build({
      ...commonBuildOptions,
      entryPoints: [entryPoint],
      outfile,
      banner: {
        js: `// Academic Writer Hooks - ${name} bundle\n// Generated: ${new Date().toISOString()}\n`,
      },
    });

    const outputFile = result.metafile.outputs[`dist/${name}.mjs`];
    stats.bundles[name] = {
      size: outputFile.bytes,
      sizeKB: (outputFile.bytes / 1024).toFixed(2),
    };
    stats.totalSize += outputFile.bytes;

    console.log(`  ${name}.mjs: ${stats.bundles[name].sizeKB} KB`);
  }

  // Also build unified bundle
  const unifiedResult = await build({
    ...commonBuildOptions,
    entryPoints: ['./src/index.ts'],
    outfile: './dist/hooks.mjs',
    banner: {
      js: `// Academic Writer Hooks - Unified Bundle\n// Generated: ${new Date().toISOString()}\n`,
    },
  });

  const unifiedOutput = unifiedResult.metafile.outputs['dist/hooks.mjs'];
  stats.bundles['hooks'] = {
    size: unifiedOutput.bytes,
    sizeKB: (unifiedOutput.bytes / 1024).toFixed(2),
  };

  console.log(`\n  hooks.mjs (unified): ${stats.bundles['hooks'].sizeKB} KB`);

  stats.buildTimeMs = Date.now() - startTime;
  writeFileSync('./dist/bundle-stats.json', JSON.stringify(stats, null, 2));

  console.log(`\nBuild complete in ${stats.buildTimeMs}ms`);
}

main().catch((err) => {
  console.error('Build failed:', err);
  process.exit(1);
});
