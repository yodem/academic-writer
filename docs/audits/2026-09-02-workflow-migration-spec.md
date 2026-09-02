# Migration spec: `write` / `edit` / `edit-section` onto Workflow-tool scripts

**Date:** 2026-09-02 · **Repo:** `$REPO` ·
**Branch:** `feat/proofread-pipeline-0.7.0` (HEAD `98f5bf7`, 4 commits ahead of `main` `24b2154`) ·
**Status:** scoping only — no workflow script or skill/agent file was written or modified by this item.

This spec scopes the Phase 2 migration described in
`the 0.7.0 plan of record (local, not committed to this repo)` ("Phase 2 — `write` as a workflow",
lines 349–373), extended to `edit` and `edit-section` per the follow-up audit's goal contract
(same file, lines 404–405: "`write` / `edit` / `edit-section` migration to workflow scripts is
scoped as a spec with the Phase 2 mechanics of this plan as its precondition").

---

## 0. Precondition check — Phase 1 shipped and its eval gate passed

**Plan text (line 351):** "Precondition: Phase 1 shipped and the eval gate passed (proves
scriptPath under the plugin root, `agentType` resolution of plugin agents, `args` plumbing, and
the size guideline behaviour)."

**Verdict: NOT MET, as of 2026-09-02 on `feat/proofread-pipeline-0.7.0`.**

Evidence gathered this session (commands run against the live tree, not against the plan's
narrative):

- `find src/workflows src/scripts -maxdepth 1` → no `src/workflows/` directory exists at all;
  `src/scripts/` contains only pre-existing deterministic scripts (`generate-docx.py`,
  `extract-style-metrics.py`, `write-proof-report.py`, `detect-ai-typography.py`,
  `citation-guard.py`, `validate-hebrew-punctuation.py`, `check-voice-populated.py`). None of the
  Phase 1 scripts the plan lists at lines 267–278 (`chunk-article.py`, `spellcheck-candidates.py`,
  `apply-changes.py`, `build-tracked-docx.py`) exist yet, though `write-proof-report.py` and
  `citation-guard.py` do.
- `grep -rn "Workflow(" src/` → zero hits. No call site anywhere in `src/` invokes the Workflow
  tool. `scriptPath` resolution under `${CLAUDE_PLUGIN_ROOT}/workflows/`, `agentType` resolution of
  plugin-namespaced agents (e.g. `academic-writer:auditor`), and `args` plumbing are therefore
  **unproven mechanisms**, not merely an unshipped feature — the plan names exactly these three as
  what Phase 1's eval gate would prove (line 351), and none has been exercised end-to-end via the
  Workflow tool in this codebase.
