import { setPathArguments, projectDir, dataDir } from './paths.ts';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { stepIds } from './routing.ts';
import { voiceBundle, voiceCandidates, voiceMigrate, voiceMoves, voiceSync } from './voice.ts';
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
} else if (command === 'models' && subcommand === 'check') {
  process.stdout.write(`Configured Gemini steps: ${stepIds.join(', ')}\nLive model verification requires GOOGLE_API_KEY.\n`);
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
  process.stderr.write('ERROR: expected aw models check or aw ledger show <runId>\n');
  process.exitCode = 2;
}
