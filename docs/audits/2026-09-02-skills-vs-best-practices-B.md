# Skills vs Best Practices — Part B (9 skills + hook layer)

Audited 2026-09-02 on branch `feat/proofread-pipeline-0.7.0`, repo `/Users/yotamfromm/dev/learning/Academic Helper`.
Skills: `setup`, `help`, `health`, `ocr`, `learn`, `present`, `feedback`, `update-field`, `update-tools`.
Rules: TST-02, WRK-13, WRK-14, REV-03, VER-08, VER-10, SPC-14 (from CandleKeep `cmtifqy5a2cpun00jzpuztuca` ch.5/7/10/11/12) + repo-specific checks from `CLAUDE.md`.
This is part 2 of 2 — the first run's single 18-skill item died before returning a result; this half covers the above nine plus the hook layer, which no other item covers.

## Findings (most severe first)

| # | Severity | File:Line | Rule/Check | Finding |
|---|---|---|---|---|
| 1 | HIGH | `src/skills/present/SKILL.md:5,166-180` | Frontmatter completeness (CLAUDE.md) / correctness | `allowedTools` is `[Bash, Read, Write, Glob, Grep, AskUserQuestion]` — no `mcp__notebooklm-mcp__*` grant — yet the "Audio Overview" and "Study Guide" sections instruct calling `notebook_create`, `source_add`, `studio_create`, `studio_status`, `download_artifact` as MCP tools. Confirmed via `grep -n "mcp__" src/skills/present/SKILL.md` → **no matches**: the tools are referenced only by bare, unqualified name, never as `mcp__notebooklm-mcp__...`. Compare `src/skills/ocr/SKILL.md:5` and `setup/SKILL.md:6`, which both correctly declare `mcp__gemini-api__gemini_*` in `allowedTools` and invoke tools by fully-qualified name. As written, these two present.md branches cannot actually call the tools they describe. |
| 2 | HIGH | `CLAUDE.md` (repo root) command table vs `src/skills/setup/SKILL.md:4-5` | Correctness of repo claims | `CLAUDE.md`'s command table states `/academic-writer:init` "replaces the old `/academic-writer:setup` command — **setup is now an internal, non-invocable thin wrapper**." The actual file has `user-invocable: true` (only `disable-model-invocation: true`, a *different* property — that only blocks autonomous model invocation, not user slash-command exposure). `setup` is still a live, user-facing slash command, and `src/skills/help/SKILL.md:64` lists it as one ("Quick setup — creates profile, detects integrations"), consistent with the actual file but contradicting `CLAUDE.md`'s own documented convention. Either the CLAUDE.md claim is stale or the intended conversion to internal-only never shipped — worth a decision either way. |
| 3 | MEDIUM | `src/skills/present/SKILL.md:48,53,58,86,88,93,98,111,126,133,154` | Inline numeric gates (CLAUDE.md: "never inline numbers in skills — edit `thresholds.json`") | Ten+ inline numeric constants govern deliverable shape and are not read from `thresholds.json`: talk length "20-30 min" (L48, L86), per-section timing 3/5/15/5 min (L88,93,98,111), abstract "150-300 words" (L53, L126), keyword count "5-7" (L133), chapter length "8,000-12,000 words" (L154). `thresholds.json` has no corresponding keys and `present/` has no `references/` directory to hold them elsewhere (unlike `setup/references/`). These are softer "generation targets" than the paragraph/proofread quality *gates* thresholds.json defines, but the convention as literally stated is "never inline numbers in skills," with no carve-out for target lengths vs. hard gates — flagging as a convention gap rather than a functional bug. |
| 4 | MEDIUM | `src/skills/ocr/SKILL.md:139-147` | WRK-14 (caps/gates belong in the orchestrator script, not agent prompts) | The Files-API-failure "retry once, then narrow to single-page, then give up" cap is stated entirely in prose ("Retry **once**... If a single page alone still fails... do not keep retrying"). Nothing in `plugins/academic-writer/mcp/gemini-server` or a workflow script enforces this cap — it depends entirely on the executing agent's judgment to honor "once." Contrast the `thresholds.json` comment for the proofread pipeline, which explicitly notes its caps are "enforced in `src/workflows/proofread.js` from `args.thresholds` (WRK-14)" — i.e., a real precedent exists in this repo for doing this correctly, and `ocr.md`'s retry logic doesn't follow it. Low real-world risk (worst case is one extra retry loop, not a runaway), but it is a genuine WRK-14 gap by the rule's own test ("could an agent's judgment change this? If yes, it is not a gate"). |
| 5 | LOW | `src/skills/help/SKILL.md:206-211` | Correctness (internal document) | "Critical Guarantees" list is numbered 1, 2, 3, 5 — item 4 is missing (skipped in the source, not a rendering artifact — confirmed by reading the raw numbered list). Cosmetic, but a numbering bug in user-facing help text. |
| 6 | LOW | `src/skills/health/SKILL.md:110-121` | Correctness (internal document) | Section numbering is 1 (Profile), 2 (Past Articles), 3 (Candlekeep), 6 (NotebookLM), 7 (Agent Files) — sections 4 and 5 do not exist. Also, "Agent Files" (§7, `health/SKILL.md:117-121`) checks exactly 5 agents (`deep-reader`, `architect`, `section-writer`, `auditor`, `synthesizer`), matching `CLAUDE.md`'s own Agents table entries for those five. But `src/agents/` (`ls src/agents/`) actually holds 12 `.md` files: those 5, plus `proofreader.md` and `copyeditor.md`/`editor.md` (all three are proofread-pipeline agents per their own frontmatter — `editor.md:2` "Spawned once per article by the proofread skill", `copyeditor.md:2` "Spawned by the proofread skill" — confirmed by reading both files directly, not inferred from naming), plus the 4 voice-subsystem agents (`voice-miner.md`, `voice-interviewer.md`, `voice-distiller.md`, `voice-calibrator.md`). `CLAUDE.md`'s own Agents table also only lists 7 of the 12 (the 5 health.md checks, plus `proofreader.md` and `voice-miner.md`) — so health.md is additionally missing `proofreader.md`, which CLAUDE.md does document. Health's agent-file check is stale relative to both the current agent roster and CLAUDE.md's own table. |
| 7 | LOW | `src/skills/setup/SKILL.md:3` , `src/skills/learn/SKILL.md:3`, `src/skills/feedback/SKILL.md:3` | "Use when…" trigger phrase (CLAUDE.md anti-pattern: "don't author skill descriptions that omit 'Use when…' trigger phrases") | `setup`: "Use on first install, or anytime you want a fast guided re-check…" — no "Use when" phrase. `learn`: "Use after adding new past articles to `past-articles/`…" — no "when" clause at all. `feedback`: "Use after the researcher reviews an article produced by /academic-writer." — no "when" clause. All three describe a trigger condition in substance, just not the literal "Use when" wording the anti-pattern names. The other six skills (`help`, `health`, `ocr`, `present`, `update-field`, `update-tools`) all use "Use when…" verbatim. |
| 8 | N/A | — | REV-03 (parallel reviewers, orthogonal lenses) | None of the 9 skills in this batch implement a review/verification stage with multiple reviewer lenses — that pattern belongs to `auditor`/`synthesizer` (out of scope here) and the review skill audited elsewhere. N/A for this batch. |
| 9 | PASS | `src/hooks/bin/run-hook.mjs:53-59` and per-hook checks (see Hook Layer below) | VER-08 (verify the negative case) | Directly tested, not just read — see Hook Layer section. |

