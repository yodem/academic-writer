import thresholds from '../../thresholds.json' with { type: 'json' };
import { appendFileSync, mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { projectDir } from './paths.ts';
import { askJev } from './jev.ts';

// thresholds.json > jev.points is the single source of truth for valid Jev
// decision points -- a point that isn't listed there has no configured mode
// and cannot be decided. Deriving the type and the runtime validity check
// from the same object keeps `aw decide` (and every caller of decide())
// from drifting out of sync with the config, as `main.ts`'s previous
// hand-copied `validPoints` array did (it was missing `proofread.risk`).
export type JevPoint = keyof typeof thresholds.jev.points;
const VALID_POINTS = new Set(Object.keys(thresholds.jev.points)) as Set<JevPoint>;
type Mode = 'off' | 'shadow' | 'cascade';
type JevCall = (input: { question: string; options: string[]; context: string }) => Promise<{ answer: string; confidence: number }>;
let jevCall: JevCall | undefined = askJev;
const modeOverrides = new Map<JevPoint, Mode>();
export function __setJev(value: JevCall | undefined): void { jevCall = value; }
export function __setMode(point: JevPoint, mode: Mode): void { modeOverrides.set(point, mode); }
export type DecideRequest = { point: JevPoint; question: string; options: string[]; context: string; runId: string; fallback: () => Promise<string>; label?: string };
export async function decide(req: DecideRequest): Promise<{ answer: string; by: 'jev' | 'model'; confidence: number | null }> {
  const config = thresholds.jev as { threshold: number; points: Record<JevPoint, { mode: Mode }> };
  const mode = modeOverrides.get(req.point) ?? config.points[req.point]?.mode ?? 'off';
  const enabled = Boolean((process.env.JEV_API_KEY ?? '').trim()) || jevCall !== askJev;
  const activeMode = enabled ? mode : 'off';
  let jevResult: { answer: string; confidence: number } | null = null;
  let modelAnswer: string | null = null;
  let answer: string;
  let by: 'jev' | 'model' = 'model';
  if (activeMode === 'off') {
    modelAnswer = await req.fallback(); answer = modelAnswer;
  } else if (activeMode === 'shadow') {
    // Shadow must never affect the model path: a Jev failure is logged as a null answer.
    const [model, jev] = await Promise.all([req.fallback(), (jevCall?.(req) ?? Promise.resolve(null)).catch(() => null)]);
    modelAnswer = model; jevResult = jev; answer = model;
  } else {
    jevResult = await (jevCall?.(req) ?? Promise.resolve(null)).catch(() => null);
    if (jevResult && jevResult.confidence >= config.threshold && req.options.includes(jevResult.answer)) { answer = jevResult.answer; by = 'jev'; }
    else { modelAnswer = await req.fallback(); answer = modelAnswer; }
  }
  const dir = join(projectDir(), '.academic-helper', 'runs', req.runId);
  mkdirSync(dir, { recursive: true });
  appendFileSync(join(dir, 'jev.jsonl'), `${JSON.stringify({ point: req.point, jevAnswer: jevResult?.answer ?? null, jevConfidence: jevResult?.confidence ?? null, modelAnswer, decidedBy: by, label: req.label ?? null })}\n`, 'utf8');
  return { answer, by, confidence: jevResult?.confidence ?? null };
}

// Thin, generic CLI surface over decide(), shared by every `aw decide <point> ...`
// call site (outline.support today; T15 reuses it for other points). `args` is the
// full CLI argument vector with `args[0] === 'decide'` and `args[1]` the point name.
export async function runDecideCli(args: string[]): Promise<{ answer: string; by: 'jev' | 'model'; confidence: number | null }> {
  const value = (name: string): string | undefined => {
    const position = args.indexOf(name);
    return position >= 0 ? args[position + 1] : undefined;
  };
  const pointValue = args[1];
  const question = value('--question');
  const rawOptions = value('--options');
  const contextFile = value('--context-file');
  const fallback = value('--fallback');
  const runIdValue = value('--run');
  const label = value('--label');
  if (!pointValue || !VALID_POINTS.has(pointValue as JevPoint) || !question || !rawOptions || !contextFile || !fallback || !runIdValue) {
    throw new Error('ERROR decide: expected aw decide <point> --question <text> --options a,b --context-file <file> --fallback <answer> --run <id>');
  }
  const options = rawOptions.split(',').map(item => item.trim()).filter(Boolean);
  if (options.length < 2) throw new Error('ERROR decide: --options requires at least two comma-separated answers');
  if (!options.includes(fallback)) throw new Error('ERROR decide: --fallback must match one of --options');
  const context = readFileSync(contextFile, 'utf8');
  return decide({ point: pointValue as JevPoint, question, options, context, runId: runIdValue, fallback: async () => fallback, label });
}
