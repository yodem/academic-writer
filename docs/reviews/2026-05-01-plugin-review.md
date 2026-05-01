# Academic Helper — Plugin Review

**Date:** 2026-05-01
**Method:** Cross-check of plugin source against ~80 best-practice rules extracted from 6 books in the user's CandleKeep library, including the user-mandated *Claude Opus 4.7 + Claude Code: Operator's Rulebook*.
**Scope:** All agents, skills, hooks, manifests, build script, and routing.
**Subagent execution:** Sonnet, per user instruction.

---

## TL;DR

The plugin's **architecture is sound** — the section-writer pipeline matches Anthropic's "prompt chaining with gates" pattern (Building Effective Agents, p. 7), the auditor implements proper Trust-Then-Verify (Best Practices, p. 11), and the deep-reader correctly uses two-level read-only enforcement (Architecture, p. 1). Skill folders follow naming and frontmatter rules.

The **biggest weaknesses** are: dead hook code (3 of 4 hooks defined but unregistered), magic-number thresholds scattered across files, no CLAUDE.md (which the routing layer assumes exists), mismatched model assignments (section-writer is opus despite running a deterministic 8-skill pipeline), and zero progressive-disclosure use beyond the `write` skill.

A small set of high-leverage changes (register the hooks or delete them, centralize the thresholds, add CLAUDE.md, push references/ for big skills, reconsider opus-on-section-writer) addresses 70% of the violations.

---

## Strengths (keep these)

