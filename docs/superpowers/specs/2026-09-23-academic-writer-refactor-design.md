# academic-writer refactor (design, rev 3)

Date: 2026-09-23. Status: rev 3 (Pi harness + Jev everywhere), approved rev 2 + rev 3 deltas 2026-09-23. Run: `.ale/runs/aw-refactor-2026-09-23/`.

**Evidence** (local, gitignored, in the run dir):
- `evidence-cost.md`: measured.
- `evidence-architecture.md`: file:line.
- `evidence-ale-delegation.md`
- `evidence-best-practices.md`: CandleKeep review of the Claude Code docs.
- `~/dev/learn-research/learn-llm-author-voice-academic-writing/` and `learn-claude-code-plugin-best-practices/`: the two `/learn` runs.

## 1. Brief

**The author's goals:**
- Much cheaper /write and /proofread.
- Prose in the author's own voice that argues the author's thesis from the core text.
- An outline with real flow between sections.
- A proofread that never misses typos, style words or names/terms.
- A faster and better deep read.
- One voice shared across all projects.
- A supported loop for the docx comments and suggestions round-trip, which improves both the voice and the plugin.
- Best-practice Claude Code plugin construction.

**Decisions** (from `decisions.md`):
- Quality and cost are joint first priorities.
- /write is co-authored.
- Gemini is flash only, the latest model.
- Codex is being retired; non-Claude delegation goes to OpenRouter **through Pi as the harness** (rev 3).
- Jev is used at **every** plugin decision point, in a cascade (Jev → code → model), shadow-first for Hebrew (rev 3).
- The refactor is **built** with ALE (`/work`, `ale`). The plugin ships no ALE machinery.
- Design choices are challenged, not taken as given. §7 lists where this spec disagrees with a stated preference.

## 2. What is wrong, in one paragraph

**Cost.** Most cost is fixed context, not work [measured].
- One shmaria paper took 705M tokens across two /write runs; the second happened after the first invented a structure. One kabalah /proofread took 98M tokens and never finished.
- The drivers are about 58k-token agents spawned in the hundreds, 210 Opus yes/no voters, and an Opus main session re-reading 264–485k tokens per turn.
- Dynamic workflows make this worse by construction: `agent()` cannot call MCP tools or the network, so every model call is a full Claude agent.

**Quality.** The author's thesis and core text never enter the pipeline as data.
- The deep read is discarded down to 400 words.
- Units are drafted in parallel, blind to their neighbours.
- The drafter sees rules instead of the author's prose.
- The proofread funnel silently drops true fixes at five points.

**Construction.** Several of the plugin's settings do nothing [docs-verified].
- Every skill uses `allowedTools`; the key is `allowed-tools`.
- `disallowed_tools` should be `disallowedTools`; the `agents:` key and the plugin `settings.json` permissions are ignored.
- 5 phantom agents come from `agents/memory/*`.
- `write/SKILL.md` is over the 500-line limit.
- The MCP server has no timeout or abort.
- There are 10 installs at 4 versions, so fixes never reach use: 847c831 never ran.

## 3. Architecture

```
main session  ── co-author dialogue only; never holds article text; skills pass paths
   │ Bash (≤10 min, backgroundable)                 │ Agent (only where tools+multi-turn are needed)
   ▼                                                ▼
aw CLI  (plugin bin/, TypeScript bundle)            Claude subagents: auditor (hard gate), architect dialogue
  ├─ code steps: fetch, chunk, must-catch, hspell, gates, line anchoring, docx in/out, assembly
  ├─ gemini   : flash latest, HTTP, responseSchema, finishReason check, context cache per run
  ├─ pi harness (optional): `pi -p --mode json --no-session --no-tools --no-extensions --no-skills
  │             --no-context-files --no-prompt-templates --provider openrouter --model <m>
  │             --system-prompt <file> --skill ${CLAUDE_PLUGIN_ROOT}/pi-skills/aw-judge`;
  │             cross-family judge; JSON validated in aw, one retry; usage from json events;
  │             pi or its openrouter auth absent → gemini judge, row marked same_family
  ├─ jev      : typed judgments (yes/no, one-of-N, 0-3) at every decision point; cascade
  │             Jev → code → model; per-point mode off|shadow|cascade in thresholds.json
  └─ ledger   : .academic-helper/runs/<id>/usage.jsonl + events.jsonl (every call, every stage)
```

