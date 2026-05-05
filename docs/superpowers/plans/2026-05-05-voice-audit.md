# Voice Infrastructure Audit — Academic Helper
**Date:** 2026-05-05
**Phase:** 0.1 — Pre-work before voice-profile v1 implementation

---

## Summary

Academic Helper has one primary voice/style agent (`style-miner`), invoked internally by the `learn` and `feedback` skills, and run inline during `init` (Phase 3 — Style Analysis). There is no user-facing `/voice` or `/style-miner` slash command today. The `init` skill performs style fingerprinting directly (not by delegating to `style-miner`), making the agent's role secondary — it is spawned only when re-analysis is needed.

---

## `src/agents/style-miner.md`

- **Status:** rewrite as `voice-miner.md` with v1 contract; leave `style-miner.md` in place with a deprecation note pointing to `voice-miner.md` for one release.
- **Inputs:**
  - `newArticles` — list of filenames in `past-articles/` to analyze
  - `currentFingerprint` — existing style fingerprint from `.academic-helper/profile.md` (may be null)
  - `targetLanguage` — article language
  - Shared Hebrew baseline from CandleKeep (`cmomjonvy0fdmk30zwef79c48`, chapter `08-style-fingerprint-baseline`)
  - Agent memory: `.academic-helper/agent-memory/style-miner/MEMORY.md`
- **Outputs:**
  - `mergedFingerprint` — full 30+ dimension JSON fingerprint (written back to `.academic-helper/profile.md` by the calling skill)
  - `diff` — per-dimension change report
  - `newExcerpts` — 5 representative passages
  - `distinctiveTraits` — human-readable summary of distinctive patterns
  - `statistics` — article count, word count, sentence count, paragraph count, changed-dimension count
- **Inbound references (grep result):**
  - `src/skills/learn/SKILL.md` — spawns `style-miner` as a subagent
  - `src/skills/feedback/SKILL.md` — optionally spawns `style-miner` for broad voice drift
  - `src/agents/memory/style-miner/MEMORY.md` — agent's persistent memory file
  - `plugins/academic-writer/agents/style-miner.md` — built copy (mirrors src/)
  - `plugins/academic-writer/skills/learn/SKILL.md` — built copy reference
  - `plugins/academic-writer/skills/feedback/SKILL.md` — built copy reference
  - `plugins/academic-writer/commands/learn.md` — built copy reference
  - `plugins/academic-writer/commands/feedback.md` — built copy reference
  - `src/skills/init/references/profile-schema.md` — documents fingerprint schema
  - `docs/superpowers/plans/2026-05-05-voice-profile-v1.md` — plan document
  - `docs/reviews/2026-05-01-plugin-review.md` — review document
  - `.removal-log/cognetivy-removal-20260501-141633.jsonl` — audit log
  - `CLAUDE.md` — agents table lists `style-miner.md`
- **User-facing slash command today:** None. `style-miner` is an internal subagent only. No `/style-miner` or `/voice` command exists.
- **Migration plan:** In Phase 2, create `src/agents/voice-miner.md` with the v1 AUTHOR_VOICE.md contract (CandleKeep output, structured pages); add a deprecation notice at the top of `style-miner.md` pointing to `voice-miner.md`; update `learn` and `feedback` skills to spawn `voice-miner` instead of `style-miner`.

---

## `src/skills/init/SKILL.md` — Style Analysis Phase (Phase 3)

- **Status:** modify to invoke the new `voice-miner` in Stage 1 (Phase 3 of this plan).
- **Inputs:**
  - Past articles in `past-articles/`
  - CandleKeep Hebrew baseline (`cmomjonvy0fdmk30zwef79c48`)
  - Researcher's answers to 4 profile questions
- **Outputs:**
  - `.academic-helper/profile.md` with `styleFingerprint` + `articleStructure` sections
- **Inbound references (grep result):**
  - `CLAUDE.md` — documents `/academic-writer:init` slash command
  - `src/skills/init/references/profile-schema.md` — documents the fingerprint schema
  - `src/skills/init/references/integration-setup.md` — referenced inline
- **User-facing slash command today:** `/academic-writer:init` (user-invocable: true)
- **Migration plan:** Replace Phase 3 (Style Analysis) inline implementation with a call to the new `voice-miner` agent; wire output to the v1 AUTHOR_VOICE.md profile page structure in CandleKeep.

---

## Additional voice-related files found (not in original list)

### `src/skills/learn/SKILL.md`
Spawns `style-miner` as subagent when user adds new articles. Will need updating in Phase 2 to reference `voice-miner`.

### `src/skills/feedback/SKILL.md`
Optionally spawns `style-miner` when feedback indicates broad voice drift. Will need updating in Phase 2 to reference `voice-miner`.

### `src/agents/memory/style-miner/MEMORY.md`
Agent persistent memory file. Keep as-is; rename to `voice-miner/MEMORY.md` when `style-miner.md` is deprecated.

### `src/skills/init/references/profile-schema.md`
Documents the current `styleFingerprint` schema. Will need updating in Phase 2 to reflect v1 AUTHOR_VOICE.md schema.

### `src/skills/write/references/style-fingerprint-rubric.md`
Style fingerprint rubric used by the section-writer. Should be reviewed and aligned with v1 voice profile contract in Phase 2.

---

## Cross-project shared infrastructure

Both projects share the **Hebrew Linguistic Reference** CandleKeep book (`cmomjonvy0fdmk30zwef79c48`). The `style-miner` agent explicitly documents this: *"The fingerprint baseline lives in chapter 08-style-fingerprint-baseline"* and *"The same book is also loaded by the `hebrew-book-producer` plugin so both share one source of truth."* The v1 design must preserve this shared baseline.

---

## Decision summary

| File | v1 Decision |
|------|-------------|
| `src/agents/style-miner.md` | Rewrite as `voice-miner.md`; leave `style-miner.md` with deprecation notice for one release |
| `src/skills/init/SKILL.md` | Modify Phase 3 to invoke `voice-miner` |
| `src/skills/learn/SKILL.md` | Update agent reference from `style-miner` → `voice-miner` (Phase 2) |
| `src/skills/feedback/SKILL.md` | Update agent reference from `style-miner` → `voice-miner` (Phase 2) |
| `src/agents/memory/style-miner/MEMORY.md` | Rename to `voice-miner/MEMORY.md` at deprecation point |
| `src/skills/init/references/profile-schema.md` | Update schema to v1 AUTHOR_VOICE.md contract (Phase 2) |
