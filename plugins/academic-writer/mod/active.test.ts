import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, utimesSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES as HOOK_DEFAULT, findActiveRun } from '../hooks/src/lib/activity.ts';
import { DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES, activeRunMaxAgeMinutes, pickActiveRun, type RunFile } from './active.ts';

const NOW = Date.parse('2026-10-18T12:00:00Z');
const MIN = 60_000;
const ev = (kind: string) => JSON.stringify({ v: 1, run: 'r', flow: 'write', ts: '2026-10-18T10:00:00Z', kind });

const RUNS: Array<{ id: string; text: string; ageMin: number }> = [
  { id: 'old-active', text: [ev('run_start')].join('\n') + '\n', ageMin: 10 },
  { id: 'new-active', text: [ev('run_start'), ev('step_start')].join('\n') + '\n', ageMin: 2 },
  { id: 'finished', text: [ev('run_start'), ev('run_end')].join('\n') + '\n', ageMin: 1 },
  { id: 'stale', text: ev('run_start') + '\n', ageMin: 400 },
  { id: 'no-start', text: ev('step_start') + '\n', ageMin: 1 },
  { id: 'torn', text: ev('run_start') + '\n{"kind":"run_e', ageMin: 5 },
];

function fixture(runs: typeof RUNS): string {
  const dir = mkdtempSync(join(tmpdir(), 'aw-active-'));
  for (const r of runs) {
    mkdirSync(join(dir, '.academic-helper', 'runs', r.id), { recursive: true });
    const file = join(dir, '.academic-helper', 'runs', r.id, 'activity.jsonl');
    writeFileSync(file, r.text);
    const t = (NOW - r.ageMin * MIN) / 1000;
    utimesSync(file, t, t);
  }
  return dir;
}

function modPick(dir: string, max: number): string | undefined {
  const root = join(dir, '.academic-helper', 'runs');
  const files: RunFile[] = readdirSync(root).map((id) => {
    const file = join(root, id, 'activity.jsonl');
    return { id, text: readFileSync(file, 'utf-8'), mtimeMs: statSync(file).mtimeMs };
  });
  return pickActiveRun(files, NOW, max)?.id;
}

test('mod active-run rule matches the hook rule on the same run folders', () => {
  const subsets = [RUNS, RUNS.filter((r) => r.id !== 'new-active'), RUNS.filter((r) => ['finished', 'stale', 'no-start'].includes(r.id))];
  for (const subset of subsets) {
    const dir = fixture(subset);
    try {
      for (const max of [360, 3]) {
        assert.equal(modPick(dir, max), findActiveRun(dir, max, NOW)?.id, `max ${max}, runs ${subset.map((r) => r.id)}`);
      }
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }
});

test('a finished run is not shown when nothing is running', () => {
  const dir = fixture(RUNS.filter((r) => r.id === 'finished'));
  try {
    assert.equal(modPick(dir, 360), undefined);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('max age is read from thresholds.json, with the hook default as fallback', () => {
  const real = readFileSync(join(process.cwd(), '..', 'thresholds.json'), 'utf-8');
  const configured = (JSON.parse(real) as { activity: { activeRunMaxAgeMinutes: number } }).activity.activeRunMaxAgeMinutes;
  assert.equal(activeRunMaxAgeMinutes(real), configured);
  assert.equal(activeRunMaxAgeMinutes('{"activity":{"activeRunMaxAgeMinutes":45}}'), 45);
  assert.equal(activeRunMaxAgeMinutes(undefined), DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES);
  assert.equal(activeRunMaxAgeMinutes('not json'), DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES);
  assert.equal(DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES, HOOK_DEFAULT);
  assert.equal(DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES, configured);
});