- **A CLI, not an MCP server.** Claude Code's MCP client has a hard ~60 s timeout (issues #52137 and #47076) and caps output at 25k tokens, while a long Gemini draft or synthesis can exceed both. Bash calls allow 10 minutes, can run in the background, and write their outputs to disk. MCP tool schemas also cost context in every session.
  - The Gemini MCP server is retired. Its client code moves into the CLI, and the OCR tool becomes `aw ocr`.
  - Source moves to `src/cli/`, which ends the `plugins/…/mcp` clean-script trap.
- **No dynamic workflows.** `src/workflows/` is deleted. Fan-out is concurrent HTTP inside the CLI, capped by `thresholds.json`.
- **Routing is a table, not a framework.** `thresholds.json > models` maps each step to `{provider, model, maxOutputTokens, concurrency}`, and `thresholds.json > budget` holds per-run token and USD caps.
  - A step exceeding its budget exits `CAP_REACHED` or `ERROR`; it never degrades silently.
  - A missing verdict is an `ERROR`, never a `PASS`.
- **Heavy non-interactive skills run forked.** /proofread and the deep read run with `context: fork` and a pinned `model`/`effort` (docs-verified: skills may pin these), so the main session pays only for the summary. Subagents set `omitClaudeMd: true`, which saves about 4k tokens per spawn.

### 3.1 Jev decision points (rev 3)

Jev book (CandleKeep `cmu8rrf5k3y4dln0ie7g8qwtk`):
- **Ch 5:** roughly 0–7 points below a frontier model, about 10–25× faster and 14–100× cheaper.
- **RULE 6.3:** non-English work needs at least 100 labelled examples and a measured accuracy before adoption.

Every Hebrew point therefore starts in `shadow`. Each is promoted to `cascade` only by a release, after it has ≥100 labels and meets the roster bar (agreement ≥0.8, instability ≤0.1). In `cascade`, a confident Jev answer (≥ threshold) decides and an uncertain one escalates to the model.

| Point | Question | Labels come from |
|---|---|---|
| proofread.verify | uphold / refute this change | the author's accept/reject in Word, read back by /revise |
| proofread.triage | is this candidate a real error? | the same |
| revise.classify | text_edit / argument / voice_signal / plugin_defect | the author's confirmations |
| evidence.relevance | 0–3 relevance of a passage to the thesis | passages the outline actually used |
| outline.support | does this section claim support the thesis? | the author's section approvals |
| write.audit_prescreen | clearly supported / needs full audit (**never skips the Claude auditor while the gate is active**) | auditor verdicts |
| write.voice_check | does this paragraph read like the author? | the author's rewrites (pairs.jsonl) |
| synthesize.needs_bridge | does this paragraph boundary need a transition? | synthesis edits the author kept |
| style.filler | is this style-word use filler here? | must-catch hits the author accepted |

Every Jev call is logged to the run ledger with its answer, confidence and the eventual label, so `aw-improve` can compute agreement per point. The key is a sensitive user setting, `jev_api_key`, and the model id lives in `thresholds.json` (the API requires `model`). Jev is optional: with no key, every point runs on the model path.

**Dev side (Jev wherever it helps):**
- ALE judge in shadow on every plan bake (`--judge`);
- the `/work` executor-close shadow (`--criteria`);
- `aw-improve`: are two ledger items the same defect?
- an eval pre-grader: a rubric check before any model judge.

Lanes are never decided by Jev (WRK-46).

## 4. Components

### 4.1 Deep read → `evidence.json`

**Why it is slow and weak today.** One Sonnet agent reads each whole source serially over `ck`, then compresses everything into 400 words with no passage ids. Downstream agents then re-fetch the same pages.

