import type { RouteName } from '../types.ts';

export type Route = RouteName;
export type Engine = 'claude' | 'codex';
export type Verdict = 'A' | 'B' | 'same' | 'neither' | 'skip';

export type Book = { id: string; title: string };

export type Claim = {
  id: string;
  text: string;
  source_id: string;
  source_title: string;
  /** The Trove pages the article's citation points at; empty when they cannot be worked out. */
  cited_trove_pages: number[];
  cited_printed_page: number | null;
  paragraph_id: string | null;
  auditor_verdict: 'PASS' | 'FAIL' | null;
  corrected_page: number | null;
};

export type SkipCounts = { too_short: number; no_source: number; multi_source: number; unresolved: number; over_cap: number };

export type Plan = {
  schema: 1;
  eval_id: string;
  created_at: string;
  article: string | null;
  seed: string;
  routes: Route[];
  shelf: Book[];
  claims: Claim[];
  skipped: SkipCounts;
  estimate: { runs: number; usd: number };
};

export type Answer = { book: string; pages: number[]; reason: string };

export type Run = {
  schema: 1;
  eval_id: string;
  claim_id: string;
  route: Route;
  engine: Engine;
  model: string;
  status: 'ok' | 'error';
  attempts: number;
  started_at: string;
  answer: Answer | null;
  tool_calls: string[];
  n_reads: number;
  n_toc: number;
  pages_per_read: number[];
  over_budget: boolean;
  permission_denials: number;
  wall_ms: number;
  agent_ms: number | null;
  turns: number | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  returned_chars: number | null;
  returned_est_tokens: number | null;
  agent_version: string | null;
  error: string | null;
};

export type PairOption = { book: string | null; book_title: string | null; pages: Array<{ page: number; text: string }> };

export type Pair = {
  pair_id: string;
  claim: { id: string; text: string };
  auto_same: boolean;
  options: { A: PairOption; B: PairOption };
};

export type Pairs = { schema: 1; eval_id: string; created_at: string; mapping_sha256: string; pairs: Pair[] };

export type Mapping = {
  schema: 1;
  eval_id: string;
  seed: string;
  nonce: string;
  pairs: Array<{ pair_id: string; claim_id: string; A: Route; B: Route }>;
};

export type JudgmentEntry = { pair_id: string; verdict: Verdict; note: string; source: 'judge' | 'auto'; judged_at: string | null; imported_at: string };
export type Judgments = { schema: 1; eval_id: string; pairs_sha256: string; mapping_sha256: string; entries: JudgmentEntry[] };

export type EvalIo = {
  out: (text: string) => void;
  err: (text: string) => void;
  /** Reads piped input for `import --stdin`. */
  stdin?: () => Promise<string>;
  /** The article project; default: --project-dir, CLAUDE_PROJECT_DIR, or the current folder. */
  project?: string;
  env?: NodeJS.ProcessEnv;
  /** The command that runs `aw` (a word list). Default: this program's own entry file. */
  awCommand?: string[];
  now?: () => Date;
  /** Test hooks. */
  runTimeoutMs?: number;
};
