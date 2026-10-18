import { appendFileSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { projectDir } from './paths.ts';

export type ActivityFlow = 'write' | 'edit' | 'edit-section' | 'proofread' | 'revise';
export type ActivityKind = 'run_start' | 'run_end' | 'step_start' | 'step_end' | 'unit_drafted' | 'audit_verdict' | 'redraft' | 'gate' | 'file_written' | 'subagent_start' | 'subagent_stop';
export type ActivityEvent = {
  v: 1; ts: string; run: string; flow: ActivityFlow; kind: ActivityKind;
  step?: string; unit?: string; paragraph?: number; verdict?: 'PASS' | 'FAIL' | 'PARTIAL' | 'unknown'; reason?: string;
  gate?: string; ok?: boolean; path?: string; agent?: string; exit?: 'OK' | 'ERROR' | 'CAP_REACHED';
};
export type ActivityFields = Omit<ActivityEvent, 'v' | 'ts' | 'run' | 'flow' | 'kind'>;

/** Fixed step order per flow; the first write step (`outline`) is done by the skill before `aw draft` runs. */
export const FLOW_STEPS: Record<ActivityFlow, string[]> = {
  write: ['outline', 'draft', 'audit', 'redraft', 'synthesize', 'word'],
  proofread: ['find', 'verify', 'memo', 'apply'],
  revise: ['read', 'update-draft', 'update-stores'],
  edit: ['edit'],
  'edit-section': ['edit'],
};

function runsRoot(project?: string): string | undefined {
  if (project) return join(project, '.academic-helper', 'runs');
  try { return join(projectDir(), '.academic-helper', 'runs'); } catch { return undefined; }
}
export function activityFile(runId: string, project?: string): string | undefined {
  const root = runsRoot(project);
  return root ? join(root, runId, 'activity.jsonl') : undefined;
}
export function hasRunStarted(runId: string, project?: string): boolean {
  const file = activityFile(runId, project);
  return file !== undefined && existsSync(file);
}

/** Appends one JSON line. Never throws: a write error goes to stderr. With no project folder known it does nothing. */
export function appendEvent(runId: string, ev: ActivityEvent, project?: string): void {
  try {
    const file = activityFile(runId, project);
    if (!file) return;
    const event = ev.reason !== undefined && ev.reason.length > 300 ? { ...ev, reason: ev.reason.slice(0, 300) } : ev;
    mkdirSync(join(file, '..'), { recursive: true });
    appendFileSync(file, `${JSON.stringify(event)}\n`, 'utf8');
  } catch (error) {
    process.stderr.write(`activity: could not record event (${error instanceof Error ? error.message : 'unknown error'})\n`);
  }
}

/** Builds the event (v, ts, run filled in) and appends it. */
export function emit(runId: string, flow: ActivityFlow, kind: ActivityKind, fields: ActivityFields = {}, project?: string): void {
  appendEvent(runId, { v: 1, ts: new Date().toISOString(), run: runId, flow, kind, ...fields }, project);
}
/** `run_start` only the first time a run has no activity file. Returns true when it wrote one. */
export function startRunOnce(runId: string, flow: ActivityFlow, project?: string): boolean {
  if (hasRunStarted(runId, project)) return false;
  emit(runId, flow, 'run_start', {}, project);
  return true;
}

export function readEvents(file: string): ActivityEvent[] {
  let text: string;
  try { text = readFileSync(file, 'utf8'); } catch { return []; }
  const events: ActivityEvent[] = [];
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try {
      const parsed: unknown = JSON.parse(line);
      if (typeof parsed === 'object' && parsed !== null && 'kind' in parsed) events.push(parsed as ActivityEvent);
    } catch { /* torn line: skipped */ }
  }
  return events;
}

/** One plain status line for a run, e.g. `write run r1: step 2/6 draft (running)`. */
export function statusLine(events: ActivityEvent[], runId: string): string {
  const start = events.find((e) => e.kind === 'run_start') ?? events[0];
  if (!start) return `Run ${runId}: no activity yet.`;
  const flow = start.flow;
  const steps = FLOW_STEPS[flow] ?? [];
  const total = steps.length || 1;
  let current = '';
  for (const e of events) if (e.kind === 'step_start' && e.step) current = e.step;
  const ended = events.find((e) => e.kind === 'run_end');
  const index = Math.max(1, steps.indexOf(current) + 1);
  const label = current || steps[0] || '';
  if (ended) return `${flow} run ${runId}: ${ended.exit && ended.exit !== 'OK' ? `stopped (${ended.exit})` : 'done'}, step ${current ? index : total}/${total} ${label}`.trimEnd();
  return `${flow} run ${runId}: step ${index}/${total} ${label} (running)`.trimEnd();
}

export function latestRunId(project?: string): string | undefined {
  const root = runsRoot(project);
  if (!root || !existsSync(root)) return undefined;
  let best: { id: string; mtime: number } | undefined;
  for (const id of readdirSync(root)) {
    const file = join(root, id, 'activity.jsonl');
    if (!existsSync(file)) continue;
    const mtime = statSync(file).mtimeMs;
    if (!best || mtime > best.mtime) best = { id, mtime };
  }
  return best?.id;
}

export function activityShow(options: { run?: string; latest?: boolean }, project?: string): string {
  const runId = options.run ?? (options.latest ? latestRunId(project) : undefined);
  if (!runId) return 'No agent activity yet.';
  const file = activityFile(runId, project);
  if (!file || !existsSync(file)) return `Run ${runId}: no activity yet.`;
  return statusLine(readEvents(file), runId);
}