- `src/agents/editor.md` and `src/agents/copyeditor.md` exist (new agents per plan §1.7, line 334),
  but `src/skills/proofread/SKILL.md` still contains the plan's own "future Option B" language at
  line 18 (`"One-click accept/reject is the future Option B — DOCX tracked-changes + /apply"`)
  that plan line 337 says must be removed as part of the rewrite ("Remove the 'future Option B'
  note at `:16-18`"). The proofread skill has not been rewritten into the
  `resolve → chunk/spellcheck/venue → Workflow (or fallback) → guard → apply → build DOCX → report`
  shape the plan specifies.

**Conclusion:** Phase 1 is partially started (new agents exist, some deterministic scripts exist)
but has not shipped a working `src/workflows/proofread.js`, has not exercised the Workflow tool
once, and its eval gate (`node tests/e2e/proofread-recall.mjs`, plan line 438: "9/9 mechanical,
5/5 editorial") has not run because the workflow script it depends on does not exist. **This spec
scopes Phase 2 (and the edit / edit-section extension) as work that cannot start until that gate
passes** — everything below is a scoping document to be validated against real `scriptPath`,
`agentType`, and `args` behavior once Phase 1 proves them, not a spec that can be executed as-is
today.

---

## 1. Per-skill stage mapping

For each skill: which stages move into a workflow script, and which MUST stay interactive in the
skill under SPC-03 ("Put the human approval gate **before** code generation" — CandleKeep Agent
Best Practices, Ch. 11, quoted verbatim via `ck items get cmtifqy5a2cpun00jzpuztuca --page 11`).

### 1.1 `write` (`src/skills/write/SKILL.md`)

| Stage | Lines | Moves to script? | Rationale |
|---|---|---|---|
| Voice precondition gate | `:16-37` | **Stays in skill** | Gates the whole run before any generation; a `python3 check-voice-populated.py` exit-code check the skill must act on interactively (STOP + human message on exit 1/2). |
| Gemini pre-flight / engine commit | `:48-65`, `:336-341` | **Stays in skill** | Determines engine (`geminiMode`/`geminiFallback`) before any agent spawns; writes `.academic-helper/session-state.json`, which the script's `args` object then simply reads and passes through. |
| Steps 1–5 (Subject/Language, Length, Draft detection, Source Selection, NotebookLM query, Deep Read, Thesis Proposal, Outline+Approval) | `:129-296` | **Stays in skill (SPC-03)** | Plan line 354: "Planning (deep-reader → architect → human approval of the outline) **stays in the skill** (SPC-03)." Every one of these steps either asks the researcher a question (`AskUserQuestion` or free text) or requires their explicit "go/looks good/start writing" (`:293`). |
| Step 5.5 Argument Graph Validation | `:298-313` | **Stays in skill** | Explicitly "not a subagent call; it is reasoning directly over the outline JSON already in memory" (`:300`) — a pre-generation gate with four named checks (orphan sections, `depends_on` cycles, empty evidence, ordering) that must pass or loop back to the architect (interactive), before Step 6 is allowed to run at all. |
| Step 6 Parallel Section Writing + per-paragraph 8-skill pipeline (draft → audit → rewrite loop) | `:332-359` | **Moves to script** (`src/workflows/write-sections.js`) | This is the generation stage the plan targets (line 356: `pipeline(units, draft (...), audit each paragraph (...), rewrite loop ...)`). No human input occurs mid-loop today — the loop is fully mechanical once the outline is approved. |
| Step 8 Synthesis + repetition check | `:363-387` | **Moves to script** | Plan line 362: "barrier → `synthesizer` → `review` scorecard ... → return." Runs automatically today with no human gate between Step 6 and Step 8. |
| Step 8.5 Abstract Generation | `:391-409` | **Moves to script** (folded into synthesis/return) | No human interaction; deterministic generation off the completed article. |
| Step 8.7 Self-Review (Quality Gate) scorecard | `:412-429` | **Split**: scoring **moves to script** (reads `references/scorecard.json` schema, returns numeric scorecard as part of the workflow's return value), but **the below-threshold branch stays in the skill** | Plan line 364: "Skill resumes inline: below-threshold scorecard → `AskUserQuestion` (human gate)." The threshold comparison against `thresholds.json > selfReview.passThreshold` (`src/thresholds.json:10-15`, default 40/60) can run inside the script (it is a pure comparison), but only the skill can invoke `AskUserQuestion`, since the script has no interactive tool access (see §3). |
| Step 9 DOCX Output (`generate-docx.py`) | `:433-489` | **Stays in skill** | Plan line 365: "DOCX via `generate-docx.py` as today (`write/SKILL.md:466-478`)." This is a deterministic script call already outside any agent loop — no reason to route it through the Workflow tool; it also needs the skill's own `Write` tool to stage `/tmp/aw-article-data.json` first (`:472-476`), and `Write`/`Bash` at this shape are already available to the skill. |

**Section 5.5's ownership matters for the script boundary**: because the argument-graph gate runs
*before* Step 6 and *inside the skill's own reasoning* (not a subagent, not the script), the
script's `args.outline` arrives **already validated** — the script does not need to re-implement
the four checks, but the skill must pass the *post-validation* outline, not the raw architect
output, so a Phase 2 regression test should assert the skill does not skip 5.5 when the Workflow
path is used (see §5).

### 1.2 `edit` (`src/skills/edit/SKILL.md`)

| Stage | Lines | Moves to script? | Rationale |
|---|---|---|---|
| Voice profile load, Gemini routing decision | `:14-51` | **Stays in skill** | Same class as write's engine commit — a precondition, not generation. |
| Load Profile / Load Article / Load Source Registry | `:53-98` | **Stays in skill** | Requires interactive researcher choice at `:69-73` ("Which article do you want to edit?") and a conditional `AskUserQuestion`-style prompt at `:94-97` when `sources.json` is stale. |
| Understand the Edit Request | `:101-113` | **Stays in skill** | Free-text human input; determines which Mode (A–G) runs. |
| Mode A: Section-Level Edit (spawn section-writer per section) | `:117-123` | **Moves to script** | Same shape as write Step 6 — parallel section-writer spawns with no interaction mid-loop. |
| Mode B: Citation Fix ("Apply fixes, then re-audit" `:131`) | `:125-131` | **Moves to script** | Mechanical spawn-and-loop; **flagged finding**: this loop today has **no named cap** (see §4). |
| Mode C: Tone/Style Adjustment (incl. citation hard gate) | `:133-143` | **Moves to script** | Deterministic per-paragraph scoring + rewrite + mandatory auditor re-gate (`:141`), no human step inside the loop. |
| Mode D: Restructure | `:145-155` | **Split**: step 1 (show current structure) and step 2 (let researcher reorder/split/merge/add/remove) **stay in skill**; steps 3–5 (spawn section-writer for new sections, combine+synthesize merged sections, spawn synthesizer for transitions) **move to script** | `:147-152` is a human decision point (the researcher literally reorders sections); everything after the decision is generation. |
| Mode E: Strengthen Argument | `:157-168` | **Moves to script** | Research subagent spawn + evidence integration + citation audit re-run, no interactive step. |
| Mode F: Cut/Expand (incl. citation hard gate) | `:170-174` | **Moves to script** | Same shape as Mode C; Cut's mandatory auditor gate (`:172`) belongs inside the script's per-paragraph loop. |
| Mode G: Full Review | `:176-187` | **Split**: synthesizer spawn (`:178-185`) **moves to script**; "Present revision notes to the researcher for approval before applying" (`:187`) **stays in skill** | Explicit human approval step before changes are applied — a textbook SPC-03 gate. |
| Output (diff summary, export prompt, DOCX) | `:191-217` | **Stays in skill** | `:201-206` asks the researcher three follow-up questions; DOCX export reuses write's Step 9 (already staying in the skill). |

### 1.3 `edit-section` (`src/skills/edit-section/SKILL.md`)

| Stage | Lines | Moves to script? | Rationale |
|---|---|---|---|
| Voice profile load, Gemini routing | `:16-45` | **Stays in skill** | Same precondition class as above. |
| Identify the Section, Load Source Registry | `:57-83` | **Stays in skill** | `:59-60` and `:88-89` are direct researcher questions; `:79-82` is a conditional interactive prompt for stale `sources.json`, same shape as `edit/SKILL.md:94-97`. |
| Understand the Edit | `:86-99` | **Stays in skill** | Free-text human input selecting edit type. |
| Rewrites / expansions / new paragraphs (section-writer spawn, optional research subagents) | `:102-114` | **Moves to script** | Same shape as `edit` Mode A/E — mechanical spawn-and-loop, no interaction mid-flight. |
| Citation fixes ("Apply fixes, re-audit until all pass" `:120`) | `:116-120` | **Moves to script** | Same class as `edit` Mode B; **same uncapped-loop finding applies here independently** (see §4) — `edit-section/SKILL.md:120` never routes through section-writer, so it does not inherit `rewriteCycles.max` either. |
| Cuts | `:122-128` | **Split**: steps 1–2 (identify what to remove, check no argument step is lost) arguably need human confirmation on a destructive edit per `edit/SKILL.md:213`'s "Critical Rules" analog, but `edit-section/SKILL.md` has no equivalent explicit rule — **this spec recommends adding an interactive confirm step here during migration**, not silently moving all five steps to the script; steps 3–5 (style compliance re-run, show cut to researcher) **stay in skill**, step 5 ("Show the researcher what was cut before finalizing", `:128`) already is an explicit gate | Flag: `edit-section/SKILL.md` is currently the only one of the three skills with **no** explicit "never apply a destructive edit without showing the researcher first" rule at the top level (contrast `edit/SKILL.md:217`, "Show changes before applying destructive edits"). This is a pre-existing gap independent of the migration, worth carrying into the migration so it isn't silently baked into a script's non-interactive loop. |
| Style adjustments | `:130-136` | **Moves to script**, with `:136` ("Show before/after for the researcher") **staying in skill** as the final display step | Scoring + rewriting is mechanical; the display-and-confirm step needs the skill's interactive surface. |
| Output | `:140-161` | **Stays in skill** | `:159` asks the researcher whether to export — an explicit human gate. |

---

## 2. Args object each script would receive

Following the plan's own shape for `write-sections.js` (lines 356–358), and extending the same
pattern to `edit`/`edit-section` scripts (no equivalent args object exists in the plan text for
`edit`/`edit-section` — the object below is this spec's proposal, not a plan quote, and is marked
as such).

### 2.1 `write-sections.js` (plan lines 356–358, quoted)

```
args = {
  outline.units, thesis, sources, evidenceOwnership, styleFingerprint, authorVoice,
  citationStyle, targetLanguage, geminiApproved,
  thresholds: { rewriteCycles.max, antiAi, writerUnit }
}
```

Cross-checked against what `section-writer.md`'s current `## Input` section (`:76-95`) actually
requires per spawn: `unit`, `parentSection`, `siblingUnitsSummary`, `sectionIndex`, `unitIndex`/
`unitId`, `totalUnitsInSection`, `totalSections`, `thesis`, `articleStructure`, `targetLanguage`,
`tools`, `priorSectionTexts`, `outlineOverview`, `geminiFallback`. The plan's `args` shape does
not list `articleStructure`, `tools`, `outlineOverview`, or per-unit `parentSection`/
`siblingUnitsSummary` explicitly — these are currently derived by the skill from the outline
object and profile before each spawn (`write/SKILL.md:349-355` — "read it before constructing the
spawn prompts", referring to `references/section-writer-dispatch.md`). **Finding, not a
correction**: the script's `args.outline.units` must already carry (or the script must
reconstruct) `parentSection` and `siblingUnitsSummary` per unit, and `args` needs `articleStructure`
and `tools` added explicitly, or every per-unit spawn prompt the script builds will be missing
fields `section-writer.md` documents as required input. This is a gap in the plan's args shape,
not in this spec's reading of it — file it as an open item for whoever writes
`write-sections.js`.

### 2.2 Proposed `edit-sections.js` args (this spec's proposal — no plan precedent)

```
args = {
  mode: 'A'|'B'|'C'|'D'|'E'|'F'|'G',
  sections: [{ sectionIndex, title, currentText, editInstructions }],
  thesis, sources, evidenceOwnership, styleFingerprint, authorVoice, citationStyle,
  targetLanguage, geminiApproved, sourcesRegistry, priorSectionTexts,
  thresholds: { rewriteCycles: { max, editModeB, editModeE }, antiAi, writerUnit }
}
```

`mode` selects which of the Mode A/B/C/E/F/G stage-blocks in §1.2 the script runs; `edit-sections.js`
would return `{ sections: [...revised], auditOutcomes: [...], gates: [...] }` (mirroring the
`write-sections.js` return shape's `{sections, scorecard, needsReview[]}`, minus the article-level
scorecard, which does not exist in `edit`).

### 2.3 Proposed `edit-section-single.js` args

```
args = {
  editType: 'rewrite'|'expand'|'cut'|'citation'|'style',
  section: { title, currentText, editInstructions, suggestedSources },
  sectionIndex, thesis, styleFingerprint, authorVoice, citationStyle, targetLanguage,
  geminiApproved, sourcesRegistry, priorSectionTexts,
  thresholds: { rewriteCycles: { max, editSection } }
}
```

Note that `edit-section` operates on exactly one section, so there is no fan-out/barrier shape —
the script's `pipeline()` call in the write-sections sense degenerates to a single spawn-and-loop.

---

## 3. Where caps come from in `thresholds.json`

| Cap | Current location | Used by (today) | Migration status |
|---|---|---|---|
| `rewriteCycles.max` = 3 | `src/thresholds.json:16-19` | `section-writer.md:282`, `:438` (paragraph rewrite loop, both Gemini and fallback path) | Already centralized; `write-sections.js` reads it via `args.thresholds.rewriteCycles.max` per the plan (line 358). |
| `antiAi.passThreshold` = 35, `maxScore` = 50 | `src/thresholds.json:4-9` | `section-writer.md:264`, `:430` (anti-AI gate) | Already centralized; passed via `args.thresholds.antiAi`. |
| `writerUnit.targetWords`/`minWords`/`maxWords` = 500/300/800 | `src/thresholds.json:25-30` | `section-writer.md:81` (unit sizing, indirectly via the architect's outline) | Already centralized; passed via `args.thresholds.writerUnit`. |
| `selfReview.passThreshold` = 40/60 | `src/thresholds.json:10-15` | `write/SKILL.md:426-427` (Step 8.7 scorecard gate) | Stays with the skill's post-script branch (§1.1) since the `AskUserQuestion` on failure must stay interactive — but the numeric comparison can be pre-computed in the script's return value if the script is handed this threshold too. **Not currently in the plan's `write-sections.js` args list (line 358)** — this spec flags that `thresholds.selfReview` must be added to the args object if the scorecard comparison is to move into the script at all; otherwise the whole of Step 8.7 stays in the skill, unchanged from today. |
| `styleFingerprint.passThreshold` = 7/10 | `src/thresholds.json:31-35` | Referenced by `write/references/style-fingerprint-rubric.md` (loaded by `section-writer.md:377`) | Already centralized, flows through the same style-compliance skill inside the section-writer, unaffected by the script/skill boundary. |
| Anti-AI regeneration cap = **1** attempt | `section-writer.md:54`, `:267` ("After one regeneration attempt, proceed to the auditor regardless") | Hardcoded in the agent prompt | **Finding**: this cap is NOT read from `thresholds.json` today, unlike every other cap in this table. It is a WRK-14 violation as it stands ("Put caps, gates, and model routing in the **orchestrator script**, not in agent prompts" — CandleKeep Ch. 7, quoted verbatim). Migration should add a `thresholds.antiAi.regenerationAttempts` key (default `1`, matching current behavior) and read it from `args.thresholds` in the script rather than leaving it a bare hardcoded "once" inside the agent's own prompt text. |
| `edit` Mode B "apply fixes, then re-audit" loop | `edit/SKILL.md:131` | No cap exists — the loop is described only as "Apply fixes, then re-audit" | **Finding (WRK-13 gap)**: this loop has no named termination and no cap today. It does not route through `section-writer`, so it does not inherit `rewriteCycles.max`. Migration must add an explicit cap — this spec proposes `thresholds.rewriteCycles.editModeB` (new key, no plan precedent), defaulting to the same `3` as `rewriteCycles.max` unless the user changes it, with named exits `converged` (auditor PASS) / `cap-reached`. |
| `edit-section` citation-fix loop | `edit-section/SKILL.md:120` | Same as above — "Apply fixes, re-audit until all pass," no cap | **Finding (WRK-13 gap), independent instance** — same defect, different file. Proposed key: `thresholds.rewriteCycles.editSection`. |
| Proofread pipeline block (`chunkWords`, `maxPasses`, `dryRounds`, `concurrencyCap`, `refuteVotes`, `refuteMajority`) | `src/thresholds.json:48-55` | `src/workflows/proofread.js` (Phase 1, **does not exist yet** per §0) | Not relevant to write/edit/edit-section migration directly, but is the only precedent in the repo for a `"proofread"` thresholds block wired to `args.thresholds` — the pattern this spec's proposed `rewriteCycles.editModeB`/`editSection` keys should follow once Phase 1 actually ships that wiring. |

**No `edit` or `editSection` top-level block currently exists in `thresholds.json`.** Per this
project's CLAUDE.md ("Don't inline thresholds — read `thresholds.json`"), the migration must add
these new keys to `src/thresholds.json` rather than hardcoding the new caps inside
`edit-sections.js` / `edit-section-single.js`.

---

## 4. Named termination conditions for every loop

Per WRK-13 ("Every automated loop terminates in a **named outcome** under a cap the orchestrator
enforces... There is no 'it got stuck and the human fixes it manually' path" — CandleKeep Ch. 7,
quoted verbatim):

| Loop | Skill/agent | Cap source | Named exits (proposed where none exist today) |
|---|---|---|---|
| Per-paragraph rewrite (auditor VERDICT: FAIL/PARTIAL → rewrite → re-audit) | `section-writer.md:269-283`, `:438` | `thresholds.json > rewriteCycles.max` (`:16-19`) | Today: implicit — "If still failing after the max, include the paragraph with a `[NEEDS REVIEW]` marker" (`:282`). Named exits for the script: `PASS` (auditor approves within cap) / `NEEDS_REVIEW` (cap reached) — matches plan line 361's `PASS \| NEEDS_REVIEW` outcome vocabulary exactly. |
| Anti-AI regeneration | `section-writer.md:264-267`, `:430` | Currently hardcoded "once", not in `thresholds.json` (see §3 finding) | Today: unnamed — "proceed to the auditor regardless" after one attempt. Proposed named exits: `regenerated` (score met after 1 attempt) / `proceeded-below-threshold` (still below threshold, auditor runs anyway as the binding gate). |
| Step 5.5 argument-graph validation → architect repair loop | `write/SKILL.md:298-313` | No numeric cap — human-terminated | **Stays interactive (§1.1)**; not a script loop. Named exits: all four checks pass (proceed to Step 6) / researcher is shown failing node IDs and decides whether to loop back to the architect or intervene manually — this is intentionally open-ended because it is a human-in-the-loop repair conversation, not an automated retry. |
| `write` Step 8.7 self-review scorecard gate | `write/SKILL.md:412-429` | `thresholds.json > selfReview.passThreshold` (`:10-15`) | Named exits: `score >= threshold` → continue to DOCX / `score < threshold` → `AskUserQuestion` ("proceed or address issues first") — the human's answer is the actual terminating event, not a cap the script can enforce past the first ask. |
| `edit` Mode B citation-fix loop | `edit/SKILL.md:125-131` | **None today** — proposed `thresholds.rewriteCycles.editModeB` (§3) | Proposed named exits: `converged` (auditor PASS on all sections) / `cap-reached` (proposed cap hit, remaining sections marked `[NEEDS REVIEW]`, mirroring `section-writer.md:282`'s existing convention). |
| `edit-section` citation-fix loop | `edit-section/SKILL.md:116-120` | **None today** — proposed `thresholds.rewriteCycles.editSection` (§3) | Same proposed exits as above, scoped to the single section. |
| Mode C / Mode F citation hard gate ("gate on `VERDICT: PASS`... If the auditor rejects, fix the citation and re-audit before finalizing") | `edit/SKILL.md:141`, `:172` | Inherits `rewriteCycles.max` only if routed through a fresh `section-writer`-style loop; as written it is prose without an explicit numeric cap reference | **Finding**: same class of gap as Mode B — the text says "before finalizing" with no stated retry ceiling. Migration should route this through the same `thresholds.rewriteCycles.editModeB`/`editSection` cap rather than leaving it open-ended in the script. |

---

## 5. Fallback path when the Workflow tool is unavailable

The plan's own template for `proofread` (lines 227–228) is the pattern to replicate for all three
skills: **"The skill runs the same stages sequentially with the same agents and scripts (control
flow only is duplicated)."**

Applied per skill:

- **`write`**: if the Workflow tool errors or is unavailable when the skill reaches Step 6, the
  skill falls back to spawning `section-writer` subagents directly via the `Agent` tool — exactly
  today's behavior (`write/SKILL.md:345`, "Call the Agent tool multiple times in a single
  response"). The invariant this spec states explicitly (not stated in the plan text): **the
  fallback path must produce the same per-paragraph gate outcomes as the script path** — i.e. the
  fallback cannot silently skip the auditor hard gate or the rewrite-cycle cap just because it is
  running without the Workflow tool's structure. Concretely, `section-writer.md` gains an
  `AUDIT_MODE: external` input (plan line 366) for the script-driven path; when the Workflow tool
  is unavailable, the skill spawns section-writer **without** `AUDIT_MODE: external`, so the
  agent's existing in-agent audit path (`section-writer.md:269-283`, `:436-438`) runs unchanged —
  this is the actual fallback mechanism, not a separate code path the skill must maintain.
- **`edit`**: same shape — on Workflow-tool failure, the skill runs Modes A–G's script-bound
  stages (§1.2) as direct `Agent`-tool spawns in the same sequence the script would have run them,
  reusing the skill's pre-migration prose (`edit/SKILL.md:117-187`) as the literal fallback
  implementation, since that prose is exactly "today's behavior" the script is meant to replace.
- **`edit-section`**: same shape, using `edit-section/SKILL.md:102-137` as the fallback
  implementation.

**Per SPC-14** ("State which gates are **automatic**, out loud, as a policy... every gate you drop
after the pre-generation gate is a decision that has to be written down" — CandleKeep Ch. 11,
quoted verbatim): whichever report/summary each migrated skill produces at the end of a run must
state explicitly whether the run used the Workflow-tool path or the fallback path, and confirm
that the same named gates (auditor VERDICT, anti-AI threshold, rewrite-cycle cap) ran either way —
this is the write/edit/edit-section analog of the proofread pipeline's planned "Gates table: every
stage ran/skipped/why" (plan line 64, VER-10/SPC-14 row).

---

## 6. The `AUDIT_MODE: external` contract (write only — the one Phase 2 names explicitly)

Plan lines 366–367 (quoted): "`section-writer.md` gets an `AUDIT_MODE: external` input so it does
not spawn the auditor when the script owns the gate; the in-agent path remains for the fallback."

Precisely, against the current agent text:

- With `AUDIT_MODE: external` set, `section-writer.md` **skips** Step D (`:269-283`, the
  `Agent`-tool spawn of the `auditor` subagent) and Step E (`:284-310`, the claims-registry
  append, which today only fires "Once the auditor returns `VERDICT: PASS`" — with no in-agent
  audit, there is no in-agent PASS event to trigger it). The section-writer instead returns its
  drafted, unaudited paragraphs directly to the script.
- The script then owns: spawning the `auditor` subagent itself (via `agentType:
  'academic-writer:auditor'`, per plan line 359), and **re-implementing the post-fence VERDICT
  parsing rule** currently described at `section-writer.md:56` and `auditor.md:243-257` — "Read
  the VERDICT line that appears **after** the auditor's fenced paragraph block... do NOT match a
  `VERDICT:` line that falls inside the fenced paragraph text." This is a correctness contract,
  not incidental plumbing: a paragraph whose own text happens to end in the literal string
  `VERDICT: PASS` must not be mistaken for the gate's actual verdict. Any reimplementation of this
  parse inside `write-sections.js` needs a dedicated test fixture (a paragraph body ending in
  `VERDICT: PASS` with the real verdict, `VERDICT: FAIL`, appearing after the fence) asserting the
  script reads the post-fence line, not the last line of the combined text.
- The claims-registry append (Step E, `:284-310`) — which uses `fcntl.flock` to serialize
  concurrent writes from parallel section-writers (`:294-306`, "so that parallel section-writers
  cannot clobber each other") — must move to the script or to a location the script calls after
  each PASS, since it currently only fires from inside the agent's own audited-PASS branch, which
  no longer runs under `AUDIT_MODE: external`.
- `subagent-start.ts` (`src/hooks/src/lifecycle/subagent-start.ts:23-27`) already matches
  `subagentType !== 'auditor' && subagentType !== 'academic-writer:auditor'` and injects the
  auditor's threshold context regardless of caller — this hook requires **no change** for the
  script-spawned auditor path, since it keys off `subagent_type`/`subagentType`, not off which
  caller (skill, agent, or script) issued the spawn. This is confirmed by reading the hook source
  directly (`subagent-start.ts:6-27`), not assumed from the plan text.

`edit`/`edit-section` have **no equivalent `AUDIT_MODE` contract in the plan** — their auditor
spawns (`edit/SKILL.md:127`, `:141`, `:172`; `edit-section/SKILL.md:118`) are already direct
skill-level `Agent`-tool spawns, not routed through `section-writer`'s internal gate, so there is
no in-agent audit path to bypass. The script versions of Modes A/B/C/E/F/G simply take over the
existing spawn-and-gate prose as-is; no analogous "external" flag is needed on the auditor itself.

---

## 7. Risks measured this session (first-class, not appendix material)

### 7.1 Write-capability must be classified from the item, not its topic

Per WRK-24 (CandleKeep Ch. 7, quoted verbatim): "Classify a work item onto the WRITE CAPABILITY it
needs, never onto its topic — and phrase every item that must land on disk with its acceptance
command, not with a verb like revise/review/investigate... 'Revise the existing prompt file
`src/agents/proofreader.md` in place' was classified `debug` by the haiku classifier and routed to
`orchestration:debug-investigator`, whose tool grant has no Write/Edit — it correctly reported it
could not comply and wrote nothing... Relaunching identical work as 'Write the new full text ...
then run the test suite and make it pass' routed it to a write-capable specialist."

Applied to this work item specifically: this item was phrased "Write a migration spec to
`docs/audits/...`" — an explicit write verb naming a concrete deliverable path — which is exactly
the phrasing WRK-24 recommends. It was not phrased as "scope" or "review" alone, which is the
class of phrasing the rule flags as at risk of read-only misrouting. **This spec itself is the
positive control**: it landed on disk because it was phrased as a write with a named target, not
because the topic ("scoping a migration") implies write access.

### 7.2 An adversarial verifier shown only output + source-of-truth confirmed a blocked report as accurate

Per REV-06 (CandleKeep Ch. 5, quoted verbatim): "An adversarial verifier shown only the worker's
output and its source of truth verifies whether the CLAIM is accurate, not whether the DELIVERABLE
exists — give it the acceptance command, or check the tree yourself before believing a
confirmation... a work item that wrote zero files and honestly reported itself blocked was
CONFIRMED by 2 of 3 lenses (the correctness lens verified the blocked-report was truthful), and
the run returned `itemsConfirmed: 2`, `deviations: 'none'` while `git status` showed the target
file unmodified. Only the separate acceptance-criteria verdict caught it (`met: false`)."

**Consequence for this migration's per-stage acceptance, stated as policy**: every stage of the
Phase 2 (and edit/edit-section) migration must have **a command whose exit code is checked**, not
a claim a reviewer reads about whether the stage "looks done." Concretely, for the stages this
spec scopes:

| Stage | Acceptance command (exit code checked, not narrated) |
|---|---|
| `write-sections.js` exists and is syntactically valid | `node --check src/workflows/write-sections.js` |
| `meta.phases` literal matches the script's actual `phase()` calls | grep-based structural test, e.g. `python3 -m pytest tests/test_write_workflow_meta.py -q` (new test, mirrors the plan's proofread equivalent at line 314) |
| `section-writer.md` documents the `AUDIT_MODE: external` contract | `grep -q "AUDIT_MODE" src/agents/section-writer.md` |
| `subagent-start.ts` still injects auditor rules for the script-spawned path | `python3 -m pytest tests/test_plugin_structure.py -q` (existing agent-whitelist coverage; the plan notes at line 369 this already covers `academic-writer:auditor` at `subagent-start.ts:23-27`) |
| New `thresholds.json` keys (`rewriteCycles.editModeB`, `.editSection`, `antiAi.regenerationAttempts`) are present and read, not inlined | A dedicated pytest asserting the keys exist in `src/thresholds.json` and are not hardcoded elsewhere via `grep -rn` for the literal cap values in the migrated scripts |
| Full suite green on the migration branch | `python3 -m pytest tests/ -q` and `npm run typecheck` |

This table is this spec's answer to REV-06 for the migration it scopes — it does not certify that
any of these commands currently pass (Phase 1 has not shipped, so none of these files exist yet;
see §0). It states what "done" must be checked against once the migration is implemented.

### 7.3 Full article exceeds the 15-agent "medium" workflow-size guideline

Plan lines 371–372 (quoted): "Note for the user (cannot be set by the plugin): a full article
exceeds the 15-agent 'medium' workflow guideline; raise 'Dynamic workflow size' in `/config`
before the first run."

Grounded in the actual numbers rather than restated as a vibe: `thresholds.json > writerUnit`
(`:25-30`) targets 500 words per writer unit (min 300, max 800). A `targetWordCount` of, say,
6,000–8,000 words (a typical full academic article, consistent with the hebrew-recall article's
"7,000-word article" scale cited in the plan's Context section, line 20) divided by a 500-word
target unit yields **12–16 writer units** — each writer unit spawns one `section-writer` subagent,
which in turn spawns at least one `auditor` subagent per paragraph (multiple paragraphs per unit,
since `writerUnit.maxWords` = 800 at, say, ~150–220 words/paragraph implies roughly 4–5 paragraphs
per unit). That already puts total agent-spawn count for a single full-article run into the
**several-dozen range** even before counting the `deep-reader`, `architect` (invoked at least
twice per plan `write/SKILL.md:242`, `:277`), and `synthesizer` spawns. This is well past a 15-agent
"medium" ceiling on arithmetic grounds, not just the plan's assertion — and **the plugin cannot
raise this ceiling itself**; only the user can do so via `/config`. This spec states the same
constraint the plan states, but ties it to the concrete `writerUnit` numbers already in
`thresholds.json` so a future implementer does not have to re-derive it.

`edit`/`edit-section` are lower-risk on this axis: `edit` fans out per **section actually being
revised** (typically far fewer than the full article's total writer-unit count), and
`edit-section` is single-section by design — this spec does not extend the 15-agent warning to
those two skills as a blanket rule, but recommends the same `/config` guidance apply
**conditionally**, only when an `edit` Mode A/D/E spawn count (computed the same way, from the
number of sections actually being touched) would itself exceed 15.

---

## 8. CandleKeep rule citations used in this spec — provenance note

Per this task's instruction to read the actual CandleKeep rule text rather than work from IDs
alone: the following rules were fetched and quoted verbatim in this spec via
`ck items get cmtifqy5a2cpun00jzpuztuca --page N` this session: **SPC-03** and **SPC-14** (page
11), **WRK-13**, **WRK-14**, and **WRK-24** (page 7), **REV-06** (page 5), **VER-08**, **VER-09**,
**VER-10** (page 12). All quotations above are copied from the actual retrieved page text, not
reconstructed from the plan's own summary table (plan lines 56–68), which cites these same rule
IDs but was not treated as the source of truth here.

---

## 9. Non-goals of this spec (explicit)

- No workflow script was written. `src/workflows/` does not exist after this item; this spec does
  not create it.
- No skill or agent file (`write/SKILL.md`, `edit/SKILL.md`, `edit-section/SKILL.md`,
  `section-writer.md`, `auditor.md`, `synthesizer.md`) was modified by this item.
- This spec does not re-scope Phase 1 (`proofread`) beyond the precondition check in §0, which is
  in scope only because Phase 2's precondition depends on it.
- This spec does not resolve the `write-sections.js` args-shape gap noted in §2.1 (missing
  `articleStructure`, `tools`, `outlineOverview`, per-unit `parentSection`/`siblingUnitsSummary`)
  — it is flagged as an open item for whoever implements Phase 2, not resolved here.

---

## 10. Sources consulted

- `the 0.7.0 plan of record (local, not committed to this repo)` (full read; Phase 1.2, Phase 2 lines
  349–373, Research digest lines 107–202, Follow-up section lines 394–409)
- `src/skills/write/SKILL.md` (full read, 489 lines)
- `src/skills/edit/SKILL.md` (full read, 217 lines)
- `src/skills/edit-section/SKILL.md` (full read, 162 lines)
- `src/agents/section-writer.md` (full read, 491 lines)
- `src/agents/auditor.md` (full read, 257 lines)
- `src/agents/synthesizer.md` (full read, 215 lines)
- `src/thresholds.json` (full read, 65 lines)
- `src/hooks/src/lifecycle/subagent-start.ts` (read for the `agentType` match confirmation in §6)
- Live repo state: `git branch -a`, `git log --oneline -6`, `git status`, `find src/workflows
  src/scripts -maxdepth 1`, `grep -rn "Workflow(" src/`, `ls src/agents | grep -E
  "editor|copyeditor"` (all run 2026-09-02 against `feat/proofread-pipeline-0.7.0` @ `98f5bf7`)
- CandleKeep "Personal · Agent Best Practices" (`cmtifqy5a2cpun00jzpuztuca`), pages 5, 7, 11, 12 —
  fetched live this session via `ck items get`, not read from the plan's summary table
