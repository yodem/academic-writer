import { appendFileSync, existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

/** Same shape as src/schemas/activity-event.schema.json; written by hooks as well as by `aw`. */
export type ActivityKind = 'subagent_start' | 'subagent_stop' | 'audit_verdict' | 'step_start' | 'step_end';
export type ActivityFields = {
  step?: string; unit?: string; paragraph?: number; verdict?: 'PASS' | 'FAIL' | 'PARTIAL' | 'unknown'; reason?: string; agent?: string;
};
export type ActiveRun = { id: string; flow: string; file: string };

export const DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES = 360;

/** thresholds.json `activity.activeRunMaxAgeMinutes`, read from the plugin root; the default when unreadable. */
export function activeRunMaxAgeMinutes(pluginRoot?: string): number {
  const root = pluginRoot ?? process.env['CLAUDE_PLUGIN_ROOT'];
  if (!root) return DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES;
  try {
    const parsed = JSON.parse(readFileSync(join(root, 'thresholds.json'), 'utf-8')) as { activity?: { activeRunMaxAgeMinutes?: unknown } };
    const value = parsed.activity?.activeRunMaxAgeMinutes;
    return typeof value === 'number' && value > 0 ? value : DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES;
  } catch {
    return DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES;
  }
}

function lineKinds(text: string): { flow: string | null; started: boolean; ended: boolean } {
  let flow: string | null = null;
  let started = false;
  let ended = false;
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try {
      const row = JSON.parse(line) as { kind?: unknown; flow?: unknown };
      if (row.kind === 'run_start') { started = true; if (typeof row.flow === 'string') flow = row.flow; }
      if (row.kind === 'run_end') ended = true;
    } catch {
      // a torn line (run killed mid-write) is skipped
    }
  }
  return { flow, started, ended };
}

/** The newest runs/<id>/activity.jsonl with a run_start, no run_end and a recent mtime; null when there is none. */
export function findActiveRun(projectDir: string, maxAgeMinutes: number, now: number = Date.now()): ActiveRun | null {
  const runs = join(projectDir, '.academic-helper', 'runs');
  if (!existsSync(runs)) return null;
  let best: { run: ActiveRun; mtime: number } | null = null;
  let ids: string[];
  try { ids = readdirSync(runs); } catch { return null; }
  for (const id of ids) {
    const file = join(runs, id, 'activity.jsonl');
    try {
      const mtime = statSync(file).mtimeMs;
      if (now - mtime > maxAgeMinutes * 60_000) continue;
      const { flow, started, ended } = lineKinds(readFileSync(file, 'utf-8'));
      if (!started || ended) continue;
      if (!best || mtime > best.mtime) best = { run: { id, flow: flow ?? 'write', file }, mtime };
    } catch {
      // no activity file in this run folder
    }
  }
  return best ? best.run : null;
}

/** Appends one event to the active run. No active run, or any write error: nothing happens and nothing throws. */
export function recordActivity(projectDir: string, kind: ActivityKind, fields: ActivityFields, options: { pluginRoot?: string; now?: number } = {}): boolean {
  try {
    const run = findActiveRun(projectDir, activeRunMaxAgeMinutes(options.pluginRoot), options.now);
    if (!run) return false;
    const reason = fields.reason !== undefined ? fields.reason.slice(0, 300) : undefined;
    const event = { v: 1, ts: new Date(options.now ?? Date.now()).toISOString(), run: run.id, flow: run.flow, kind, ...fields, ...(reason !== undefined ? { reason } : {}) };
    // A run killed mid-write leaves a line without its newline; start on a fresh line so both stay readable.
    const text = readFileSync(run.file, 'utf-8');
    appendFileSync(run.file, `${text.length > 0 && !text.endsWith('\n') ? '\n' : ''}${JSON.stringify(event)}\n`, 'utf-8');
    return true;
  } catch {
    return false;
  }
}
