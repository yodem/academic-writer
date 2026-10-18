import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, utimesSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { draftAll, __stubs as draftStubs } from '../src/draft.js';
import { runProofread, __stubs as proofreadStubs } from '../src/proofread.js';
import { editText } from '../src/edit.js';
import { applyPlan, __setDataDir } from '../src/revise.js';
import { setPathArguments } from '../src/paths.js';
import { activityShow, readEvents, FLOW_STEPS, type ActivityEvent } from '../src/activity.js';
import { FLOW_STEPS as MOD_FLOW_STEPS } from '../../mod/model.ts';
import { subagentStop } from '../../hooks/src/lifecycle/subagent-stop.js';

function fresh(prefix: string): { root: string; project: string } {
  const root = mkdtempSync(join(tmpdir(), prefix));
  const project = join(root, 'proj');
  mkdirSync(join(project, '.academic-helper'), { recursive: true });
  writeFileSync(join(project, '.academic-helper', 'profile.md'), 'profile');
  setPathArguments(['--data-dir', join(root, 'data'), '--project-dir', project]);
  return { root, project };
}
const noVoice = { exemplars: [] as unknown[], pairs: [] as unknown[], rules: '', styleWords: { banned: [{ word: 'ZQBANNEDWORD', replacement: null }], capped: [] as { word: string; maxPer: 'paragraph' | 'chapter'; max: number }[], filler: [] as string[] } };
const runFile = (project: string, run: string): string => join(project, '.academic-helper', 'runs', run, 'activity.jsonl');
const eventsOf = (project: string, run: string): ActivityEvent[] => readEvents(runFile(project, run));

test('no emitted event holds any piece of the article text or the auditor feedback', async () => {
  const { project } = fresh('aw-act-leak-');
  const articles: Record<string, string> = {
    quote: 'כתוב ״משפט ארוך מאוד שאינו מופיע במקורות הנתונים כלל ועיקר״ והמשך',
    cite: 'טענה עם הערה [^qxzjk-secret-key] ועוד מלל מיוחד',
    banned: 'פסקה מיוחדת עם ZQBANNEDWORD בתוכה ועוד מילים',
  };
  const inputs: string[] = [...Object.values(articles)];
  draftStubs({ gen: async (u) => articles[u.id] ?? 'x', evidenceQuotes: ['ציטוט מהמקור'], voice: noVoice });
  await draftAll({ units: [{ id: 'quote', dependsOn: [] }, { id: 'cite', dependsOn: [] }, { id: 'banned', dependsOn: [] }] }, { runId: 'leak' });
  const feedback = '1. The sentence about Maimonides and the unseen wheel is unsourced.\n2. Footnote ZZ-17 page range is wrong.';
  inputs.push(feedback);
  const transcript = join(project, 'agent.jsonl');
  writeFileSync(transcript, `${JSON.stringify({ type: 'user', message: { role: 'user', content: 'unitId: quote\nrunId: leak' } })}\n`);
  const reply = `\`\`\`json\n${JSON.stringify({ results: [{ paragraphIndex: 0, verdict: 'FAIL', feedback, taggedText: null }] })}\n\`\`\``;
  subagentStop({ tool_name: '', session_id: 's', tool_input: {}, project_dir: project, agent_type: 'auditor', last_assistant_message: reply, agent_transcript_path: transcript });
  const events = eventsOf(project, 'leak');
  assert.ok(events.some((e) => e.kind === 'gate' && e.ok === false));
  assert.ok(events.some((e) => e.kind === 'audit_verdict'));
  const dump = events.map((e) => JSON.stringify(e)).join('\n');
  for (const text of inputs) {
    const chars = [...text];
    for (let i = 0; i + 10 <= chars.length; i += 1) {
      const window = chars.slice(i, i + 10).join('');
      assert.ok(!dump.includes(window), `activity.jsonl leaks article text: ${window}`);
    }
  }
});

test('flow step lists agree between aw, the pane model and the dashboard reader', () => {
  const py = spawnSync('python3', ['-I', '-c', 'import importlib.util,json,sys; s=importlib.util.spec_from_file_location("a", sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(json.dumps(m.FLOW_STEPS))', join(process.cwd(), '..', 'scripts', 'activity.py')], { encoding: 'utf8' });
  assert.equal(py.status, 0, py.stderr);
  const fromPython = JSON.parse(py.stdout) as Record<string, string[]>;
  assert.deepEqual(Object.keys(FLOW_STEPS).sort(), ['edit', 'edit-section', 'proofread', 'revise', 'write']);
  assert.deepEqual(MOD_FLOW_STEPS, FLOW_STEPS);
  assert.deepEqual(fromPython, FLOW_STEPS);
});

test('aw draft --flow edit emits only steps its flow lists', async () => {
  const { project } = fresh('aw-act-editsteps-');
  draftStubs({ gen: async (u) => `Body ${u.id}.`, evidenceQuotes: [], voice: noVoice });
  await draftAll({ units: [{ id: 'A', dependsOn: [] }] }, { runId: 'e1', flow: 'edit-section' });
  const steps = eventsOf(project, 'e1').filter((e) => e.step).map((e) => e.step as string);
  assert.ok(steps.length > 0);
  for (const step of steps) assert.ok(FLOW_STEPS['edit-section'].includes(step), step);
});

