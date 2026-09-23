import { appendFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { dataDir, projectDir } from './paths.ts';
import thresholds from '../../thresholds.json' with { type: 'json' };

export type Usage = { in: number; out: number };
export class AwError extends Error {
  readonly code: 'ERROR' | 'CAP_REACHED';
  readonly step: string;
  constructor(code: 'ERROR' | 'CAP_REACHED', step: string, reason: string) { super(`${code} ${step}: ${reason}`); this.code = code; this.step = step; }
}
export type LedgerRow = { run_id: string; step: string; provider: string; model: string; input_tokens: number; output_tokens: number; cost_usd: number | null; latency_ms: number; exit: 'OK' | 'ERROR' | 'CAP_REACHED'; same_family: boolean };
export function appendLedger(row: LedgerRow): void {
  dataDir();
  const dir = join(projectDir(), '.academic-helper', 'runs', row.run_id);
  mkdirSync(dir, { recursive: true });
  appendFileSync(join(dir, 'usage.jsonl'), `${JSON.stringify(row)}\n`, 'utf8');
}
export class Budget {
  private tokens = 0;
  private usd = 0;
  private readonly runId: string;
  private readonly caps: { maxTokens: number; maxUsd?: number };
  constructor(runId: string, caps: { maxTokens: number; maxUsd?: number }) { this.runId = runId; this.caps = caps; }
  charge(usage: Usage, costUsd = 0, step: string = 'write.draft'): void {
    this.tokens += usage.in + usage.out;
    this.usd += costUsd;
    if (this.tokens > this.caps.maxTokens || (this.caps.maxUsd !== undefined && this.usd > this.caps.maxUsd)) {
      throw new AwError('CAP_REACHED', step, `budget exceeded for ${this.runId}`);
    }
  }
}
export function budgetFor(pipeline: 'proofread' | 'write'): { maxTokens: number; maxUsd: number } {
  return thresholds.budget[pipeline];
}