**New flow:**
1. `aw fetch`: `ck` child process plus the Sefaria public HTTP API, run in parallel. The raw text is cached in `${CLAUDE_PLUGIN_DATA}/sources/<ck-id>@<version-hash>/`, so a CandleKeep book read for one project is not re-read for the next.
2. `aw extract` (Gemini flash, 1M context, one call per source, all sources in parallel) returns passage records: `{id, sourceId, locator, verbatim quote, gloss, relevance to thesis}`.
   - Each source record also carries `role: primary|secondary` and `isCoreText`, with the core text indexed passage by passage.
   - Code checks that every quote occurs verbatim in the cached text; a failing record is dropped and logged.
3. The result is `evidence.json`, which /write, /edit, /review and the auditor all read. Nothing re-fetches a source.

The thesis-relevance ranking uses `author-intent.json` (4.3), so the extraction serves the author's argument, not a generic summary. NotebookLM is dropped from this path.

### 4.2 Voice: one per person, shared across projects

**One store.** `${CLAUDE_PLUGIN_DATA}/voice/` holds:
- `profile.json`: a schema-versioned fingerprint from `extract-style-metrics.py`, the only source of statistics.
- `exemplars.jsonl`: 12–20 author-picked paragraphs, including quote-then-analysis pairs.
- `pairs.jsonl`: the author's rewrites of plugin prose, as before/after pairs from the docx loop.
- `style-words.json`: banned words, connective caps from the Hebrew Linguistic Reference, and filler/hedging.
- `rules.md`: at most 40 lines of qualitative moves.

This location is docs-verified: the data dir is shared by every install scope and version, and it survives updates. Projects keep only `author_key` and the voice version used in each run. `CLAUDE.md`'s "never write to `$HOME`" rule is narrowed to "only inside `${CLAUDE_PLUGIN_DATA}` and the project".

**Cross-machine sync and backup.** CandleKeep changes from a pull on every session start to push-on-change plus pull-on-demand (`aw voice pull`). Conflicts are resolved by the voice version and change log, not last-write-wins.

**Draft prompt.** 6 exemplars drawn by code (at most 1 per source paper, deliberately *not* topic-matched), 2 recent rewrite pairs, `rules.md` and `style-words.json`. The 10 KB generic terminology list is removed.

**Mining.** Statistics come from the script. Qualitative moves come from one Gemini-flash call over the author-picked corpus, not four Haiku agents. **The 7-session interview is removed.** It ran 0 of 7 times according to the stored profile, and the docx loop replaces it as the continuous voice learner.

**Fidelity metric.** `aw voice score` computes a function-word and character 3-gram authorship-verification distance to held-out author paragraphs. It is a regression gate and an eval grader.

### 4.3 /write (co-author)

```
W0 intent    main session: author-intent.json — thesis in the author's words, core text, main moves,
             must-use passages; seeded from /ideate research-brief.md when present
W1 evidence  4.1 (forked, background)
W2 outline   architect subagent (dialogue with the author) → outline.json under a schema:
             sections → units → paragraphs[{move, evidenceIds, bridgeTo}]; thesis stored verbatim + hash
             gates (code): evidence ids resolve, thesis hash unchanged, every must-use passage placed
   HUMAN     the author approves the thesis and each section's claim
W3 draft     aw draft: body units in dependency order; each call gets the whole outline, its predecessors'
             final text, its evidence passages, the voice bundle; intro and conclusion last, from the body
             gates (code): citation keys ∈ sources, quotes verbatim ∈ evidence.json, style-words, bounds
W4 audit     Claude auditor subagent, one batched call per unit (hard gate, active);
             OpenRouter judge in shadow beside it until it matches on the broken-citation fixture
W5 synthesis aw synthesize: paragraph-level transition diff given outline + thesis (no whole-article rewrite)
W6 docx      aw docx → the author comments in Word → /academic-writer:revise (4.5)
```

### 4.4 /proofread (forked, pinned model)

1. **P0 prepare** (code): docx→md, line-numbered chunks, protected spans (geresh-aware quotation detection, and a verse regex restricted to book names).
2. **P1 must-catch** (code): `style-words.json`, the project's `terms.json` (a names/terms canon seeded from `sources.json` authors and titles and grown by the docx loop), and hspell non-words.
   - Each hit is anchored on its text and is **always applied**, whatever its risk class.