## Compact per-skill block

**setup** (`src/skills/setup/SKILL.md`) — Frontmatter complete (name/description/user-invocable/allowedTools/metadata.author+version, L1-8). Description lacks literal "Use when" (#7). Claims about repo checked: the `mcp__gemini-api__gemini_raw` credential-precedence description (plugin config → env var → `.academic-helper/secrets.json`, L175-178) matches the OCR skill's identical three-tier check (`ocr/SKILL.md:58-66`) — consistent. TST-02/WRK-13/WRK-14/VER-10/SPC-14: N/A, no automated loop or gate logic in this skill beyond a bounded, single-pass wizard.

**help** (`src/skills/help/SKILL.md`) — Frontmatter complete. Pure documentation skill, `allowedTools: [Read]` only — correctly scoped (no Bash/Write needed for a read-only doc dump). Finding #5 (numbering gap). Content cross-checked against `CLAUDE.md`'s own command table: all 12 CLAUDE.md-listed commands appear in help's table, plus `setup` (see finding #2) and the internal-skill list (`learn`, `update-tools`, `update-field`, `present`, `feedback`) matches CLAUDE.md's "Internal skills" table exactly.

**health** (`src/skills/health/SKILL.md`) — Frontmatter complete. Finding #6 (numbering gap, stale agent-file list). No numeric quality gates present — N/A for TST-02/inline-numbers. VER-08 relevant only in that health.md itself *is* the "confirm silence" tool for other integrations (reports Disabled when `tools.X.enabled` is false, L53, L74) — this is the correct behavior, not a bug.

**ocr** (`src/skills/ocr/SKILL.md`) — Frontmatter complete, correctly declares `mcp__gemini-api__gemini_ocr` (L5). Finding #4 (WRK-14 gap on retry cap). The ">20MB → Files API" and "40-page cap" numbers (L112, L134) are Gemini API/tool-level constants explicitly excluded from `thresholds.json`'s own scope (per its top-level `description` field: "Gemini model/thinking-budget defaults... are NOT read from here"), so these are **N-A** for the inline-numeric-gate check, not a violation. Sequential-only processing (L91-94, L201-203) is a genuinely hard rule stated with its own incident rationale ("a prior parallel run of this same tool corrupted output") — good practice, matches SPC-07's "record the ruled-out branch" pattern even though SPC-07 wasn't in this batch's required-rule list.

**learn** (`src/skills/learn/SKILL.md`) — Frontmatter complete (`user-invocable: false`, correctly matches CLAUDE.md's "internal skill" designation). Finding #7 (description wording). No numeric gates inline. Spawns `voice-miner` per `agents: [voice-miner]` frontmatter (L6) — matches `CLAUDE.md`'s Agents table entry for `voice-miner.md`.

**present** (`src/skills/present/SKILL.md`) — Frontmatter present but incomplete in practice (finding #1 — declared tool list doesn't cover the tools the skill body calls). Findings #1 and #3 are both in this skill. `user-invocable: false` correctly matches CLAUDE.md's internal-skill table.

**feedback** (`src/skills/feedback/SKILL.md`) — Frontmatter complete, `allowedTools` includes `Agent` (needed for the `voice-miner` spawn at L150) and `agents: [voice-miner]` (L6) — both correctly declared, unlike present.md's gap. Finding #7 (description wording). Category C pattern-cap edits (e.g., "lower cap from 3 to 2," L118, L161) are **not** an inline-numeric-gate violation — those numbers live in and are edited directly in `anti-ai-patterns-<language>.md` reference files (L157, referenced not duplicated), which is the correct pattern-cap storage mechanism per the write skill's own design (out of scope here, but consistent with the repo's stated architecture).

**update-field** (`src/skills/update-field/SKILL.md`) — Frontmatter complete. No numeric gates, no loops, "Use when" phrase present. Clean — no findings.

**update-tools** (`src/skills/update-tools/SKILL.md`) — Frontmatter complete. No numeric gates. "Use when" phrase present. The profile round-trip Python (L72-154) is a plain scalar/JSON-block rewrite with no gate logic — clean, no findings.

## Hook layer (`src/hooks/hooks.json` + `src/hooks/src/lifecycle/*.ts`)

All 5 lifecycle hooks plus `src/skills/voice/voice-migrate.sh` were read AND empirically tested (VER-08: confirmed the negative case, not just read the code) in two scenarios: (a) no `.academic-helper/` directory at all, and (b) `.academic-helper/` present but no `profile.md`. Both scenarios were run against the actual built `dist/lifecycle.mjs` via `run-hook.mjs`, in a throwaway tmp project dir, with `CLAUDE_PROJECT_DIR` set explicitly.

| Hook | Own `profile.md` check | Evidence | Empirical test (scenario b) |
|---|---|---|---|
| `session-dashboard.ts` | Yes, via `loadProfile()` → `existsSync(profilePath)` in `src/hooks/src/lib/profile.ts:78-79` | `session-dashboard.ts:8-12` returns `{continue:true, suppressOutput:true}` when `loadProfile` returns `null` | PASS — silent |
| `voice-pull.ts` | Yes, explicit | `voice-pull.ts:11-13` | PASS — silent |
| `subagent-start.ts` | Yes, explicit ("Hard gate") | `subagent-start.ts:18-21` | PASS — silent |
| `notify-stop.ts` | Yes, explicit ("Hard gate") | `notify-stop.ts:9-12` | PASS — silent |
| `session-end-log.ts` | Yes, explicit via `getProfilePath()` | `session-end-log.ts:9-13` | PASS — silent |
| `voice-migrate.sh` | Yes, explicit, and the comment names `run-hook.mjs:54` directly | `voice-migrate.sh:7-11` | PASS — exit 0, no output |

No hook is missing its own `profile.md` check — all six honour the CLAUDE.md profile-scoping convention on top of `run-hook.mjs`'s outer `.academic-helper/`-directory guard (`run-hook.mjs:53-59`, confirmed by direct code read and by an empirical scenario-a test above). `run-hook.mjs:54` is confirmed as the described outer guard (`join(projectDir, '.academic-helper')`, `existsSync` check, silent-JSON short-circuit).

`voice-migrate.sh` additionally widened its scope guard in commit `eaec73c` ("feat(gemini,docs): Gemini default-on for the target language; two P0 corrections", 2026-09-02): `voice-migrate.sh:16-19` now also recognizes `.academic-helper/profile.md` as a valid trigger for the *inner* legacy-migration logic (previously the inner check — distinct from the outer profile-scope guard at L7-11 — only recognized `.academic-writer/profile.json`, `AUTHOR_VOICE.md`, and `book.yaml`, so an Academic-Helper-only project with no legacy artifacts never reached the migration body at all). Commit message confirms the same rationale directly: "its profile-scope guard now recognizes `.academic-helper/profile.md` — previously only legacy markers counted, so an Academic-Helper-only project never reached it." Verified via `git show eaec73c --stat` and reading the commit body.

## Rule verdicts summary

| Rule | Verdict | Basis |
|---|---|---|
| TST-02 | PASS (no violation found) | No skill in this batch pushes a deterministic check into an LLM judgment call where a script would do; conversely `ocr.md`'s retry cap is a WRK-14 issue, not a TST-02 one (the cap itself is fine, its enforcement location is the gap). |
| WRK-13 (named-outcome, capped loops) | PASS | Every bounded operation in this batch (ocr retry-once, learn's single confirm/discard cycle) terminates in a named state; none are open-ended. |
| WRK-14 (caps in orchestrator script, not prompts) | FAIL (1 instance) | Finding #4 — `ocr.md`'s Files-API retry cap is prose-only, unlike the `proofread.js`-enforced precedent this repo already has for the same kind of cap. |
| REV-03 (orthogonal-lens parallel review) | N-A | No review-stage skill in this batch. |
| VER-08 (verify the negative case) | PASS, empirically verified | All 6 hook-layer files tested directly (see table above), not just read. |
| VER-10 (label pipeline-bypassed artifacts) | N-A | None of these 9 skills produce a final deliverable that bypasses the plugin's own quality pipeline in a way requiring a bypass label — `present.md`'s outputs (conference outline, abstract, etc.) are explicitly *post*-pipeline deliverables generated fresh from an already-finished article, not artifacts that skipped a gate that would otherwise apply to them. |
| SPC-14 (state which gates are automatic, out loud) | Partial gap | None of these 9 skills state explicitly which of their steps are human-gated vs. automatic. Most are conversational (every step has an implicit human-in-the-loop via `AskUserQuestion`), so the omission is lower-stakes than in a fully automated pipeline, but `feedback.md` Phase 4 ("Apply Changes") executes file edits immediately after a single `multiSelect` confirmation (Phase 3) without a second explicit "these will now be written automatically" statement — worth a one-line SPC-14 label but not a functional problem. |

## Test suite / typecheck tails

```
$ python3 -m pytest tests/ -q
........................................................................ [ 52%]
................................................................              [100%]
136 passed in 1.65s
```

```
$ npm run typecheck
> academic-writer@0.6.3 typecheck
> cd src/hooks && npx tsc --noEmit
(clean exit, no output)
```

Both commands exited 0 — re-run fresh for this revision (not carried over from the prior draft, which mis-stated 131/2.49s; the corrected, reproduced count is 136 passed in 1.65s), verified directly rather than inferred from a cache or prior run (per VER-09 / this vault's own `TST-05` precedent of not trusting `tests/` existence alone).
