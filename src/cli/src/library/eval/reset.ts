import { existsSync } from 'node:fs';
import { mkdir, rename } from 'node:fs/promises';
import { basename, join } from 'node:path';
import type { EvalPaths } from './files.ts';

/**
 * Start a new generation of an evaluation: move the pairs, the sealed mapping, the judgments, the runs and the reports of
 * the old one into `archive/<time>/` (kept, never deleted). The plan stays. Returns the archive folder, or null when
 * there was nothing to move.
 */
export async function archiveGeneration(paths: EvalPaths, now: Date): Promise<string | null> {
  const parts = [paths.pairs, paths.sealedDir, paths.judgments, paths.runsDir, paths.reportJson, paths.reportMd, paths.judgeHtml].filter((part) => existsSync(part));
  if (parts.length === 0) return null;
  const target = join(paths.archiveDir, now.toISOString().replace(/[:.]/gu, '-'));
  await mkdir(target, { recursive: true });
  for (const part of parts) await rename(part, join(target, basename(part)));
  return target;
}
