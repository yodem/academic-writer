import thresholds from '../../thresholds.json' with { type: 'json' };
import { appendFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { projectDir } from './paths.ts';
import { askJev } from './jev.ts';

export type JevPoint = 'proofread.verify' | 'proofread.triage' | 'proofread.risk' | 'revise.classify' | 'evidence.relevance' | 'outline.support' | 'write.audit_prescreen' | 'write.voice_check' | 'synthesize.needs_bridge' | 'style.filler';
type Mode = 'off' | 'shadow' | 'cascade';
type JevCall = (input: { question: string; options: string[]; context: string }) => Promise<{ answer: string; confidence: number }>;
let jevCall: JevCall | undefined = askJev;
const modeOverrides = new Map<JevPoint, Mode>();
export function __setJev(value: JevCall | undefined): void { jevCall = value; }
export function __setMode(point: JevPoint, mode: Mode): void { modeOverrides.set(point, mode); }
export type DecideRequest = { point: JevPoint; question: string; options: string[]; context: string; runId: string; fallback: () => Promise<string> };
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
  appendFileSync(join(dir, 'jev.jsonl'), `${JSON.stringify({ point: req.point, jevAnswer: jevResult?.answer ?? null, jevConfidence: jevResult?.confidence ?? null, modelAnswer, decidedBy: by })}\n`, 'utf8');
  return { answer, by, confidence: jevResult?.confidence ?? null };
}
