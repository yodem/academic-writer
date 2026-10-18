import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, utimesSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { subagentStop } from './subagent-stop.js';
import { subagentStart } from './subagent-start.js';

type Row = { unit?: string; kind: string; run: string; flow: string; verdict?: string; paragraph?: number; reason?: string; agent?: string };

function project(options: { profile?: boolean; run?: 'active' | 'ended' | 'none' | 'old' } = {}): { root: string; file: string } {
  const root = mkdtempSync(join(tmpdir(), 'aw-subagent-stop-'));
  mkdirSync(join(root, '.academic-helper', 'runs', 'r1'), { recursive: true });
  if (options.profile !== false) writeFileSync(join(root, '.academic-helper', 'profile.md'), 'profile');
  const file = join(root, '.academic-helper', 'runs', 'r1', 'activity.jsonl');
  const start = JSON.stringify({ v: 1, ts: '2026-10-18T10:00:00.000Z', run: 'r1', flow: 'write', kind: 'run_start' });
  const end = JSON.stringify({ v: 1, ts: '2026-10-18T10:05:00.000Z', run: 'r1', flow: 'write', kind: 'run_end', exit: 'OK' });
  const run = options.run ?? 'active';
  if (run === 'active' || run === 'old') writeFileSync(file, `${start}\n`);
  if (run === 'ended') writeFileSync(file, `${start}\n${end}\n`);
  if (run === 'old') { const past = new Date(Date.now() - 7 * 3600_000); utimesSync(file, past, past); }
  return { root, file };
}
const rows = (file: string): Row[] => readFileSync(file, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line) as Row);
const auditorReply = (results: unknown): string => `\`\`\`json\n${JSON.stringify({ results })}\n\`\`\``;

process.env['CLAUDE_CODE_ENABLE_FUNCTION_HOOKS'] = '1';
const input = (root: string, extra: Record<string, unknown>) => ({ tool_name: '', session_id: 's', tool_input: {}, project_dir: root, ...extra });

