// src/hooks/src/lifecycle/voice-pull.ts
// Pulls AUTHOR_VOICE.md from CandleKeep before write/edit skills run.
// Profile-scoped: silently skips in projects without `.academic-helper/profile.md`.
import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";
import type { HookInput, HookResult } from "../types.js";

export function voicePull(input: HookInput): HookResult {
  const projectDir = input.project_dir ?? process.env["CLAUDE_PROJECT_DIR"] ?? process.cwd();
  if (!existsSync(join(projectDir, ".academic-helper", "profile.md"))) {
    return { continue: true, suppressOutput: true };
  }

  const sync = join(projectDir, "src", "skills", "voice", "voice-sync.sh");
  if (!existsSync(sync)) {
    return { continue: true, suppressOutput: true };
  }

  const r = spawnSync("bash", [sync, "pull"], {
    cwd: projectDir,
    env: { ...process.env, VOICE_PROJECT_ROOT: projectDir },
    encoding: "utf-8",
  });
  if (r.status !== 0) {
    console.warn(`[voice-pull] non-fatal: ${r.stderr}`);
  }
  return { continue: true, suppressOutput: true };
}
