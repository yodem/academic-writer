// Pure active-run rule for the activity pane. It must give the same answer as `findActiveRun` in
// src/hooks/src/lib/activity.ts (the hooks are bundled and ship without their sources, so the mod cannot import
// it); active.test.ts runs both over the same run folders and fails if they drift. No imports, no Node, no Claude Code.

/** Fallback when thresholds.json is unreadable; same value as the hooks' default and `activity.activeRunMaxAgeMinutes`. */
export const DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES = 360

export type RunFile = { id: string; text: string; mtimeMs: number }

/** `activity.activeRunMaxAgeMinutes` from the text of the plugin's thresholds.json. */
export function activeRunMaxAgeMinutes(thresholdsText: string | undefined): number {
  if (thresholdsText === undefined) return DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES
  try {
    const parsed = JSON.parse(thresholdsText) as { activity?: { activeRunMaxAgeMinutes?: unknown } }
    const value = parsed.activity?.activeRunMaxAgeMinutes
    return typeof value === 'number' && value > 0 ? value : DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES
  } catch {
    return DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES
  }
}

function startedAndEnded(text: string): { started: boolean; ended: boolean } {
  let started = false
  let ended = false
  for (const line of text.split('\n')) {
    if (!line.trim()) continue
    try {
      const row = JSON.parse(line) as { kind?: unknown }
      if (row.kind === 'run_start') started = true
      if (row.kind === 'run_end') ended = true
    } catch {
      // a torn line is skipped
    }
  }
  return { started, ended }
}

/** The newest run with a run_start, no run_end and a recent mtime; undefined when none is active. */
export function pickActiveRun(runs: RunFile[], now: number, maxAgeMinutes: number): RunFile | undefined {
  let best: RunFile | undefined
  for (const run of runs) {
    if (now - run.mtimeMs > maxAgeMinutes * 60_000) continue
    const { started, ended } = startedAndEnded(run.text)
    if (!started || ended) continue
    if (!best || run.mtimeMs > best.mtimeMs) best = run
  }
  return best
}