| # | What's right | Rule satisfied |
|---|---|---|
| S1 | All skill folders kebab-case; all `SKILL.md` exact case | RULE-S01, S02 (Skills Guide, p. 1) |
| S2 | All 15 skills have `name` + `description` frontmatter | RULE-S04 (Skills Guide, p. 1) |
| S3 | All 6 agents declare `## Input` and `## Output` sections | (Architecture book convention) |
| S4 | `deep-reader` enforces read-only with both `disallowed_tools` AND prompt prohibition | RULE-A11 (Architecture, p. 1) — two-level enforcement |
| S5 | Auditor spawns as separate subagent with restricted tools, fresh context | RULE-C9, C13, C14 (Best Practices, p. 7-11) |
| S6 | Section-writer pipeline has explicit hard gates (citation audit halts on failure) | RULE-B7, B8 (Building Effective Agents, p. 7) |
| S7 | Self-review scorecard has explicit threshold + dimensions, not vague "quality" | RULE-B14 (Building Effective Agents, p. 11) |
| S8 | `run-hook.mjs` short-circuits if `.academic-helper/` absent — silent in non-academic projects | (matches user's prior feedback memory) |
| S9 | Build script generates `commands/*.md` from user-invocable skills — single source of truth | RULE-V14 inverse (no duplicate parsing) |
| S10 | Plugin agents are namespaced (`academic-writer:*`) | RULE-A14 (Architecture, p. 1) |
| S11 | `respectGitignore: true` in plugin settings | (defensive default) |
| S12 | `[NEEDS REVIEW: <field>]` marker contract is explicit and bidirectional (writer emits `[?]`, auditor tags) | RULE-V15 (structured error context) |

---

## Violations

Severity scale (from *Code Review for AI Agents v4*, Ch. 1): **CRITICAL** = data loss / silent corruption · **HIGH** = bugs that ship · **MEDIUM** = maintenance burden · **LOW** = polish.

### V1 — `runId` orphan reference (HIGH)
- **Location:** `src/agents/section-writer.md:464` still lists `runId` as an agent input parameter, left over from cognetivy removal.
- **Why it matters:** Section-writer's input contract is now wrong — callers (the `write` skill) no longer pass `runId`, so the field is documented but never populated. RULE-A12 says agent prompts must not include orphaned/unused fields.
- **Fix:** Remove the `runId` bullet from `src/agents/section-writer.md:464`.

### V2 — Three hook handlers defined but unregistered (HIGH)
- **Location:** `src/hooks/src/lifecycle/check-profile.ts`, `load-fingerprint.ts`, `session-dashboard.ts` are compiled into the bundle but `src/hooks/hooks.json` only registers `lifecycle/session-end-log` (SessionEnd).
- **Why it matters:** RULE-V13 (Code Review v4): "shallow modules" where public surface ≥ implementation are a code smell. Here the modules have zero public callers — they're entirely dead code that ships with every install. RULE-S15 (composability) is also violated — these handlers exist but never compose with anything.
- **Fix:** Either (a) register them under the right lifecycle events in `hooks.json` (`SessionStart` for dashboard + fingerprint + check-profile), or (b) delete them and trim the bundle.
- **Recommendation:** Delete `check-profile.ts` (its job is now done by the `run-hook.mjs:54` directory check) and `load-fingerprint.ts` (verbose dump on every session is anti-pattern per RULE-C7 "ruthlessly prune"). Keep `session-dashboard.ts` and register it on `SessionStart` — that's the user-facing value.

### V3 — Magic-number gate thresholds (HIGH)
- **Location:**
  - Anti-AI threshold `35/50` in `src/agents/section-writer.md` and referenced from `src/skills/write/SKILL.md`
  - Self-review threshold `40/60` in `src/skills/review/SKILL.md`
  - "3 rewrite cycles" in `src/agents/section-writer.md:467`
- **Why it matters:** RULE-V10 (Code Review v4, Ch. 3, Rule 3.3): "Magic number in conditional/calculation [Severity:] HIGH". RULE-V30 (shotgun surgery): changing a threshold requires editing multiple unrelated files.
- **Fix:** Centralize all thresholds in one file (e.g., `src/thresholds.json` or YAML in profile.md). Section-writer / review / write all reference the same source.

### V4 — `CLAUDE.md` missing despite being load-bearing (HIGH)
- **Location:** Referenced by tests (`tests/test_plugin_structure.py:289`) and by the user's *global* `~/.claude/CLAUDE.md` Intent Table. Project root `CLAUDE.md` does not exist (gitignored per commit `ea48a76`).
- **Why it matters:** RULE-C6 (Best Practices, p. 3): "CLAUDE.md must include only what the agent cannot infer from code." RULE-C17 (p. 4): "Each team at Anthropic maintains a CLAUDE.md in git to document mistakes." The plugin **expects** routing/intent to flow through CLAUDE.md but there isn't one. Without it, the routing layer can't know which skill to invoke for which intent inside the project context.
- **Fix:** Author a minimal `CLAUDE.md` (≤ 60 lines) with: project-specific bash commands (`npm run build`, `python3 tests/test_plugin_structure.py`), the convention that `.academic-helper/` profile is the single source of truth, and an intent table for the 15 skills. Un-gitignore it (commit `ea48a76` was wrong — CLAUDE.md is meant to be committed per Best Practices p. 4).

### V5 — Section-writer is `opus` for a deterministic 8-skill pipeline (HIGH)
- **Location:** `src/agents/section-writer.md` frontmatter `model: opus`, body 550 lines, runs once per paragraph.
- **Why it matters:** RULE-A05 (Architecture, p. 1): "use `inherit` for agents that need the same reasoning capacity as the parent; use a fast-model ID only for agents where speed is the priority." RULE-O01 (Operator's Rulebook, p. 1): "Default to xhigh for coding and agentic work" — but this rule is about *effort level*, not *model*. The 8-skill pipeline is largely transformational (style check, grammar, repetition, citation match against a registry); the only step that needs deep reasoning is the Draft step, and even that has a tight context (one paragraph + sources). Running opus per paragraph for a 10-paragraph article = 10× opus cost where sonnet would do.
- **Fix:** Change section-writer to `model: sonnet` (or `inherit`). Keep `style-miner` and `synthesizer` on opus — those genuinely need cross-document reasoning. Run a benchmark on 2-3 representative paragraphs before/after per RULE-O10.

### V6 — `description` field violations (MEDIUM)
- **Location:** Several skill descriptions describe WHAT but skip WHEN trigger phrases.
  - `health/SKILL.md`: "Check the health of all Academic Writer integrations…" → no trigger like "use when something stops working" or "use after install"
  - `update-field/SKILL.md`: similar — describes capability, not trigger
  - `learn/SKILL.md`: "Update style fingerprint by analyzing newly added past articles." → describes what, not when
- **Why it matters:** RULE-S08 (Skills Guide, p. 1): description must include trigger phrases users would say. RULE-S18: undertriggering = add keyword diversity. The router can't pick a skill it doesn't know is relevant.
- **Fix:** Add a "Use when…" clause to every user-invocable skill description. Example for `health`: "Check the health of all Academic Writer integrations — profile, Candlekeep, RAG, past articles. **Use when something stops working, after a fresh install, or before starting a long write session.**"

### V7 — Three skills have no `allowedTools` declaration (MEDIUM)
- **Location:** `health`, `help`, `update-field`. Inventory confirms no `allowedTools` key.
- **Why it matters:** RULE-S16 (Skills Guide, p. 1): use `allowed-tools` when the skill has no need for full tool access. `help` is documentation-only — should be `allowed-tools: []` or omit. `health` runs many bash commands — must be restricted. `update-field` writes to profile.md — needs Write/Edit only.
- **Fix:** Add explicit `allowedTools` to `health` (Bash, Read), `update-field` (Read, Write, Edit, AskUserQuestion). For `help`, declare `allowedTools: []` or just `[Read]`.

### V8 — No `references/` for big skills (MEDIUM)
- **Location:** `init/SKILL.md` is **568 lines**, `setup/SKILL.md` is 355, `write/SKILL.md` is 520, `feedback/SKILL.md` is 243, `ideate/SKILL.md` is 241. Only `write` uses `references/` (for anti-AI patterns).
- **Why it matters:** RULE-S09, S10, S11 (Skills Guide, p. 1, p. 9): SKILL.md should be under 5,000 words; move detailed docs to `references/`. The `init` skill body alone has detailed JSON schemas, profile parsing examples, integration registration commands, all inlined. RULE-O05: front-load intent, but progressive disclosure means the *body* is loaded every time the skill triggers.
- **Fix:**
  - `init`: split detail (profile JSON schema, registration commands, vectorless setup) into `references/profile-schema.md`, `references/integration-setup.md`. Body becomes phase-by-phase orchestration only.
  - `write`: split per-skill detail (style fingerprint scoring rubric, anti-AI scoring matrix) into `references/`.
  - Target SKILL.md body length: under 200 lines.

### V9 — All 15 skills are user-invocable (MEDIUM)
- **Location:** Every `SKILL.md` has `user-invocable: true`.
- **Why it matters:** That's 15 slash commands the user must remember. Some (`update-field`, `update-tools`, `learn`, `present`, `feedback`) are sub-workflows that could be invoked from `/academic-writer` or `/academic-writer:edit` rather than be top-level commands. RULE-C12 (Best Practices, p. 3): skills are for "domain knowledge or workflows that are only relevant sometimes." Internal helpers don't need their own slash command.
- **Fix:** Consider making `learn`, `update-field`, `update-tools`, `present`, `feedback` **internal** (no `user-invocable` flag). The main entry points stay user-invocable: `init`, `setup`, `write`, `edit`, `edit-section`, `research`, `ideate`, `review`, `health`, `help`. That's 10 commands instead of 15.

### V10 — No `SubagentStart` hook for cross-agent context injection (MEDIUM)
- **Location:** Plugin spawns subagents (auditor) but `hooks.json` doesn't register a `SubagentStart` hook.
- **Why it matters:** RULE-H05 (Architecture, p. 1): "`SubagentStart` hooks should be used to inject context that must be consistent across every spawned agent." Currently every section-writer paragraph re-includes the full citation rules in its prompt (~100 lines of audit instructions repeated per paragraph). A `SubagentStart` hook could inject these once.
- **Fix:** Add a `lifecycle/subagent-start.ts` hook that injects citation rules + thresholds for `auditor`-type spawns. Register on `SubagentStart` in `hooks.json`. Strip duplicated rules from `section-writer.md`.

### V11 — No completion notification hook (MEDIUM)
- **Location:** `hooks.json` has only `SessionEnd` (which writes a log file).
- **Why it matters:** RULE-O08 (Operator's Rulebook, p. 1): "Set a notification hook (sound, system notification, push) that fires when the agent finishes a task." A 10-paragraph article runs 10 minutes; the user doesn't know when it's done.
- **Fix:** Add a `Stop` or `SessionEnd` hook that issues `osascript -e 'display notification …'` (macOS) or a sound. One-liner.

### V12 — Section-writer instructions don't include speed/depth cues (MEDIUM)
- **Location:** No agent or skill body uses "think carefully and step-by-step" or "respond directly without thinking."
- **Why it matters:** RULE-O03, O04 (Operator's Rulebook, p. 1): Opus 4.7 uses **adaptive** thinking, controlled by prompt phrasing. Without explicit cues, the model defaults — which may be wrong for high-stakes citation audits (need depth) or for quick repetition checks (need speed).
- **Fix:** Add to auditor system prompt: "Think carefully and step-by-step before each VERDICT — citation correctness is non-negotiable." Add to repetition-check skill step: "Prioritize responding quickly; this is a mechanical scan, not deep reasoning."

### V13 — Self-review gate is prose, not contract (MEDIUM)
- **Location:** `src/skills/review/SKILL.md` describes the 6-dimension scorecard and the < 40/60 threshold in markdown body.
- **Why it matters:** RULE-V17 (Code Review v4): gates must be precondition/postcondition contracts, not docstring. The current gate is enforced by Claude reading the prose and deciding — fragile.
- **Fix:** Move scorecard rubric into a JSON file (`src/skills/review/references/scorecard.json` with `dimensions`, `weights`, `thresholds`). The skill body just orchestrates; the file is the contract. Test by reading and validating the JSON in a hook.

### V14 — Citation auditor's WebSearch results unvalidated (MEDIUM)
- **Location:** `src/agents/auditor.md:5` adds `WebSearch` for optional external verification but no schema validation of returned results before treating them as ground truth.
- **Why it matters:** RULE-V27 (Code Review v4, Rule 7.4): "Every external API response must be validated before use. Zero trust for any data that crosses a process boundary." A WebSearch hit returning a Google Books snippet that *looks like* the citation but is from a different edition silently passes.
- **Fix:** Auditor must verify: title match (exact), author match, year (±1), page number range. If any field misses, mark `[NEEDS REVIEW: external_verification]` rather than auto-pass.

### V15 — `health/SKILL.md` and others lack negative triggers (LOW)
- **Location:** No `Do NOT use for…` clauses anywhere.
- **Why it matters:** RULE-S17 (Skills Guide, p. 9): over-triggering correction = add negative triggers.
- **Fix:** Where two skills overlap (e.g., `setup` vs `init`, `edit` vs `edit-section`), add a "Do NOT use for…" clause to the smaller one pointing to the bigger one.

### V16 — No `metadata` block (author/version) in skill frontmatter (LOW)
- **Location:** None of 15 skills.
- **Why it matters:** RULE-S20 (Skills Guide, p. 1): suggested fields `author`, `version` for attribution and update tracking.
- **Fix:** Add `metadata: {author: "Yotam Fromm", version: "0.2.18"}` to each SKILL.md frontmatter, sourcing version from `manifests/academic-writer.json`.

### V17 — Plugin doesn't declare effort level for any agent (LOW)
- **Location:** No agent or skill mentions effort.
- **Why it matters:** RULE-O01 (Operator's Rulebook, p. 1): "Default to xhigh for coding and agentic work."
- **Fix:** This is set per-session by the user, not in the agent definition. But the `write`/`edit` skills should remind users: "For full articles, run with effort = xhigh."

---

## Recommended changes (ranked)

| Rank | Change | Effort | Severity addressed | Files |
|---|---|---|---|---|
| 1 | Delete dead hooks (`check-profile`, `load-fingerprint`); register `session-dashboard` on `SessionStart` | 30 min | V2 | `src/hooks/src/lifecycle/`, `src/hooks/hooks.json` |
| 2 | Remove orphan `runId` from section-writer input contract | 2 min | V1 | `src/agents/section-writer.md:464` |
| 3 | Centralize thresholds in `src/thresholds.json` (anti-AI 35/50, self-review 40/60, max-rewrites 3) | 1 hr | V3 | new file + 3 refs |
| 4 | Author a minimal committed `CLAUDE.md` (≤ 60 lines) | 1 hr | V4 | `CLAUDE.md` (un-gitignore) |
| 5 | Switch section-writer to `model: sonnet`; benchmark on 3 paragraphs | 30 min + bench | V5 | `src/agents/section-writer.md` |
| 6 | Add `allowedTools` to `health`, `update-field`, `help` | 10 min | V7 | 3 files |
| 7 | Rewrite skill descriptions to include trigger phrases ("Use when…") | 1 hr | V6 | 15 files (1 line each) |
| 8 | Push `init/`, `write/`, `setup/` long bodies into `references/` | 3-4 hr | V8 | 3 skills |
| 9 | Demote 5 skills to internal (`learn`, `update-field`, `update-tools`, `present`, `feedback`) | 30 min | V9 | 5 frontmatter edits + build script |
| 10 | Add `SubagentStart` hook injecting citation rules; strip dup rules from `section-writer.md` | 2 hr | V10 | new hook + edit |
| 11 | Add macOS notification hook on `Stop` | 10 min | V11 | new hook |
| 12 | Add depth/speed cues to auditor + repetition-check | 30 min | V12 | 2 files |
| 13 | Move review scorecard rubric to `references/scorecard.json` | 1 hr | V13 | review skill |
| 14 | Tighten WebSearch validation in auditor | 1 hr | V14 | auditor agent |
| 15 | Add negative triggers where skills overlap | 30 min | V15 | 4-5 skills |
| 16 | Add `metadata` block to all skills | 30 min | V16 | 15 frontmatters |

**High-leverage subset (do these first):** V1 (2 min), V2 (30 min), V4 (1 hr), V5 (30 min + bench), V7 (10 min). That's about 2.5 hours and addresses the most visible issues.

---

## Books consulted (CandleKeep)

- *Claude Opus 4.7 + Claude Code: Operator's Rulebook* (`cmo2kdydq00x1qp0z5ytxf951`) — user-mandated; supplied O1-O10
- *The Complete Guide to Building Skills for Claude* (`cmljdcdjx0007p90zj50hbajf`) — supplied S01-S21
- *Inside Claude Code: The Architecture* (`cmnft2cot0163qh0zskpzuphq`) — supplied A01-A14, H01-H09, SA01-SA06
- *Building Effective Agents* (`cmljg1ebo000pmn0zgxkxg3vk`) — supplied B1-B22
- *Claude Code: Best Practices for Agentic Coding* (`cmljgy3zc0061mn0zljyxwe2w`) — supplied C1-C18
- *Code Review for AI Agents v4* (`cmn0o20r901ccqo0znj3zzqh9`) — supplied V1-V30 (selected from 231 rules)

Total: ~110 rules considered, 17 violations identified, 12 strengths confirmed.
