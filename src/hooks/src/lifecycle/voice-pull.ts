// src/hooks/src/lifecycle/voice-pull.ts
// Pulls the shared voice store into CLAUDE_PLUGIN_DATA before write/edit skills run.
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

  const pluginRoot = input.plugin_root ?? process.env["CLAUDE_PLUGIN_ROOT"] ?? "";
  const sync = join(pluginRoot, "skills", "voice", "voice-sync.sh");
  if (!existsSync(sync)) {
    return { continue: true, suppressOutput: true };
  }

  const dataDir = process.env["CLAUDE_PLUGIN_DATA"];
  const args = dataDir ? [sync, "pull", dataDir, projectDir] : [sync, "pull"];
  const r = spawnSync("bash", args, {
    cwd: projectDir,
    env: { ...process.env, VOICE_PROJECT_ROOT: projectDir },
    encoding: "utf-8",
  });
  if (r.status !== 0) {
    console.warn(`[voice-pull] non-fatal: ${r.stderr}`);
  }
  return { continue: true, suppressOutput: true };
}