3. **P2 find** (Gemini flash, batched per chunk): typos, wrong words and register. Each change carries its `before` text, and code resolves the line within the chunk's range.
4. **P3 verify** (OpenRouter cross-family if a key is set, else Gemini): one batched call per chunk, only for changes that *can* apply. P1 hits are never vetoed, and the wrong-word class is explicitly in scope.
5. **P4 editorial memo** (one call). **P5 apply** (code): tracked-changes docx and a report.

The funnel bugs from the evidence are fixed along the way: line anchoring, the veto of wrong-word fixes, the geresh guard, the budget order and the skipReason schema. **Recall is scored on applied output.**

### 4.5 The docx loop: `/academic-writer:revise` (new, user-invocable)

This skill replaces the internal `feedback` skill. It:
- is not user-invocable today;
- writes to `.academic-writer/`, the wrong directory;
- hardcodes the developer's memory path;
- edits plugin files that updates overwrite.

**Flow:**
1. **Read.** `aw docx read <file>` extracts comments (python-docx native API) and tracked changes (raw `w:ins`/`w:del` XML, including moves and paragraphs wholly inside revisions) as items `{id, anchorText, author, kind: comment|insert|delete|replace, text}`.
2. **Classify.** One Gemini call plus the author's confirmation in the main session sorts each item into:
   - **text edit**: apply it to the article source, then regenerate the docx;
   - **argument/content**: route it to W2/W3 for the affected unit only;
   - **voice signal**: the author's own rewrite of plugin prose. It becomes a before/after pair, and repeated word swaps become `style-words.json` or `terms.json` proposals. The author sees the diff to their voice before it is written;
   - **plugin defect**: something the tool did wrong in a way that will recur (for example, a wrong translation chosen, or a structure invented). It is appended to `${CLAUDE_PLUGIN_DATA}/feedback/ledger.jsonl` with the run id, step, item and the author's words.
3. **Improve the plugin** (dev side, never self-modifying at runtime).
   - A repo-local skill `.claude/skills/aw-improve/` (not shipped) reads the ledger and each run's `events.jsonl`/`usage.jsonl`, and clusters recurring defects.
   - Each cluster becomes an **eval case** (4.7) plus a fix, planned and built with `/work` + ALE, then released.
   - A defect is closed only when its eval case fails before the fix and passes after it.

This formalizes what the author already does by hand: `ACADEMIC-WRITER-BUGS.md` and `PLUGIN-ISSUES-FOR-OTHER-SESSION.md` in the shmaria project.

### 4.6 Construction fixes (best-practice checklist)

- Use `allowed-tools` (and fix CLAUDE.md:32), `disallowedTools`, and drop `agents:` and the plugin `settings.json` permissions. A structure test asserts the documented keys, and a fixture proves the test can fail.
- Move `agents/memory/` out of `agents/` (it creates 5 phantom agents), and remove the phantom `research-rag` and `research-candlekeep` references.
- Keep every SKILL.md under 500 lines, with bulk moved to `references/`, and set `omitClaudeMd: true` on agents.
- Remove the plaintext `secrets.json` fallback; keys live only in the keychain via userConfig `sensitive`. Quote `"${CLAUDE_PLUGIN_ROOT}"` in hooks.
- Hooks: fix the SubagentStart contradictions and delete the stale anti-AI scoring text. Make the stale-ownership gate hash-based.
- **One install.** Move to a single user-scope install and uninstall the 10 per-project installs with `--keep-data`. The hooks already skip projects without `.academic-helper/profile.md`.
- **Release discipline.** Every release does a version bump, a marketplace refresh and `claude plugin update`. `/health` reports the installed version against the repo's version.

### 4.7 Evaluation

- `evals/` holds a `claude plugin eval` suite with code-first graders:
  - proofread applied recall on an injected fixture (typos, style words, names/terms, adversarial geresh and quotation constructs);
  - citation-gate reject recall on broken citations;
  - evidence quote-verbatim rate;
  - the voice-fidelity distance;
  - an outline gate (thesis hash kept, must-use passages placed);
  - per-case token and USD from the ledger.
