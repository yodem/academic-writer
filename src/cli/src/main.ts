import { setPathArguments, projectDir, dataDir } from './paths.ts';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { stepIds } from './routing.ts';
import { runProofread } from './proofread.ts';
import thresholds from '../../thresholds.json' with { type: 'json' };

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
} else if (command === 'models' && subcommand === 'check') {
  process.stdout.write(`Configured Gemini steps: ${stepIds.join(', ')}\nLive model verification requires GOOGLE_API_KEY.\n`);
} else {
  process.stderr.write('ERROR: expected aw models check or aw ledger show <runId>\n');
  process.exitCode = 2;
}
