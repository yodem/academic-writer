# Agent-prompt audit vs. CandleKeep "Personal · Agent Best Practices"

**Date:** 2026-09-02 · **Repo:** `~/dev/learning/Academic Helper` · **Branch:** `feat/proofread-pipeline-0.7.0` @ `98f5bf7` (4 commits ahead of `main` @ `24b2154`)
**Scope:** all 12 agent prompts in `src/agents/*.md`. This is a read-and-report audit — no agent, skill, script, or config file was modified. The only artifact written by this item is this report.

**Rule source:** CandleKeep item `cmtifqy5a2cpun00jzpuztuca` ("Personal · Agent Best Practices"), chapters 5 (REV), 7 (WRK), 10 (TST), 11 (SPC), 12 (VER), read in full via `ck items get <id> --page N` on 2026-09-02, cross-checked against the register at `~/dev/claude-obsidian/wiki/projects/ai-agent-best-practices.md` (both quoted verbatim below their rule IDs, not worked from IDs alone).

**Version stamp (VER-09):** this audit reads the working tree at commit `98f5bf7` on 2026-09-02. Any of these verdicts is stale the moment a later commit touches the cited file:line.

---

## Findings table (most severe first)

| # | Severity | Rule | Verdict | Agent(s) | Evidence |
|---|---|---|---|---|---|
| 1 | HIGH | TST-02 | FAIL | `proofreader.md`, `copyeditor.md`, `editor.md` | Each requires "the object MUST validate against `src/skills/proofread/references/changes-schema.json`" (`proofreader.md:98`, `copyeditor.md:61`, `editor.md:44`) as a **model-followed instruction**, not an enforced check. `find` over `src/scripts/` (`check-voice-populated.py`, `citation-guard.py`, `detect-ai-typography.py`, `extract-style-metrics.py`, `generate-docx.py`, `validate-hebrew-punctuation.py`, `write-proof-report.py`) found no JSON-schema validator script. Schema conformance — a textbook deterministic check — is asserted to the LLM with nothing downstream that would catch a malformed change object before it reaches `citation-guard.py` or the DOCX writer. |
| 2 | HIGH | WRK-13 / WRK-14 | FAIL | `section-writer.md`, `auditor.md` (as coordinated by `section-writer.md`) | `section-writer.md:282` ("Max rewrite cycles per paragraph defined in `thresholds.json > rewriteCycles.max` (default 3). If still failing after the max, include the paragraph with a `[NEEDS REVIEW]` marker.") and `:438` (fallback path, same cap) put a numeric cap in config, but the **counting and termination is the agent's own judgment** — there is no orchestrator script that tracks attempt N and refuses a 4th spawn. `find src/workflows` returns nothing; the plan of record (`~/.claude/plans/the-plugin-did-terrable-swift-lantern.md`, "Critical files") lists `src/workflows/proofread.js` and `src/workflows/write-sections.js` (Phase 2) as **not yet created** — the orchestrator today is `src/skills/write/SKILL.md`, itself a prompt read and executed by a Claude instance, not code. WRK-14's test — "could an agent's judgment change this? If yes, it is not a gate" — is failed directly: the same agent doing the rewriting is also the one deciding when it has hit 3. |
| 3 | MEDIUM | TST-02 | FAIL (partial) | `architect.md` | The "Coverage Pre-Check" (`architect.md:28-41`) — verify every chapter has a `status`, verify chapter numbers form a contiguous range, cross-check every `evidence_ids` entry exists in the evidence map — is pure array/set validation over a JSON structure the architect already has in context. This is fully scriptable (three checks: field presence, range contiguity, referential integrity) yet is executed by LLM reasoning with no deterministic pre-check gating the spawn. Contrast with finding #6 below, where the same repo does this correctly elsewhere. |
| 4 | MEDIUM | TST-02 | FAIL (partial) | `proofreader.md` | The "2017 כתיב מלא (Academy spelling reform)" table (`proofreader.md:79`, e.g. `תכנית→תוכנית`, `אמתי→אמיתי`, `לעתים→לעיתים`, `בנין→בניין`) is a fixed lookup-table substitution — the kind of exact-match rule that belongs in a dictionary/regex script — done via LLM instruction instead. Partial credit: the prompt itself names the exception cases needing judgment (proper names exempt, don't retro-fix deliberately pre-2017 text, internal-consistency override), which are genuinely not scriptable without more context, so this is not a clean-cut violation — the *lookup* half could still be deterministic with the *exception* half staying on the model. |
| 5 | MEDIUM | REV-03 | N/A (for all 12) | all 12 | No two of the 12 agent prompts are spawned in parallel over the *same* artifact with different lenses. The closest candidate — `editor.md` → `copyeditor.md` → `proofreader.md` — is an explicitly **sequential** chain (`copyeditor.md:3` "Runs AFTER editor and BEFORE proofreader"; `proofreader.md:3` "Runs AFTER copyeditor") with non-overlapping scope (venue/genre vs. sentence-level language vs. mechanics), not redundant parallel review. `auditor.md` is the sole citation verifier per paragraph with no second, differently-lensed reviewer ever spawned alongside it. REV-03 cannot be scored PASS or FAIL on any individual agent prompt because the parallel-review construct it names does not exist anywhere in this roster — recorded as a design gap, not a violation of a stated rule, since no agent claims to run in parallel with a same-lens twin. |
| 6 | — (positive) | TST-02 | PASS | `section-writer.md` | Step B, "Tier 1 typography auto-fix (deterministic, mandatory)" (`section-writer.md:242-260`, restated for the fallback path at `:397-409`) runs `scripts/detect-ai-typography.py` as an actual script call, explicitly labeled "This step is always run... because it is deterministic and cheap." This is the correct TST-02 pattern and is the one place in the roster the rule is applied as intended. |
| 7 | — (positive) | TST-02 (adjacent) | PASS | `proofreader.md`, `copyeditor.md`, `editor.md` (enforced externally) | The prompt-level "never touch citations" rule stated identically in all three (`proofreader.md:132`, `copyeditor.md:95`, `editor.md:76,79`) is **actually backed by a deterministic script** downstream: `src/scripts/citation-guard.py` (header comment, lines 1-24) reads every returned change and downgrades any change overlapping a citation/quotation/footnote/page-locator token to `applied: false`, "never dropped from the output." This is the correct WRK-14 shape (a gate an agent's own judgment cannot override) and stands in useful contrast to finding #1, where the *schema-validity* half of the same JSON contract has no equivalent script. |
| 8 | LOW | VER-08 | PASS | `proofreader.md`, `copyeditor.md`, `editor.md` | All three explicitly state the negative case as a valid, expected result: `proofreader.md:135` "If you find nothing, return `\"changes\": []` with an honest summary. A clean pass is a valid result."; `copyeditor.md:99` (identical pattern); `editor.md:81` "a clean editorial pass, with no findings, is a valid and expected result." This is exactly VER-08's "dog that doesn't bark" acceptance criterion, stated explicitly rather than left implicit. |
| 9 | LOW | VER-08 | N/A | `auditor.md`, `architect.md`, `deep-reader.md`, `section-writer.md`, `synthesizer.md`, `voice-miner.md`, `voice-distiller.md`, `voice-interviewer.md`, `voice-calibrator.md` | These agents are generative or binary-decision roles (must always produce a verdict, a draft, a fingerprint, or a question), not retrieval/detection roles with a genuine "stay silent" state to verify. VER-08 does not apply in the form the register states it. |
| 10 | LOW | VER-10 | PASS | `section-writer.md`, `synthesizer.md` | Both require `PATH: gemini \| fallback` as a mandatory field in every returned output (`section-writer.md:462`, `synthesizer.md` output section references the same path-reporting convention via its MCP-error-handling section at `:44-52`), so a bypass of the primary Gemini path is never silently absorbed — the researcher-facing output always names which path ran. `section-writer.md:29-33`'s voice rule-coverage WARN band is the same pattern: a degraded-but-passing state is required to prepend a labeled note to the output rather than proceed silently. |
| 11 | LOW | VER-10 | N/A | `architect.md`, `auditor.md`, `deep-reader.md`, `proofreader.md`, `copyeditor.md`, `editor.md`, `voice-miner.md`, `voice-distiller.md`, `voice-interviewer.md`, `voice-calibrator.md` | None of these ten has a documented alternate/bypass path for its own quality pipeline (auditor's gate is never itself bypassed; it *is* the gate). VER-10 has nothing to attach to. |
| 12 | LOW | SPC-14 | PASS | `proofreader.md`, `copyeditor.md`, `editor.md`, `auditor.md`, `voice-calibrator.md` | Each explicitly states, in its own frontmatter `description` and body, whether it is automatic-and-binding or comment/suggestion-only: `auditor.md:3` "citation hard gate... Returns VERDICT line as final output" (automatic); `editor.md:3,12` "Comment-only — never edits the article... Nothing you find is auto-applied" (explicitly not automatic); `copyeditor.md:3,12` "Suggestion-only... never edits files"; `proofreader.md:3,12` "Suggestion-only... never edits any file." `voice-calibrator.md:131-134` states the pass/warn/block score bands and their exact behavior at each band. This is SPC-14's "state which gates are automatic, out loud" done well and consistently across the pipeline's editorial layer. |
| 13 | INFO | Book-citation check (`ck items list`) | PASS (with a correction to the task's premise) | all 12 | `ck items list` (run 2026-09-02) shows `Hebrew Linguistic Reference` (`cmomjonvy0fdmk30zwef79c48`) is **present** in the CandleKeep library, not absent. `grep -n "Hebrew Linguistic Reference" src/agents/proofreader.md` returns no match — confirmed removed from `proofreader.md` per the task's premise — but `src/skills/init/references/style-analysis.md:58` and `src/scripts/extract-style-metrics.py:95` (the `--baseline` argparse help string) still name it, and that name still resolves to a real, `READY` library item. None of the 12 `src/agents/*.md` files hardcode a CandleKeep book title anywhere (`grep -n "Hebrew Linguistic\|CandleKeep\|Candlekeep book" src/agents/*.md` finds only generic sync/verification prose in `auditor.md`, `voice-miner.md`, `voice-calibrator.md` — no fixed title). So: (a) no agent in scope cites an absent book — PASS — and (b) the book the task flagged as possibly orphaned is in fact still in the library, so the two non-agent references are not currently broken, only inconsistently deduplicated across the codebase (the removal happened in one file, not three). |
| 14 | INFO | Frontmatter completeness | PASS (all 12) | all 12 | See per-agent detail below — every file declares `name`, `description`, `tools`, `model`, matching the project's own `CLAUDE.md` requirement ("Agents require `name`, `description`, `tools`, `model`"). |

---

## Per-agent detail

For each agent: frontmatter check, then the seven rules (TST-02, WRK-13, WRK-14, REV-03, VER-08, VER-10, SPC-14) in that order. Verdicts already justified in the findings table above are cross-referenced by number rather than re-argued.

### `architect.md`
- **Frontmatter** — `name: architect` (l.2), `description` with a "Use to..." trigger (l.3), `tools: Bash, Read, Write, Grep, Glob` (l.4), `model: sonnet` (l.5). PASS.
- **TST-02** — FAIL (partial). See finding #3: Coverage Pre-Check (l.28-41) is scriptable JSON validation done by LLM reasoning.
- **WRK-13/14** — N/A. No retry/rewrite loop in this prompt; the coverage-check failure path is a single reject-and-return, not a capped loop.
- **REV-03** — N/A (finding #5).
- **VER-08** — N/A (finding #9): architect always produces an output (thesis options, outline, or ownership map, or a single reject message) — no "stay silent" acceptance criterion is stated.
- **VER-10** — N/A (finding #11).
- **SPC-14** — Not scored (no automatic/human-gate distinction stated in this prompt for its own outputs — Mode A/B outputs are always presented to the researcher for approval per the caller skill, but that gate lives in `write/SKILL.md`, not here). UNVERIFIED for this file specifically — the gate exists but is described in the calling skill, not restated here; not a violation, just not this file's job to state.

### `auditor.md`
- **Frontmatter** — `name: auditor` (l.2), description with "Use as..." (l.3), `tools: Bash, Read, Grep, Glob, WebSearch` (l.4), `model: sonnet` (l.5). PASS.
- **TST-02** — Mixed. Check D (Metadata Integrity, l.119-134) is exact-field-string comparison against a registry (`sources.json`) — mechanically scriptable — done via LLM instruction. Check A/B/E/F/G require genuine judgment (does the passage support the claim; is a claim analytically anchored) and are correctly LLM-scoped. Net: FAIL on the Check D sub-scope specifically, by the same logic as finding #3 — not scored as a fresh top-level finding since it is the same pattern already captured, but noted here per-agent for completeness.
- **WRK-13/14** — Not directly in this file (the rewrite-cycle cap lives in `section-writer.md`, which coordinates the auditor — see finding #2). `auditor.md` itself has no loop; it emits one VERDICT per spawn and the *caller* decides whether to re-spawn.
- **REV-03** — N/A (finding #5): auditor is the sole citation verifier, no parallel second-lens reviewer.
- **VER-08** — N/A (finding #9): auditor always emits APPROVED or REJECTED, never "silent."
- **VER-10** — N/A (finding #11): auditor's own gate is never bypassed by design ("Non-Negotiable Rules", l.233-241).
- **SPC-14** — PASS (finding #12): l.3 states plainly it is the hard gate returning a binding VERDICT.

### `copyeditor.md`
- **Frontmatter** — `name: copyeditor` (l.2), description with scope + "Runs AFTER/BEFORE" ordering + "NOT for..." exclusions (l.3), `tools: Read, Grep, Glob` (l.4), `model: opus` (l.5). PASS.
- **TST-02** — FAIL (finding #1): schema-validation instruction (l.61) with no validator script.
- **WRK-13/14** — N/A. No loop or cap in this prompt (single pass, returns a change list; the orchestrator's refute-verify pass over `meaningRisk` bands is described but not owned by this file).
- **REV-03** — N/A (finding #5): sequential position confirmed at l.3.
- **VER-08** — PASS (finding #8): l.99.
- **VER-10** — N/A (finding #11).
- **SPC-14** — PASS (finding #12): l.3, l.12 ("Suggestion-only... never edits files").

### `deep-reader.md`
- **Frontmatter** — `name: deep-reader` (l.2), description with "Use to..." + explicit write exception (l.3), `tools: Bash, Read, Write, Grep, Glob, mcp__claude_ai_Sefaria__get_text` (l.4), `disallowed_tools: Edit, MultiEdit, NotebookEdit` (l.5), `model: sonnet` (l.6). PASS — and the `disallowed_tools` field is itself a good WRK-14-adjacent pattern (a capability boundary enforced by the tool grant, not by prompt wording alone): l.11-13 states the read-only rule in prose, and the frontmatter backs it with an actual tool-list restriction. Not scored as a numbered finding since it is not one of the seven audited rules, but worth recording as the strongest access-boundary example in the roster.
- **TST-02** — N/A. No mechanical validation logic comparable to architect's coverage check; the chapter-coverage schema (l.112-146) here is *produced* by deep-reader, not validated by it (the architect does the validation — see architect.md finding #3).
- **WRK-13/14** — N/A. No retry loop.
- **REV-03** — N/A (finding #5).
- **VER-08** — N/A (finding #9): always produces a structured summary.
- **VER-10** — N/A (finding #11).
- **SPC-14** — Not scored for this file specifically (same reasoning as architect.md — the approval gate is stated in the calling skill).

### `editor.md`
- **Frontmatter** — `name: editor` (l.2), description with scope + "Comment-only" + "NOT for..." (l.3), `tools: Read, Grep, Glob` (l.4), `model: opus` (l.5). PASS.
- **TST-02** — FAIL (finding #1): l.44.
- **WRK-13/14** — N/A. Single pass, no loop.
- **REV-03** — N/A (finding #5).
- **VER-08** — PASS (finding #8): l.81.
- **VER-10** — N/A (finding #11).
- **SPC-14** — PASS (finding #12): l.3, l.12.

### `proofreader.md`
- **Frontmatter** — `name: proofreader` (l.2), description with scope + ordering + "NOT for..." (l.3), `tools: Read, Grep, Glob` (l.4), `model: sonnet` (l.5). PASS.
- **TST-02** — FAIL, two distinct instances: schema validation (finding #1, l.98) and the 2017 spelling-reform lookup table (finding #4, l.79). Positive counterpart at finding #7 (citation-guard.py backs the "never touch citations" rule stated at l.132).
- **WRK-13/14** — N/A within this file (the re-sweep discipline at l.133 is a quality habit, not a numeric capped loop; the rewrite-cycle cap that *is* WRK-13/14-relevant lives in `section-writer.md`, finding #2).
- **REV-03** — N/A (finding #5): sequential position confirmed at l.3 ("Runs AFTER copyeditor").
- **VER-08** — PASS (finding #8): l.135.
- **VER-10** — N/A (finding #11).
- **SPC-14** — PASS (finding #12): l.3, l.12.
- **Book citation** — confirmed clean (finding #13): no "Hebrew Linguistic Reference" string anywhere in this file.

### `section-writer.md`
- **Frontmatter** — `name: section-writer` (l.2), description with routing + fallback + "NOT for..." (l.3), `tools: Bash, Read, Grep, Glob, Agent, mcp__gemini-api__gemini_write_section` (l.4), `model: sonnet` (l.5). PASS.
- **TST-02** — Mixed: PASS for the Tier 1 typography auto-fix (finding #6, l.242-260, restated l.397-409); FAIL for the rewrite-cycle cap being self-counted rather than script-enforced (part of finding #2).
- **WRK-13/14** — FAIL (finding #2): l.282 and l.438, no orchestrator script exists yet (`src/workflows/` absent) to enforce `thresholds.json > rewriteCycles.max`.
- **REV-03** — N/A (finding #5): section-writer spawns one auditor at a time (Continue vs. Spawn Decision Matrix, l.66-73) — sequential re-spawns on failure, never two auditors in parallel on the same paragraph.
- **VER-08** — N/A (finding #9): section-writer always produces section output.
- **VER-10** — PASS (finding #10): `PATH: gemini | fallback` mandatory in output (l.462); voice rule-coverage WARN-band note requirement (l.29-33).
- **SPC-14** — Partially stated: l.54-58 names the "two non-negotiable gates" (anti-AI threshold, auditor VERDICT: PASS) explicitly as gates the section-writer must not skip — this is the agent stating its *own* hard-gate obligations out loud, which is the SPC-14 spirit, though it is a self-imposed instruction rather than an orchestrator-external policy statement (relevant tension with the WRK-14 finding above: the same file that names its gates clearly also self-enforces their caps).

### `synthesizer.md`
- **Frontmatter** — `name: synthesizer` (l.2), description with routing + "does NOT write new section content" (l.3), `tools: Bash, Read, Grep, Glob, mcp__gemini-api__gemini_synthesize` (l.4), `model: opus` (l.5). PASS.
- **TST-02** — N/A. The full-article checks (introduction/conclusion structure, argument-graph fidelity, repetition) are inherently prose-judgment tasks not reducible to a script; the one quasi-mechanical piece (formula-pattern cap counting, l.195) is closer to a countable check than the others but still requires reading prose to find instances, so this is not flagged as a clean TST-02 violation.
- **WRK-13/14** — N/A within this file (no numeric retry cap; MCP-error fallback is a single deterministic branch, not a loop).
- **REV-03** — N/A (finding #5): synthesizer runs once, alone, after all sections — no parallel co-reviewer.
- **VER-08** — N/A (finding #9): synthesizer always returns a revised draft plus revision notes; no documented "if nothing to fix, stay silent" branch is stated (a genuinely clean article would still get a "Revision Notes" section, presumably near-empty) — UNVERIFIED whether an empty-findings run is explicitly handled as a valid terminal state, since the prompt does not say so the way proofreader/copyeditor/editor do.
- **VER-10** — PASS (finding #10): MCP fallback logging requirement (l.44-52) mirrors section-writer's path-labeling pattern.
- **SPC-14** — Not directly scored; l.68 ("Never write new section content... flag it with `[GAP: ...]`") is a scope boundary, not an automatic/human-gate statement about synthesizer's own output being auto-applied vs. reviewed — UNVERIFIED whether the synthesizer's revised draft is auto-committed or human-reviewed before becoming the article; that gate, if it exists, lives in the calling skill, not here.

### `voice-calibrator.md`
- **Frontmatter** — `name: voice-calibrator` (l.2), description with mode coverage (l.3), `tools: Read, Write, Edit, Bash, mcp__gemini-api__gemini_calibrate_sample` (l.4), `model: claude-haiku-4-5-20251001` (l.5), `metadata: {author, version}` (l.6-8). PASS.
- **TST-02** — N/A. The `--compare-models` side-by-side and the 3-question calibration are inherently human-judgment tasks; the rule-coverage score computation (l.119-134) is a corpus-scan-for-evidence task that is closer to an eval than a mechanical check — not flagged.
- **WRK-13/14** — Not applicable as a *loop* (this agent runs once per invocation, at fixed checkpoints — session 3, session 7 — not in a retry loop), but the pass/warn/block thresholds themselves (l.131-134) are read from `thresholds.json`, which is the correct WRK-14 shape (data-driven cap, not a hardcoded number in prose) — PASS on the narrow question of "is the cap itself deterministic data," though there is no orchestrator script independently checking the calibrator obeyed its own block rule (UNVERIFIED whether anything outside this prompt would catch a calibrator that ignored its own `< block` rule and proceeded anyway).
- **REV-03** — N/A (finding #5).
- **VER-08** — N/A (finding #9).
- **VER-10** — Not directly scored as a top-level finding, but l.47-49 ("If the tool returns `{ error: { code: "no_credentials" } }`: print... and exit without modifying the profile") is a clean, labeled bypass-and-stop pattern consistent with VER-10's spirit.
- **SPC-14** — PASS (finding #12): l.131-134 states the three score bands and exactly what happens at each, out loud.

### `voice-distiller.md`
- **Frontmatter** — `name: voice-distiller` (l.2), description (l.3), `tools: Read, Write, Edit` (l.4), `model: claude-haiku-4-5-20251001` (l.5), `metadata` (l.6-8). PASS.
- **TST-02** — N/A. Compression/merging of prose into a profile is not a mechanically-checkable task by nature.
- **WRK-13/14** — N/A. No loop.
- **REV-03** — N/A (finding #5).
- **VER-08** — Adjacent PASS: l.36-43 explicitly handles the negative/precondition-failed case — if `.voice/fingerprint.md` is missing or a `NEEDS CORPUS` stub, the agent must say so explicitly and "stop without writing `AUTHOR_VOICE.md` — leave any existing `AUTHOR_VOICE.md` untouched" rather than silently producing a fabricated profile. This is the constructive form of VER-08 (verifying the tool stays silent/inert when its precondition isn't met) even though it is not phrased as "if you find nothing." Recorded as a PASS for this agent specifically, distinct from finding #8's proofreader/copyeditor/editor pattern.
- **VER-10** — PASS: the partial-coverage marker (l.65-81, "Sessions covered: 1-2 of 7...") is a direct, mandatory VER-10 instance — an artifact that only went through part of the interview pipeline is required to say so at the point of delivery, in the file itself, not just in a log.
- **SPC-14** — Not directly scored (no automatic-vs-human-gate statement in this file; the profile it writes is consumed downstream without an explicit approval step named here).

### `voice-interviewer.md`
- **Frontmatter** — `name: voice-interviewer` (l.2), description (l.3), `tools: Read, Write, Glob` (l.4), `model: claude-haiku-4-5-20251001` (l.5), `metadata` (l.6-8). PASS.
- **TST-02** — N/A. Interview conduct is not mechanically checkable.
- **WRK-13/14** — Partial PASS on the cap shape: "Soft floor: 12 questions per session. Hard cap: 18 questions per session" (l.46-50) and "Stop at hard cap 18 even mid-thread" (l.98) are numeric, named caps — but they are still self-enforced by the interviewer agent counting its own questions, not checked by an external script. Given the low stakes of this particular loop (a chat interview, not a code-mutating retry loop), this is recorded as a minor instance of the same pattern as finding #2, not a fresh top-severity finding.
- **REV-03** — N/A (finding #5).
- **VER-08** — N/A (finding #9): the interviewer always asks something or explicitly ends the session; no silent-when-correct state applies.
- **VER-10** — PASS: session-end marker `<!-- session complete: <count> questions, <iso8601 timestamp> -->` (l.100-106) is an explicit, machine-readable record of exactly how much interviewing actually happened — directly supports the downstream `voice-distiller`'s VER-10 partial-coverage labeling.
- **SPC-14** — Not directly scored (no automatic/human-gate statement; the whole point of this agent is the human-in-the-loop interview itself).

### `voice-miner.md`
- **Frontmatter** — `name: voice-miner` (l.2), description (l.3), `tools: Read, Glob, Grep, Write, Bash` (l.4), `model: claude-haiku-4-5-20251001` (l.5), `metadata` (l.6-8). PASS.
- **TST-02** — Mixed: sentence/paragraph-length distribution and phrase-frequency stats (l.51-53) are exactly the kind of computation a deterministic script should own; the file does route PDF extraction through `pdfplumber` mechanically (l.23-42) rather than an LLM guess, which is the right TST-02 call for that specific sub-step — but the corpus-threshold check ("`> NEEDS CORPUS`" gate, l.68-69) reads `thresholds.json` values (`voice.corpus.minArticles` etc.) via prose comparison rather than a script computing and asserting the boolean. Not scored as a fresh top-line finding (lower stakes, no external artifact corrupted by an LLM arithmetic slip going unnoticed — the whole fingerprint is human-reviewed downstream by the interviewer and calibrator), but recorded as the same class of gap as findings #3/#4.
- **WRK-13/14** — N/A. No loop.
- **REV-03** — N/A (finding #5).
- **VER-08** — PASS (adjacent to voice-distiller's pattern): l.72-79 explicitly names the failure modes ("Empty/unreadable corpus → write stub flagged `> NEEDS CORPUS`; do not error") and requires downstream callers to check for that flag before proceeding — a documented, checkable negative-case signal.
- **VER-10** — Adjacent PASS: the `> NEEDS CORPUS` stub marker and the "N PDF(s) skipped — pdfplumber unavailable" note (l.37-42) both label a degraded/partial artifact at the point of delivery.
- **SPC-14** — Not directly scored.

---

## UNVERIFIED items (explicit)

- **`architect.md`, `deep-reader.md` SPC-14** — whether the outline/thesis/evidence-map these agents produce is gated by an *automatic* or *human* approval step is stated in the calling skill (`src/skills/write/SKILL.md`), not in the agent file itself. Not read as part of this item's scope (the task specified auditing `src/agents/*.md`); recorded as UNVERIFIED rather than scored, since scoring it PASS or FAIL from the agent file alone would not be grounded in evidence I actually read.
- **`synthesizer.md` VER-08** — whether a fully clean article (zero findings across all 11 review criteria) is an explicitly documented valid terminal state, the way it is for proofreader/copyeditor/editor. The prompt implies it (nothing forbids an empty "Revision Notes" section) but does not say so the way the other three do. UNVERIFIED, not scored FAIL, because the absence of a statement is not the same as a documented wrong behavior.
- **`voice-calibrator.md` WRK-14 (external enforcement)** — whether anything outside this prompt would actually catch a calibrator run that computed a `< block` score and proceeded anyway. No orchestrator script exists to check this (same absence as findings #1/#2). Recorded as UNVERIFIED-and-adjacent-to-#2 rather than double-counted as a fresh top-line finding, since the same root cause (no `src/workflows/*.js` yet) explains all of these.

---

## Verification run (unchanged code, per task requirement)

```
$ cd '/Users/yotamfromm/dev/learning/Academic Helper' && python3 -m pytest tests/ -q && npm run typecheck
```

**pytest tail:**
```
........................................................................ [ 56%]
.......................................................                  [100%]
127 passed in 1.42s
```
Exit code: `0`.

**typecheck tail:**
```
> academic-writer@0.6.3 typecheck
> cd src/hooks && npx tsc --noEmit
```
Exit code: `0` (no `tsc` output at all is the expected clean result under `--noEmit`).

Both green, unchanged from the state at commit `98f5bf7` — no code, skill, agent, or config file was modified by this audit. The only file this item wrote is this report.
