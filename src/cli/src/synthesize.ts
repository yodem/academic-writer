import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { callGemini } from './gemini.ts';
import { decide } from './decide.ts';
import { projectDir } from './paths.ts';
import { AwError, Budget, budgetFor } from './ledger.ts';
import SYNTHESIZE_PROMPT from './prompts/write-synthesize.md';

export type Edit = { unitId: string; paragraphIndex: number; before: string; after: string; reason: string };
type UnitParagraphs = { id: string; paragraphs: string[] };
type GenFn = (units: UnitParagraphs[]) => Promise<Edit[]>;
type Stubs = { gen?: GenFn };
let stubs: Stubs = {};
export function __stubs(value: Stubs): void { stubs = value; }

export type SynthesizeOptions = { runId: string; outline?: string };
export type SynthesizeResult = { edits: Edit[]; applied: number };

const editsSchema = {
  type: 'object',
  required: ['edits'],
  properties: {
    edits: {
      type: 'array',
      items: {
        type: 'object',
        required: ['unitId', 'paragraphIndex', 'before', 'after', 'reason'],
        properties: {
          unitId: { type: 'string' },
          paragraphIndex: { type: 'integer' },
          before: { type: 'string' },
          after: { type: 'string' },
          reason: { type: 'string' },
        },
      },
    },
  },
};

function splitParagraphs(text: string): string[] {
  return text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
}

function fillTemplate(template: string, vars: Record<string, string>): string {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key: string) => vars[key] ?? '');
}

async function realGenerate(units: UnitParagraphs[], runId: string, budget: Budget): Promise<Edit[]> {
  const system = fillTemplate(SYNTHESIZE_PROMPT, {
    units: JSON.stringify(units.map((u) => ({ unitId: u.id, paragraphs: u.paragraphs.map((text, paragraphIndex) => ({ paragraphIndex, text })) })), null, 2),
  });
  const result = await callGemini({ step: 'write.synthesize', system, parts: ['Propose transition edits now. Return JSON only.'], responseSchema: editsSchema, runId, budget });
  const json = result.json as { edits?: Edit[] } | null;
  if (!json || !Array.isArray(json.edits)) throw new AwError('ERROR', 'write.synthesize', 'missing edits array');
  return json.edits;
}

function draftsDir(): string { return join(projectDir(), '.academic-helper', 'drafts'); }

export async function synthesizeAll(options: SynthesizeOptions): Promise<SynthesizeResult> {
  const dir = draftsDir();
  if (!existsSync(dir)) throw new AwError('ERROR', 'write.synthesize', 'no drafts directory — run aw draft first');
  const files = readdirSync(dir).filter((f) => f.endsWith('.md')).sort();
  if (files.length === 0) throw new AwError('ERROR', 'write.synthesize', 'drafts directory is empty');

  const units = files.map((file) => ({ id: file.replace(/\.md$/, ''), text: readFileSync(join(dir, file), 'utf8') }));
  const unitsWithParagraphs: UnitParagraphs[] = units.map((u) => ({ id: u.id, paragraphs: splitParagraphs(u.text) }));

  const budget = new Budget(options.runId, budgetFor('write'));
  const generate = stubs.gen ?? ((list: UnitParagraphs[]) => realGenerate(list, options.runId, budget));
  const proposed = await generate(unitsWithParagraphs);

  const byUnit = new Map(units.map((u) => [u.id, u]));
  const paragraphsByUnit = new Map(units.map((u) => [u.id, splitParagraphs(u.text)]));
  let appliedCount = 0;

  for (const edit of proposed) {
    const unit = byUnit.get(edit.unitId);
    const paragraphs = paragraphsByUnit.get(edit.unitId);
    if (!unit || !paragraphs || edit.paragraphIndex < 0 || edit.paragraphIndex >= paragraphs.length) continue;

    // Jev point synthesize.needs_bridge, per boundary. The fallback is "the
    // synthesize call decides" -- since a candidate edit only exists because
    // the model proposed one, the fallback answer is to apply it.
    const decision = await decide({
      point: 'synthesize.needs_bridge',
      question: 'Does this paragraph boundary need the proposed transition edit?',
      options: ['bridge', 'no-bridge'],
      context: JSON.stringify(edit),
      runId: options.runId,
      fallback: async () => 'bridge',
      label: `${edit.unitId}:${edit.paragraphIndex}`,
    });
    if (decision.answer !== 'bridge') continue;

    // `before` must match the paragraph exactly, or the edit is skipped and
    // reported rather than applied against drifted text (never a whole-
    // article rewrite -- one verified paragraph swap at a time).
    if (paragraphs[edit.paragraphIndex] !== edit.before) continue;

    paragraphs[edit.paragraphIndex] = edit.after;
    appliedCount += 1;
  }

  for (const unit of units) {
    const paragraphs = paragraphsByUnit.get(unit.id);
    if (!paragraphs) continue;
    writeFileSync(join(dir, `${unit.id}.md`), `${paragraphs.join('\n\n')}\n`, 'utf8');
  }

  return { edits: proposed, applied: appliedCount };
}
