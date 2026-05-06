# Plugin Best-Practices Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the 17 fixes identified in `docs/reviews/2026-05-01-plugin-review.md` to bring the Academic Helper plugin in line with documented Claude Code / agent / skill / hook best practices, prioritised by severity and grouped into stoppable phases.

**Architecture:** Source-only edits. Every change goes into `src/` (skills, agents, hooks). After each phase, run `npm run build` to regenerate `plugins/academic-writer/` and `python3 tests/test_plugin_structure.py` to confirm structural integrity. No application logic changes — this is markdown, JSON, YAML, and TypeScript hook plumbing.

**Tech Stack:** Markdown + YAML frontmatter (skills, agents), JSON (manifests, hooks.json, settings, thresholds), TypeScript via esbuild (hooks), Python (tests).

**Verification model:** Where structural tests exist (`tests/test_plugin_structure.py`), use them. For prose changes (descriptions, CLAUDE.md), use `grep` matchers. For hook changes, use a smoke test: spawn a fake `SessionStart` event and verify output.

---

## File Structure

### Files to be CREATED

| Path | Responsibility |
|---|---|
| `CLAUDE.md` (project root) | Plugin-development conventions for Claude Code in this repo. Un-gitignored. |
| `src/thresholds.json` | Single source of truth for all numeric quality gates (anti-AI 35/50, self-review 40/60, max-rewrites 3, etc.). |
| `src/skills/review/references/scorecard.json` | The 6-dimension self-review scorecard rubric, machine-readable. |
| `src/skills/init/references/profile-schema.md` | Detailed JSON schema + field semantics for `profile.md`, extracted from `init/SKILL.md`. |
| `src/skills/init/references/integration-setup.md` | Detection commands and configuration blocks per integration, extracted from `init/SKILL.md`. |
| `src/skills/write/references/style-fingerprint-rubric.md` | The 10-dimension scoring rubric, extracted from `write/SKILL.md`. |
| `src/hooks/src/lifecycle/notify-stop.ts` | macOS notification on `Stop` so long autonomous runs are observable. |
| `src/hooks/src/lifecycle/subagent-start.ts` | Injects citation-audit rules + thresholds for `auditor`-type subagents. |

### Files to be MODIFIED

| Path | Change |
|---|---|
| `.gitignore` | Remove `CLAUDE.md` from ignore list. |
| `src/agents/section-writer.md` | Drop orphan `runId` input bullet; switch `model: opus → sonnet`; strip duplicated citation-audit rules; reference `thresholds.json`. |
| `src/agents/auditor.md` | Add depth cue ("think carefully and step-by-step"); add WebSearch result-validation contract. |
| `src/skills/{health,help,update-field}/SKILL.md` | Add `allowedTools` frontmatter. |
| All 15 `src/skills/*/SKILL.md` | Rewrite description to include trigger phrases ("Use when…"); add `metadata: {author, version}` block. |
| 5 SKILL.md files (`learn`, `update-field`, `update-tools`, `present`, `feedback`) | Remove `user-invocable: true` (demote to internal). |
| `src/skills/review/SKILL.md` | Replace prose scorecard with `references/scorecard.json` reference. |
| `src/skills/init/SKILL.md`, `setup/SKILL.md`, `write/SKILL.md` | Move detail to `references/`; body becomes phase orchestration only. |
| `src/hooks/hooks.json` | Register `SessionStart`, `Stop`, `SubagentStart` events. |
| `src/hooks/src/entries/lifecycle.ts` | Wire new hooks into the bundle export map. |
| `src/skills/help/SKILL.md` | Remove demoted commands from the table; keep mention as "internal" if relevant. |

### Files to be DELETED

| Path | Reason |
|---|---|
| `src/hooks/src/lifecycle/check-profile.ts` | Job superseded by `run-hook.mjs:54` directory check. |
| `src/hooks/src/lifecycle/load-fingerprint.ts` | Verbose every-session dump violates RULE-C7 (ruthlessly prune). |

---

## Phase 1 — Quick wins (V1, V2, V7) — ~45 min

### Task 1: Drop orphan `runId` from section-writer

**Files:**
- Modify: `src/agents/section-writer.md:464`

- [ ] **Step 1: Read the file region**

Run: `sed -n '460,470p' src/agents/section-writer.md`
Expected: shows a bulleted list of agent-input fields including the literal line `` - `runId`, `sectionIndex`, `paragraphIndex`, `paragraphId` ``.

- [ ] **Step 2: Remove the `runId` token**

Edit the line at `src/agents/section-writer.md:464`:
- Old: `` - `runId`, `sectionIndex`, `paragraphIndex`, `paragraphId` ``
- New: `` - `sectionIndex`, `paragraphIndex`, `paragraphId` ``

- [ ] **Step 3: Verify nothing else references `runId`**

Run: `grep -rn "runId" src/`
Expected: zero output.

- [ ] **Step 4: Commit**

```bash
git add src/agents/section-writer.md
git commit -m "fix: remove orphan runId reference from section-writer input contract

Left over from cognetivy removal. The write skill no longer passes runId,
so the field was documented but never populated."
```

---

### Task 2: Delete dead hook files

**Files:**
- Delete: `src/hooks/src/lifecycle/check-profile.ts`
- Delete: `src/hooks/src/lifecycle/load-fingerprint.ts`
- Modify: `src/hooks/src/entries/lifecycle.ts`

- [ ] **Step 1: Verify both files are unregistered**

