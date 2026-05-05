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

---

## `src/agents/section-writer.md`

- **Status:** modify (load `AUTHOR_VOICE.md` per Phase 10.2 of the plan — primary inbound consumer reading styleFingerprint on every paragraph write).
- **Inputs:**
  - `section` — section spec (title, description, argument role, suggested sources, paragraph count)
  - `sectionIndex`, `totalSections`, `thesis`, `articleStructure`, `citationStyle`, `targetLanguage`, `tools`, `priorSectionTexts`, `outlineOverview`
  - `styleFingerprint` — researcher's writing style profile (loaded from `.academic-helper/profile.md` directly from disk, not passed in prompt)
  - `.academic-helper/sources.json` — bibliographic source registry (written by deep-reader)
  - `.academic-helper/evidence-ownership.json` — evidence ownership map (written by architect)
  - `plugins/academic-writer/words.md` — linking words reference
  - Per-paragraph: Agentic-Search-Vectorless query results (mandatory before every paragraph)
  - Auditor subagent verdict (`VERDICT: PASS` / `FAIL` / `PARTIAL`) — hard gate before proceeding to next paragraph
- **Outputs:**
  - Prose paragraphs for the section with inline citations in the requested `citationStyle` format
  - Per-paragraph skills log (draft, style compliance score, grammar issues, academic language, language purity violations, anti-AI score, repetition fixes, audit verdict)
  - Section summary: paragraph count, total words, avg style compliance, avg anti-AI score, audit rewrite count
  - Appends to `evidenceOwnership.claimsRegistry` in `.academic-helper/evidence-ownership.json` after each approved paragraph
- **Inbound references (grep result):**
  - `src/skills/write/SKILL.md` — spawns one section-writer subagent per section in parallel (Step 7)
  - `src/skills/edit/SKILL.md` — spawns section-writer subagents for Mode A (section-level edit)
  - `src/skills/edit-section/SKILL.md` — spawns section-writer for rewrites, expansions, new paragraphs
  - `src/agents/architect.md` — produces the section specs that section-writer consumes
  - `src/agents/synthesizer.md` — reviews section-writer output for coherence
  - `src/agents/auditor.md` — per-paragraph citation hard gate coordinated by section-writer
  - `src/agents/memory/section-writer/MEMORY.md` — agent persistent memory
  - `src/agents/memory/auditor/MEMORY.md` — references section-writer context
  - `src/skills/write/references/style-fingerprint-rubric.md` — rubric used in Skill 2 of pipeline
  - `src/skills/health/SKILL.md` — health check references section-writer
  - `src/skills/help/SKILL.md` — help mentions section-writer
  - `CLAUDE.md` — agents table documents section-writer
- **Migration plan:** Per Phase 10.2, section-writer must load `AUTHOR_VOICE.md` at paragraph-write time. Currently the agent loads `styleFingerprint` from `.academic-helper/profile.md`. The migration adds a second load step: after loading the fingerprint, also load the v1 `AUTHOR_VOICE.md` (or the equivalent CandleKeep page once the Academic Helper plugin adopts CandleKeep storage). The `styleFingerprint` object currently drives all 10 Skill 2 dimensions; v1 must clarify whether `AUTHOR_VOICE.md` replaces `styleFingerprint` entirely or supplements it with additional voice constraints (banned terms, preferred phrases). This must be resolved in the Phase 10.2 task spec before coding begins. Until resolved, section-writer is an inbound consumer but not yet a blocker.

---

## `src/skills/write/SKILL.md`

- **Status:** modify (Phase 10.2: load AUTHOR_VOICE.md as voice source for the write pipeline).
- **Inputs:**
  - Researcher profile from `.academic-helper/profile.md` (including `styleFingerprint` object)
  - User-supplied subject, article language (`targetLanguage`), target word count
  - Source selection from CandleKeep (if enabled) or `profile.sources` array
  - Deep-reader output (`.academic-helper/sources.json`, vectorless-ingested documents)
  - Architect outputs (thesis, outline, `.academic-helper/evidence-ownership.json`)
- **Outputs:**
  - `articles/<slug>.md` — complete article in Markdown
  - `articles/<slug>.docx` — formatted Word document (via `generate-docx.py`)
  - Researcher-facing scorecard (structure, argument logic, citation completeness, source coverage, writing quality, academic conventions — scored 1–10 each)
- **Inbound references (grep result):**
  - `CLAUDE.md` — documents `/academic-writer:write` as user-facing command
  - `src/agents/section-writer.md` — loaded and spawned in parallel by this skill (Step 7)
  - `src/agents/synthesizer.md` — spawned for synthesis review (Step 8)
  - `src/agents/deep-reader.md` — spawned for source deep-read (Step 3)
  - `src/agents/architect.md` — spawned for thesis and outline (Steps 4 and 5)
