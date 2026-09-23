---
name: voice
description: "Stage 2 of the voice subsystem. Run `:voice` to resume or start a 7-session adversarial interview seeded by the past-articles fingerprint — progress is checkpointed after every question, so `:voice` is always safe to re-run and always picks up where you left off. Sub-actions for explicit init/continue, restart, jump-to-session, recompress, audit, quick mode, sync, and status. Use when the user wants to deepen their voice profile beyond what the corpus reveals."
user-invocable: true
disable-model-invocation: true
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Agent]
metadata: {author: "Yotam Fromm", version: "0.3.0"}
---

# voice

Top-level entry to the Stage 2 voice-deepening pipeline. Sub-actions inferred from natural language
or specified explicitly. **The pipeline is resumable by design**: every answered question is
checkpointed, `AUTHOR_VOICE.md` is regenerated after every session (not only at the end), and
stopping at any point after session 3 leaves a genuinely usable profile — see "Minimum viable
voice" below.

## Author key

Voice sync is keyed by the profile.md `author_key` field (`.academic-helper/profile.md`), not by a
free-text writer name. CandleKeep is the canonical cross-project store: per the plugin's no-`$HOME`
rule (see root `CLAUDE.md`), the plugin cannot write a local cross-project file outside the current
project, so CandleKeep — under a book titled `Voice Profile — <author_key>` — is the only
cross-project persistence mechanism. `${CLAUDE_PLUGIN_ROOT}/skills/voice/voice-sync.sh` resolves `author_key` from
`.academic-helper/profile.md` and fails loudly (exit 1, no silent fallback) if it is missing; run
`/academic-writer:init` to set it.

## Checkpoint state

Progress lives in `.academic-helper/voice-checkpoint.json`, updated after **every answered
question** (not every session) — the `voice-interviewer` agent writes it directly. Full schema,
field semantics, and the crash-safety write ordering: `references/checkpoint-schema.md`. Read that
file before touching the checkpoint format.

## Sub-actions

- `:voice` (no args) — **default entry point.** Detect checkpoint state and act accordingly:
  - No checkpoint / all sessions `not_started` → same as `:voice init`.
  - Some session `in_progress` or incomplete → **resume**, showing the user exactly where they are
    first (see "Resume behavior" below), then continue that session.
  - All 7 sessions `complete` → report full completion; offer `recompress` / `audit` / `sync`.
- `:voice init` — explicit alias for the fresh-start branch above.
- `:voice continue` — explicit alias for the resume branch above.
- `:voice --restart` — archive the current checkpoint + transcripts and start over from session 1.
  Destructive; requires explicit user confirmation naming what will be discarded.
- `:voice --session N` — jump directly to session N (e.g. to revise an already-completed session,
  or skip ahead). Updates the checkpoint's `sessions.<N>.status` to `in_progress` if it was
  `not_started`; re-entering a `complete` session appends further Q&A rather than clearing it.
- `:voice recompress` — re-distill all transcripts + fingerprint into `AUTHOR_VOICE.md`.
- `:voice audit` — run rule-coverage check against the corpus.
- `:voice quick` — adaptive short path (skips sessions 4 and 7, caps at 8 questions per session,
  one calibration at end, ~43 prompts total).
- `:voice sync` — push local `AUTHOR_VOICE.md` to CandleKeep (pulls first to avoid clobber).
- `:voice status` — list completed sessions, MVV status, last calibration score, last sync stamp,
  and whether `AUTHOR_VOICE.md` currently passes the stub check (see "Stub definition" below).

## Resume behavior

Before doing anything else, `:voice` and `:voice continue` print a one-line status derived from the
checkpoint, e.g.:

> "Resuming: session 3 of 7 (Aesthetics), 12 of ~40 questions answered so far. Last activity
> 2026-08-06. Continuing session 3..."

or, if a prior session finished but was never distilled (interrupted mid-orchestration):

> "Resuming: session 2 is complete but wasn't folded into AUTHOR_VOICE.md yet — running
> voice-distiller for session 2 first, then continuing to session 3."

