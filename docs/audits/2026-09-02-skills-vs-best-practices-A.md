# Skills audit A — 9 skills vs. Agent Best Practices

Repo: Academic Helper, branch `feat/proofread-pipeline-0.7.0`. Scope: `src/skills/{write,edit,edit-section,proofread,review,research,ideate,voice,init}/SKILL.md`.
Sources of truth: CandleKeep `cmtifqy5a2cpun00jzpuztuca` pages 5/7/10/11/12 (REV/WRK/TST/SPC/VER), wiki register `~/dev/claude-obsidian/wiki/projects/ai-agent-best-practices.md`, `src/thresholds.json`, `docs/proofread-feature.md` + plan `~/.claude/plans/the-plugin-did-terrable-swift-lantern.md` (Phase 1.1 table), `CLAUDE.md`. Read-and-report only; no code changed.

Commit audited: `78d48c4` (HEAD of `feat/proofread-pipeline-0.7.0` at audit time — VER-09). This is a **static read of skill markdown**; no skill was executed (VER-10, applied to this report itself). `python3 -m pytest tests/ -q` still green (see tail below) since nothing was touched.

## Findings table (most severe first)

| # | Severity | Skill:line | Rule | Verdict | Evidence |
|---|---|---|---|---|---|
| 1 | MEDIUM (in-progress branch, not a shipped regression) | `src/skills/proofread/SKILL.md` (whole file, esp. Step 3–6) | Plan Phase 1.1 stage sequence + TST-02 | **FAIL** | Plan (`~/.claude/plans/the-plugin-did-terrable-swift-lantern.md:215-227`) specifies a unified 3-stage skill: 1 Editorial (`editor.md`, opus) → 2 Language (`copyeditor.md`, opus) → 3 Mechanical (`proofreader.md`, sonnet), driven by `src/workflows/proofread.js` with `args.thresholds`. Commit `82594aa` (`feat(proofread): shared changes contract, three-stage agents...`, per `docs/proofread-feature.md:84` still "v2 (0.7.0, **in progress**)") built the three agents (`src/agents/editor.md`, `src/agents/copyeditor.md`, revised `src/agents/proofreader.md`) and two deterministic scripts — `src/scripts/citation-guard.py` (confirmed present; its own docstring names `src/skills/proofread/SKILL.md:73-78` and `src/skills/proofread/references/changes-schema.json` as what it replaces) and `src/scripts/write-proof-report.py` — but `src/skills/proofread/SKILL.md` was **not modified in this branch** (`git log --oneline main..HEAD -- src/skills/` shows only `write/SKILL.md` changed). One root cause, two visible symptoms: (a) the live skill still spawns only `proofreader` (Step 3, line 53) — no editorial/language stages, no `--venue`/`--only` flags, no reference to `src/workflows/proofread.js`; (b) Step 4's citation-integrity guard is still described as reasoning the orchestrator performs itself each run ("does its `before` snippet... overlap... one of these tokens?"), rather than invoking `citation-guard.py` — though note `citation-guard.py` takes a `changes-schema.json` payload the v1 skill never produces, so it genuinely is not callable from the current skill without the rest of the Phase-1 wiring; this is unshipped work, not a script sitting unused for no reason. `edit` and `edit-section` are a different pipeline (interactive Modes A–G) and are **N/A** against this specific Phase 1.1 sequence — they never claimed to implement it. |
| 2 | HIGH | `src/skills/write/SKILL.md:298-313` (Step 5.5, argument graph validation) | TST-02 | **FAIL** | "reason through it as a topological sort / DFS with a visited/in-progress marker over node `id`s" — cycle detection and topological ordering are textbook deterministic algorithms, explicitly assigned to the LLM ("This is not a subagent call; it is reasoning directly over the outline JSON") rather than a script. Confirmed by listing `src/scripts/` in full (`apply-changes.py`, `check-voice-populated.py`, `citation-guard.py`, `detect-ai-typography.py`, `extract-style-metrics.py`, `generate-docx.py`, `validate-hebrew-punctuation.py`, `write-proof-report.py`) — no cycle-detection/topo-sort validator exists anywhere in the script directory. |
| 3 | HIGH | `src/skills/edit/SKILL.md:127-131` (Mode B); `src/skills/edit-section/SKILL.md:116-120` | WRK-13 / WRK-14 | **FAIL** | Mode B: "Apply fixes, then re-audit." edit-section: "Apply fixes, re-audit until all pass." Both are retry loops with **no cap and no named terminal outcome** — no "converged"/"cap-reached"/"give up and flag for human" state, unlike the new proofread pipeline's own `maxPasses`/`dryRounds` design (`thresholds.json > proofread`, cap-reached/converged named explicitly). An audit can read `thresholds.json` and see `proofread.maxPasses: 3`; nothing in `edit`/`edit-section` bounds "re-audit until all pass." |
| 4 | HIGH | `src/skills/edit/SKILL.md:141,172` (Mode C, Mode F citation hard gates) | WRK-13 | **FAIL** | "If the auditor rejects, fix the citation and re-audit before finalizing" (Mode C) and the identical pattern in Mode F — no stated retry cap, no named exit if the auditor keeps rejecting. Same uncapped-loop shape as #3. |
| 5 | MEDIUM | `src/skills/review/SKILL.md:111-115` | Repo rule (a): thresholds inline vs `thresholds.json` | **FAIL** | `thresholds.json > selfReview` only defines `minScore: 40`, `maxScore: 60`, `passThreshold: 40`. `review/SKILL.md`'s "Grade thresholds" table (50–60 Excellent / 40–49 Good / 30–39 Needs Work / <30 Poor) hardcodes three additional band boundaries (50, 30) nowhere in `thresholds.json`. Lines 131 and 146 also hardcode the `40` pass/fail split inline a second time instead of reading `scoring.passThreshold` from `references/scorecard.json` (which the skill itself names as "the single source of truth" at line 53) or `thresholds.json`. |
| 6 | MEDIUM | `src/skills/research/SKILL.md:75` | Repo rule (a) | **FAIL** | `` `top_k: 30`, `rerank_top_k: 10` `` hardcoded RAG parameters in prose; not present anywhere in `thresholds.json`. |
| 7 | MEDIUM | `src/skills/voice/SKILL.md:51,104,131,172` | Repo rule (a) | **FAIL (partial)** | "caps at 8 questions per session" (×2, lines 51 & 172) and "soft floor 12, hard cap 18" (line 104) are hardcoded in prose and appear nowhere in `thresholds.json > voice` (which only has `ruleCoverage` and `corpus` keys) — no script or config backs them, so this part is a genuine repo-rule (a) violation. The "20-word floor" mentioned at line 111 is **not** a violation on closer check: `src/scripts/check-voice-populated.py:53` defines `DEFAULT_MIN_WORDS = 20` as the actual enforcement point (TST-02-compliant, a real script owns the number); the skill/reference-doc mention is a documentation echo of that script constant, not a second hardcoded gate. |
| 8 | MEDIUM | `src/skills/proofread/SKILL.md:56` | Repo rule (a) | **FAIL (soft)** | "concurrency cap 6" is hardcoded in prose. It happens to equal `thresholds.json > proofread.concurrencyCap: 6` today, so there is no live drift, but the skill does not read the file — it repeats the number. A future edit to `thresholds.json` would silently desync from this skill's prose. |
| 9 | LOW | `src/skills/edit-section/SKILL.md:134` | Repo rule (a) | **FAIL (soft)** | "Fix any dimension scoring ≤3" — a distinct fingerprint-quality gate from `thresholds.json > styleFingerprint.passThreshold: 7`; the `≤3` cutoff appears nowhere in `thresholds.json`. |
| 10 | LOW | `src/skills/review/SKILL.md:3` (frontmatter description) | Repo rule (c) — "Use when…" trigger | **FAIL** | Description ends "Use after writing to score the article on quality dimensions before publication." No "when" clause anywhere in the description — CLAUDE.md names omitting the "Use when…" trigger phrase as the anti-pattern to avoid. |
| 11 | INFO | `src/skills/init/SKILL.md:3` | Repo rule (c) | **PASS (borderline)** | "Use on first install, when redoing onboarding from scratch, or when the user wants a quick onboarding (pass --quick)." Doesn't literally start "Use when," but does carry two explicit "when" trigger clauses — functionally compliant. |
| 12 | INFO | all 9 | REV-03 (parallel reviewers, different lenses) | **N/A** across all 9 | None of the 9 skills spawn two-or-more reviewers over the *same* artifact with different lenses in parallel. `research.md` spawns RAG/Candlekeep/NotebookLM in parallel, but those are data-source fan-out, not review lenses over one artifact — REV-03 doesn't apply to a retrieval fan-out. `write`'s `synthesizer` and `edit`'s `auditor` are single-lens gates, run once, not paired lenses. The forthcoming 3-stage proofread pipeline (editor/copyeditor/proofreader, plan Phase 1.1) is sequential-by-design (different *stages*, book-production order), not parallel lenses either — so REV-03 is inapplicable there too, by design, not a gap. |
| 13 | INFO | `src/skills/proofread/SKILL.md:89` (Step 5) | VER-08 (negative case verified) | **PASS** | "If there are zero applicable mechanical changes... do not write a `*.proofed.md`. Skip to Step 6 and report a clean pass." An explicit, tested "clean article" branch — the dog that doesn't bark is a named, distinct path, not a fallthrough. |
| 14 | INFO | `src/skills/research/SKILL.md:170` | VER-08 | **PASS** | "If a question can't be answered from available sources, say so clearly" — explicit no-hit branch. |
| 15 | INFO | `src/skills/write/SKILL.md:426`, `edit/SKILL.md:94-97`, `edit-section/SKILL.md:79-82`, `voice/SKILL.md:174` (`[quick]` marker), `init/SKILL.md` (Quick Mode table) | VER-10 (bypassed gate labelled) | **PASS across the board** | Every skill that can skip a gate labels it out loud to the user at the point of delivery: write's sub-40 self-review score triggers an explicit `AskUserQuestion` rather than silent pass-through; edit/edit-section explicitly warn "Check D will be skipped for any citation whose source isn't in the registry" when `sources.json` is stale/missing; `voice quick` stamps a `[quick]` marker in both `AUTHOR_VOICE.md` and `.voice/audit.md`; `init`'s Quick Mode table states exactly what is downgraded/skipped versus full mode. This is the strongest pattern in the audited set — no silent gate bypasses found. |
| 16 | INFO | `src/skills/write/SKILL.md:412-429`, `426` | SPC-14 (automatic gates stated) | **PASS** | The self-review gate states its own automatic behavior explicitly: "If score meets or exceeds the threshold... show the scorecard and continue to DOCX output" (automatic) vs. below-threshold requiring `AskUserQuestion` (human gate) — the split is written down, not left for the reader to infer. |
| 17 | INFO | `src/skills/edit/SKILL.md` frontmatter `agents:` list vs. Mode E research subagents; `research/SKILL.md` frontmatter `agents: [research-rag, research-candlekeep]` vs. the NotebookLM subagent instructed at line 88-97; `voice/SKILL.md` has no `agents:` field despite spawning `voice-interviewer`/`voice-distiller`/`voice-calibrator` | Frontmatter hygiene (not a CLAUDE.md-mandated field) | **N/A** | CLAUDE.md's required frontmatter fields for skills are `name`, `description`, `user-invocable`, `allowedTools` (+ `metadata: {author, version}`) — `agents:` is not in that mandatory list, so these mismatches are not a FAIL against CLAUDE.md, only a documentation-completeness nit worth fixing opportunistically. |

