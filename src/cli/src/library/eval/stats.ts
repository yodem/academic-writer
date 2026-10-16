// Small, exact statistics for the unblinded report. No model, no dependency.

export function sum(values: number[]): number { return values.reduce((total, value) => total + value, 0); }

/** The middle value (mean of the two middle ones for an even count); null for an empty list. */
export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  const low = sorted[middle - 1] as number;
  const high = sorted[middle] as number;
  return sorted.length % 2 === 1 ? high : (low + high) / 2;
}

/** 95% Wilson score interval for `successes` of `n`; null when n is 0. */
export function wilson95(successes: number, n: number): [number, number] | null {
  if (n <= 0) return null;
  const z = 1.959963984540054;
  const p = successes / n;
  const denominator = 1 + (z * z) / n;
  const centre = (p + (z * z) / (2 * n)) / denominator;
  const margin = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / denominator;
  return [Math.max(0, centre - margin), Math.min(1, centre + margin)];
}

function logFactorials(n: number): number[] {
  const table = [0];
  for (let index = 1; index <= n; index += 1) table.push((table[index - 1] as number) + Math.log(index));
  return table;
}

/**
 * Exact two-sided sign test: with `n` decisive pairs and `k` wins for one side, the chance of a split at least
 * this uneven if both sides were equally good (a fair coin). 1 when n is 0.
 */
export function signTestP(k: number, n: number): number {
  if (n <= 0) return 1;
  const low = Math.min(k, n - k);
  const logs = logFactorials(n);
  let tail = 0;
  for (let index = 0; index <= low; index += 1) {
    tail += Math.exp((logs[n] as number) - (logs[index] as number) - (logs[n - index] as number) - n * Math.LN2);
  }
  return Math.min(1, 2 * tail);
}
