import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { draftAll, __stubs as draftStubs } from '../src/draft.js';
import { runProofread, __stubs as proofreadStubs } from '../src/proofread.js';
import { setPathArguments } from '../src/paths.js';
import { appendEvent, activityShow, readEvents, type ActivityEvent } from '../src/activity.js';
import { checkSchema, type JsonSchema } from '../src/library/jsonschema.js';
import schema from '../../schemas/activity-event.schema.json' with { type: 'json' };

function fresh(prefix: string): { root: string; project: string } {
  const root = mkdtempSync(join(tmpdir(), prefix));
  const project = join(root, 'proj');
  mkdirSync(project, { recursive: true });
  setPathArguments(['--data-dir', join(root, 'data'), '--project-dir', project]);
  return { root, project };
}
const noVoice = { exemplars: [] as unknown[], pairs: [] as unknown[], rules: '', styleWords: { banned: [] as { word: string; replacement: string | null }[], capped: [] as { word: string; maxPer: 'paragraph' | 'chapter'; max: number }[], filler: [] as string[] } };
const eventsOf = (project: string, run: string): ActivityEvent[] => readEvents(join(project, '.academic-helper', 'runs', run, 'activity.jsonl'));

test('draft emits run_start once and unit_drafted per unit', async () => {
  const { project } = fresh('aw-act-draft-');
  draftStubs({ gen: async (u) => `Body text for ${u.id}.`, evidenceQuotes: [], voice: noVoice });
  const outline = { units: [{ id: 'A', dependsOn: [] }, { id: 'B', dependsOn: ['A'] }] };
  await draftAll(outline, { runId: 'r1' });
  await draftAll(outline, { runId: 'r1', unit: 'B' });
  const events = eventsOf(project, 'r1');
  assert.equal(events.filter((e) => e.kind === 'run_start').length, 1);
  assert.equal(events.find((e) => e.kind === 'run_start')?.flow, 'write');
  assert.deepEqual(events.filter((e) => e.kind === 'unit_drafted').map((e) => e.unit), ['A', 'B', 'B']);
  assert.ok(events.some((e) => e.kind === 'step_start' && e.step === 'draft'));
  assert.ok(events.some((e) => e.kind === 'step_end' && e.step === 'draft'));
});

test('--flow sets the run flow; a redraft with feedback emits redraft', async () => {
  const { project, root } = fresh('aw-act-flow-');
  draftStubs({ gen: async (u) => `Body text for ${u.id}.`, evidenceQuotes: [], voice: noVoice });
  const feedback = join(root, 'fb.txt'); writeFileSync(feedback, 'tighten it');
  await draftAll({ units: [{ id: 'A', dependsOn: [] }] }, { runId: 'r2', flow: 'edit' });
  await draftAll({ units: [{ id: 'A', dependsOn: [] }] }, { runId: 'r2', unit: 'A', feedbackFile: feedback });
  const events = eventsOf(project, 'r2');
  assert.equal(events.find((e) => e.kind === 'run_start')?.flow, 'edit');
  assert.ok(events.some((e) => e.kind === 'redraft' && e.unit === 'A'));
});

test('gate failure emits gate ok=false', async () => {
  const { project } = fresh('aw-act-gate-');
  draftStubs({ gen: async () => 'כתוב ״ציטוט ארוך שאינו מופיע במקור כלל״', evidenceQuotes: ['ציטוט מהמקור'], voice: noVoice });
  await draftAll({ units: [{ id: 'U3', dependsOn: [] }] }, { runId: 'r3' });
  const gate = eventsOf(project, 'r3').find((e) => e.kind === 'gate');
  assert.equal(gate?.ok, false);
  assert.equal(gate?.gate, 'quote-not-in-evidence');
  assert.equal(gate?.unit, 'U3');
});

test('proofread emits four steps in order then run_end', async () => {
  const { project, root } = fresh('aw-act-proof-');
  proofreadStubs({
    find: async (chunk) => [{ id: `f${chunk.index}`, line: chunk.startLine, before: 'x', after: 'y', class: 'typo', meaningRisk: 'low' }],
    verify: async (changes) => changes.map((c) => ({ id: c.id, verdict: 'uphold' as const })),
    mustCatch: async () => [], memo: async () => 'Memo',
  });
  const chunks = [{ id: 'c0', index: 0, startLine: 1, endLine: 1, text: 'x' }];
  await runProofread({ chunks, runId: 'p1', out: join(root, 'out'), projectDir: project });
  const events = eventsOf(project, 'p1');
  assert.deepEqual(events.filter((e) => e.kind === 'step_start').map((e) => e.step), ['find', 'verify', 'memo', 'apply']);
  assert.deepEqual(events.filter((e) => e.kind === 'step_end').map((e) => e.step), ['find', 'verify', 'memo', 'apply']);
  assert.equal(events[0]?.kind, 'run_start');
  assert.equal(events[0]?.flow, 'proofread');
  assert.equal(events[events.length - 1]?.kind, 'run_end');
  assert.equal(events[events.length - 1]?.exit, 'OK');
});

test('events validate against the schema', async () => {
  const { project } = fresh('aw-act-schema-');
  draftStubs({ gen: async (u) => `Body ${u.id}.`, evidenceQuotes: [], voice: noVoice });
  await draftAll({ units: [{ id: 'A', dependsOn: [] }] }, { runId: 's1' });
  const events = eventsOf(project, 's1');
  assert.ok(events.length >= 4);
  for (const event of events) assert.deepEqual(checkSchema(schema as JsonSchema, event), []);
  assert.ok(checkSchema(schema as JsonSchema, { ...events[0], kind: 'nope' }).length > 0);
  assert.ok(checkSchema(schema as JsonSchema, { ...events[0], extra: 1 }).length > 0);
});

test('append failure does not throw', () => {
  const { project } = fresh('aw-act-fail-');
  // runs/<id> exists as a plain file, so the directory cannot be created.
  mkdirSync(join(project, '.academic-helper', 'runs'), { recursive: true });
  writeFileSync(join(project, '.academic-helper', 'runs', 'blocked'), 'x');
  const event: ActivityEvent = { v: 1, ts: new Date().toISOString(), run: 'blocked', flow: 'write', kind: 'run_start' };
  assert.doesNotThrow(() => appendEvent('blocked', event));
  assert.doesNotThrow(() => appendEvent('blocked', event, join(project, 'nope', '\0bad')));
});

test('activity show prints step k/6', async () => {
  fresh('aw-act-show-');
  draftStubs({ gen: async (u) => `Body ${u.id}.`, evidenceQuotes: [], voice: noVoice });
  await draftAll({ units: [{ id: 'A', dependsOn: [] }] }, { runId: 'w1' });
  assert.match(activityShow({ run: 'w1' }), /^write run w1: step 2\/6 draft/);
  assert.match(activityShow({ latest: true }), /step 2\/6/);
  assert.equal(activityShow({ run: 'w1' }).includes('\n'), false);
});
