import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseEvents, viewOf } from './model.ts';

const NOW = new Date('2026-10-18T10:10:00Z');
const row = (o: Record<string, unknown>, flow = 'write') => JSON.stringify({ v: 1, run: 'r1', flow, ...o });

test('write run shows six steps with current hatched', () => {
  const text = [
    row({ ts: '2026-10-18T10:00:00Z', kind: 'run_start' }),
    row({ ts: '2026-10-18T10:00:01Z', kind: 'step_start', step: 'outline' }),
    row({ ts: '2026-10-18T10:01:00Z', kind: 'step_end', step: 'outline' }),
    row({ ts: '2026-10-18T10:01:01Z', kind: 'step_start', step: 'draft' }),
    row({ ts: '2026-10-18T10:02:00Z', kind: 'unit_drafted', unit: 'intro' }),
  ].join('\n');
  const view = viewOf(parseEvents(text), NOW);
  assert.deepEqual(view.steps.map((s) => s.id), ['outline', 'draft', 'audit', 'redraft', 'synthesize', 'word']);
  assert.deepEqual(view.steps.map((s) => s.state), ['done', 'current', 'todo', 'todo', 'todo', 'todo']);
  assert.equal(view.flow, 'write');
  assert.equal(view.elapsedS, 600);
  assert.deepEqual(view.units, [{ id: 'intro', state: 'drafted' }]);
});

test('model ignores unparseable lines', () => {
  const text = [
    row({ ts: '2026-10-18T10:00:00Z', kind: 'run_start' }),
    'not json at all',
    '{"v":1,"kind":',
    JSON.stringify({ kind: 'bogus' }),
    row({ ts: '2026-10-18T10:00:05Z', kind: 'step_start', step: 'outline' }),
    '{"v":1,"run":"r1","flow":"write","kind":"unit_dra',
  ].join('\n');
  const events = parseEvents(text);
  assert.equal(events.length, 2);
  const view = viewOf(events, NOW);
  assert.equal(view.steps[0]?.state, 'current');
  assert.deepEqual(viewOf(parseEvents('garbage'), NOW).steps, []);
});

test('rejection carries reason', () => {
  const text = [
    row({ ts: '2026-10-18T10:00:00Z', kind: 'run_start' }),
    row({ ts: '2026-10-18T10:00:10Z', kind: 'unit_drafted', unit: 'sec-1' }),
    row({ ts: '2026-10-18T10:00:20Z', kind: 'audit_verdict', unit: 'sec-1', paragraph: 2, verdict: 'FAIL', reason: 'citation not in sources.json' }),
    row({ ts: '2026-10-18T10:00:30Z', kind: 'subagent_start', agent: 'auditor' }),
  ].join('\n');
  const view = viewOf(parseEvents(text), NOW);
  assert.deepEqual(view.rejections, [{ unit: 'sec-1', reason: 'citation not in sources.json' }]);
  assert.deepEqual(view.units, [{ id: 'sec-1', state: 'rejected' }]);
  assert.equal(view.agent, 'auditor');
});

test('finished run has no current step', () => {
  const text = [
    row({ ts: '2026-10-18T10:00:00Z', kind: 'run_start' }, 'proofread'),
    row({ ts: '2026-10-18T10:00:01Z', kind: 'step_start', step: 'find' }, 'proofread'),
    row({ ts: '2026-10-18T10:00:02Z', kind: 'step_end', step: 'find' }, 'proofread'),
    row({ ts: '2026-10-18T10:00:03Z', kind: 'subagent_start', agent: 'auditor' }, 'proofread'),
    row({ ts: '2026-10-18T10:00:04Z', kind: 'subagent_stop', agent: 'auditor' }, 'proofread'),
    row({ ts: '2026-10-18T10:05:00Z', kind: 'run_end', exit: 'OK' }, 'proofread'),
  ].join('\n');
  const view = viewOf(parseEvents(text), NOW);
  assert.equal(view.flow, 'proofread');
  assert.deepEqual(view.steps.map((s) => s.id), ['find', 'verify', 'memo', 'apply']);
  assert.ok(view.steps.every((s) => s.state !== 'current'));
  assert.equal(view.agent, null);
  assert.equal(view.elapsedS, 300);
});

