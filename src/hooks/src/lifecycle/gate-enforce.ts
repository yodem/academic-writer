import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { HookInput, HookResult } from '../types.js';

/**
 * gate-enforce — the plugin's first hook that actually blocks.
 *
 * Registered on `Stop`. Reads `.academic-helper/session-state.json` for an
 * in-flight run's `requiredGates`, then checks the `gates` ledger that
 * `src/scripts/gate.py` writes. A required gate that is missing entirely is
 * treated the same as a required gate that failed — the whole point of the
 * design (VER-18) is that skipping the gate call is itself detected, because
 * the ledger records absence.
 *
 * Fail-closed on a genuine gate failure (continue: false).
 * Fail-open on the hook's own infrastructure problems — unreadable/missing
 * session-state, malformed JSON, missing keys, or any thrown exception —
 * because a gate that breaks the plugin in projects that never opted in is
 * worse than the gap it closes.
 */

interface GateVerdict {
  status?: unknown;
  at?: unknown;
  detail?: unknown;
  violations?: unknown;
}

interface SessionState {
  run?: {
    id?: unknown;
    skill?: unknown;
    requiredGates?: unknown;
    completed?: unknown;
  };
  gates?: Record<string, unknown>;
}

const SILENT_PASS: HookResult = { continue: true, suppressOutput: true };

function formatViolations(violations: unknown): string {
  if (!Array.isArray(violations) || violations.length === 0) return '';
  const shown = violations.slice(0, 3).map((v) => {
    if (typeof v === 'string') return v;
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  });
  const suffix = violations.length > shown.length ? ` (+${violations.length - shown.length} more)` : '';
  return `\n    violations: ${shown.join('; ')}${suffix}`;
}

export function gateEnforce(input: HookInput): HookResult {
  try {
    const projectDir = input.project_dir ?? process.env['CLAUDE_PROJECT_DIR'] ?? '.';

    // Hard gate: only enforce in academic-writer projects. Same convention
    // every other hook in this directory follows.
    if (!existsSync(join(projectDir, '.academic-helper', 'profile.md'))) {
      return SILENT_PASS;
    }

    // Loop guard — mandatory. Without it, a gate that can never be satisfied
    // (or a genuine infrastructure bug in the gate itself) traps the session
    // in an endless Stop retry loop.
    if (input.stop_hook_active === true) {
      return SILENT_PASS;
    }

    const statePath = join(projectDir, '.academic-helper', 'session-state.json');
    if (!existsSync(statePath)) {
      return SILENT_PASS;
    }

    let state: SessionState;
    try {
      const raw = readFileSync(statePath, 'utf-8');
      const parsed: unknown = JSON.parse(raw);
      if (typeof parsed !== 'object' || parsed === null) {
        // Malformed shape — infrastructure problem, fail open.
        return SILENT_PASS;
      }
      state = parsed as SessionState;
    } catch {
      // Unreadable or unparseable — infrastructure problem, fail open.
      return SILENT_PASS;
    }

    const run = state.run;
    if (typeof run !== 'object' || run === null) {
      // No run object at all — nothing in flight.
      return SILENT_PASS;
    }
    if (run.completed === true) {
      return SILENT_PASS;
    }

    const requiredGatesRaw = run.requiredGates;
    if (!Array.isArray(requiredGatesRaw) || requiredGatesRaw.length === 0) {
      // Data-driven by design: no required gates declared means nothing to
      // enforce. The hook has no hardcoded knowledge of which gates belong
      // to which skill.
      return SILENT_PASS;
    }
    const requiredGates: string[] = requiredGatesRaw.filter((g): g is string => typeof g === 'string');
    if (requiredGates.length === 0) {
      return SILENT_PASS;
    }

    const ledger: Record<string, unknown> =
      typeof state.gates === 'object' && state.gates !== null ? state.gates : {};

    const failures: string[] = [];
    for (const gateName of requiredGates) {
      const entry = ledger[gateName];
      if (typeof entry !== 'object' || entry === null) {
        failures.push(`  - "${gateName}": MISSING — gate.py was never run for this gate.`);
        continue;
      }
      const verdict = entry as GateVerdict;
      if (verdict.status !== 'pass') {
        const status = typeof verdict.status === 'string' ? verdict.status : 'unknown';
        const detail = typeof verdict.detail === 'string' && verdict.detail ? `\n    detail: ${verdict.detail}` : '';
        const violations = formatViolations(verdict.violations);
        failures.push(`  - "${gateName}": status=${status}${detail}${violations}`);
      }
    }

    if (failures.length === 0) {
      return SILENT_PASS;
    }

    const skillName = typeof run.skill === 'string' ? run.skill : '<unknown skill>';
    const runId = typeof run.id === 'string' ? run.id : '<unknown run>';

    const message = [
      `GATE ENFORCEMENT BLOCKED THIS STOP (run "${runId}", skill "${skillName}").`,
      `The following required gate(s) did not pass:`,
      ...failures,
      '',
      'To resolve, run the missing/failing gate(s) and re-check, e.g.:',
      ...requiredGates.map(
        (g) => `  python3 src/scripts/gate.py ${g} <target-file> --json`,
      ),
      '',
      'Then continue the run. This Stop hook will pass once every required gate in',
      '.academic-helper/session-state.json > gates reports status "pass".',
    ].join('\n');

    return { continue: false, systemMessage: message };
  } catch {
    // Any unexpected exception in the hook itself is an infrastructure
    // problem — fail open rather than trap the session.
    return SILENT_PASS;
  }
}