- The private shmaria corpus stays local, as a pre-release regression run (per the regression-fixture memory). The committed fixtures are synthetic plus adversarial.
- `measure-run.py` is a port of the forensics `aw_cost.py`, with the same method: message-id dedupe, main session included.

## 5. Targets

| Metric | Baseline [measured] | Target |
|---|---|---|
| /proofread, kabalah article (2,338 words), all Claude tokens incl. main session | 39.9M for one killed run (98.1M across 3 attempts) | ≤ 5M, one run, all stages complete |
| /write, 5–6k-word seminar paper, Claude tokens incl. main session | 289M (R2) / 416M (R1) | ≤ 40M |
| Gemini + OpenRouter spend per run | not tracked | /proofread ≤ $0.50, /write ≤ $3.00 (thresholds) |
| Proofread applied recall: names/terms, style words | not measured | ≥ 0.98 |
| Proofread applied recall: plain typos | not measured | ≥ 0.85 |
| Changes applied inside protected quotations | not measured | 0 |
| Evidence quotes verbatim in the source | not measured | 1.00 (enforced by code) |
| Voice fidelity: median draft→author distance | baseline on HEAD | ≤ the author's own cross-paper p75 |
| Outline rewrites after drafting starts | 1 of 1 (shmaria) | 0 on the pilot paper |

## 6. Build plan shape (ALE)

The plan is built with `/work` and ALE, and lanes come from `flow lane`. Pi panes are the unattended executor, per the global rules. Codex is not used.

**Slices, each ending in a release plus one measured real run:**
0. Construction fixes, the eval harness, `measure-run.py`, the ledger, and the move to one user-scope install. This makes every later slice measurable.
1. The `aw` CLI core (Gemini client moved in, the OpenRouter adapter, budgets) plus /proofread.
2. Voice store and migration, the deep read → `evidence.json`, and `/revise` with the ledger and `aw-improve`.
3. /write (W0–W6).

## 7. Where this spec disagrees with a stated preference

- **"Delegate via Pi + OpenRouter."** Rev 2 objected: your Pi loads vault `AGENTS.md`, guards and autosave extensions, and writes sessions under `~/.pi`. **Resolved in rev 3** by Pi's isolation flags (`--no-context-files --no-extensions --no-skills --no-session --no-tools`, plus `--system-prompt`), so Pi is the harness.
  - **Remaining costs, accepted:** Pi has no schema enforcement, so `aw` validates and retries once; process start-up latency per call; and usage and cost must be read from `--mode json` events (T1 verifies this).
  - OpenRouter credits are not bought yet, so the judge stays optional.
- **"Codex for delegation"** (rev 1). Dropped, per your retirement of Codex. The probe numbers stay in the run dir for reference.
- **"Improve the plugin with every fix."** The installed plugin must not edit itself: updates overwrite it, and silent self-modification can't be reviewed. It improves through the ledger → eval case → release loop instead.
- **The 7-session voice interview.** Removed. Your corrections in Word are better voice evidence than an interview you never had time to finish.
- **Gemini flash only.** Accepted. The fidelity metric will show whether flash limits the voice; if it does, the model is a one-line change in `thresholds.json > models`.
- **Open question for you:** should /write's default output be a **full draft** (the current default) or **evidence-anchored paragraph plans** that you write from, with drafting on request? This spec keeps the full draft, since the docx loop learns from your rewrites of it. If you mainly rewrite heavily anyway, plans-first would be cheaper.

## 8. Risks

- **`${CLAUDE_PLUGIN_DATA}` is not in the Bash environment.** The CLI must resolve it: slice 0 spikes whether a skill's `${CLAUDE_PLUGIN_DATA}` substitution can pass it as an argument, and falls back to the documented path.
- **Migration.** Moving 10 installs to one could touch per-project configs. Slice 0 lists each and needs your approval before any uninstall.
- **The OpenRouter judge on Hebrew is unmeasured.** It stays in shadow until the fixtures show parity.
- **Whether `claude plugin eval` can run cases that call Gemini** (network, keys) is unverified. The fallback is repo-side e2e scripts with the same graders.
