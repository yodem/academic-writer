import { setPathArguments, projectDir, dataDir } from './paths.ts';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { stepIds } from './routing.ts';
import { runProofread } from './proofread.ts';
import thresholds from '../../thresholds.json' with { type: 'json' };
import { buildEvidence } from './evidence.ts';
import { voiceBundle, voiceCandidates, voiceMigrate, voiceMoves, voiceSync } from './voice.ts';
import { decide, type JevPoint } from './decide.ts';
import { classify, applyPlan, type RevisePlan } from './revise.ts';

const args = setPathArguments(process.argv.slice(2));
const [command, subcommand, runId] = args;
if (command === 'ledger' && subcommand === 'show' && runId) {
  try {
    dataDir();
    const file = join(projectDir(), '.academic-helper', 'runs', runId, 'usage.jsonl');
    const rows = readFileSync(file, 'utf8').trim().split('\n').filter(Boolean).map(line => JSON.parse(line) as { step: string; input_tokens: number; output_tokens: number; cost_usd: number | null });
    const totals = new Map<string, { input_tokens: number; output_tokens: number; cost_usd: number | null }>();
    for (const row of rows) { const total = totals.get(row.step) ?? { input_tokens: 0, output_tokens: 0, cost_usd: 0 }; total.input_tokens += row.input_tokens; total.output_tokens += row.output_tokens; total.cost_usd = total.cost_usd === null || row.cost_usd === null ? null : total.cost_usd + row.cost_usd; totals.set(row.step, total); }
    process.stdout.write(`${JSON.stringify(Object.fromEntries(totals), null, 2)}\n`);
  } catch (error) { process.stderr.write(`${error instanceof Error && error.message.startsWith('ERROR:') ? error.message : `ERROR ledger: missing run ${runId}`}\n`); process.exitCode = error instanceof Error && error.message.startsWith('ERROR:') ? 3 : 2; }
} else if (command === 'proofread') {
  try {
    const values = new Map<string, string>();
    const positional: string[] = [];
    for (let index = 1; index < args.length; index += 1) {
      const arg = args[index];
      if (arg.startsWith('--') && args[index + 1]) { values.set(arg, args[index + 1]); index += 1; }
      else positional.push(arg);
    }
    const requiredRun = values.get('--run');
    if (!requiredRun) throw new Error('ERROR proofread: --run <id> is required');
    const project = projectDir(); const data = dataDir();
    const only = values.get('--only');
    if (only && !['mechanical','language','editorial'].includes(only)) throw new Error('ERROR proofread: invalid --only value');
    const result = await runProofread({ article: positional[0], runId: requiredRun, venue: values.get('--venue'), only: only as 'mechanical' | 'language' | 'editorial' | undefined, out: values.get('--out'), dataDir: data, projectDir: project });
    const summaryCaps = thresholds.budget.proofread as { summaryMaxBytes: number; summaryMemoChars: number; summaryExcerptChars: number };
    let summary = JSON.stringify({ changes: result.changes.length, memo: result.memo.slice(0, summaryCaps.summaryMemoChars), proofed: values.get('--out') ? `${values.get('--out')}/proofed.md` : 'proofed.md', report: result.report });
    if (Buffer.byteLength(summary, 'utf8') > summaryCaps.summaryMaxBytes) summary = JSON.stringify({ changes: result.changes.length, report: 'report.md' });
    process.stdout.write(`${summary}\n`);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'ERROR proofread: unknown failure';
    process.stderr.write(`${message}\n`);
    process.exitCode = message.includes('CAP_REACHED') ? 4 : 2;
  }
} else if (command === 'models' && subcommand === 'check') {
  process.stdout.write(`Configured Gemini steps: ${stepIds.join(', ')}\nLive model verification requires GOOGLE_API_KEY.\n`);
} else if (command === 'revise') {
  try {
    dataDir(); projectDir();
    const fileArg = args[args.indexOf(subcommand === 'classify' ? '--items' : '--plan') + 1];
    if (!fileArg) throw new Error('ERROR revise: --items/--plan path required');
    const input = JSON.parse(readFileSync(fileArg, 'utf8')) as unknown;
    if (subcommand === 'classify') {
      if (!Array.isArray(input)) throw new Error('ERROR revise.classify: items must be an array');
      process.stdout.write(`${JSON.stringify(await classify(input, args[args.indexOf('--run') + 1] ?? 'revise'))}\n`);
    } else if (subcommand === 'apply') process.stdout.write(`${JSON.stringify(await applyPlan(input as RevisePlan))}\n`);
    else throw new Error('ERROR revise: expected classify or apply');
  } catch (error) { process.stderr.write(`${error instanceof Error ? error.message : 'ERROR revise: unknown failure'}\n`); process.exitCode = 2; }
} else if (command === 'evidence' && subcommand === 'build') {
  const value = (name: string): string | undefined => {
    const position = args.indexOf(name);
    return position >= 0 ? args[position + 1] : undefined;
  };
  const list = (name: string): string[] => (value(name) ?? '').split(',').map(item => item.trim()).filter(Boolean);
  const runIdValue = value('--run');
  try {
    if (!runIdValue) throw new Error('ERROR evidence.build: --run is required');
    const result = await buildEvidence({ sources: list('--sources'), sefaria: list('--sefaria'), intent: value('--intent'), runId: runIdValue });
    process.stdout.write(`${JSON.stringify({ sourceCount: result.sources.length, passageCount: result.passages.length })}\n`);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : 'ERROR evidence.build: unknown failure'}\n`);
    process.exitCode = 1;
  }
} else if (command === 'decide') {
  const value = (name: string): string | undefined => {
    const position = args.indexOf(name);
    return position >= 0 ? args[position + 1] : undefined;
  };
  const pointValue = args[1];
  const validPoints: JevPoint[] = ['proofread.verify', 'proofread.triage', 'revise.classify', 'evidence.relevance', 'outline.support', 'write.audit_prescreen', 'write.voice_check', 'synthesize.needs_bridge', 'style.filler'];
  try {
    const question = value('--question');
    const rawOptions = value('--options');
    const contextFile = value('--context-file');
    const fallback = value('--fallback');
    const runIdValue = value('--run');
    const label = value('--label');
    if (!pointValue || !validPoints.includes(pointValue as JevPoint) || !question || !rawOptions || !contextFile || !fallback || !runIdValue) {
      throw new Error('ERROR decide: expected aw decide <point> --question <text> --options a,b --context-file <file> --fallback <answer> --run <id>');
    }
    const options = rawOptions.split(',').map(item => item.trim()).filter(Boolean);
    if (options.length < 2) throw new Error('ERROR decide: --options requires at least two comma-separated answers');
    if (!options.includes(fallback)) throw new Error('ERROR decide: --fallback must match one of --options');
    const context = readFileSync(contextFile, 'utf8');
    const result = await decide({ point: pointValue as JevPoint, question, options, context, runId: runIdValue,
      fallback: async () => fallback, label });
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : 'ERROR decide: unknown failure'}\n`);
    process.exitCode = 1;
  }
} else if (command === 'voice') {
  try {
    dataDir();
    projectDir();
    if (subcommand === 'migrate') process.stdout.write(`${voiceMigrate(args[args.indexOf('--from') + 1] ?? projectDir())}\n`);
    else if (subcommand === 'exemplars') process.stdout.write(`${JSON.stringify(voiceCandidates(args[args.indexOf('--corpus') + 1] ?? ''), null, 2)}\n`);
    else if (subcommand === 'bundle') {
      const bundle = await voiceBundle({ n: Number(args[args.indexOf('--n') + 1] ?? thresholds.voice.bundle.exemplars), pairs: Number(args[args.indexOf('--pairs') + 1] ?? thresholds.voice.bundle.pairs), runId: args[args.indexOf('--run-id') + 1] ?? 'default' });
      process.stdout.write(`${bundle.path}\n`);
    } else if (subcommand === 'moves') process.stdout.write(`${await voiceMoves(args[args.indexOf('--run-id') + 1] ?? 'voice-moves')}\n`);
    else if (subcommand === 'push' || subcommand === 'pull') process.stdout.write(`${voiceSync(subcommand)}\n`);
    else throw new Error('ERROR: expected aw voice migrate|exemplars|bundle|moves|push|pull');
  } catch (error) {
    const message = error instanceof Error ? error.message : 'ERROR voice: unknown failure';
    process.stderr.write(`${message}\n`);
    process.exitCode = message.includes('no voice store') ? 3 : 2;
  }
} else {
  process.stderr.write('ERROR: expected aw models check, aw ledger show <runId>, aw evidence build, or aw decide <point>\n');
  process.exitCode = 2;
}