## Per-skill blocks

### write (v0.2.19)
- Frontmatter: name/description/user-invocable/allowedTools/metadata.author/metadata.version all present — **PASS**.
- Description trigger phrase: "Use when starting a new article from scratch…" — **PASS**.
- TST-02: FAIL, argument-graph DFS/topo-sort done by LLM reasoning (Step 5.5, finding #2).
- WRK-13/14: the Step 5.5 repair loop ("loop back to the architect... re-run this checklist") has no numeric cap either, though it is human-gated (researcher sees flagged nodes) so the risk is lower than edit's silent auto-retries — **FAIL (soft)**, no cap stated.
- VER-10/SPC-14: PASS (findings #15, #16).
- Repo rule (a): the 220-word ceiling and thresholds.json self-review default are correctly deferred to `thresholds.json` / the agent file, not hardcoded here — **PASS** for this skill's own numeric mentions.

### edit (v0.2.19)
- Frontmatter: **PASS**. Description trigger: "Use when revising an article…" — **PASS**.
- WRK-13: FAIL — Mode B "re-audit" loop and Mode C/F citation-gate retries, both uncapped (findings #3, #4).
- VER-10: PASS (sources.json staleness disclosed explicitly).
- Not a Phase-1.1 proofread-pipeline skill — **N/A** on finding #1's specific check.

### edit-section (v0.2.19)
- Frontmatter: **PASS**. Description trigger: "Use when changing one specific section only…" — **PASS**.
- WRK-13: FAIL — "Apply fixes, re-audit until all pass" (finding #3).
- Repo rule (a): FAIL (soft) — "scoring ≤3" hardcoded (finding #9).
- Not a Phase-1.1 proofread-pipeline skill — **N/A** on finding #1.

### proofread (v0.2.1)
- Frontmatter: **PASS**. Description trigger: "Use when an article is drafted…" — **PASS**.
- Finding #1 (HIGH, FAIL): stage sequence does not match plan Phase 1.1 — still single-stage mechanical-only; the 3-stage agents/scripts built in `82594aa` are unwired.
- Finding #2 (HIGH, FAIL): citation-integrity guard is LLM-reasoned, not calling the now-existing `citation-guard.py`.
- Finding #8 (soft FAIL): concurrency cap hardcoded rather than read from `thresholds.json`.
- VER-08: PASS (clean-pass branch, finding #13).
- VER-10: PASS (guard-downgrades and unlocalizable fixes recorded in Notes, not silently dropped).

### review (v0.2.24)
- Frontmatter: **PASS**.
- Description trigger: FAIL — no "when" clause (finding #10).
- Repo rule (a): FAIL — hardcoded grade bands and repeated inline `40` split (finding #6).
- SPC-14: PASS (finding #16).
- REV-03: N/A (single-pass self-scoring, no parallel lenses claimed).

### research (v0.2.23)
- Frontmatter: **PASS**. Description trigger: "Use when investigating a topic…" — **PASS**.
- Repo rule (a): FAIL — hardcoded `top_k`/`rerank_top_k` (finding #6).
- VER-08: PASS (finding #14).
- Frontmatter `agents:` list omits the NotebookLM subagent it instructs elsewhere — N/A per CLAUDE.md's mandatory-field list (finding #17), but worth a documentation fix.

### ideate (v0.2.23)
- Frontmatter: **PASS**. Description trigger: "Use when you have a vague topic…" — **PASS**.
- No numeric gates found inline (grep clean) — **PASS** on repo rule (a).
- WRK-13/REV-03/VER-08/VER-10/SPC-14: mostly **N/A** — this skill is a conversational brief-writer with no retry loops, no review lenses, no gate to bypass; it writes one file (`research-brief.md`) once, with no pass/fail gate at all.

### voice (v0.3.0)
- Frontmatter: **PASS**. Description trigger: "Use when the user wants to deepen their voice profile…" — **PASS**.
- Repo rule (a): FAIL — multiple hardcoded caps/floors not in `thresholds.json` (finding #7).
- `:voice audit` correctly reads `thresholds.json: voice.ruleCoverage.block` for its refusal gate (line 169) — **PASS** for that one specific gate, showing the pattern is known and applied elsewhere in the same file, which makes the other hardcodes look like an oversight rather than a design choice.
- VER-10: PASS (`[quick]` marker labelling, finding #15).
- WRK-13: the MVV/session loop has a named, bounded structure (7 sessions, explicit resume/complete states) — **PASS**, this is the one skill with clearly named termination states throughout its whole control flow.

### init (v0.3.0)
- Frontmatter: **PASS**. Description trigger: borderline **PASS** (finding #11).
- No numeric quality gates hardcoded inline (grep clean beyond step/phase counts, which are not quality gates) — **PASS** on repo rule (a).
- VER-10/SPC-14: PASS — the Quick Mode table states exactly what is skipped/downgraded per phase, up front, before the user picks it.
- Not a Phase-1.1 proofread-pipeline skill — **N/A** on finding #1.

## Test suite tail

```
$ python3 -m pytest tests/ -q
........................................................................ [ 52%]
................................................................ [100%]
136 passed in 1.53s
```
No code was modified by this audit; the suite was already green and stays green.
