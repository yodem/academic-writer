import { appendFileSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { projectDir, projectDirOr } from './paths.ts';
import thresholds from '../../thresholds.json' with { type: 'json' };

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
    // A run killed mid-write leaves a line without its newline; start on a fresh line so both stay readable.
    const torn = existsSync(file) && (() => { const text = readFileSync(file, 'utf8'); return text.length > 0 && !text.endsWith('\n'); })();
    appendFileSync(file, `${torn ? '\n' : ''}${JSON.stringify(event)}\n`, 'utf8');
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

/** Ends a run as failed when `fn` throws, then rethrows. The reason is a fixed word: an error message may quote the article. */
export async function endRunOnError<T>(runId: string, flow: ActivityFlow, fn: () => Promise<T> | T, project?: string): Promise<T> {
  try {
    return await fn();
  } catch (error) {
    startRunOnce(runId, flow, project);
    emit(runId, flow, 'run_end', { exit: 'ERROR', reason: 'command failed' }, project);
    throw error;
  }
}

/** One plain status line for a run, e.g. `write run r1: step 2/6 draft (running)`. A run quiet for longer than the readers' limit is `stalled`. */
export function statusLine(events: ActivityEvent[], runId: string, stalled = false): string {
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
  return `${flow} run ${runId}: step ${index}/${total} ${label} (${stalled ? 'stalled' : 'running'})`.trimEnd();
}

function argValue(argv: string[], name: string): string | undefined {
  const i = argv.indexOf(name);
  return i >= 0 ? argv[i + 1] : undefined;
}

/** The flow a run was started with (its `run_start` event); undefined when the run has not started. */
function startedFlow(runId: string, project: string): ActivityFlow | undefined {
  const file = activityFile(runId, project);
  if (!file || !existsSync(file)) return undefined;
  return readEvents(file).find((e) => e.kind === 'run_start')?.flow;
}

/**
 * The `aw activity start|step|end` subcommands the skills call, so a run shows in the dashboard even when no
 * `aw draft` runs (the short-assignment path). Returns one line for stdout; throws an `ERROR activity: ...` message.
 */
export function runActivityCli(subcommand: string, argv: string[], project: string): string {
  const runId = argValue(argv, '--run-id');
  if (!runId) throw new Error('ERROR activity: --run-id is required');
  if (subcommand === 'start') {
    const flow = argValue(argv, '--flow') as ActivityFlow | undefined;
    if (!flow || !Object.prototype.hasOwnProperty.call(FLOW_STEPS, flow)) throw new Error(`ERROR activity: --flow must be one of ${Object.keys(FLOW_STEPS).join(', ')}`);
    return startRunOnce(runId, flow, project) ? 'started' : 'already started';
  }
  const flow = startedFlow(runId, project);
  if (!flow) throw new Error(`ERROR activity: run ${runId} has no start; run "aw activity start" first`);
  if (subcommand === 'step') {
    const step = argValue(argv, '--step');
    const state = argValue(argv, '--state');
    if (!step || !FLOW_STEPS[flow].includes(step)) throw new Error(`ERROR activity: --step must be one of ${FLOW_STEPS[flow].join(', ')} for ${flow}`);
    if (state !== 'start' && state !== 'end') throw new Error('ERROR activity: --state must be start or end');
    emit(runId, flow, state === 'start' ? 'step_start' : 'step_end', { step }, project);
    return `${step} ${state === 'start' ? 'started' : 'ended'}`;
  }
  if (subcommand === 'end') {
    const exit = argValue(argv, '--exit') ?? 'OK';
    if (exit !== 'OK' && exit !== 'ERROR') throw new Error('ERROR activity: --exit must be OK or ERROR');
    const file = activityFile(runId, project);
    if (file && readEvents(file).some((e) => e.kind === 'run_end')) return 'already ended';
    emit(runId, flow, 'run_end', { exit }, project);
    return 'ended';
  }
  throw new Error(`ERROR activity: unknown subcommand ${subcommand}`);
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

export function activityShow(options: { run?: string; latest?: boolean }, projectArg?: string): string {
  const project = projectArg ?? projectDirOr();
  const runId = options.run ?? (options.latest ? latestRunId(project) : undefined);
  if (!runId) return 'No agent activity yet.';
  const file = activityFile(runId, project);
  if (!file || !existsSync(file)) return `Run ${runId}: no activity yet.`;
  const limitMs = thresholds.activity.activeRunMaxAgeMinutes * 60_000;
  return statusLine(readEvents(file), runId, Date.now() - statSync(file).mtimeMs > limitMs);
}