This status line is not optional — a fresh Claude session with no memory of prior runs must be able
to read it and understand exactly what happens next without asking the user "where were we?".

## Minimum viable voice (MVV)

**Session 3 is the finish line that counts.** After session 3 completes (Beliefs → Writing
Practices → Aesthetics, ~40 questions, the highest-yield categories — see "Question bank"), the
mid-point calibrator already runs and folds a rule-coverage audit into `AUTHOR_VOICE.md`. The first
time this happens, tell the user explicitly:

> "Minimum viable voice reached (3 of 7 sessions, rule-coverage: X.X/10). AUTHOR_VOICE.md is a real,
> usable profile now — stopping here is a legitimate finish, not an abandoned interview. Sessions
> 4-7 (Personality, Structure, Refusals, Warning Signs) sharpen it further whenever you have time;
> `:voice` will resume exactly here."

Set `mvvReached: true` in the checkpoint the first time this fires; never re-announce it on later
resumes. This is the direct fix for the abandonment pattern this pipeline is known for: stopping at
session 2 previously left a stub because nothing was ever distilled for it and nothing told the user
they'd done anything worthwhile. Now sessions 1 and 2 already each produce a real (if partial and
explicitly-labeled) profile — MVV at session 3 is just the point where the profile also gets its
first rule-coverage validation pass.

## Question bank and miner pre-fill

