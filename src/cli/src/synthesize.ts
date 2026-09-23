import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { callGemini } from './gemini.ts';
import thresholds from '../../thresholds.json' with { type: 'json' };
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

// Deterministic hint: paragraph openers repeated across the article. Live rehearsal 2026-09-23: 7 units
// opened with "אני טוען כי" and synthesis proposed 0 edits; the model needs the pattern pointed out.
export function repeatedOpeners(units: UnitParagraphs[], words: number, minCount: number): Array<{ opener: string; at: Array<{ unitId: string; paragraphIndex: number }> }> {
  const seen = new Map<string, Array<{ unitId: string; paragraphIndex: number }>>();
  for (const u of units) u.paragraphs.forEach((text, paragraphIndex) => {
    const opener = text.split(/\s+/).slice(0, words).join(' ');
    if (!opener) return;
    seen.set(opener, [...(seen.get(opener) ?? []), { unitId: u.id, paragraphIndex }]);
  });
  return [...seen.entries()].filter(([, at]) => at.length >= minCount).map(([opener, at]) => ({ opener, at }));
}

export function outlineOrder(path: string | undefined): string[] {
  if (!path) return [];
  try {
    const o = JSON.parse(readFileSync(path, 'utf8')) as { units?: Array<{ id: string }>; sections?: Array<{ units?: Array<{ id: string }> }> };
    return (o.units ?? (o.sections ?? []).flatMap((x) => x.units ?? [])).map((u) => u.id);
  } catch { return []; }
}

function outlineContext(path: string | undefined): string {
  if (!path) return '(no outline)';
  try {
    const o = JSON.parse(readFileSync(path, 'utf8')) as { thesis?: string; sections?: Array<{ id: string; title?: string; claim?: string }> };
    return JSON.stringify({ thesis: o.thesis, sections: (o.sections ?? []).map((x) => ({ id: x.id, title: x.title, claim: x.claim })) }, null, 2);
  } catch { return '(no outline)'; }
}

async function realGenerate(units: UnitParagraphs[], runId: string, budget: Budget, outlinePath?: string): Promise<Edit[]> {
  const cfg = thresholds.synthesis as { openerWords: number; repeatedOpenerMin: number };
  const repeats = repeatedOpeners(units, cfg.openerWords, cfg.repeatedOpenerMin);
  const system = fillTemplate(SYNTHESIZE_PROMPT, {
    units: JSON.stringify(units.map((u) => ({ unitId: u.id, paragraphs: u.paragraphs.map((text, paragraphIndex) => ({ paragraphIndex, text })) })), null, 2),
    outline: outlineContext(outlinePath),
    repetition: repeats.length ? JSON.stringify(repeats, null, 2) : '(none)',
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

  // Article order comes from the outline (sections -> units), not from file names: alphabetical order put
  // `conclusion` before `intro` (live rehearsal 2026-09-23). Units missing from the outline keep file order at the end.
  const order = outlineOrder(options.outline);
  const rank = (id: string): number => { const i = order.indexOf(id); return i < 0 ? order.length : i; };
  const units = files.map((file) => ({ id: file.replace(/\.md$/, ''), text: readFileSync(join(dir, file), 'utf8') }))
    .sort((a, b) => rank(a.id) - rank(b.id));
  const unitsWithParagraphs: UnitParagraphs[] = units.map((u) => ({ id: u.id, paragraphs: splitParagraphs(u.text) }));

  const budget = new Budget(options.runId, budgetFor('write'));
  const generate = stubs.gen ?? ((list: UnitParagraphs[]) => realGenerate(list, options.runId, budget, options.outline));
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
