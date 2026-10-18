import { readFileSync, writeFileSync } from 'node:fs';
import { callGemini } from './gemini.ts';
import { AwError, Budget, budgetFor } from './ledger.ts';
import { voiceBundle } from './voice.ts';
import thresholds from '../../thresholds.json' with { type: 'json' };
import { emit } from './activity.ts';

export type EditOptions = { textFile: string; instruction: string; language: 'he' | 'en'; runId: string; out?: string; section?: boolean };
const schema = { type: 'object', required: ['revised_text'], properties: { revised_text: { type: 'string' } } };
export async function editText(options: EditOptions): Promise<{ revised_text: string }> {
  const flow = options.section ? 'edit-section' : 'edit';
  emit(options.runId, flow, 'run_start');
  emit(options.runId, flow, 'step_start', { step: 'edit' });
  const original = readFileSync(options.textFile, 'utf8');
  if (!original.trim()) throw new AwError('ERROR', 'edit', 'text file is empty');
  if (!options.instruction.trim()) throw new AwError('ERROR', 'edit', 'instruction is empty');
  const voice = await voiceBundle({ n: thresholds.voice.bundle.exemplars, pairs: thresholds.voice.bundle.pairs, runId: options.runId });
  const system = `You are revising a passage of a scholarly article as its author. Apply only the requested change; preserve citations, footnote markers, and quotations exactly. Match this author's voice.\n<voice_examples>\n${voice.exemplars.map((x) => x.text).join('\n\n')}\n</voice_examples>\n<voice_pairs>\n${JSON.stringify(voice.pairs)}\n</voice_pairs>\nLanguage: ${options.language}\n<existing_text>\n${original}\n</existing_text>\n<edit_instruction>\n${options.instruction}\n</edit_instruction>\nReturn one JSON object with revised_text.`;
  const response = await callGemini({ step: 'edit', system, parts: ['Apply the edit now. Return JSON only.'], responseSchema: schema, runId: options.runId, budget: new Budget(options.runId, budgetFor('write')) });
  const result = response.json as { revised_text?: unknown } | null;
  if (!result || typeof result.revised_text !== 'string') throw new AwError('ERROR', 'edit', 'invalid revised_text response');
  if (options.out) { writeFileSync(options.out, result.revised_text, 'utf8'); emit(options.runId, flow, 'file_written', { step: 'edit', path: options.out }); }
  emit(options.runId, flow, 'step_end', { step: 'edit' });
  emit(options.runId, flow, 'run_end', { exit: 'OK' });
  return { revised_text: result.revised_text };
}
