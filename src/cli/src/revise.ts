import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { callGemini } from './gemini.ts';
import { decide } from './decide.ts';
import { Budget } from './ledger.ts';
import { dataDir, projectDir } from './paths.ts';
import thresholds from '../../thresholds.json' with { type: 'json' };
import { appendVoicePair, writeVoiceStyleWords } from './voice.ts';
import { emit, startRunOnce } from './activity.ts';

export type ReviseCategory = 'text_edit' | 'argument' | 'voice_signal' | 'plugin_defect';
export type ReviseItem = { id: string; category: ReviseCategory; proposal: Record<string, unknown> };
export type RevisePlan = { runId: string; pluginVersion: string; items: ReviseItem[] };
type Confirm = (group: ReviseItem[]) => Promise<boolean>;
let dataOverride: string | undefined;
let confirm: Confirm = async () => false;
export function __setDataDir(value: string): void { dataOverride = value; }
export function __confirm(value: Confirm): void { confirm = value; }
function voiceDir(): string { return dataOverride ?? join(dataDir(), 'voice'); }
function append(file: string, row: unknown): void { mkdirSync(dirname(file), { recursive: true }); appendFileSync(file, `${JSON.stringify(row)}\n`, 'utf8'); }

export async function classify(items: unknown[], runId: string): Promise<{ items: ReviseItem[] }> {
  startRunOnce(runId, 'revise');
  emit(runId, 'revise', 'step_start', { step: 'read' });
  const schema = { type: 'OBJECT', properties: { items: { type: 'ARRAY', items: { type: 'OBJECT', properties: { id: { type: 'STRING' }, category: { type: 'STRING', enum: ['text_edit','argument','voice_signal','plugin_defect'] }, proposal: { type: 'OBJECT' } }, required: ['id','category','proposal'] } } }, required: ['items'] };
  const fallback = async (): Promise<string> => {
    const caps = (thresholds.budget as Record<string, { maxTokens: number; maxUsd: number }>).revise;
    const result = await callGemini({ step: 'revise.classify', system: 'Classify review feedback accurately. Return JSON only.', parts: [JSON.stringify(items)], responseSchema: schema, runId, budget: new Budget(runId, caps) });
    return JSON.stringify(result.json);
  };
  const result = await decide({ point: 'revise.classify', question: 'Classify each Word review item.', options: ['text_edit','argument','voice_signal','plugin_defect'], context: JSON.stringify(items), runId, fallback });
  const parsed: unknown = JSON.parse(result.answer);
  if (typeof parsed !== 'object' || parsed === null || !Array.isArray((parsed as {items?: unknown}).items)) throw new Error('ERROR revise.classify: missing verdict');
  emit(runId, 'revise', 'step_end', { step: 'read' });
  return parsed as {items: ReviseItem[]};
}

function applyTextEdit(item: ReviseItem): void {
  const file = item.proposal.file;
  const before = item.proposal.before;
  const after = item.proposal.after;
  if (typeof file !== 'string' || typeof before !== 'string' || typeof after !== 'string') return;
  const target = join(projectDir(), file);
  const body = readFileSync(target, 'utf8');
  if (!body.includes(before)) throw new Error(`ERROR revise.apply: anchor not found for ${item.id}`);
  writeFileSync(target, body.replace(before, after), 'utf8');
}

export async function applyPlan(plan: RevisePlan): Promise<{ applied: string[]; deferred: string[] }> {
  if (!dataOverride) dataDir();
  const applied: string[] = []; const deferred: string[] = [];
  const feedbackDir = join(dataOverride ?? dataDir(), 'feedback');
  startRunOnce(plan.runId, 'revise');
  emit(plan.runId, 'revise', 'step_start', { step: 'update-draft' });
  for (const item of plan.items) {
    append(join(dataOverride ?? dataDir(), 'labels', 'revise.classify.jsonl'), { point: 'revise.classify', itemId: item.id, label: item.category });
    if (typeof item.proposal.changeId === 'string' && (item.proposal.label === 'uphold' || item.proposal.label === 'refute')) {
      append(join(dataOverride ?? dataDir(), 'labels', 'proofread.verify.jsonl'), { point: 'proofread.verify', changeId: item.proposal.changeId, label: item.proposal.label });
    }
    if (item.category === 'text_edit') { applyTextEdit(item); applied.push(item.id); }
    else if (item.category === 'argument') {
      const file = join(projectDir(), '.academic-helper', 'revise-todo.md');
      mkdirSync(join(projectDir(), '.academic-helper'), { recursive: true });
      appendFileSync(file, `\n- [ ] ${String(item.proposal.text ?? JSON.stringify(item.proposal))}\n`, 'utf8'); deferred.push(item.id);
    } else if (item.category === 'plugin_defect') {
      append(join(feedbackDir, 'ledger.jsonl'), { ts: new Date().toISOString(), runId: plan.runId, step: String(item.proposal.step ?? 'unknown'), item: item.proposal, authorWords: String(item.proposal.authorWords ?? ''), pluginVersion: plan.pluginVersion }); applied.push(item.id);
    } else {
      const accepted = await confirm([item]);
      if (!accepted) { deferred.push(item.id); continue; }
      const dir = voiceDir(); mkdirSync(dir, { recursive: true });
      appendVoicePair({ before: String(item.proposal.before ?? ''), after: String(item.proposal.after ?? ''), source: plan.runId }, dataOverride ?? dataDir());
      if (item.proposal.styleWords !== undefined) writeVoiceStyleWords(item.proposal.styleWords, dataOverride ?? dataDir());
      if (item.proposal.terms !== undefined) writeFileSync(join(projectDir(), '.academic-helper', 'terms.json'), JSON.stringify(item.proposal.terms, null, 2), 'utf8');
      applied.push(item.id);
    }
  }
  emit(plan.runId, 'revise', 'step_end', { step: 'update-draft' });
  emit(plan.runId, 'revise', 'step_start', { step: 'update-stores' });
  emit(plan.runId, 'revise', 'step_end', { step: 'update-stores' });
  emit(plan.runId, 'revise', 'run_end', { exit: 'OK' });
  return { applied, deferred };
}