test('audit verdicts with a unit mark it passed or rejected; a later PASS does not hide a rejection', () => {
  const text = [
    row({ ts: '2026-10-18T10:00:00Z', kind: 'run_start' }),
    row({ ts: '2026-10-18T10:00:01Z', kind: 'unit_drafted', unit: 'A' }),
    row({ ts: '2026-10-18T10:00:02Z', kind: 'unit_drafted', unit: 'B' }),
    row({ ts: '2026-10-18T10:00:03Z', kind: 'audit_verdict', unit: 'A', paragraph: 0, verdict: 'PASS' }),
    row({ ts: '2026-10-18T10:00:04Z', kind: 'audit_verdict', unit: 'B', paragraph: 0, verdict: 'FAIL', reason: 'FAIL, 1 issues' }),
    row({ ts: '2026-10-18T10:00:05Z', kind: 'audit_verdict', unit: 'B', paragraph: 1, verdict: 'PASS' }),
    row({ ts: '2026-10-18T10:00:06Z', kind: 'audit_verdict', verdict: 'unknown' }),
  ].join('\n');
  const view = viewOf(parseEvents(text), NOW);
  assert.deepEqual(view.units, [{ id: 'A', state: 'passed' }, { id: 'B', state: 'rejected' }]);
});

test('a redraft resets the audit result of its unit', () => {
  const text = [
    row({ ts: '2026-10-18T10:00:00Z', kind: 'run_start' }),
    row({ ts: '2026-10-18T10:00:01Z', kind: 'unit_drafted', unit: 'B' }),
    row({ ts: '2026-10-18T10:00:04Z', kind: 'audit_verdict', unit: 'B', verdict: 'FAIL' }),
    row({ ts: '2026-10-18T10:00:05Z', kind: 'redraft', unit: 'B' }),
    row({ ts: '2026-10-18T10:00:06Z', kind: 'unit_drafted', unit: 'B' }),
    row({ ts: '2026-10-18T10:00:07Z', kind: 'audit_verdict', unit: 'B', verdict: 'PASS' }),
  ].join('\n');
  assert.deepEqual(viewOf(parseEvents(text), NOW).units, [{ id: 'B', state: 'passed' }]);
});

test('a finished run shows skipped for a step that did not happen, never todo; a failed run keeps todo', () => {
  const steps = (exit: string) => viewOf(parseEvents([
    row({ ts: '2026-10-18T10:00:00Z', kind: 'run_start' }),
    row({ ts: '2026-10-18T10:00:01Z', kind: 'step_start', step: 'draft' }),
    row({ ts: '2026-10-18T10:00:02Z', kind: 'step_end', step: 'draft' }),
    row({ ts: '2026-10-18T10:00:03Z', kind: 'step_start', step: 'audit' }),
    row({ ts: '2026-10-18T10:00:04Z', kind: 'step_end', step: 'audit' }),
    row({ ts: '2026-10-18T10:00:05Z', kind: 'step_start', step: 'synthesize' }),
    row({ ts: '2026-10-18T10:00:06Z', kind: 'step_end', step: 'synthesize' }),
    row({ ts: '2026-10-18T10:00:07Z', kind: 'step_start', step: 'word' }),
    row({ ts: '2026-10-18T10:00:08Z', kind: 'step_end', step: 'word' }),
    row({ ts: '2026-10-18T10:00:09Z', kind: 'run_end', exit }),
  ].join('\n')), NOW).steps.map((s) => s.state);
  assert.deepEqual(steps('OK'), ['done', 'done', 'done', 'skipped', 'done', 'done']);
  assert.deepEqual(steps('ERROR'), ['done', 'done', 'done', 'todo', 'done', 'done']);
});

test('edit flows list the single step aw edit emits', () => {
  assert.deepEqual(viewOf(parseEvents(row({ ts: '2026-10-18T10:00:00Z', kind: 'run_start' }, 'edit')), NOW).steps.map((s) => s.id), ['edit']);
});