test('a draft that throws ends the run with ERROR', async () => {
  const { project } = fresh('aw-act-throwd-');
  draftStubs({ gen: async () => { throw new Error('boom'); }, evidenceQuotes: [], voice: noVoice });
  await assert.rejects(draftAll({ units: [{ id: 'A', dependsOn: [] }] }, { runId: 'td' }));
  const last = eventsOf(project, 'td').at(-1);
  assert.equal(last?.kind, 'run_end'); assert.equal(last?.exit, 'ERROR');
  assert.ok(!JSON.stringify(last).includes('boom'));
});

test('an edit that throws ends the run with ERROR', async () => {
  const { project, root } = fresh('aw-act-throwe-');
  const file = join(root, 't.md'); writeFileSync(file, 'text');
  await assert.rejects(editText({ textFile: file, instruction: '', language: 'en', runId: 'te', section: true }));
  const last = eventsOf(project, 'te').at(-1);
  assert.equal(last?.kind, 'run_end'); assert.equal(last?.exit, 'ERROR'); assert.equal(last?.flow, 'edit-section');
});

test('a proofread that throws ends the run with ERROR', async () => {
  const { project, root } = fresh('aw-act-throwp-');
  proofreadStubs({ find: async () => { throw new Error('boom'); }, verify: async () => [], mustCatch: async () => [], memo: async () => '' });
  await assert.rejects(runProofread({ chunks: [{ id: 'c0', index: 0, startLine: 1, endLine: 1, text: 'x' }], runId: 'tp', out: join(root, 'out'), projectDir: project }));
  const last = eventsOf(project, 'tp').at(-1);
  assert.equal(last?.kind, 'run_end'); assert.equal(last?.exit, 'ERROR'); assert.equal(last?.flow, 'proofread');
});

test('a revise apply that throws ends the run with ERROR', async () => {
  const { project, root } = fresh('aw-act-throwr-');
  __setDataDir(join(root, 'data'));
  writeFileSync(join(project, 'a.md'), 'hello');
  await assert.rejects(applyPlan({ runId: 'tr', pluginVersion: '0', items: [{ id: 'i', category: 'text_edit', proposal: { file: 'a.md', before: 'missing anchor', after: 'x' } }] }));
  const last = eventsOf(project, 'tr').at(-1);
  assert.equal(last?.kind, 'run_end'); assert.equal(last?.exit, 'ERROR'); assert.equal(last?.flow, 'revise');
});

test('activity show reports a quiet unfinished run as stalled, a fresh one as running', async () => {
  const { project } = fresh('aw-act-stall-');
  draftStubs({ gen: async (u) => `Body ${u.id}.`, evidenceQuotes: [], voice: noVoice });
  await draftAll({ units: [{ id: 'A', dependsOn: [] }] }, { runId: 's1' });
  assert.match(activityShow({ run: 's1' }), /\(running\)$/);
  const old = new Date(Date.now() - 7 * 3600_000);
  utimesSync(runFile(project, 's1'), old, old);
  assert.match(activityShow({ run: 's1' }), /\(stalled\)$/);
});

test('aw activity show --latest works without --project-dir (CLAUDE_PROJECT_DIR, then cwd)', async () => {
  const { project, root } = fresh('aw-act-cli-');
  draftStubs({ gen: async (u) => `Body ${u.id}.`, evidenceQuotes: [], voice: noVoice });
  await draftAll({ units: [{ id: 'A', dependsOn: [] }] }, { runId: 'c1' });
  const bundle = join(root, 'aw.mjs');
  const built = spawnSync(join(process.cwd(), 'node_modules', '.bin', 'esbuild'), [join(process.cwd(), 'src', 'main.ts'), '--bundle', '--platform=node', '--format=esm', '--target=node20', '--loader:.md=text', `--outfile=${bundle}`, "--banner:js=import { createRequire as __r } from 'node:module'; const require = __r(import.meta.url);"], { encoding: 'utf8' });
  assert.equal(built.status, 0, built.stderr);
  const env = { ...process.env }; delete env['CLAUDE_PROJECT_DIR'];
  const viaEnv = spawnSync('node', [bundle, 'activity', 'show', '--latest'], { encoding: 'utf8', env: { ...env, CLAUDE_PROJECT_DIR: project }, cwd: root });
  assert.equal(viaEnv.status, 0, viaEnv.stderr);
  assert.match(viaEnv.stdout, /^write run c1:/);
  const viaCwd = spawnSync('node', [bundle, 'activity', 'show', '--latest'], { encoding: 'utf8', env, cwd: project });
  assert.equal(viaCwd.status, 0, viaCwd.stderr);
  assert.match(viaCwd.stdout, /^write run c1:/);
});
