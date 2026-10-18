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