test('auditor JSON yields one verdict per paragraph', () => {
  const { root, file } = project();
  try {
    const reply = auditorReply([
      { paragraphIndex: 1, verdict: 'PASS', feedback: 'Claims verified: 2.', taggedText: 'x' },
      { paragraphIndex: 2, verdict: 'FAIL', feedback: 'a'.repeat(400), taggedText: null },
      { paragraphIndex: 3, verdict: 'PARTIAL', feedback: 'page mismatch', taggedText: null },
    ]);
    const result = subagentStop(input(root, { agent_type: 'academic-writer:auditor', last_assistant_message: reply }));
    assert.equal(result.continue, true);
    const verdicts = rows(file).filter((row) => row.kind === 'audit_verdict');
    assert.deepEqual(verdicts.map((row) => [row.paragraph, row.verdict]), [[1, 'PASS'], [2, 'FAIL'], [3, 'PARTIAL']]);
    // The reason is derived from the verdict, never the auditor's own words.
    assert.deepEqual(verdicts.map((row) => row.reason), [undefined, 'FAIL', 'PARTIAL']);
    assert.equal(rows(file).filter((row) => row.kind === 'subagent_stop').length, 1);
    assert.equal(rows(file)[1]!.run, 'r1');
    assert.equal(rows(file)[1]!.flow, 'write');
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('the reply is read from the agent transcript when last_assistant_message is absent', () => {
  const { root, file } = project();
  try {
    const transcript = join(root, 'agent.jsonl');
    const reply = auditorReply([{ paragraphIndex: 4, verdict: 'PASS', feedback: 'ok', taggedText: 'x' }]);
    writeFileSync(transcript, `${JSON.stringify({ type: 'user', message: { role: 'user', content: 'go' } })}\n${JSON.stringify({ type: 'assistant', message: { role: 'assistant', content: [{ type: 'text', text: reply }] } })}\n`);
    subagentStop(input(root, { agent_type: 'auditor', agent_transcript_path: transcript }));
    assert.deepEqual(rows(file).filter((row) => row.kind === 'audit_verdict').map((row) => [row.paragraph, row.verdict]), [[4, 'PASS']]);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('prose output yields one unknown verdict', () => {
  const { root, file } = project();
  try {
    subagentStop(input(root, { agent_type: 'academic-writer:auditor', last_assistant_message: 'All paragraphs look fine to me.' }));
    const verdicts = rows(file).filter((row) => row.kind === 'audit_verdict');
    assert.equal(verdicts.length, 1);
    assert.equal(verdicts[0]!.verdict, 'unknown');
    subagentStop(input(root, { agent_type: 'auditor', last_assistant_message: '```json\n{not json\n```' }));
    assert.equal(rows(file).filter((row) => row.kind === 'audit_verdict' && row.verdict === 'unknown').length, 2);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('another subagent records only subagent_stop, and subagent_start records for every subagent', () => {
  const { root, file } = project();
  try {
    subagentStop(input(root, { agent_type: 'academic-writer:architect', last_assistant_message: 'done' }));
    subagentStart(input(root, { agent_type: 'general-purpose' }));
    const kinds = rows(file).map((row) => `${row.kind}:${row.agent ?? ''}`);
    assert.deepEqual(kinds, ['run_start:', 'subagent_stop:academic-writer:architect', 'subagent_start:general-purpose']);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('no active run writes nothing', () => {
  for (const run of ['none', 'ended', 'old'] as const) {
    const { root, file } = project({ run });
    try {
      const before = existsSync(file) ? readFileSync(file, 'utf8') : null;
      subagentStop(input(root, { agent_type: 'auditor', last_assistant_message: auditorReply([{ paragraphIndex: 1, verdict: 'PASS', feedback: 'ok' }]) }));
      subagentStart(input(root, { agent_type: 'auditor' }));
      assert.equal(existsSync(file) ? readFileSync(file, 'utf8') : null, before, run);
    } finally { rmSync(root, { recursive: true, force: true }); }
  }
});

test('no profile writes nothing', () => {
  const { root, file } = project({ profile: false });
  try {
    const before = readFileSync(file, 'utf8');
    subagentStop(input(root, { agent_type: 'auditor', last_assistant_message: auditorReply([{ paragraphIndex: 1, verdict: 'PASS', feedback: 'ok' }]) }));
    subagentStart(input(root, { agent_type: 'auditor' }));
    assert.equal(readFileSync(file, 'utf8'), before);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('a torn last line does not hide the active run', () => {
  const { root, file } = project();
  try {
    writeFileSync(file, `${readFileSync(file, 'utf8')}{"v":1,"ts":"2026-10-18T10:0`);
    subagentStart(input(root, { agent_type: 'general-purpose' }));
    assert.ok(readFileSync(file, 'utf8').includes('subagent_start'));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('the one-line status is shown when the author turned the pane off, and not while the pane is on', () => {
  const { root } = project();
  const plugin = mkdtempSync(join(tmpdir(), 'aw-plugin-root-'));
  const names = ['CLAUDE_PLUGIN_ROOT', 'CLAUDE_PLUGIN_OPTION_ACTIVITY_PANE'] as const;
  const before = names.map((n) => process.env[n]);
  try {
    mkdirSync(join(plugin, 'bin'));
    writeFileSync(join(plugin, 'bin', 'aw'), '#!/bin/sh\necho "write: step 3/6"\n', { mode: 0o755 });
    process.env['CLAUDE_PLUGIN_ROOT'] = plugin;
    process.env['CLAUDE_PLUGIN_OPTION_ACTIVITY_PANE'] = 'true';
    assert.equal(subagentStop(input(root, { agent_type: 'Explore' })).systemMessage, undefined);
    process.env['CLAUDE_PLUGIN_OPTION_ACTIVITY_PANE'] = 'false';
    assert.equal(subagentStop(input(root, { agent_type: 'Explore' })).systemMessage, 'write: step 3/6');
  } finally {
    names.forEach((n, i) => { const v = before[i]; if (v === undefined) delete process.env[n]; else process.env[n] = v; });
    rmSync(root, { recursive: true, force: true });
    rmSync(plugin, { recursive: true, force: true });
  }
});

const writeTranscript = (root: string, firstUser: unknown, reply: string): string => {
  const transcript = join(root, 'agent.jsonl');
  writeFileSync(transcript, `${JSON.stringify({ type: 'user', message: { role: 'user', content: firstUser } })}\n${JSON.stringify({ type: 'assistant', message: { role: 'assistant', content: [{ type: 'text', text: reply }] } })}\n`);
  return transcript;
};

test('the unit id comes from the auditor input (unitId or sectionId) and rides on every verdict', () => {
  for (const [prompt, expected] of [
    ['runId: r1\nunitId: U2\nPARAGRAPH_INDEX: 0', 'U2'],
    ['{"sectionId": "sec-3", "runId": "r1"}', 'sec-3'],
    [[{ type: 'text', text: 'unitId: "intro"\nrunId: r1' }], 'intro'],
  ] as const) {
    const { root, file } = project();
    try {
      const reply = auditorReply([{ paragraphIndex: 0, verdict: 'PASS', feedback: 'ok' }, { paragraphIndex: 1, verdict: 'FAIL', feedback: '1. bad' }]);
      subagentStop(input(root, { agent_type: 'auditor', agent_transcript_path: writeTranscript(root, prompt, reply) }));
      assert.deepEqual(rows(file).filter((row) => row.kind === 'audit_verdict').map((row) => row.unit), [expected, expected]);
    } finally { rmSync(root, { recursive: true, force: true }); }
  }
});

test('no unit id in the auditor input leaves the unit absent', () => {
  const { root, file } = project();
  try {
    const reply = auditorReply([{ paragraphIndex: 0, verdict: 'PASS', feedback: 'ok' }]);
    subagentStop(input(root, { agent_type: 'auditor', last_assistant_message: reply, agent_transcript_path: writeTranscript(root, 'audit these paragraphs please', reply) }));
    const verdict = rows(file).find((row) => row.kind === 'audit_verdict');
    assert.ok(verdict && !('unit' in verdict));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('the reason holds the verdict and the count of numbered issues, never the feedback', () => {
  const { root, file } = project();
  try {
    const feedback = '1. The Rambam passage is misquoted.\n2. Footnote 4 has the wrong page.\n3) Missing source.';
    subagentStop(input(root, { agent_type: 'auditor', last_assistant_message: auditorReply([{ paragraphIndex: 0, verdict: 'FAIL', feedback }]) }));
    const verdict = rows(file).find((row) => row.kind === 'audit_verdict');
    assert.equal(verdict?.reason, 'FAIL, 3 issues');
    assert.ok(!JSON.stringify(rows(file)).includes('Rambam'));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('an auditor stop closes the audit step', () => {
  const { root, file } = project();
  try {
    subagentStop(input(root, { agent_type: 'auditor', last_assistant_message: auditorReply([{ paragraphIndex: 0, verdict: 'PASS', feedback: 'ok' }]) }));
    const kinds = rows(file).map((row) => `${row.kind}:${(row as { step?: string }).step ?? ''}`);
    assert.ok(kinds.includes('step_start:audit') && kinds.includes('step_end:audit'));
    assert.ok(kinds.indexOf('step_end:audit') > kinds.indexOf('audit_verdict:audit'));
  } finally { rmSync(root, { recursive: true, force: true }); }
});
