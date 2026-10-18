// Pure model of one run's activity.jsonl: no Claude Code imports, so it is unit-testable.
// Mirrors src/schemas/activity-event.schema.json. Steps and verdicts only; never article text.

export type ActivityEvent = {
  v: 1;
  ts: string;
  run: string;
  flow: string;
  kind: string;
  step?: string;
  unit?: string;
  paragraph?: number;
  verdict?: string;
  reason?: string;
  agent?: string;
  exit?: string;
};

export type StepState = 'done' | 'current' | 'todo';
export type UnitState = 'drafted' | 'passed' | 'rejected' | 'redrafted';
export type PaneView = {
  flow: string;
  steps: { id: string; state: StepState }[];
  units: { id: string; state: UnitState }[];
  agent: string | null;
  elapsedS: number;
  rejections: { unit: string; reason: string }[];
};

export const FLOW_STEPS: Record<string, string[]> = {
  write: ['outline', 'draft', 'audit', 'redraft', 'synthesize', 'word'],
  edit: ['draft', 'synthesize', 'word'],
  'edit-section': ['draft', 'synthesize', 'word'],
  proofread: ['find', 'verify', 'memo', 'apply'],
  revise: ['read', 'update-draft', 'update-stores'],
};

/** Every line that parses as an event with a string `kind` and `ts`; torn or foreign lines are skipped. */
export function parseEvents(text: string): ActivityEvent[] {
  const events: ActivityEvent[] = [];
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try {
      const row: unknown = JSON.parse(line);
      if (!row || typeof row !== 'object') continue;
      const rec = row as Record<string, unknown>;
      if (typeof rec['kind'] !== 'string' || typeof rec['ts'] !== 'string' || typeof rec['flow'] !== 'string') continue;
      events.push(rec as unknown as ActivityEvent);
    } catch {
      // a half-written last line (run killed mid-write) is skipped
    }
  }
  return events;
}

function unitOf(ev: ActivityEvent): string | undefined {
  if (ev.unit) return ev.unit;
  return typeof ev.paragraph === 'number' ? `¶${ev.paragraph}` : undefined;
}

export function viewOf(events: ActivityEvent[], now: Date): PaneView {
  const first = events[0];
  if (!first) return { flow: 'write', steps: [], units: [], agent: null, elapsedS: 0, rejections: [] };
  const flow = events.find((e) => e.kind === 'run_start')?.flow ?? first.flow;
  const ids = FLOW_STEPS[flow] ?? FLOW_STEPS['write'] ?? [];
  const started = new Set<string>();
  const ended = new Set<string>();
  const units = new Map<string, UnitState>();
  const rejections: { unit: string; reason: string }[] = [];
  let agent: string | null = null;
  let finished = false;
  let endTs: string | null = null;
  for (const ev of events) {
    if (ev.kind === 'step_start' && ev.step) started.add(ev.step);
    else if (ev.kind === 'step_end' && ev.step) ended.add(ev.step);
    else if (ev.kind === 'unit_drafted' && ev.unit) units.set(ev.unit, 'drafted');
    else if (ev.kind === 'redraft' && ev.unit) units.set(ev.unit, 'redrafted');
    else if (ev.kind === 'audit_verdict') {
      const unit = unitOf(ev);
      if (unit && ev.verdict === 'PASS') units.set(unit, 'passed');
      else if (unit && (ev.verdict === 'FAIL' || ev.verdict === 'PARTIAL')) {
        units.set(unit, 'rejected');
        rejections.push({ unit, reason: ev.reason ?? '' });
      }
    } else if (ev.kind === 'subagent_start') agent = ev.agent ?? null;
    else if (ev.kind === 'subagent_stop') agent = null;
    else if (ev.kind === 'run_end') { finished = true; endTs = ev.ts; }
  }
  if (finished) agent = null;
  const steps = ids.map((id) => ({
    id,
    state: (ended.has(id) || (finished && started.has(id)) ? 'done' : started.has(id) && !finished ? 'current' : 'todo') as StepState,
  }));
  const t0 = Date.parse(events.find((e) => e.kind === 'run_start')?.ts ?? first.ts);
  const t1 = endTs ? Date.parse(endTs) : now.getTime();
  const elapsedS = Number.isFinite(t0) && Number.isFinite(t1) ? Math.max(0, Math.round((t1 - t0) / 1000)) : 0;
  return { flow, steps, units: [...units].map(([id, state]) => ({ id, state })), agent, elapsedS, rejections };
}