- **Migration plan:** Per Phase 10.2, the write skill's "Load Profile" step (currently prints a styleFingerprint summary to confirm loading) must be extended to also load and confirm `AUTHOR_VOICE.md`. The `styleFingerprint` summary print should include a line confirming the voice profile is loaded. The v1 `AUTHOR_VOICE.md` should be passed (or made available on disk) so section-writer subagents can read it directly in the same way they currently read `styleFingerprint` from `.academic-helper/profile.md`. If Academic Helper moves to CandleKeep storage for the voice profile (mirroring hebrew-book-producer), the write skill's load step must also cache the CandleKeep voice pages to a local `.academic-helper/author-voice.md` file before spawning section-writers.

---

## `src/skills/edit/SKILL.md`

- **Status:** modify (Phase 10.2: load AUTHOR_VOICE.md).
- **Inputs:**
  - Researcher profile from `.academic-helper/profile.md` (including `styleFingerprint`)
  - Existing article — provided as a file path (`.docx` or `.md`) or pasted text
  - Edit request describing what to change (section, citations, tone, structure, argument, cut/expand, or full review)
- **Outputs:**
  - Revised article paragraphs/sections (via section-writer subagents for Modes A, D, E, F)
  - Diff summary: what changed per section and citation counts
  - Optionally: updated `.docx` export (using the same DOCX generation as `write/SKILL.md` Step 9)
- **Inbound references (grep result):**
  - `CLAUDE.md` — documents `/academic-writer:edit` as user-facing command
  - `src/agents/section-writer.md` — spawned for Mode A (section-level edit) and Mode D (restructure — new sections)
  - `src/agents/auditor.md` — spawned for Mode B (citation fix)
  - `src/agents/synthesizer.md` — spawned for Mode D (restructure transitions) and Mode G (full review)
  - `src/skills/write/SKILL.md` — edit's pre-flight guard redirects here when an article file already exists
- **Migration plan:** Per Phase 10.2, update the "Load Profile" step at the top of the skill: after loading `styleFingerprint`, also load the v1 `AUTHOR_VOICE.md` (or cache from CandleKeep if that storage path is adopted). The fingerprint summary confirmation print should include a voice-profile confirmation line. Pass or make available the voice profile to section-writer subagents spawned in Mode A. Modes C (tone adjustment) and G (full review) read `styleFingerprint` explicitly — both must also reference `AUTHOR_VOICE.md` constraints (banned phrases, register) after v1 lands.

---

## `src/skills/edit-section/SKILL.md`

- **Status:** modify (Phase 10.2: load AUTHOR_VOICE.md).
- **Inputs:**
  - Researcher profile from `.academic-helper/profile.md` (including `styleFingerprint`)
  - Target section — identified by title, number, or pasted text; parsed from `.docx` or `.md` file
  - Edit instruction: rewrite, expand (with new evidence), cut, fix citations, adjust style, add/remove paragraph
  - Adjacent sections — parsed for repetition checking and transition context
- **Outputs:**
  - Revised section text with change summary: what changed per paragraph, citation counts, skills scores (style compliance, grammar, repetition, citation audit)
  - Optionally: updated `.docx` export of the full article
- **Inbound references (grep result):**
  - `CLAUDE.md` — documents `/academic-writer:edit-section` as user-facing command
  - `src/agents/section-writer.md` — spawned for rewrites, expansions, new paragraphs
  - `src/agents/auditor.md` — spawned per paragraph for citation fix mode
  - `src/skills/edit/SKILL.md` — references edit-section as the faster alternative for single-section changes
  - `src/skills/help/SKILL.md` — help mentions edit-section
- **Migration plan:** Per Phase 10.2, update the "Load Profile" step: after loading `styleFingerprint`, also load the v1 `AUTHOR_VOICE.md`. The style adjustment flow (re-read `styleFingerprint` → score 10 dimensions → fix ≤3 dimension scores → use `representativeExcerpts`) must be extended to also check against `AUTHOR_VOICE.md` banned phrases and preferred phrases after v1 lands. Because edit-section is the most frequently-invoked edit path, this is the highest-impact Phase 10.2 change — it should be the first skill updated in that phase.

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
| `src/agents/section-writer.md` | Modify to load AUTHOR_VOICE.md per Phase 10.2; primary inbound voice consumer |
| `src/skills/write/SKILL.md` | Modify profile load step to include AUTHOR_VOICE.md per Phase 10.2 |
| `src/skills/edit/SKILL.md` | Modify profile load step to include AUTHOR_VOICE.md per Phase 10.2 |
| `src/skills/edit-section/SKILL.md` | Modify profile load step + style check to include AUTHOR_VOICE.md per Phase 10.2; highest-impact edit path — update first |
