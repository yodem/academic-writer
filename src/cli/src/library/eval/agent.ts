import { spawn, type ChildProcess } from 'node:child_process';
import type { Engine } from './types.ts';

// ---------------------------------------------------------------- running one agent process

/** Agent processes started by one eval run, so an interrupt or a fatal error can stop them all (each is its own process group). */
export class ChildGroup {
  private readonly children = new Set<ChildProcess>();
  add(child: ChildProcess): void { this.children.add(child); }
  remove(child: ChildProcess): void { this.children.delete(child); }
  get size(): number { return this.children.size; }
  killAll(): void {
    for (const child of this.children) killGroup(child);
    this.children.clear();
  }
}

export function killGroup(child: ChildProcess): void {
  try { if (process.platform !== 'win32' && child.pid) process.kill(-child.pid, 'SIGKILL'); else child.kill('SIGKILL'); }
  catch { try { child.kill('SIGKILL'); } catch { /* already gone */ } }
}

export type AgentExit = { stdout: string; stderr: string; code: number | null; timedOut: boolean; tooLarge: boolean; spawnError: 'missing' | string | null; wallMs: number };

/**
 * Run `command` + `args` with `input` on stdin in its own process group. At the deadline the whole group is killed
 * and the promise settles even if a grandchild keeps the pipes open (same approach as exec.ts, but the output of a
 * failed run is kept: its usage and cost still count).
 */
export function runAgent(command: string[], args: string[], options: { input: string; cwd: string; env: NodeJS.ProcessEnv; timeoutMs: number; maxBuffer: number; group: ChildGroup }): Promise<AgentExit> {
  const [file, ...prefix] = command;
  const started = Date.now();
  if (!file) return Promise.resolve({ stdout: '', stderr: '', code: null, timedOut: false, tooLarge: false, spawnError: 'empty command', wallMs: 0 });
  return new Promise<AgentExit>((resolve) => {
    let settled = false;
    const out: Buffer[] = [];
    let size = 0;
    let stderr = '';
    let timedOut = false;
    let tooLarge = false;
    const child = spawn(file, [...prefix, ...args], { stdio: ['pipe', 'pipe', 'pipe'], env: options.env, cwd: options.cwd, detached: process.platform !== 'win32', windowsHide: true });
    options.group.add(child);
    const finish = (code: number | null, spawnError: string | null): void => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      options.group.remove(child);
      resolve({ stdout: Buffer.concat(out).toString('utf8'), stderr: stderr.slice(0, 8192), code, timedOut, tooLarge, spawnError, wallMs: Date.now() - started });
    };
    const timer = setTimeout(() => {
      timedOut = true;
      killGroup(child);
      child.stdout?.destroy();
      child.stderr?.destroy();
      finish(null, null);
    }, options.timeoutMs);
    child.stdout?.on('data', (chunk: Buffer) => {
      size += chunk.length;
      if (size > options.maxBuffer) { tooLarge = true; killGroup(child); finish(null, null); return; }
      out.push(chunk);
    });
    child.stderr?.on('data', (chunk: Buffer) => { if (stderr.length < 8192) stderr += chunk.toString('utf8'); });
    child.stdin?.on('error', () => { /* the agent closed its input early */ });
    child.on('error', (error: NodeJS.ErrnoException) => finish(null, error.code === 'ENOENT' ? 'missing' : error.message));
    // Once the agent is gone, whatever it left in its process group is killed too.
    child.on('close', (code) => { killGroup(child); finish(code, null); });
    child.stdin?.end(options.input);
  });
}

// ---------------------------------------------------------------- reading what an agent printed

export type Parsed = {
  /** The agent's final message. */
  text: string | null;
  calls: string[];
  toolErrors: string[];
  permissionDenials: number;
  version: string | null;
  model: string | null;
  inputTokens: number;
  outputTokens: number;
  costUsd: number | null;
  agentMs: number | null;
  turns: number | null;
  /** A reason the agent reported for stopping without an answer (turn or budget cap, an error result). */
  stopReason: string | null;
};

function emptyParsed(): Parsed {
  return { text: null, calls: [], toolErrors: [], permissionDenials: 0, version: null, model: null, inputTokens: 0, outputTokens: 0, costUsd: null, agentMs: null, turns: null, stopReason: null };
}

function records(stdout: string): Array<Record<string, unknown>> {
  const out: Array<Record<string, unknown>> = [];
  for (const line of stdout.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed.startsWith('{')) continue;
    try { const value: unknown = JSON.parse(trimmed); if (typeof value === 'object' && value !== null && !Array.isArray(value)) out.push(value as Record<string, unknown>); } catch { /* not an event */ }
  }
  return out;
}

const num = (value: unknown): number => (typeof value === 'number' && Number.isFinite(value) ? value : 0);
const str = (value: unknown): string | null => (typeof value === 'string' && value ? value : null);
const rec = (value: unknown): Record<string, unknown> => (typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {});

/**
 * `claude -p --output-format stream-json --verbose`: one JSON event per line. Parsed defensively (the event shape
 * differs between Claude Code versions): the init event gives the model and version, assistant events carry the
 * Bash commands, and the last `result` event the answer text, usage, cost, turns and duration.
 */