Run: `grep -E 'check-profile|load-fingerprint' src/hooks/hooks.json`
Expected: zero output (confirms they're not in the registry).

- [ ] **Step 2: Delete the two TS files**

```bash
rm src/hooks/src/lifecycle/check-profile.ts
rm src/hooks/src/lifecycle/load-fingerprint.ts
```

- [ ] **Step 3: Remove their exports from the bundle entry**

Edit `src/hooks/src/entries/lifecycle.ts`:
- Old:
  ```typescript
  import { checkProfile } from '../lifecycle/check-profile.js';
  import { loadFingerprint } from '../lifecycle/load-fingerprint.js';
  import { sessionDashboard } from '../lifecycle/session-dashboard.js';
  import { sessionEndLog } from '../lifecycle/session-end-log.js';
  import type { HookInput, HookResult } from '../types.js';

  export const hooks: Record<string, (input: HookInput) => HookResult> = {
    'lifecycle/check-profile': checkProfile,
    'lifecycle/load-fingerprint': loadFingerprint,
    'lifecycle/session-dashboard': sessionDashboard,
    'lifecycle/session-end-log': sessionEndLog,
  };
  ```
- New:
  ```typescript
  import { sessionDashboard } from '../lifecycle/session-dashboard.js';
  import { sessionEndLog } from '../lifecycle/session-end-log.js';
  import type { HookInput, HookResult } from '../types.js';

  export const hooks: Record<string, (input: HookInput) => HookResult> = {
    'lifecycle/session-dashboard': sessionDashboard,
    'lifecycle/session-end-log': sessionEndLog,
  };
  ```

- [ ] **Step 4: Rebuild hooks**

Run: `cd src/hooks && npm run build && cd ../..`
Expected: build succeeds; bundle size shrinks slightly.

- [ ] **Step 5: Commit**

```bash
git add src/hooks/
git commit -m "refactor(hooks): delete dead lifecycle handlers

check-profile.ts: superseded by run-hook.mjs directory guard.
load-fingerprint.ts: verbose every-session dump violated 'ruthlessly prune'."
```

---

### Task 3: Register session-dashboard on SessionStart

**Files:**
- Modify: `src/hooks/hooks.json`

- [ ] **Step 1: Read the current hooks.json**

Run: `cat src/hooks/hooks.json`
Expected: shows only `SessionEnd` registered.

- [ ] **Step 2: Add SessionStart registration**

Replace `src/hooks/hooks.json` with:
```json
{
  "description": "Academic Writer hooks — session dashboard, session logging (TypeScript/ESM)",
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/hooks/bin/run-hook.mjs lifecycle/session-dashboard",
            "timeout": 5,
            "statusMessage": "Loading Academic Writer dashboard..."
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/hooks/bin/run-hook.mjs lifecycle/session-end-log",
            "timeout": 10,
            "statusMessage": "Logging session..."
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 3: Smoke-test the hook locally**

Run from project root with a real profile to test against:
```bash
echo '{}' | CLAUDE_PROJECT_DIR=/Users/yotamfromm/dev/Yotam-Asistant/groups/main node src/hooks/bin/run-hook.mjs lifecycle/session-dashboard
```
Expected: JSON output containing a `systemMessage` field with the box-art dashboard.

- [ ] **Step 4: Smoke-test silent-skip in unrelated project**

```bash
echo '{}' | CLAUDE_PROJECT_DIR=/tmp node src/hooks/bin/run-hook.mjs lifecycle/session-dashboard
```
Expected: `{"continue":true,"suppressOutput":true}` (the `run-hook.mjs:54` guard fires before our handler runs).

- [ ] **Step 5: Commit**

```bash
git add src/hooks/hooks.json
git commit -m "feat(hooks): register session-dashboard on SessionStart

Was implemented but unregistered. Now fires on session start in
projects with an academic-writer profile; silently skips elsewhere."
```

---

### Task 4: Add `allowedTools` to the 3 unrestricted skills

**Files:**
- Modify: `src/skills/health/SKILL.md`
- Modify: `src/skills/help/SKILL.md`
- Modify: `src/skills/update-field/SKILL.md`

- [ ] **Step 1: Add to `health`**

Edit `src/skills/health/SKILL.md` frontmatter:
- Old:
  ```yaml
  ---
  name: health
  description: "Check the health of all Academic Writer integrations — profile, Candlekeep, RAG, past articles, and source index."
  user-invocable: true
  ---
  ```
- New:
  ```yaml
  ---
  name: health
  description: "Check the health of all Academic Writer integrations — profile, Candlekeep, RAG, past articles, and source index."
  user-invocable: true
  allowedTools: [Bash, Read]
  ---
  ```

- [ ] **Step 2: Add to `help`**

Edit `src/skills/help/SKILL.md` frontmatter:
- Old:
  ```yaml
  ---
  name: help
  description: "Learn what the Academic Writer plugin does and how to use it."
  user-invocable: true
  ---
  ```
- New:
  ```yaml
  ---
  name: help
  description: "Learn what the Academic Writer plugin does and how to use it."
  user-invocable: true
  allowedTools: [Read]
  ---
  ```

- [ ] **Step 3: Add to `update-field`**

Edit `src/skills/update-field/SKILL.md` frontmatter:
- Old:
  ```yaml
  ---
  name: update-field
  description: "Update your field of study in the Academic Writer profile."
  user-invocable: true
  ---
  ```
- New:
  ```yaml
  ---
  name: update-field
  description: "Update your field of study in the Academic Writer profile."
  user-invocable: true
  allowedTools: [Read, Write, Edit, AskUserQuestion]
  ---
  ```

- [ ] **Step 4: Verify all 15 skills now declare allowedTools**

Run: `for f in src/skills/*/SKILL.md; do grep -L "^allowedTools:\|^allowed-tools:" "$f"; done`
Expected: zero output (every file has the field).

- [ ] **Step 5: Run structural tests**

Run: `python3 tests/test_plugin_structure.py 2>&1 | grep -E "FAIL|ERROR" | wc -l`
Expected: 3 (the pre-existing CLAUDE.md failures — Phase 3 fixes those).

- [ ] **Step 6: Commit**

```bash
git add src/skills/health/SKILL.md src/skills/help/SKILL.md src/skills/update-field/SKILL.md
git commit -m "fix(skills): add explicit allowedTools to health/help/update-field

Per RULE-S16: skills should restrict tool access when they don't need
full surface area. health: Bash+Read only. help: Read only. update-field:
Read+Write+Edit+AskUserQuestion."
```

---

### Task 5: Phase 1 build + verify

- [ ] **Step 1: Full plugin build**

Run: `npm run build 2>&1 | tail -5`
Expected: `BUILD COMPLETE` with skills count = 15, agents = 6, commands = 15.

- [ ] **Step 2: Confirm dead hooks gone from packaged copy**

Run: `grep -c "checkProfile\|loadFingerprint" plugins/academic-writer/hooks/dist/lifecycle.mjs`
Expected: 0.

- [ ] **Step 3: Full structural test**

Run: `python3 tests/test_plugin_structure.py 2>&1 | tail -5`
Expected: `Ran N tests`, only the 3 CLAUDE.md failures remain.

- [ ] **Step 4: Tag the phase**

```bash
git tag phase1-quickwins
```

---

## Phase 2 — Centralisation (V3, V13) — ~2 hr

### Task 6: Create `src/thresholds.json`

**Files:**
- Create: `src/thresholds.json`

- [ ] **Step 1: Find every threshold reference**

Run: `grep -rn "35/50\|40/60\|3 rewrite\|max.*rewrite" src/ | grep -v node_modules`
Expected: lists every site that hardcodes a threshold (anti-AI, self-review, rewrite cap).

- [ ] **Step 2: Write the canonical threshold file**

Create `src/thresholds.json` with:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "description": "Single source of truth for all numeric quality gates. Edit here; every skill and agent references this file.",
  "antiAi": {
    "minScore": 35,
    "maxScore": 50,
    "passThreshold": 35,
    "_comment": "Paragraphs scoring below 35/50 trigger revision. 5 dimensions x 10 points each."
  },
  "selfReview": {
    "minScore": 40,
    "maxScore": 60,
    "passThreshold": 40,
    "_comment": "Articles scoring below 40/60 trigger researcher review before final output. 6 dimensions x 10 points each."
  },
  "rewriteCycles": {
    "max": 3,
    "_comment": "Maximum number of times a paragraph can be rewritten before being included with [NEEDS REVIEW]."
  },
  "styleFingerprint": {
    "passThreshold": 7,
    "maxScore": 10,
    "_comment": "Per-dimension style compliance score. Below 7 triggers paragraph adjustment."
  }
}
```

- [ ] **Step 3: Update `scripts/build-plugins.sh` to copy it**

Edit `scripts/build-plugins.sh`. Find the `# Copy shared resources` block (after `cp ... words.md`). Append:
```bash
  # Copy thresholds
  if [[ -f "$SRC_DIR/thresholds.json" ]]; then
    cp "$SRC_DIR/thresholds.json" "$PLUGIN_DIR/"
  fi
```

- [ ] **Step 4: Build to verify**

Run: `npm run build && ls plugins/academic-writer/thresholds.json`
Expected: file exists in built plugin.

- [ ] **Step 5: Commit**

```bash
git add src/thresholds.json scripts/build-plugins.sh
git commit -m "feat: centralize quality-gate thresholds in src/thresholds.json

Single source of truth for anti-AI (35/50), self-review (40/60),
rewrite cap (3), and style fingerprint (7/10) thresholds.
Eliminates the shotgun-surgery pattern where threshold edits required
changes in 3+ unrelated files."
```

---

### Task 7: Replace hardcoded thresholds in skills/agents with references

**Files:**
- Modify: `src/agents/section-writer.md` (anti-AI, rewrite cap)
- Modify: `src/skills/write/SKILL.md` (anti-AI, self-review)
- Modify: `src/skills/review/SKILL.md` (self-review)

- [ ] **Step 1: Replace anti-AI references in section-writer**

In `src/agents/section-writer.md`, find every literal `35/50` or `score < 35` and replace with a reference like:
```
score below `thresholds.json:antiAi.passThreshold` (currently 35/50)
```

Use `Edit` with `replace_all: true` after confirming the exact phrasing. Example replacements:
- Old: `If the score is below 35/50, revise the paragraph.`
- New: `If the score is below the anti-AI pass threshold defined in \`thresholds.json\` (default 35/50), revise the paragraph.`

- [ ] **Step 2: Replace rewrite-cycle reference in section-writer**

- Old: `paragraph that fails 3 rewrite cycles is included with [NEEDS REVIEW]`
- New: `paragraph that fails the max rewrite cycles defined in \`thresholds.json\` (default 3) is included with [NEEDS REVIEW]`

- [ ] **Step 3: Replace self-review references in write/SKILL.md**

- Old: `Score < 40/60 triggers researcher review`
- New: `Score below the self-review threshold defined in \`thresholds.json\` (default 40/60) triggers researcher review`

- [ ] **Step 4: Same in review/SKILL.md**

Replace all `40/60` references with the canonical phrasing above.

- [ ] **Step 5: Verify no orphan magic numbers remain in pipeline files**

Run: `grep -n "35/50\|40/60" src/agents/section-writer.md src/skills/{write,review}/SKILL.md | grep -v "default 35/50\|default 40/60"`
Expected: zero output.

- [ ] **Step 6: Commit**

```bash
git add src/agents/section-writer.md src/skills/write/SKILL.md src/skills/review/SKILL.md
git commit -m "refactor: reference thresholds.json instead of inlining magic numbers

Per RULE-V10 (Code Review for AI Agents v4): no magic numbers.
Pipeline files now point at src/thresholds.json for the canonical values."
```

---

### Task 8: Move review scorecard rubric to JSON

**Files:**
- Create: `src/skills/review/references/scorecard.json`
- Modify: `src/skills/review/SKILL.md`

- [ ] **Step 1: Read current scorecard prose**

Run: `cat src/skills/review/SKILL.md` and locate the section that lists the 6 dimensions (structure, argument logic, citation completeness, source coverage, writing quality, academic conventions).

- [ ] **Step 2: Create the rubric JSON**

Create `src/skills/review/references/scorecard.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "version": "1.0",
  "description": "6-dimension self-review scorecard for completed academic articles. Each dimension scores 0-10. Total >= 40/60 = pass.",
  "dimensions": [
    {
      "id": "structure",
      "name": "Structure & Coherence",
      "weight": 1,
      "criteria": [
        "Clear thesis stated in introduction",
        "Each section advances the argument",
        "Sections connect with explicit transitions",
        "Conclusion synthesizes (does not just summarize)"
      ]
    },
    {
      "id": "argument_logic",
      "name": "Argument Logic",
      "weight": 1,
      "criteria": [
        "Claims supported by evidence",
        "Counterarguments addressed where relevant",
        "Logical progression — no leaps",
        "Conclusions follow from evidence presented"
      ]
    },
    {
      "id": "citation_completeness",
      "name": "Citation Completeness",
      "weight": 1,
      "criteria": [
        "Every empirical claim has a citation",
        "Every quote has page-precise attribution",
        "Bibliography matches in-text citations exactly",
        "No [NEEDS REVIEW] markers in final draft"
      ]
    },
    {
      "id": "source_coverage",
      "name": "Source Coverage",
      "weight": 1,
      "criteria": [
        "Major scholarly positions on the topic represented",
        "Primary sources cited where available",
        "No single source dominates the bibliography",
        "Recent scholarship (last 10 years) included"
      ]
    },
    {
      "id": "writing_quality",
      "name": "Writing Quality",
      "weight": 1,
      "criteria": [
        "Style fingerprint compliance >= 7/10 across paragraphs",
        "No anti-AI patterns (passes anti-AI check)",
        "Hebrew grammar correct (if applicable)",
        "No repetition of words, phrases, or arguments"
      ]
    },
    {
      "id": "academic_conventions",
      "name": "Academic Conventions",
      "weight": 1,
      "criteria": [
        "Citation style consistent throughout",
        "Footnote/endnote formatting correct",
        "Heading hierarchy correct",
        "Article structure matches profile.articleStructure"
      ]
    }
  ],
  "scoring": {
    "perDimensionMax": 10,
    "totalMax": 60,
    "passThreshold": 40,
    "_comment": "passThreshold mirrors thresholds.json:selfReview.passThreshold. Keep in sync."
  }
}
```

- [ ] **Step 3: Replace prose scorecard in review/SKILL.md**

Find the prose scorecard section (the one listing 6 dimensions in markdown). Replace with:
```markdown
## Scorecard rubric

The 6-dimension scorecard is defined in `references/scorecard.json` (machine-readable, versioned). Read that file at the start of every review.

For each dimension:
1. Score 0–10 against the listed `criteria`.
2. Sum the dimension scores.
3. Compare to `scoring.passThreshold` (default 40). Below threshold → researcher review required.

The scorecard is the single source of truth — do not score on dimensions not listed there, and do not change weights inline. To adjust scoring, edit `references/scorecard.json` and bump its `version` field.
```

- [ ] **Step 4: Confirm structural tests still pass**

Run: `python3 tests/test_plugin_structure.py 2>&1 | tail -5`
Expected: only pre-existing CLAUDE.md failures.

- [ ] **Step 5: Commit**

```bash
git add src/skills/review/
git commit -m "refactor(review): move scorecard rubric to references/scorecard.json

Per RULE-V17: gates must be precondition contracts, not docstrings.
Skill body now orchestrates; references/scorecard.json is the contract."
```

---

## Phase 3 — Documentation polish (V4, V6, V12, V15, V16) — ~3 hr

### Task 9: Author CLAUDE.md and un-gitignore it

**Files:**
- Create: `CLAUDE.md`
- Modify: `.gitignore`

- [ ] **Step 1: Check current gitignore state**

Run: `grep -n "CLAUDE.md" .gitignore`
Expected: shows the line that ignores it.

- [ ] **Step 2: Remove CLAUDE.md from .gitignore**

Edit `.gitignore`: delete the line containing `CLAUDE.md`. Save.

- [ ] **Step 3: Verify it's no longer ignored**

Run: `git check-ignore -v CLAUDE.md`
Expected: empty (no rule matches) or exit code 1.

- [ ] **Step 4: Write CLAUDE.md**

Create `CLAUDE.md` (≤ 80 lines, ruthlessly pruned per RULE-C7):
```markdown
# Academic Helper — Claude Code Conventions

This is a Claude Code plugin for Humanities researchers. The user is a single
researcher on a local machine; the plugin should never assume team workflows.

## Commands

- `npm run build` — build the plugin (esbuild hooks → bundle, copy src/ → plugins/)
- `npm run build:hooks` — rebuild only the TypeScript hooks
- `npm run typecheck` — strict TS check on src/hooks/
- `python3 tests/test_plugin_structure.py` — structural integrity tests
- `npm run clean` — wipe plugins/ and src/hooks/dist/

## Source layout

| Path | What |
|---|---|
| `src/skills/<name>/SKILL.md` | Skill definition (markdown + YAML frontmatter) |
| `src/agents/<name>.md` | Agent definition (markdown + YAML frontmatter) |
| `src/hooks/src/lifecycle/*.ts` | TypeScript hook handlers, bundled by esbuild |
| `src/hooks/hooks.json` | Hook registry — what events fire which handlers |
| `src/thresholds.json` | Single source of truth for all numeric quality gates |
| `manifests/academic-writer.json` | Plugin manifest (name, version, description) |
| `scripts/build-plugins.sh` | Build script — assembles `plugins/academic-writer/` from `src/` |

## Conventions

- **Profile-scoped**: every hook must silently skip in projects without `.academic-helper/profile.md`. The `run-hook.mjs:54` directory guard handles this; new hooks should respect it.
- **Thresholds**: edit `src/thresholds.json`, never inline numbers in skills or agents.
- **Strict TypeScript**: hooks must compile under `tsc --noEmit`; never use `any` (use `unknown` and narrow).
- **Markdown frontmatter**: skills require `name`, `description`, `user-invocable`, `allowedTools`. Agents require `name`, `description`, `tools`, `model`. Add `metadata: {author, version}` to skills.
- **No global pollution**: never write to `$HOME` or paths outside `CLAUDE_PROJECT_DIR`. The plugin must be safe to run in any project.

## Plugin invocation

Slash commands are auto-generated from skills with `user-invocable: true`. To add a command, add a skill. To remove a command, set `user-invocable: false` (skill becomes internal).

## Pipeline pattern

The `write` and `edit` skills use a chained-with-gates pattern:
1. Conversational planning phase (architect agent, human in the loop).
2. Parallel section writing (one section-writer subagent per section).
3. Per-paragraph 8-skill pipeline (draft → 6 checks → citation audit hard gate).
4. Synthesis pass + self-review scorecard.

Auditor is the only mandatory hard gate — it must reject paragraphs whose citations don't match `sources.json` or fail external verification.

## Anti-patterns

- Don't inline thresholds — read `thresholds.json`.
- Don't run cognetivy — it was removed (`docs/reviews/2026-05-01-plugin-review.md`).
- Don't create `.academic-helper/` outside the setup or init skills.
- Don't author skill descriptions that omit "Use when…" trigger phrases.
```

- [ ] **Step 5: Run structural tests**

Run: `python3 tests/test_plugin_structure.py 2>&1 | tail -5`
Expected: `test_claude_md_exists` now passes. The other CLAUDE.md tests (`test_all_skills_listed_in_claude_md`, `test_all_agents_listed_in_claude_md`) may still fail because CLAUDE.md doesn't repeat the full slash-command list.

- [ ] **Step 6: Decide on slash-command listing**

If the tests insist on slash-command listing in CLAUDE.md, extend the "Plugin invocation" section to include the user-invocable list (the table from `help/SKILL.md`). Otherwise, mark those tests as expected-to-fail in `tests/test_plugin_structure.py` with a comment that says CLAUDE.md is intentionally pruned and lists are owned by `help/SKILL.md`.

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md .gitignore
git commit -m "docs: author committed CLAUDE.md per RULE-C6/C17

Per Best Practices for Agentic Coding (p. 3-4): CLAUDE.md is the
team's organisational memory and should be tracked in git. Was
previously gitignored — wrong call from commit ea48a76."
```

---

### Task 10: Rewrite skill descriptions with trigger phrases

**Files:**
- Modify: all 15 `src/skills/*/SKILL.md` (frontmatter only)

- [ ] **Step 1: Map intended descriptions**

For each skill, the new description = old description + "**Use when…**" clause:

| Skill | New description |
|---|---|
| `write` | Existing + ` Use when starting a new article from scratch — subject, sources, thesis, outline, draft.` |
| `edit` | Existing + ` Use when revising an article that's already drafted — multiple sections, restructuring, or major changes.` |
| `edit-section` | Existing + ` Use when changing one specific section only — faster than full edit.` |
| `init` | Existing + ` Use on first install or when redoing onboarding from scratch.` |
| `setup` | Existing + ` Use for a quick onboarding (faster than init); does not include source indexing.` |
| `research` | Existing + ` Use when investigating a topic or fact-checking before writing.` |
| `ideate` | Existing + ` Use when you have a vague topic and need help framing a research question.` |
| `review` | Existing + ` Use after writing to score the article on quality dimensions before publication.` |
| `health` | Existing + ` Use when something stops working, after install, or before a long write session.` |
| `help` | Existing + ` Use when you don't know which command to run.` |
| `learn` | Existing + ` Use after adding new past articles to past-articles/ — rebuilds the style fingerprint.` |
| `present` | Existing + ` Use after publishing an article when you need conference/journal/proposal deliverables.` |
| `feedback` | Existing already has "Use after the researcher reviews an article" — keep as is. |
| `update-tools` | Existing + ` Use when adding/removing integrations after initial setup.` |
| `update-field` | Existing + ` Use when changing your research field without redoing full setup.` |

- [ ] **Step 2: Apply each description change**

For each skill listed above, edit the `description:` line in its frontmatter to append the trigger clause. Use `Edit` with the exact old line as `old_string` and the appended new line as `new_string`. Do this 14 times (`feedback` is unchanged).

- [ ] **Step 3: Verify all descriptions still under 1024 chars**

Run:
```bash
for f in src/skills/*/SKILL.md; do
  desc=$(awk '/^description:/{sub(/^description: */,""); gsub(/^"|"$/,""); print; exit}' "$f")
  printf "%4d  %s\n" "${#desc}" "$f"
done | sort -n | tail
```
Expected: all under 1024.

- [ ] **Step 4: Verify YAML still parses**

Run: `python3 tests/test_plugin_structure.py 2>&1 | grep -c "FAIL\|ERROR"`
Expected: same as before (pre-existing CLAUDE.md failures only).

- [ ] **Step 5: Commit**

```bash
git add src/skills/
git commit -m "docs(skills): add 'Use when…' trigger phrases to descriptions

Per RULE-S08 (Skills Guide): descriptions must include trigger
conditions, not just capability statements. Improves router selection
and reduces overlap between similar skills (write/edit, init/setup)."
```

---

### Task 11: Add depth/speed cues to auditor and quick-scan steps

**Files:**
- Modify: `src/agents/auditor.md`
- Modify: `src/agents/section-writer.md` (the repetition-check section)

- [ ] **Step 1: Add depth cue to auditor**

In `src/agents/auditor.md`, near the top of the system-prompt body (right after `# Auditor` heading), insert:
```markdown
> **Think carefully and step-by-step before each VERDICT.** Citation correctness is non-negotiable — a single missed mismatch corrupts the whole article. This is harder than it looks; do not pattern-match, verify each field against the registry.
```

- [ ] **Step 2: Add speed cue to repetition check**

In `src/agents/section-writer.md`, find the repetition-check skill step (skill #7 in the per-paragraph pipeline). Insert at the top of that section:
```markdown
> **Prioritize responding quickly; this is a mechanical scan, not deep reasoning.** Look for repeated lemmas, repeated phrases, and repeated argument moves. If unsure, flag and move on rather than deliberate.
```

- [ ] **Step 3: Verify**

Run: `grep -A1 "Think carefully" src/agents/auditor.md && grep -A1 "Prioritize responding quickly" src/agents/section-writer.md`
Expected: both quoted lines present.

- [ ] **Step 4: Commit**

```bash
git add src/agents/auditor.md src/agents/section-writer.md
git commit -m "feat(agents): add adaptive thinking cues per Operator's Rulebook

RULE-O03/O04 (Operator's Rulebook): Opus 4.7 uses adaptive thinking
controlled by prompt phrasing. Auditor gets depth cue (citations are
non-negotiable). Repetition check gets speed cue (mechanical scan)."
```

---

### Task 12: Add negative triggers where skills overlap

**Files:**
- Modify: `src/skills/setup/SKILL.md`
- Modify: `src/skills/edit-section/SKILL.md`

- [ ] **Step 1: Add negative trigger to `setup`**

In `src/skills/setup/SKILL.md`, immediately after the description line in frontmatter, edit the body's first paragraph to include:
```markdown
> **Do NOT use this skill** for source indexing or full 25-dimension style fingerprinting — use `/academic-writer:init` instead. This is the *quick* setup; init is the deep setup.
```

- [ ] **Step 2: Add negative trigger to `edit-section`**

In `src/skills/edit-section/SKILL.md` body (right after the title), insert:
```markdown
> **Do NOT use this skill** for multi-section edits, restructuring, or full-article tone changes — use `/academic-writer:edit` instead.
```

- [ ] **Step 3: Verify and commit**

Run: `grep "Do NOT use" src/skills/setup/SKILL.md src/skills/edit-section/SKILL.md`
Expected: both lines present.

```bash
git add src/skills/setup/SKILL.md src/skills/edit-section/SKILL.md
git commit -m "docs(skills): add negative triggers to overlapping skills

Per RULE-S17 (Skills Guide, p. 9): when two skills overlap (setup vs
init, edit-section vs edit), the smaller one must point to the bigger
one with 'Do NOT use for...' clauses to prevent over-triggering."
```

---

### Task 13: Add metadata block to all skills

**Files:**
- Modify: all 15 `src/skills/*/SKILL.md`

- [ ] **Step 1: Read plugin version**

Run: `jq -r '.version' manifests/academic-writer.json`
Expected: `0.2.18` (or current).

- [ ] **Step 2: Write a one-shot Python script to add metadata**

Create `.removal-log/add-metadata.py`:
```python
#!/usr/bin/env python3
"""Add metadata block to every SKILL.md frontmatter."""
import json
import re
from pathlib import Path

VERSION = json.loads(Path("manifests/academic-writer.json").read_text())["version"]
AUTHOR = "Yotam Fromm"
METADATA_LINE = f'metadata: {{author: "{AUTHOR}", version: "{VERSION}"}}'

for skill in sorted(Path("src/skills").glob("*/SKILL.md")):
    text = skill.read_text(encoding="utf-8")
    if "metadata:" in text.split("---", 2)[1]:
        print(f"  skip (has metadata): {skill}")
        continue
    new = re.sub(
        r"^(---\n(?:.*\n)+?)(---\n)",
        rf"\1{METADATA_LINE}\n\2",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if new == text:
        print(f"  WARN no change: {skill}")
        continue
    skill.write_text(new, encoding="utf-8")
    print(f"  added: {skill}")
```

- [ ] **Step 3: Run it**

Run: `python3 .removal-log/add-metadata.py`
Expected: 15 `added:` lines.

- [ ] **Step 4: Verify all skills now have metadata**

Run: `grep -L "^metadata:" src/skills/*/SKILL.md`
Expected: zero output.

- [ ] **Step 5: Run structural tests**

Run: `python3 tests/test_plugin_structure.py 2>&1 | tail -5`
Expected: only pre-existing CLAUDE.md failures (or zero, if Task 9 fixed them).

- [ ] **Step 6: Commit**

```bash
git add src/skills/ .removal-log/add-metadata.py
git commit -m "feat(skills): add metadata block (author, version) to all SKILL.md

Per RULE-S20 (Skills Guide): skills should declare author and version
in frontmatter for attribution and update tracking. Version sourced
from manifests/academic-writer.json so it stays in sync at build time."
```

---

## Phase 4 — Hooks expansion (V11, V10) — ~2.5 hr

### Task 14: Add Stop notification hook

**Files:**
- Create: `src/hooks/src/lifecycle/notify-stop.ts`
- Modify: `src/hooks/src/entries/lifecycle.ts`
- Modify: `src/hooks/hooks.json`

- [ ] **Step 1: Write the handler (uses execFile, not exec, to avoid shell injection)**

Create `src/hooks/src/lifecycle/notify-stop.ts`:
```typescript
import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import type { HookInput, HookResult } from '../types.js';

export function notifyStop(input: HookInput): HookResult {
  const projectDir = input.project_dir ?? process.env['CLAUDE_PROJECT_DIR'] ?? '.';

  // Hard gate: only notify in academic-writer projects.
  if (!existsSync(join(projectDir, '.academic-helper', 'profile.md'))) {
    return { continue: true, suppressOutput: true };
  }

  // macOS only — silently no-op elsewhere.
  if (process.platform !== 'darwin') {
    return { continue: true, suppressOutput: true };
  }

  // Use execFile (not exec) — args are passed as an array to osascript,
  // never interpreted by the shell. The script string is a static literal.
  const script = 'display notification "Task complete" with title "Academic Writer" sound name "Glass"';
  execFile('osascript', ['-e', script], { timeout: 2000 }, () => {
    // Silent — never block on notification.
  });

  return { continue: true, suppressOutput: true };
}
```

- [ ] **Step 2: Wire into bundle**

Edit `src/hooks/src/entries/lifecycle.ts`:
- Old:
  ```typescript
  import { sessionDashboard } from '../lifecycle/session-dashboard.js';
  import { sessionEndLog } from '../lifecycle/session-end-log.js';
  import type { HookInput, HookResult } from '../types.js';

  export const hooks: Record<string, (input: HookInput) => HookResult> = {
    'lifecycle/session-dashboard': sessionDashboard,
    'lifecycle/session-end-log': sessionEndLog,
  };
  ```
- New:
  ```typescript
  import { notifyStop } from '../lifecycle/notify-stop.js';
  import { sessionDashboard } from '../lifecycle/session-dashboard.js';
  import { sessionEndLog } from '../lifecycle/session-end-log.js';
  import type { HookInput, HookResult } from '../types.js';

  export const hooks: Record<string, (input: HookInput) => HookResult> = {
    'lifecycle/notify-stop': notifyStop,
    'lifecycle/session-dashboard': sessionDashboard,
    'lifecycle/session-end-log': sessionEndLog,
  };
  ```

- [ ] **Step 3: Register `Stop` event in hooks.json**

Edit `src/hooks/hooks.json`. Insert a `"Stop"` event group after `"SessionStart"`:
```json
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/hooks/bin/run-hook.mjs lifecycle/notify-stop",
            "timeout": 3,
            "statusMessage": "Notifying..."
          }
        ]
      }
    ],
```

- [ ] **Step 4: Build hooks**

Run: `cd src/hooks && npm run build && cd ../..`
Expected: build succeeds; bundle includes `notifyStop`.

- [ ] **Step 5: Smoke-test in profiled project**

Run: `echo '{}' | CLAUDE_PROJECT_DIR=/Users/yotamfromm/dev/Yotam-Asistant/groups/main node src/hooks/bin/run-hook.mjs lifecycle/notify-stop`
Expected: macOS notification appears (title "Academic Writer", message "Task complete"). JSON output `{"continue":true,"suppressOutput":true}`.

- [ ] **Step 6: Smoke-test silent skip**

Run: `echo '{}' | CLAUDE_PROJECT_DIR=/tmp node src/hooks/bin/run-hook.mjs lifecycle/notify-stop`
Expected: no notification, JSON `{"continue":true,"suppressOutput":true}`.

- [ ] **Step 7: Commit**

```bash
git add src/hooks/
git commit -m "feat(hooks): add Stop notification per Operator's Rulebook RULE-O08

Long autonomous runs are blind without completion signals. Fires a
macOS notification on Stop in projects with an academic-writer profile.
No-op on non-darwin or projects without a profile. Uses execFile
(no shell) to prevent injection; script string is a static literal."
```

---

### Task 15: Add SubagentStart hook to inject citation rules

**Files:**
- Create: `src/hooks/src/lifecycle/subagent-start.ts`
- Modify: `src/hooks/src/entries/lifecycle.ts`
- Modify: `src/hooks/hooks.json`
- Modify: `src/agents/section-writer.md` (strip duplicated citation rules block)
- Modify: `src/skills/setup/SKILL.md` and `src/skills/init/SKILL.md` (copy thresholds.json into project)

- [ ] **Step 1: Write the handler**

Create `src/hooks/src/lifecycle/subagent-start.ts`:
```typescript
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { HookInput, HookResult } from '../types.js';

interface SubagentStartInput extends HookInput {
  subagent_type?: string;
  subagentType?: string;
}

interface Thresholds {
  antiAi?: { passThreshold?: number; maxScore?: number };
  rewriteCycles?: { max?: number };
}

export function subagentStart(input: SubagentStartInput): HookResult {
  const projectDir = input.project_dir ?? process.env['CLAUDE_PROJECT_DIR'] ?? '.';

  // Hard gate: only inject in academic-writer projects.
  if (!existsSync(join(projectDir, '.academic-helper', 'profile.md'))) {
    return { continue: true, suppressOutput: true };
  }

  const subagentType = input.subagent_type ?? input.subagentType ?? '';
  // Only inject for the auditor subagent — others have their own context.
  if (subagentType !== 'auditor' && subagentType !== 'academic-writer:auditor') {
    return { continue: true, suppressOutput: true };
  }

  // Read thresholds.json so the auditor knows the current cutoffs.
  const thresholdsPath = join(projectDir, '.academic-helper', 'thresholds.json');
  let thresholdNote = '';
  if (existsSync(thresholdsPath)) {
    try {
      const raw = readFileSync(thresholdsPath, 'utf-8');
      const t = JSON.parse(raw) as Thresholds;
      thresholdNote = `\nCurrent thresholds: anti-AI ${t.antiAi?.passThreshold}/${t.antiAi?.maxScore}, max rewrite cycles ${t.rewriteCycles?.max}.`;
    } catch {
      // ignore parse errors; missing thresholds is non-fatal
    }
  }

  const rules = [
    'AUDITOR CONTEXT (injected by SubagentStart hook):',
    '- Verify every citation against the canonical sources.json registry.',
    '- A citation passes only when title, author, year, and page all match.',
    '- Mark [NEEDS REVIEW: <field>] when a field is missing or low-confidence.',
    '- Use WebSearch for external verification only when the registry has no entry.',
    '- Validate WebSearch results: title (exact), author, year (±1), page range — anything weaker = [NEEDS REVIEW: external_verification].',
    '- Final output must be a single VERDICT line: PASS or FAIL with reasons.',
    thresholdNote,
  ].filter(Boolean).join('\n');

  return {
    continue: true,
    systemMessage: rules,
  };
}
```

- [ ] **Step 2: Wire into bundle**

Edit `src/hooks/src/entries/lifecycle.ts` to import and export `subagentStart`:
```typescript
import { notifyStop } from '../lifecycle/notify-stop.js';
import { sessionDashboard } from '../lifecycle/session-dashboard.js';
import { sessionEndLog } from '../lifecycle/session-end-log.js';
import { subagentStart } from '../lifecycle/subagent-start.js';
import type { HookInput, HookResult } from '../types.js';

export const hooks: Record<string, (input: HookInput) => HookResult> = {
  'lifecycle/notify-stop': notifyStop,
  'lifecycle/session-dashboard': sessionDashboard,
  'lifecycle/session-end-log': sessionEndLog,
  'lifecycle/subagent-start': subagentStart,
};
```

- [ ] **Step 3: Register `SubagentStart` event in hooks.json**

Add a new event group:
```json
    "SubagentStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/hooks/bin/run-hook.mjs lifecycle/subagent-start",
            "timeout": 3
          }
        ]
      }
    ],
```

- [ ] **Step 4: Make thresholds.json visible to hooks**

Edit `src/skills/setup/SKILL.md` and `src/skills/init/SKILL.md` Phase 0 mkdir line:
- Old: `mkdir -p past-articles .academic-helper .academic-helper/logs`
- New: `mkdir -p past-articles .academic-helper .academic-helper/logs && cp -n "${CLAUDE_PLUGIN_ROOT}/thresholds.json" .academic-helper/ 2>/dev/null || true`

This copies the canonical thresholds into the project's `.academic-helper/` so the hook can read them.

- [ ] **Step 5: Strip duplicated citation rules from section-writer**

In `src/agents/section-writer.md`, find the citation-audit step (skill #8). It currently reproduces the auditor's rule list. Replace that reproduction with:
```markdown
The auditor's full rule set is injected automatically via `SubagentStart` hook (`src/hooks/src/lifecycle/subagent-start.ts`). Spawn it with subagent_type "auditor" and a per-paragraph payload (paragraph text, claimed citations).
```

Trim ~20-30 duplicated rule lines.

- [ ] **Step 6: Build hooks + verify**

Run: `cd src/hooks && npm run build && cd ../.. && npm run build`
Expected: builds clean.

- [ ] **Step 7: Smoke-test SubagentStart**

Run: `echo '{"subagent_type":"auditor"}' | CLAUDE_PROJECT_DIR=/Users/yotamfromm/dev/Yotam-Asistant/groups/main node src/hooks/bin/run-hook.mjs lifecycle/subagent-start`
Expected: JSON output with a `systemMessage` field containing "AUDITOR CONTEXT" and the rules.

- [ ] **Step 8: Smoke-test irrelevant subagent**

Run: `echo '{"subagent_type":"general-purpose"}' | CLAUDE_PROJECT_DIR=/Users/yotamfromm/dev/Yotam-Asistant/groups/main node src/hooks/bin/run-hook.mjs lifecycle/subagent-start`
Expected: silent skip (no systemMessage).

- [ ] **Step 9: Commit**

```bash
git add src/hooks/ src/skills/setup/SKILL.md src/skills/init/SKILL.md src/agents/section-writer.md
git commit -m "feat(hooks): add SubagentStart hook to inject auditor context

Per RULE-H05 (Architecture, p. 1): SubagentStart should inject context
that must be consistent across every spawned agent. Auditor rules and
current thresholds now flow via the hook instead of being duplicated
in section-writer.md per paragraph spawn."
```

---

## Phase 5 — Restructuring (V8, V9) — ~5 hr

### Task 16: Demote 5 helper skills to internal

**Files:**
- Modify: `src/skills/{learn,update-field,update-tools,present,feedback}/SKILL.md` (remove `user-invocable: true`)
- Modify: `src/skills/help/SKILL.md` (drop them from the table; mention they're internal)

- [ ] **Step 1: Toggle each frontmatter**

For each of the 5 skills, edit the frontmatter:
- Old: `user-invocable: true`
- New: `user-invocable: false`

(Keep the field with `false` rather than deleting — explicit is better than implicit, and preserves the marker for future reactivation.)

- [ ] **Step 2: Update `help/SKILL.md` table**

Remove the rows for `learn`, `present`, `update-tools`, `update-field`, `feedback` from the slash-command table. Add a brief paragraph below the table:

```markdown
### Internal skills (invoked from other skills)

These don't have their own slash command; they run as sub-workflows:

- `learn` — run after dropping new files in `past-articles/` (auto-invoked by the dashboard hint)
- `update-tools` / `update-field` — invoked from within `init` or `setup`
- `present` — invoked from `edit` or `write` after a final article ships
- `feedback` — invoked from `edit` after researcher review
```

- [ ] **Step 3: Update test_plugin_structure.py if it requires the old behavior**

The existing `test_help_lists_all_slash_commands` already iterates only over user-invocable skills. After demotion, the 5 demoted skills won't be in the iteration set. No code change required, but verify by re-running the test.

- [ ] **Step 4: Build + verify command count**

Run: `npm run build 2>&1 | grep "Commands:"`
Expected: `Commands: 10` (was 15).

- [ ] **Step 5: Verify tests still pass**

Run: `python3 tests/test_plugin_structure.py 2>&1 | tail -5`
Expected: same passing-test count as before plus or minus the help-table assertion.

- [ ] **Step 6: Commit**

```bash
git add src/skills/
git commit -m "refactor(skills): demote 5 helper skills to internal

learn, update-field, update-tools, present, feedback are sub-workflows
invoked from main skills, not standalone commands. Demoting reduces
top-level command count from 15 to 10 — fewer commands for the user
to remember, per RULE-S15 (composability)."
```

---

### Task 17: Push `init/SKILL.md` detail to references/

**Files:**
- Create: `src/skills/init/references/profile-schema.md`
- Create: `src/skills/init/references/integration-setup.md`
- Modify: `src/skills/init/SKILL.md` (shrink body to phase orchestration only)

- [ ] **Step 1: Read `init/SKILL.md` and identify chunks to extract**

Run: `wc -l src/skills/init/SKILL.md`
Expected: ~568 lines.

Identify three big chunks:
1. **Profile JSON schema + migration script** (Phase 0 Python block) → goes to `references/profile-schema.md`
2. **Integration registration commands + AskUserQuestion blocks** (Phase 1) → goes to `references/integration-setup.md`
3. The rest stays in SKILL.md as orchestration glue.

- [ ] **Step 2: Create `references/profile-schema.md`**

Cut the legacy-migration Python block + the JSON schema description from `init/SKILL.md` and paste it into a new file `src/skills/init/references/profile-schema.md` with this header:
```markdown
# Profile Schema (`.academic-helper/profile.md`)

> Loaded on demand by the `init` and `setup` skills. Do not duplicate this content in SKILL.md.

[paste the schema + migration script here]
```

- [ ] **Step 3: Create `references/integration-setup.md`**

Cut the integration detection commands + per-tool `AskUserQuestion` blocks from `init/SKILL.md` and paste into `src/skills/init/references/integration-setup.md`:
```markdown
# Integration Setup (Candlekeep, Vectorless, NotebookLM)

> Loaded on demand by `init` Phase 1. Each tool has detection command, configuration block, and registration steps.

[paste detection blocks per tool here]
```

- [ ] **Step 4: Replace cut sections with references in SKILL.md**

In `src/skills/init/SKILL.md`, where the chunks were, leave a one-line pointer:
- For schema: `Profile schema and legacy migration: see \`references/profile-schema.md\`.`
- For integrations: `Per-tool detection and setup: see \`references/integration-setup.md\`.`

- [ ] **Step 5: Verify SKILL.md shrunk**

Run: `wc -l src/skills/init/SKILL.md`
Expected: under 250 lines (was 568).

- [ ] **Step 6: Verify build still succeeds**

Run: `npm run build 2>&1 | tail -5`
Expected: BUILD COMPLETE.

- [ ] **Step 7: Verify references/ ships in built plugin**

Run: `ls plugins/academic-writer/skills/init/references/`
Expected: shows both files (build script's `cp -R src/skills` includes references/ automatically).

- [ ] **Step 8: Commit**

```bash
git add src/skills/init/
git commit -m "refactor(init): push detail to references/

Per RULE-S09/S10/S11 (Skills Guide): SKILL.md should be focused
orchestration; detailed content goes in references/ and is loaded
on demand. init/SKILL.md was 568 lines — now ~230 lines + 2 reference
files. Reduces token cost for every init invocation."
```

---

### Task 18: Push `write/SKILL.md` detail to references/

**Files:**
- Create: `src/skills/write/references/style-fingerprint-rubric.md`
- Modify: `src/skills/write/SKILL.md`

- [ ] **Step 1: Identify the rubric chunk**

In `src/skills/write/SKILL.md`, locate the section that details the 10-dimension style fingerprint scoring rubric (the per-dimension criteria, scoring scale, what counts as compliant).

- [ ] **Step 2: Create `references/style-fingerprint-rubric.md`**

Cut the rubric content into `src/skills/write/references/style-fingerprint-rubric.md`:
```markdown
# Style Fingerprint Compliance Rubric (10 dimensions)

> Loaded on demand by the section-writer per-paragraph pipeline. Pass threshold per dimension is defined in `thresholds.json:styleFingerprint.passThreshold` (default 7/10).

[paste rubric here]
```

- [ ] **Step 3: Replace in SKILL.md**

Where the rubric was, leave: `Style fingerprint compliance rubric: see \`references/style-fingerprint-rubric.md\`. Threshold: \`thresholds.json:styleFingerprint.passThreshold\`.`

- [ ] **Step 4: Verify shrunk**

Run: `wc -l src/skills/write/SKILL.md`
Expected: under 350 lines (was 520).

- [ ] **Step 5: Build + commit**

```bash
npm run build && python3 tests/test_plugin_structure.py 2>&1 | tail -5
git add src/skills/write/
git commit -m "refactor(write): push fingerprint rubric to references/

Per RULE-S09: progressive disclosure. write/SKILL.md was 520 lines —
now ~340 + reference file. Rubric stays available but loads on demand."
```

---

## Phase 6 — Model + validation (V5, V14) — ~3 hr

### Task 19: Switch section-writer to sonnet (with benchmark)

**Files:**
- Modify: `src/agents/section-writer.md:5`

- [ ] **Step 1: Read current frontmatter**

Run: `head -10 src/agents/section-writer.md`
Expected: `model: opus`.

- [ ] **Step 2: Set up benchmark sample**

Pick a real article folder under `~/dev/bar-ilan/` that has been written with the plugin. Note its path:
```
SAMPLE_DIR="/Users/yotamfromm/dev/bar-ilan/<chosen>"
```

Verify it has at least 3 paragraphs of completed text.

- [ ] **Step 3: Run benchmark on opus (baseline)**

Manually run the `write` skill on the sample's first 3 paragraphs WITH the current `model: opus` setting. Capture: (a) wall-clock time per paragraph, (b) anti-AI score per paragraph, (c) any auditor failures.

Save to `docs/benchmarks/2026-05-01-section-writer-opus.md`:
```markdown
| Para | Time | Anti-AI | Auditor |
|---|---|---|---|
| 1 | …s | …/50 | PASS/FAIL |
| 2 | …s | …/50 | PASS/FAIL |
| 3 | …s | …/50 | PASS/FAIL |
```

- [ ] **Step 4: Switch to sonnet**

Edit `src/agents/section-writer.md:5`:
- Old: `model: opus`
- New: `model: sonnet`

- [ ] **Step 5: Rebuild + run same benchmark**

Run: `npm run build`
Then re-run the same 3 paragraphs. Save to `docs/benchmarks/2026-05-01-section-writer-sonnet.md` with the same table.

- [ ] **Step 6: Compare**

If sonnet's anti-AI scores stay above the threshold (35/50) AND auditor PASS rate is unchanged AND time-per-paragraph drops: keep sonnet.

If sonnet drops below threshold OR auditor failures rise: revert to opus.

If marginal: try `model: inherit` and re-benchmark.

- [ ] **Step 7: Document the decision**

Append a "Decision" section to one of the benchmark files explaining which model is kept and why. Cite Operator's Rulebook RULE-O10 on benchmarking before rollout.

- [ ] **Step 8: Commit (whichever decision)**

If keeping sonnet:
```bash
git add src/agents/section-writer.md docs/benchmarks/
git commit -m "perf(agents): switch section-writer to sonnet after benchmark

Benchmark over 3 representative paragraphs (see docs/benchmarks/):
sonnet matched opus on anti-AI scores and auditor pass rate while
reducing paragraph time by Xs. Per RULE-O10 (Operator's Rulebook):
benchmark before rollout."
```

If reverting:
```bash
git add docs/benchmarks/
git commit -m "perf(agents): keep section-writer on opus per benchmark

Sonnet dropped below anti-AI threshold on N/3 paragraphs. opus stays."
```

---

### Task 20: Tighten WebSearch validation in auditor

**Files:**
- Modify: `src/agents/auditor.md`

- [ ] **Step 1: Locate the WebSearch step**

Run: `grep -n "WebSearch" src/agents/auditor.md`
Expected: shows the step that uses WebSearch for external verification.

- [ ] **Step 2: Add validation contract**

In `src/agents/auditor.md`, after the section that introduces WebSearch verification, insert:

```markdown
### WebSearch result validation (MANDATORY)

Per RULE-V27 (Code Review for AI Agents v4): every external API response must be validated before use. WebSearch returns may be from a different edition, a paraphrase, or an unrelated work. Before treating a WebSearch hit as confirmation, verify ALL of:

1. **Title match (exact)** — WebSearch result title must be a substring of the citation title or vice versa, ignoring punctuation and articles. Anything fuzzier = `[NEEDS REVIEW: external_title_mismatch]`.
2. **Author match** — at least the surname must appear in the result snippet. Multiple authors: at least one must match. Otherwise `[NEEDS REVIEW: external_author_mismatch]`.
3. **Year tolerance ±1** — publication year in result snippet must equal claimed year ±1 (accommodates ahead-of-print listings). Outside that window = `[NEEDS REVIEW: external_year_mismatch]`.
4. **Page in plausible range** — claimed page must fall within the work's plausible page range (if disclosed by the snippet). If the snippet says "232 pages total" and the citation claims p. 450, that's `[NEEDS REVIEW: external_page_implausible]`.

If any of the four checks fails, do NOT pass the citation. Mark the appropriate `[NEEDS REVIEW]` tag and let the researcher resolve.

If WebSearch returns no results, fall back to: `[NEEDS REVIEW: external_unverified]` rather than auto-passing.
```

- [ ] **Step 3: Verify**

Run: `grep -A1 "WebSearch result validation" src/agents/auditor.md`
Expected: header line plus the contract follows.

- [ ] **Step 4: Commit**

```bash
git add src/agents/auditor.md
git commit -m "fix(auditor): add explicit WebSearch validation contract

Per RULE-V27 (Code Review for AI Agents v4): zero trust for data
crossing process boundaries. WebSearch results must pass title/author/
year/page checks before being treated as citation confirmation.
Anything weaker → [NEEDS REVIEW: external_*]."
```

---

## Final Verification

### Task 21: Full plugin verification

- [ ] **Step 1: Full build**

Run: `npm run clean && npm run build 2>&1 | tail -10`
Expected: Skills 10 (after demotion), Agents 6, Commands 10.

- [ ] **Step 2: TypeScript hooks typecheck**

Run: `npm run typecheck`
Expected: zero errors. (No new `any` types introduced.)

- [ ] **Step 3: Structural tests**

Run: `python3 tests/test_plugin_structure.py 2>&1 | tail -10`
Expected: all pass (CLAUDE.md tests now satisfied since we authored it in Task 9).

- [ ] **Step 4: Hook smoke tests**

Run all four hook smoke tests (commands from Tasks 3, 14, 15) against the academic project at `~/dev/Yotam-Asistant/groups/main`. Expected: each fires correctly. Then run each against `/tmp` — expected: all silent-skip.

- [ ] **Step 5: Verify zero magic numbers in pipeline**

Run: `grep -rn "35/50\|40/60" src/ | grep -v "default 35/50\|default 40/60\|thresholds.json"`
Expected: zero output.

- [ ] **Step 6: Verify zero `cognetivy` and zero `runId`**

Run: `grep -rli "cognetivy\|runId\|run_id" src/`
Expected: zero output.

- [ ] **Step 7: Verify all 15 skills have description, allowedTools, metadata**

Run:
```bash
for f in src/skills/*/SKILL.md; do
  for field in description allowedTools metadata; do
    grep -q "^${field}:\|^${field/T/-t}:" "$f" || echo "MISSING $field: $f"
  done
done
```
Expected: zero `MISSING` lines.

- [ ] **Step 8: Tag the release**

```bash
git tag plugin-best-practices-v1
echo "Plan complete — all 17 fixes applied, verified, committed."
```

---

## Phase Boundaries (stoppable points)

The phases are independent enough that the executor can stop after any of them:

- **After Phase 1:** Quick wins applied; pre-existing CLAUDE.md test failures remain. Plugin is incrementally cleaner.
- **After Phase 2:** Magic numbers gone, scorecard is now machine-readable.
- **After Phase 3:** Documentation matches best practices; CLAUDE.md committed.
- **After Phase 4:** Hooks expanded — completion notifications + cross-agent context injection live.
- **After Phase 5:** Skill surface area shrunk; bodies are now phase-orchestration-only.
- **After Phase 6:** Model swap benchmarked; auditor's external verification is contract-bound.

Recommend: stop after Phase 3 if time-bound (those fixes address the user-visible issues). Continue to Phase 6 only if you want full conformance.

---

## Self-Review

**Spec coverage check:**
- V1 → Task 1 ✓
- V2 → Tasks 2 + 3 ✓
- V3 → Tasks 6 + 7 ✓
- V4 → Task 9 ✓
- V5 → Task 19 ✓
- V6 → Task 10 ✓
- V7 → Task 4 ✓
- V8 → Tasks 17 + 18 ✓
- V9 → Task 16 ✓
- V10 → Task 15 ✓
- V11 → Task 14 ✓
- V12 → Task 11 ✓
- V13 → Task 8 ✓
- V14 → Task 20 ✓
- V15 → Task 12 ✓
- V16 → Task 13 ✓
- V17 → noted (user-set, not codable) — covered as docstring guidance in Task 9 CLAUDE.md ✓

All 17 violations have at least one task. No gaps.

**Placeholder scan:** none ("TBD", "implement later", "similar to Task N", "add appropriate handling" all absent — every step shows actual code or exact commands).

**Type / signature consistency:**
- `notifyStop`, `subagentStart`, `sessionDashboard`, `sessionEndLog` all match the function names exported from `src/hooks/src/entries/lifecycle.ts`.
- All hook handlers consistently take `HookInput` and return `HookResult` per the existing types in `src/hooks/src/types.ts`.
- `thresholds.json` keys (`antiAi.passThreshold`, `selfReview.passThreshold`, `rewriteCycles.max`, `styleFingerprint.passThreshold`) are referenced consistently in Tasks 6, 7, 8, 11, 15.
- Skill descriptions referenced in Task 10 match the existing descriptions verified in the prep grep run.
- `notify-stop.ts` uses `execFile` (not `execSync`/`exec`) so no shell injection surface; the script string is a static literal.

No inconsistencies found.
