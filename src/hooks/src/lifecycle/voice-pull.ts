// src/hooks/src/lifecycle/voice-pull.ts
// Pulls AUTHOR_VOICE.md from Trove before write/edit skills run.
// Profile-scoped: silently skips in projects without `.academic-helper/profile.md`.
import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";
import type { HookInput, HookResult } from "../types.js";

const BASE = new Set(["PATH", "HOME", "USER", "LOGNAME", "LANG", "LANGUAGE", "TMPDIR", "TEMP", "TMP", "TERM", "SHELL", "TZ", "SSH_AUTH_SOCK"]);
const SECRET = /(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)/i;
/** The bash script runs `aw voice pull`, which only talks to Trove: base names, Trove's own variables and the plugin's non-secret ones; no model keys. */
export function voicePullEnv(env: NodeJS.ProcessEnv, projectDir: string): NodeJS.ProcessEnv {
  const out: NodeJS.ProcessEnv = {};
  for (const [name, value] of Object.entries(env)) {
    if (value === undefined) continue;
    const ok = BASE.has(name) || name.startsWith("LC_") || name.startsWith("XDG_")
      || ["TROVE_", "CANDLEKEEP_", "CK_"].some((p) => name.startsWith(p))
      || ((name.startsWith("AW_") || name.startsWith("CLAUDE_")) && !SECRET.test(name));
    if (ok) out[name] = value;
  }
  out["VOICE_PROJECT_ROOT"] = projectDir;
  return out;
}

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

  const r = spawnSync("bash", [sync, "pull"], {
    cwd: projectDir,
    env: voicePullEnv(process.env, projectDir),
    encoding: "utf-8",
  });
  if (r.status !== 0) {
    console.warn(`[voice-pull] non-fatal: ${r.stderr}`);
  }
  return { continue: true, suppressOutput: true };
}