export function parseClaude(stdout: string): Parsed {
  const parsed = emptyParsed();
  for (const event of records(stdout)) {
    if (event.type === 'system') {
      parsed.version = parsed.version ?? str(event.claude_code_version);
      parsed.model = parsed.model ?? str(event.model);
    } else if (event.type === 'assistant') {
      const content = rec(event.message).content;
      for (const part of Array.isArray(content) ? content : []) {
        const item = rec(part);
        if (item.type !== 'tool_use') continue;
        const input = rec(item.input);
        parsed.calls.push(item.name === 'Bash' && typeof input.command === 'string' ? input.command : `[${String(item.name)}] ${JSON.stringify(input).slice(0, 200)}`);
      }
    } else if (event.type === 'user') {
      const content = rec(event.message).content;
      for (const part of Array.isArray(content) ? content : []) {
        const item = rec(part);
        if (item.type === 'tool_result' && item.is_error === true) parsed.toolErrors.push(String(typeof item.content === 'string' ? item.content : JSON.stringify(item.content)).slice(0, 200));
      }
    } else if (event.type === 'result') {
      const usage = rec(event.usage);
      parsed.text = str(event.result);
      parsed.inputTokens = num(usage.input_tokens) + num(usage.cache_read_input_tokens) + num(usage.cache_creation_input_tokens);
      parsed.outputTokens = num(usage.output_tokens);
      parsed.costUsd = typeof event.total_cost_usd === 'number' ? event.total_cost_usd : null;
      parsed.agentMs = typeof event.duration_ms === 'number' ? Math.round(event.duration_ms) : null;
      parsed.turns = typeof event.num_turns === 'number' ? event.num_turns : null;
      parsed.permissionDenials = Array.isArray(event.permission_denials) ? event.permission_denials.length : 0;
      const subtype = str(event.subtype);
      parsed.stopReason = event.is_error === true ? (subtype ?? 'error') : (subtype && subtype !== 'success' ? subtype : null);
    }
  }
  return parsed;
}

/**
 * `codex exec --json`: JSONL events. Commands come from `item.completed` events of type command_execution, the answer
 * from the last agent_message, tokens from `turn.completed` usage (summed). Codex reports no cost, so it stays null.
 */
export function parseCodex(stdout: string): Parsed {
  const parsed = emptyParsed();
  let sawUsage = false;
  for (const event of records(stdout)) {
    const item = rec(event.item ?? rec(event.msg));
    const kind = str(item.type) ?? str(item.item_type);
    if (event.type === 'item.completed' || event.type === 'item.started' || typeof event.msg === 'object') {
      if (kind === 'command_execution' && event.type !== 'item.started') {
        const command = str(item.command);
        if (command) parsed.calls.push(command);
        if (typeof item.exit_code === 'number' && item.exit_code !== 0) parsed.toolErrors.push(String(item.aggregated_output ?? '').slice(0, 200));
      } else if (kind === 'agent_message' || kind === 'assistant_message') {
        parsed.text = str(item.text) ?? str(item.message) ?? parsed.text;
      }
    }
    if (event.type === 'turn.completed' || event.type === 'token_count') {
      const usage = rec(event.usage ?? rec(event.msg).info);
      parsed.inputTokens += num(usage.input_tokens) + num(usage.cached_input_tokens);
      parsed.outputTokens += num(usage.output_tokens);
      sawUsage = true;
      parsed.turns = (parsed.turns ?? 0) + 1;
    }
    if (event.type === 'turn.failed' || event.type === 'error') parsed.stopReason = str(rec(event.error).message) ?? str(event.message) ?? 'error';
    if (typeof event.model === 'string' && !parsed.model) parsed.model = event.model;
  }
  if (!sawUsage) { parsed.inputTokens = 0; parsed.outputTokens = 0; }
  return parsed;
}

export function parseAgent(engine: Engine, stdout: string): Parsed { return engine === 'claude' ? parseClaude(stdout) : parseCodex(stdout); }

// ---------------------------------------------------------------- the answer

/** The last fenced json block (or, failing that, the last bare object that has "pages"): {book, pages, reason}. */
export function parseAnswer(text: string | null, maxPages: number): { book: string; pages: number[]; reason: string } | null {
  if (!text) return null;
  const candidates = [...text.matchAll(/```json\s*(\{[\s\S]*?\})\s*```/giu)].map((match) => match[1] as string);
  if (candidates.length === 0) candidates.push(...[...text.matchAll(/\{[^{}]*"pages"[^{}]*\}/gu)].map((match) => match[0]));
  for (const raw of candidates.reverse()) {
    try {
      const value = rec(JSON.parse(raw));
      const pages = [...new Set((Array.isArray(value.pages) ? value.pages : []).map((page) => Number(page)).filter((page) => Number.isInteger(page) && page > 0))].slice(0, maxPages);
      if (pages.length === 0) continue;
      return { book: String(value.book ?? ''), pages, reason: typeof value.reason === 'string' ? value.reason.slice(0, 500) : '' };
    } catch { /* try an earlier block */ }
  }
  return null;
}
