import thresholds from '../../../../thresholds.json' with { type: 'json' };

type EvalBlock = {
  maxClaims: number; minPairs: number; maxTurns: number; maxBudgetUsdPerRun: number; parallel: number;
  locateModel: string; expectedUsdPerRun: number; maxPagesPerRead: number; maxReads: number;
  /** Optional keys: the defaults below apply until src/thresholds.json carries them. */
  runTimeoutMs?: number; minClaimWords?: number; maxAnswerPages?: number; perSourceShare?: number;
};

const block = thresholds.library.eval as EvalBlock;

/** Every number the evaluation uses: the seeded `library.eval` block, plus optional keys with a default each. */
export const evalLimits = {
  maxClaims: block.maxClaims,
  minPairs: block.minPairs,
  maxTurns: block.maxTurns,
  maxBudgetUsdPerRun: block.maxBudgetUsdPerRun,
  parallel: block.parallel,
  locateModel: block.locateModel,
  expectedUsdPerRun: block.expectedUsdPerRun,
  maxPagesPerRead: block.maxPagesPerRead,
  maxReads: block.maxReads,
  /** Wall clock for one locate agent (a bench run took well under it). */
  runTimeoutMs: block.runTimeoutMs ?? 600000,
  /** A sentence shorter than this many words is not a claim worth locating. */
  minClaimWords: block.minClaimWords ?? 5,
  /** Pages one locate answer may name. */
  maxAnswerPages: block.maxAnswerPages ?? 3,
  /** No source may supply more than ceil(N / this) of the N claims. */
  perSourceShare: block.perSourceShare ?? 3,
  maxBufferBytes: thresholds.library.maxBufferBytes,
  maxRequestPages: thresholds.library.maxRequestPages,
  timeoutMs: thresholds.library.timeoutMs,
};
