# Checkpoint schema (`:voice` resume state)

> Loaded on demand by `voice` SKILL.md and by the `voice-interviewer` / `voice-distiller` /
> `voice-calibrator` agents.

## Location

`.academic-helper/voice-checkpoint.json` — project-local, gitignored, alongside `profile.md`,
`session-state.json`, `sources.json`, and `evidence-ownership.json`. This is the plugin's existing
convention for structured per-project state, so the interview pipeline follows it rather than
inventing a second state directory. (`.voice/` continues to hold the raw artifacts — transcripts,
fingerprint, audit — the checkpoint is the durable index over them.)

## Why this file exists

Before this design, the only durable record of interview progress was the per-session transcript
files under `.voice/interview/`. Two things broke resumability:

1. Nothing recorded progress **within** a session as it happened — a crash or context loss mid-session
   meant the next Claude session had to re-derive state by re-reading and re-parsing every transcript
   file, and had no single place to answer "where did we stop?" without that reconstruction.
2. Nothing recorded that a session was ever **compressed into `AUTHOR_VOICE.md`** — `voice-distiller`
   was invoked after session 1 and after session 7 only, so sessions 2–6 could be fully answered in
   the transcript and never make it into the profile at all if the user stopped before session 7.

The checkpoint fixes both: it is written after every answered question (not every session), and it
tracks distillation state per session so the orchestrator always knows exactly what still needs to
be folded into `AUTHOR_VOICE.md`.

## Schema

```json
{
  "version": 1,
  "mode": "full",
  "startedAt": "2026-08-07T10:03:00Z",
  "lastUpdated": "2026-08-07T10:41:12Z",
  "totalSessions": 7,
  "mvvSessionTarget": 3,
  "mvvReached": false,
  "mvvReachedAt": null,
  "questionsAnswered": 20,
  "sessions": {
    "01": {
      "category": "beliefs",
      "status": "complete",
      "questionsAsked": 13,
      "lastQuestionId": "01-13",
      "startedAt": "2026-08-07T10:03:00Z",
      "completedAt": "2026-08-07T10:19:44Z",
      "distilledAt": "2026-08-07T10:20:01Z"
    },
    "02": {
      "category": "writing-practices",
      "status": "in_progress",
      "questionsAsked": 7,
      "lastQuestionId": "02-07",
      "startedAt": "2026-08-07T10:22:00Z",
      "completedAt": null,
      "distilledAt": null
    },
    "03": { "category": "aesthetics", "status": "not_started", "questionsAsked": 0, "lastQuestionId": null, "startedAt": null, "completedAt": null, "distilledAt": null },
    "04": { "category": "personality", "status": "not_started", "questionsAsked": 0, "lastQuestionId": null, "startedAt": null, "completedAt": null, "distilledAt": null },
    "05": { "category": "structure", "status": "not_started", "questionsAsked": 0, "lastQuestionId": null, "startedAt": null, "completedAt": null, "distilledAt": null },
    "06": { "category": "refusals", "status": "not_started", "questionsAsked": 0, "lastQuestionId": null, "startedAt": null, "completedAt": null, "distilledAt": null },
    "07": { "category": "warning-signs", "status": "not_started", "questionsAsked": 0, "lastQuestionId": null, "startedAt": null, "completedAt": null, "distilledAt": null }
  },
  "lastCalibration": null,
  "lastSyncedAt": null
}
```

## Field notes

- `status` is one of `not_started | in_progress | complete`.
- `lastQuestionId` is `"<session>-<question index>"`, e.g. `"02-07"` for the 7th question asked in
  session 2 (index is by questions actually asked, not by seed-bank position — adaptive sessions
  drop or add questions, so the index is sequential-as-asked, not a lookup key into
  `questions-academic.md`).
- `distilledAt` is set only once `voice-distiller --session N` has run for that session and
  written to `AUTHOR_VOICE.md`. A session can be `"complete"` with `distilledAt: null` for the
  brief window between the interviewer finishing and the orchestrator invoking the distiller —
  this should never persist across a stop/resume boundary; see "Write ordering" below.
- `mvvReached` / `mvvReachedAt` — set once by the orchestrator when session `mvvSessionTarget`
  (session 3) first reaches `status: complete` and its distiller pass has run. Never unset.
- `lastCalibration` — `{ "afterSession": 3, "score": 7.2, "at": "..." } | null`.
- `lastSyncedAt` — ISO timestamp of the last successful `voice-sync push`, or `null`.

## Who writes it

- **`voice-interviewer`** updates `sessions.<N>.questionsAsked`, `lastQuestionId`, `status`
  (`not_started` → `in_progress` on the first question, `in_progress` → `complete` on
  `<!-- session complete -->`), `startedAt`/`completedAt`, and the top-level `questionsAnswered`
  counter and `lastUpdated` — **after every single answered question**, not just at session end.
  This is a full Read-modify-Write of the checkpoint file (the agent's `Write` tool is sufficient;
  no separate script is needed to mutate JSON — the interviewer parses and re-serializes the file
  itself, the same way `architect` writes `evidence-ownership.json`).
- **The `voice` skill (orchestrator)** creates the checkpoint on first run if missing, sets
  `sessions.<N>.distilledAt` after invoking `voice-distiller --session N`, sets `lastCalibration`
  after `voice-calibrator`, sets `lastSyncedAt` after `voice-sync push`, and sets `mvvReached`.

## Write ordering (crash-safety)

Because the interviewer writes the checkpoint after every question, a crash mid-session loses at
most one unwritten answer (already appended to the transcript — see below — even if the checkpoint
write that follows it is interrupted). Order per question is: **(1)** append the Q/A pair to
`.voice/interview/0N-<category>.md`, **(2)** update and write the checkpoint. If a resume finds the
transcript one question ahead of the checkpoint's `lastQuestionId` (checkpoint write was
interrupted), trust the transcript — re-derive `questionsAsked`/`lastQuestionId` from it and
continue. The transcript is always the source of truth for *content*; the checkpoint is the fast
index for *where to resume and what still needs distilling*.

## Resuming with no memory

A fresh Claude session with zero prior context can resume correctly using only this file plus the
transcripts it points at:

1. Read `.academic-helper/voice-checkpoint.json`. If missing, this is session 1 / first run.
2. Find the first session with `status != "complete"`. If none, all 7 are done — report full
   completion, offer recompress/audit/sync.
3. If that session's `status == "in_progress"`, read `.voice/interview/0N-<category>.md`, confirm
   `lastQuestionId` matches the transcript's last `## Q<n>` heading (reconcile per "Write ordering"
   above if not), and resume asking questions from there — the interviewer's own resume rule
   ("never ask a question that already has an answer in the transcript") still applies as the
   second line of defense.
4. If that session's `status == "not_started"`, start it fresh.
5. Check every prior `complete` session for `distilledAt: null` — if any exist (e.g. the
   orchestrator crashed between the interviewer finishing and the distiller running), run
   `voice-distiller --session N` for each of them, in order, before starting new interview
   questions. This is what guarantees a stop-at-any-point never leaves answered questions un-folded
   into `AUTHOR_VOICE.md`.