`questions-academic.md` is the seed bank. Two burden-reduction mechanisms, both already required of
`voice-interviewer` (see that agent's file) — this skill just names them:

1. **Confirm, don't compose, when the fingerprint already knows.** Before asking a `[T]`
   (terminology/phrase-bank) question or any question whose seed text references a corpus pattern,
   check `.voice/fingerprint.md` for a matching signal (phrase frequency, banned-word candidates,
   citation patterns, structural signals). If one exists, ask the user to confirm/reject/refine it
   instead of composing an answer from nothing — confirmation is a few seconds; composition is not.
2. **The bank itself is trimmed.** Near-duplicate questions across sessions were merged or cut
   during this redesign — see the bank file's changelog note at its top for the specific cuts and
   why. Total question count per session is unchanged (soft floor 12, hard cap 18 — same as before);
   what changed is how many of those 12-18 are cheap confirmations versus cold composition.

## Stub definition

`AUTHOR_VOICE.md` is a **stub** (not yet a usable voice profile) if the template placeholders were
never replaced, or if every section is empty, or if total content across all sections is below a
20-word floor. It is a **real, usable profile** — even if partial and only through session 1 or 2 —
the moment at least one section has real content past that floor. Full definition, rationale, and
the deterministic implementation: `references/stub-definition.md`. The check itself:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-voice-populated.py" AUTHOR_VOICE.md --json
```

Any other gate in this plugin that needs to know whether `AUTHOR_VOICE.md` is usable should call
this script rather than re-deriving the rule.

## Workflow

### `:voice` / `:voice init` / `:voice continue`
1. Read `.academic-helper/voice-checkpoint.json`. If missing, create it (all 7 sessions
   `not_started`) — this is the fresh-start path; read `.voice/fingerprint.md` first and if missing
   or `> NEEDS CORPUS`, tell the user to run `:init` first and stop.
2. Print the resume status line (see "Resume behavior").
3. If any prior `complete` session has `distilledAt: null` (interrupted orchestration), run
   `voice-distiller --session N` for each, oldest first, before proceeding.
4. Confirm the user has time for at least one session (~15 questions × ~30s = ~10 min).
5. Invoke `voice-interviewer` agent for the target session (next incomplete one, or the one already
   `in_progress`). Wait for `<!-- session complete -->`. The interviewer itself updates the
   checkpoint after every question — see `references/checkpoint-schema.md`.
6. **Run `voice-distiller --session N` immediately** — every session, not only session 1 and 7. This
   is what makes stopping at any session leave usable, non-stub output. Set
   `sessions.<N>.distilledAt` in the checkpoint.
7. Run `voice-calibrator` only after session 3 and after session 7 (mid-point + final).
8. If this is the first time session 3 has completed, announce MVV (see above) and set
   `mvvReached: true`.
9. Run `${CLAUDE_PLUGIN_ROOT}/skills/voice/voice-sync.sh push` and check its exit code — a non-zero
   exit is a real failure (see the script's own header), not a silent no-op; surface it rather than
   continuing as if the push happened.
10. If not all 7 sessions are done, ask: "Continue with session N+1, or stop here? `:voice` resumes
    automatically whenever you come back."

### `:voice --restart`
1. Confirm with the user, naming what will be discarded (checkpoint + all `.voice/interview/*.md`
   transcripts; `AUTHOR_VOICE.md` and `.voice/fingerprint.md` are NOT touched — the corpus
   fingerprint and any already-distilled profile content survive a restart).
2. On confirmation, move `.academic-helper/voice-checkpoint.json` and `.voice/interview/` to
   `.voice/legacy/restart-<timestamp>/` (archive, never delete outright).
3. Proceed as `:voice init` from a clean checkpoint.

### `:voice --session N`
1. Read the checkpoint. If session N is `not_started`, start it directly (out of order is allowed —
   the interviewer does not require prior sessions to be complete, only that it reads prior
   transcripts for context per its own resume rule).
2. If session N is already `complete`, tell the user it will be re-entered for revision (new
   questions appended, not a rewrite) and confirm before proceeding.
3. Otherwise identical to step 5 onward of the main workflow, scoped to session N.

### `:voice recompress`
1. Run `voice-distiller --recompress` (full pass, all transcripts + fingerprint).
2. Run rule-coverage check inline; write `.voice/audit.md`.
3. Run `${CLAUDE_PLUGIN_ROOT}/skills/voice/voice-sync.sh push` and check its exit code — a non-zero
   exit is a real failure, not a silent no-op.

### `:voice audit`
1. Read `AUTHOR_VOICE.md` and corpus.
2. For each rule, search corpus for evidence. Write `.voice/audit.md` with score and flagged rules.
3. If score < `thresholds.json: voice.ruleCoverage.block`, refuse to recompress until user removes or evidences flagged rules.

### `:voice quick`
1. Same as `:voice init`, but pass `--quick` to interviewer (cap 8 questions/session, skip sessions
   4 and 7). Set `checkpoint.mode: "quick"`.
2. Stamp `[quick]` marker in `AUTHOR_VOICE.md` and `.voice/audit.md`.
3. Single calibration at the end (after session 6 in quick numbering, which is the last).
4. Tell user: "Quick profile created. Run `:voice continue --upgrade` to fill in missed sessions."

### `:voice sync`
1. Run `${CLAUDE_PLUGIN_ROOT}/skills/voice/voice-sync.sh pull` (last-write-wins by `> Updated` stamp)
   and check its exit code — a non-zero exit is a real failure, not a silent no-op.
2. Run `${CLAUDE_PLUGIN_ROOT}/skills/voice/voice-sync.sh push` and check its exit code likewise.
3. Report which side won.

### `:voice status`
1. Read the checkpoint: show session table (status, questions asked per session), `questionsAnswered`
   total, `mvvReached`.
2. Run `check-voice-populated.py --json` on `AUTHOR_VOICE.md`; report populated vs stub.
3. Show `.voice/audit.md` head if present.
4. Show last `> Updated` stamp from `AUTHOR_VOICE.md`.
5. Show `.voice/.candlekeep-id` presence and checkpoint `lastSyncedAt`.

## Hard rules

- Calibrator runs ONLY after sessions 3 and 7 (or after final session in quick mode).
- Sessions 1, 2, 4, 5, 6 invoke distiller too — **every** completed session gets distilled
  immediately, not only 1 and 7. This is the load-bearing fix in this design; do not regress it.
- Sync is push-only on writes; explicit `:voice sync` is the only place that pulls.
- Quick mode is reversible: `:voice continue --upgrade` runs the missed sessions.
- The checkpoint file is the resume source of truth; transcripts are the content source of truth.
  Never let one drift from the other silently — reconcile per `references/checkpoint-schema.md`.
