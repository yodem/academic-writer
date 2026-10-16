import thresholds from '../../../../thresholds.json' with { type: 'json' };

const KEYS = [
  'maxClaims', 'minPairs', 'maxTurns', 'maxBudgetUsdPerRun', 'parallel', 'expectedUsdPerRun', 'maxPagesPerRead', 'maxReads',
  'runTimeoutMs', 'minClaimWords', 'maxAnswerPages', 'perSourceShare',
] as const;

const block = thresholds.library.eval as Record<string, unknown>;

function number(key: (typeof KEYS)[number]): number {
  const value = block[key];
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    throw new Error(`ERROR library eval: src/thresholds.json library.eval.${key} is missing or not a positive number`);
  }
  return value;
}

function text(key: 'locateModel'): string {
  const value = block[key];
  if (typeof value !== 'string' || !value) throw new Error(`ERROR library eval: src/thresholds.json library.eval.${key} is missing`);
  return value;
}

/** Every number the evaluation uses, all from the `library.eval` block of src/thresholds.json (no defaults here). */
export const evalLimits = {
  maxClaims: number('maxClaims'),
  minPairs: number('minPairs'),
  maxTurns: number('maxTurns'),
  maxBudgetUsdPerRun: number('maxBudgetUsdPerRun'),
  parallel: number('parallel'),
  locateModel: text('locateModel'),
  expectedUsdPerRun: number('expectedUsdPerRun'),
  maxPagesPerRead: number('maxPagesPerRead'),
  maxReads: number('maxReads'),
  /** Wall clock for one locate agent. */
  runTimeoutMs: number('runTimeoutMs'),
  /** A sentence shorter than this many words is not a claim worth locating. */
  minClaimWords: number('minClaimWords'),
  /** Pages one locate answer may name. */
  maxAnswerPages: number('maxAnswerPages'),
  /** No source may supply more than ceil(N / this) of the N claims. */
  perSourceShare: number('perSourceShare'),
  maxBufferBytes: thresholds.library.maxBufferBytes,
  maxRequestPages: thresholds.library.maxRequestPages,
  timeoutMs: thresholds.library.timeoutMs,
};
