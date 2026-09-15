---
name: write
description: "Write a new academic article. Conversational pipeline: subject → sources → deep read → thesis → outline → write → audit → .docx. Use when starting a new article from scratch — subject, sources, thesis, outline, draft."
user-invocable: true
allowedTools: [Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion]
agents: [deep-reader, architect, section-writer, auditor, synthesizer]
metadata: {author: "Yotam Fromm", version: "0.2.19"}
---

# Academic Writer — Write Article

You are an academic writing assistant for a Humanities researcher.

**Preflight**: If you haven't run `/academic-writer:setup` yet, run that first — it configures your Gemini key and Python tools in a few guided questions.

<!-- BEGIN voice-precondition-gate -->
### Voice profile precondition gate (mandatory — run before Step 1)

Before any drafting and before the "Voice profile load" step below, verify `AUTHOR_VOICE.md`
actually has real content — not missing, and not still the unpopulated stub:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check-voice-populated.py AUTHOR_VOICE.md
```

- **Exit 0** (populated): continue to the "Voice profile load" step immediately below.
- **Exit 1** (stub/missing): **STOP the `/write` pipeline** — do not proceed to Step 1 or spawn
  any agent. Tell the user: "Your voice profile isn't set up yet. Run `/academic-writer:voice` to
  build it, then re-run `/write`."
- **Exit 2** (usage/encoding error): also **STOP**. Exit 2 is treated as a block, not success —
  fail closed, since we cannot confirm voice is populated. Tell the user: "AUTHOR_VOICE.md could
  not be read/parsed — check the file for corruption, or run `/academic-writer:voice` to
  regenerate it."

This gate is authoritative for all three outcomes; it replaces any older warn-and-continue
behavior for this condition.
<!-- END voice-precondition-gate -->

### Voice profile load (first step of every run)

1. Run `${CLAUDE_PLUGIN_ROOT}/skills/voice/voice-sync.sh pull` — pulls latest `AUTHOR_VOICE.md` from
   CandleKeep (last-write-wins). **Check its exit code and surface its stdout/stderr** rather than
   silently continuing: exit 0 means it either pulled successfully or (an explicitly reported)
   local-only mode; any other exit code is a real failure — say so before proceeding, don't let
   Step 2 quietly read a stale local file as if the pull had happened.
2. Read `AUTHOR_VOICE.md` from project root. Whole file goes into the section-writer system prompt.
3. The section writer is instructed to weight `## Academic-specific` rules higher when they
   conflict with `## Core voice` rules; everything else applies as written.

---

### Gemini pre-flight (immediately after voice profile load)

Determine which model runs the prose for this article. This must run **after** Step 1 (Subject &
Language) captures `targetLanguage` but **before** Step 3 (Deep Read) — i.e. before any agent is
spawned. In short: read the profile's `approvedLanguages`, detect whether a Gemini key is
available, and proceed on Gemini or Claude accordingly; persist the chosen `geminiMode` to
`.academic-helper/session-state.json`. Full decision table and exact commands: see
`references/gemini-preflight.md`.

Gemini is approved by default for a project's `targetLanguage` (seeded during `init`), so this
step never blocks waiting on a human decision — `voice-calibrator --compare-models` is now an
optional, researcher-initiated opt-OUT check the user can run any time to pull a language back off
`approvedLanguages`; `/write` does not invoke it and does not wait on it.

Also covered in that reference: the **mid-run Gemini failure handler** — the one-time
AskUserQuestion prompt fired the first time a Gemini MCP call errors during this run, and how the
resulting `geminiFallback` choice propagates to subagents.

---

## Load Profile

Start by loading the researcher's profile:

```bash
cat .academic-helper/profile.md
```

If the profile doesn't exist, tell them: "Please run `/academic-writer:init` first to set up your profile."

Store the profile values — you'll use them throughout.

### Style Fingerprint — Always Loaded

**The `styleFingerprint` is the most critical part of the profile.** Read it carefully and keep it in context throughout the entire pipeline. Every paragraph and every review step checks against it.

Print a summary of the fingerprint to confirm it's loaded:
> "Loaded your style fingerprint:
> - Tone: [toneAndVoice.descriptors]
> - Sentence style: [sentenceLevel.averageLength], [sentenceLevel.structureVariety]
> - Paragraph pattern: [paragraphStructure.pattern]
> - Evidence handling: [paragraphStructure.evidenceIntroduction] → [paragraphStructure.evidenceAnalysis]
> - Author stance: [toneAndVoice.authorStance]
> - Citation density: [citations.density] (~[citations.footnotesPerParagraph]/paragraph)
>
> Every paragraph will be checked against this fingerprint."

Pass the full `styleFingerprint` object to every agent that writes or reviews text (section-writer, synthesizer). It must be available at every stage — not summarized, but the complete object.

### Tool Awareness

Read the `tools` object from the profile. Throughout this workflow, **only use tools that are enabled**:

- **Candlekeep** (`tools.candlekeep.enabled`) — If disabled, skip `ck` commands. Source listing/selection steps should use any available sources from the profile's `sources` array instead.
- **NotebookLM** (`tools.notebooklm.enabled`) — If disabled, skip notebook queries and AI summaries. NotebookLM is supplementary — it does not replace Vectorless/Candlekeep for citation verification.

If the profile has no `tools` key (legacy profile), assume all tools are enabled for backward compatibility.

---

## Pre-flight: existing-article guard

After computing the candidate slug from the user-supplied subject, check whether the article already exists:

```bash
SLUG="$(echo "$SUBJECT" | python3 -c "import sys,re; t=sys.stdin.read().strip().lower(); print(re.sub(r'[^a-z0-9]+', '-', t).strip('-')[:60])")"
MD_PATH="articles/${SLUG}.md"

if [ -f "$MD_PATH" ]; then
  echo "An article already exists at $MD_PATH."
  echo "Switching to edit mode — running /academic-writer:edit instead of overwriting."
  echo "If you intended to start over, delete $MD_PATH first."
  # Hand off to the edit skill rather than continuing the write pipeline.
  exit 0
fi
```

If the file exists, the skill MUST stop the write pipeline and tell the user to use `/academic-writer:edit articles/${SLUG}.md` (or `/academic-writer:edit-section` for a single section). Do NOT continue with deep-reader, architect, etc., because writing inline at that point produces ungated prose (the recorded 2026-05-02 post-compaction failure, in which a context compaction mid-pipeline led to prose being written inline, bypassing the audit gate entirely).

If the file does not exist, proceed with Phase 1 normally.

## PHASE 1: CONVERSATIONAL (Steps 1–5, human-in-the-loop)


```bash
echo '{"subject": "pending", "phase": "conversational"}' > /tmp/aw-run-input.json
```

Record the run ID — use it for ALL logging from this point forward.

Log profile load:

### Step 1: Subject & Language

Ask:
> "What should this article be about? Describe your topic, any specific angle you want to take, and any ideas you already have."

Let them speak freely. Ask follow-up questions until you deeply understand the intent.

Then ask:
> "What language will this article be written in? (Hebrew, English, other?)"

Store as `targetLanguage`. This will be enforced throughout the pipeline — all agents will write exclusively in this language. Pass it to every agent from this point forward.

### Article Length

After confirming topic and language, ask (using AskUserQuestion):
> "How long should this article be? (e.g., 1 page / ~400 words, 2 pages / ~800 words, 1,500 words, etc.)"

Record as `targetWordCount`. Use this number when:
- Instructing the architect how to size sections in Step 5
- Deciding whether to include section headings in DOCX output (> 1,500 words = headings shown)
- No default — always ask explicitly.

### User-Provided Draft

After the researcher describes their topic, check: did they paste a draft, pre-written paragraphs, or a structured outline along with their message?

Signs of a user draft: the message contains paragraph-length Hebrew or English text, bullet points with argument content, or phrases like "יש לי כבר בסיס" / "here's what I have" / "I already wrote..."

If a draft is detected, ask (AskUserQuestion):
- Header: "Draft detected"
- Question: "I see you've shared a draft/outline. How would you like to proceed?"
- Options:
  - "Expand my draft using sources" — use their structure as the approved outline; skip the architect's outline generation (Step 5); pass their draft text to each section-writer as the starting point to expand and anchor in sources
  - "Use my draft as context, propose a new structure" — treat their draft as research input for the architect; run the full thesis+outline flow normally

Store the draft text as `userDraftText` regardless of which option is chosen. If the researcher chose "Expand my draft", set `userDraftAsOutline = true`.


---

### Step 2: Source Selection


**If Candlekeep is enabled**, list the available sources — scoped to the active shelf when one is set:

```bash
# `ck shelf use` records the active shelf in ./.candlekeep/active-shelf.
# Scope the listing to it so a Jewish Studies write run doesn't present the
# researcher's entire library (engineering books included) as source options.
SHELF="$(tr -d '[:space:]' < ./.candlekeep/active-shelf 2>/dev/null || true)"
if [ -n "$SHELF" ]; then
  ck items list --shelf "$SHELF" --json || ck items list --json
else
  ck items list --json
fi
```

Do **not** run `ck items enrich` here. It is a manual metadata *setter* (`--title`,
`--author`, `--toc`, ...), not an auto-extractor: a bare `ck items enrich <ID>` exits
with "At least one of --title, --author, --description, --toc, --add-prompt, or
--sample-question is required". Enrichment is the researcher's curation step, and
running it across the whole library would overwrite it.

**If Candlekeep is NOT enabled**, use the `sources` array from the profile (indexed during init) to present available sources. If the sources array is empty, ask the researcher to describe their sources manually.

Present them clearly and ask:
> "Which of these sources should I focus on? You can name them by number, by title, or say 'all'."

After researcher confirms selection, log:

---

### Step 2b: NotebookLM Source Query (if enabled)

**Skip this entire step if `tools.notebooklm.enabled` is false.**

Before spawning the deep-reader, directly query NotebookLM for the article subject using MCP tools:

1. **List available notebooks** using the `notebook_list` MCP tool (no parameters needed).

2. **Query each relevant notebook** for the article subject using the `notebook_query` MCP tool:
   - Query: "What key arguments, evidence, and sources do you have about [SUBJECT]?"

3. **Show a brief summary** to the researcher:
   > "Your NotebookLM has [N] notebook(s). Key findings about your topic:
   > [bullet list of relevant results]
   > These will be passed to the deep-reader for source verification."

Pass the NotebookLM summary as additional context to the deep-reader agent prompt in Step 3.

**Important:** NotebookLM answers are AI-synthesized context. All citations must still be verified via Candlekeep or RAG — never cite NotebookLM output directly.

---

### Step 3: Deep Read


**Use the Agent tool to spawn the `deep-reader` subagent.** Pass as the prompt: the article subject, selectedSourceIds, tools configuration, AND `targetLanguage` (so the deep-reader emits its structured summary in the right language).

The deep-reader runs:
- **Step 1**: Read source content from Candlekeep
- **Step 1b**: Extract structured bibliographic metadata per source and write `.academic-helper/sources.json`. This registry is the ONLY trusted source for citation metadata in Step 7. Fields the deep-reader cannot confirm are marked `null` with `extractionConfidence: "low"` — never guessed.
- **Step 2**: Query NotebookLM notebooks (if enabled) for thematic context


Wait for the deep-reader to return retrieved passages before continuing to Step 4. Confirm `.academic-helper/sources.json` exists.

After receiving the deep-reader result, mark node complete:

---

### Step 4: Thesis Proposal


**Use the Agent tool to spawn the `architect` subagent.** Pass the subject, deep read results, and targetLanguage as the prompt.


After receiving the architect result, mark node complete:

Present the architect's output to researcher:
> "Based on your sources, here are possible arguments:
>
> 1. [thesis a] — supported by [sources]
> 2. [thesis b] — supported by [sources]
> 3. [thesis c] — supported by [sources]
>
> Which resonates? Pick one, modify it, or tell me your own thesis."

After the researcher picks a thesis, log thesis approval:

---

### Step 5: Outline + Approval

**If the researcher chose "Expand my draft" in the draft detection step (`userDraftAsOutline = true`):**

- Do NOT skip the architect entirely. The outline comes from the user's draft, but the architect is still the sole writer of `.academic-helper/evidence-ownership.json` — and without it the per-paragraph thesis-drift guard and the cross-section evidence-dedup both silently no-op. **Use the Agent tool to spawn the `architect` subagent in a lightweight "ownership-only" mode**: pass `userDraftText`, the deep-read results / `sources.json`, and `targetLanguage`, and instruct it to produce ONLY `evidence-ownership.json` (the `thesisAnchor` derived from the draft plus the `evidenceOwners` assignment for shared evidence) — it must NOT generate a new outline or thesis options, since those come from the user's draft.
- Parse `userDraftText` into sections: use the user's existing section headings and paragraph structure as the outline
- Present the extracted outline to the researcher:
  > "Using your draft structure:
  > [list extracted sections]
  > Each section-writer will expand these using source material. Confirm or adjust."
- Get approval, then proceed directly to Step 6 (ingestion sync) and Step 7 (section-writers)
- Pass `userDraftText` sections as `userDraftParagraphs` in each section-writer's prompt, so agents expand existing content rather than writing from scratch
- Log outline approval:

**If no draft (normal flow):**


**Use the Agent tool to spawn the `architect` subagent again** with the approved thesis, deep read results, targetWordCount, and targetLanguage.

The architect runs in Mode B:
- Produces the outline (titles, roles, suggested sources, word counts, paragraph counts) in `targetLanguage`
- Writes `.academic-helper/evidence-ownership.json` — for every evidence anchor (source, passage, dataset) appearing in more than one section, assigns exactly ONE section as the owner of the full description. Other sections must back-reference.
- Enforces a conciseness budget: body-section descriptions ≤ 2 sentences, intro/conclusion ≤ 3 sentences, no 5+ word phrase repeated across descriptions.


After receiving the architect result, mark node complete:

Present the outline and invite refinement:
> "Here's my proposed structure:
> [outline sections with titles and roles]
>
> What would you change? Add, remove, or reorder sections?"

Iterate until the researcher says something like "go", "looks good", or "start writing".


---

### Step 5.5: Argument Graph Validation

Before any section-writer is spawned, the approved outline's argument graph is validated — the `id` / `claim` / `evidence` / `depends_on` / `thesis_link` / `argument_role` fields captured during Step 5 approval, across every section AND every unit inside `units` arrays.

**This check is a script, not reasoning.** Write the approved outline to disk and run the gate:

```bash
# The outline must be persisted anyway — it is the artifact the gate reads and
# the record that makes the argument graph auditable after the run (VER-09).
cat > .academic-helper/outline.json <<'OUTLINE_JSON'
{ ...the approved outline, verbatim... }
OUTLINE_JSON

python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gate.py argument-graph .academic-helper/outline.json --json
```

Exit code is the verdict — do not re-derive it by reading the output prose:

| Exit | Meaning | Action |
|---|---|---|
| `0` | all four checks pass | proceed to Step 6 |
| `1` | the outline is invalid | repair it (below), then re-run the gate |
| `2` | the gate could not run | fix the cause (missing/malformed `outline.json`); do NOT proceed — an unrun gate is not a passed gate |

Also record the run in the gate ledger before Step 6, so a skipped gate is detectable rather than invisible:

```bash
python3 - <<'PY'
import json, os, pathlib
p = pathlib.Path('.academic-helper/session-state.json')
d = json.loads(p.read_text()) if p.exists() else {}
d['run'] = {'id': os.environ.get('CLAUDE_SESSION_ID', 'run'), 'skill': 'write',
            'requiredGates': ['argument-graph', 'citation-floor'], 'completed': False}
p.write_text(json.dumps(d, indent=2, ensure_ascii=False))
PY
```

The `gate-enforce` Stop hook reads this and will refuse to let the turn end while a required gate is missing or failing. Mark `run.completed = true` after Step 9b.

The four checks the gate enforces (documented here so a reader knows what it covers — the script, not this list, is the enforcement):

- **No orphan sections/units**: every node's claim must trace back to the thesis via `thesis_link` — either the node has its own `thesis_link` directly, or it `depends_on` a node that (transitively) does. Walk the `depends_on` chain from each node; flag any node where the chain never reaches a `thesis_link`.
- **No circular `depends_on` references**: no node may depend, directly or transitively, on itself. The gate reports the cycle path.
- **No empty evidence**: every node's `evidence` array must be non-empty. Flag any node with `evidence: []`.
- **Dependency ordering**: the section/unit sequence in the outline (which becomes the Step 6 writing order) must respect `depends_on` — a node cannot appear before every node listed in its `depends_on`. Flag any node whose position violates this topological ordering.

**On exit 1**, the outline must be revised before Step 6 begins. The gate's `--json` output names each violation as `{check, nodeId, detail}` — use those ids directly:
- Present the failing node `id`s and their checks to the researcher, or
- Loop back to the architect with the flagged nodes and ask it to repair the outline (fix missing `thesis_link`, break the cycle, add evidence, or reorder).

Then rewrite `.academic-helper/outline.json` and **re-run the gate**.

Do NOT proceed to Step 6 until all four checks pass on the current outline — that means a fresh exit `0`, re-run after every edit. A remembered pass is not a pass: the artifact changed (`VER-09`).

### Step 5.6: stale evidence-ownership check

`.academic-helper/evidence-ownership.json` (written by the architect — see the ownership-only
fallback above, and "Writes evidence-ownership.json" under the architect's own responsibilities)
is loaded from disk by every section-writer, by contract. A copy left over from a *previous* run
of the same article — mapping ownership for a thesis the researcher has since rejected — is never
compared against the current outline anywhere else, so it would silently steer every freshly
spawned writer back toward the abandoned frame. Same class of check as Step 5.5, a script not
reasoning, run once more right before Step 6:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gate.py stale-evidence-ownership .academic-helper/outline.json \
  --evidence-ownership .academic-helper/evidence-ownership.json --json
```

| Exit | Meaning | Action |
|---|---|---|
| `0` | `evidence-ownership.json` doesn't exist yet, or is newer than or equal to `outline.json` | proceed to Step 6 |
| `1` | `evidence-ownership.json` is OLDER than `outline.json` — built for a prior outline | move it aside (e.g. rename to `evidence-ownership.stale.json`) or re-run the architect in ownership-only mode to regenerate it, then re-run the gate |
| `2` | the gate could not run (missing `outline.json`) | fix the cause; do NOT proceed |

Do NOT proceed to Step 6 on exit `1` — an outline can change without evidence-ownership.json being
regenerated (the researcher revises the thesis after Step 5.5 passes, or a stale file survives from
an earlier attempt at the same article), and a stale ownership map is a correctness trap, not a
missing-file error: nothing else in the pipeline will ever notice it's wrong.

---

## ⛔ MANDATORY: NO DIRECT WRITING

**You (the write-article skill) MUST NEVER write article paragraphs or sections yourself.**

This means:
- NEVER use the `Write` tool for article body text during Phase 2
- NEVER produce paragraph content inline in your response
- ALL article content MUST come exclusively from `section-writer` subagents

The 8-skill quality pipeline (style fingerprint compliance, grammar, anti-AI, citation audit, etc.) only runs inside section-writer agents. Writing directly bypasses every quality gate and produces unchecked output that does not match the researcher's voice.

**If you are tempted to write the article yourself because the user provided a detailed draft or the sources seem clear — DO NOT. Spawn the section-writers.**

---

## PHASE 2: AUTONOMOUS (Steps 6–9, fully automatic)

**Generation stages (Step 6 through the Step 8.7 scorecard computation) now run via the Workflow
tool** with `scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflows/write-sections.js"`. Planning (Steps 1–5,
Step 5.5's argument-graph validation, and the human's outline approval) stays fully interactive in
this skill, never inside the script — this is the SPC-03 human-approval-before-generation gate,
and it is not something the script can perform since the script has no `AskUserQuestion` access.
The skill invokes the Workflow tool only after Step 5.5 passes, passing it the already-validated
outline (not the raw architect output).

If the script returns a scorecard below the `thresholds.json > selfReview.passThreshold`, the
skill resumes inline at that point and asks the researcher via `AskUserQuestion` (see Step 8.7) —
the below-threshold branch is never handled inside the script itself, only the numeric comparison
is.

**Note on workflow size**: a full article's writer-unit fan-out (Step 6) plus its per-paragraph
auditor spawns can exceed the default 15-agent "medium" dynamic-workflow size guideline —
`thresholds.json > writerUnit` targets ~500 words per unit, so a 6,000–8,000 word article yields
roughly 12–16 writer units before counting auditor, deep-reader, architect, and synthesizer spawns.
The plugin cannot raise this ceiling itself; if the run is large, tell the researcher to raise
"Dynamic workflow size" in `/config` before starting Step 6.

**Fallback when the Workflow tool is unavailable**: run the same stages sequentially through the
`Agent` tool exactly as described below (control flow only is duplicated) — spawn `section-writer`
subagents directly, **without** `AUDIT_MODE: external`, so each agent's in-agent audit path
(auditor spawn per paragraph, rewrite-cycle cap, claims-registry append) runs unchanged. The
fallback path must produce the same named gate outcomes (auditor VERDICT, anti-AI threshold,
rewrite-cycle cap) as the script path; state in the closing report which path (Workflow or
fallback) actually ran.

### Step 6: Parallel Section Writing + Auditing

#### Step 6.0: Engine commit (run BEFORE the parallel spawn)

Before spawning any section-writer, commit the whole run to ONE engine (Gemini or Claude-only) by
live-probing Gemini (not just checking the key file) and writing the result to
`.academic-helper/session-state.json > geminiFallback`. Never mix engines across writer units in
the same run. Full probe procedure and exact commands: see `references/section-writer-dispatch.md`.

#### Spawning section-writers

**CRITICAL: Use the Agent tool to spawn one `section-writer` subagent per WRITER UNIT. Call the Agent tool multiple times in a single response — one call per unit — so all writer units write in parallel.**

A section with no `units` array in the approved outline is itself a single writer unit — spawn exactly one subagent for it. A section WITH a `units` array is NOT itself spawned directly — spawn one subagent per entry in its `units` array instead. The parallel fan-out count for this step is therefore the total number of writer units across the whole outline, which may exceed the number of top-level sections.

The exact prompt fields each spawn needs (`unit`, `parentSection`, `siblingUnitsSummary`,
`sectionIndex`, `totalSections`, `unitIndex`/`unitId`, `totalUnitsInSection`, `thesis`,
`articleStructure`, `citationStyle`, `targetLanguage`, `targetWordCount`, `tools`,
`priorSectionTexts`, `outlineOverview`, `userDraftParagraphs`, `geminiFallback`) and the four values
section-writers load directly from disk instead (`styleFingerprint`, `linkingWords`,
`sourcesRegistry`, `evidenceOwnership`) are listed in full in `references/section-writer-dispatch.md`
— read it before constructing the spawn prompts.

Each section-writer handles a **per-paragraph 8-skill pipeline** internally — in order: Draft → Style Compliance → Grammar Check (language-specific, dispatched by `targetLanguage`) → Academic Language → Language Purity → Anti-AI → Repetition Check → Citation Audit (logged per paragraph as `section_N_p_M_<skill>`). The authoritative contract for that pipeline — exact skill behavior, the 220-word ceiling, the `thresholds.json`-driven anti-AI gate, and the auditor hard gate (Citation Audit / Skill 8) — lives in the `section-writer` agent definition (`${CLAUDE_PLUGIN_ROOT}/agents/section-writer.md`). Do not duplicate or override it here; the orchestrator only spawns section-writers and waits for their results.

After receiving each section-writer result (per writer unit), mark node complete:

---

### Step 8: Synthesis + Full-Article Repetition Check

Once all sections are approved, log the spawn event:

**Use the Agent tool to spawn the `synthesizer` subagent.** Pass the following as the prompt:
- All completed section texts
- The thesis statement
- The complete styleFingerprint object
- The articleStructure conventions
- The linkingWords reference
- The `targetLanguage` (so the synthesizer loads the correct anti-AI patterns reference)
- The tools configuration


**Phase A — Synthesis review** (`synthesize` node):
- Argument coherence, logical flow, transitions — including subsection-to-subsection transitions WITHIN a section (between sibling writer units), not just section-to-section transitions
- Full-article style fingerprint compliance
- Redundancies & gaps

**Phase B — Full-article repetition check** (`synthesize_repetition_check` node):
- Cross-section argument, phrase, opener, transition, and evidence repetition

Makes targeted revisions only — does not rewrite from scratch. Citations are locked.

After receiving the synthesizer result, mark node complete:

---

### Step 8.5: Abstract Generation


Generate a structured abstract (תקציר) from the completed article. The abstract has 3 parts:

1. **Topic & research question** — What is this article about? What question does it address?
2. **Methodology & sources** — What approach was used? Which sources were analyzed?
3. **Main findings & contribution** — What did the research find? How does it advance the field?

**Length:** 150–300 words in `targetLanguage`.

**Dual-language abstracts:** Check the profile for `abstractLanguages`. If it includes languages beyond `targetLanguage` (e.g., both Hebrew and English), generate an abstract in each language.

If `abstractLanguages` is not set in the profile, default to `[targetLanguage]` only.

Store the abstract(s) for inclusion in the DOCX output.

Log completion:

---

### Step 8.7: Self-Review (Quality Gate)


Run the self-review checklist from `/academic-writer:review`. Score the article on 6 dimensions (each 1–10):

1. **Structure** — Intro/conclusion conventions, logical section order
2. **Argument Logic** — Each section advances thesis, no gaps
3. **Citation Completeness** — Every claim cited, consistent format
4. **Source Coverage** — All sources used, balanced distribution
5. **Writing Quality** — Matches style fingerprint, no grammar issues
6. **Academic Conventions** — Linking word variety, paragraph length, transitions

Present the scorecard to the researcher.

**If score is below the self-review threshold defined in `thresholds.json` (default 40/60)**, ask whether to proceed or address issues first (using `AskUserQuestion`).
**If score meets or exceeds the threshold (default 40/60)**, show the scorecard and continue to DOCX output.

Log completion:

---

### Step 9: DOCX Output


Assemble the final article and write to both Markdown and DOCX:

```bash
# Output to project's articles/ directory (created if needed)
mkdir -p articles
FILEBASE="$(echo 'SUBJECT' | tr ' ' '-' | tr '[:upper:]' '[:lower:]' | head -c 50)"
MD_PATH="articles/${FILEBASE}.md"
DOCX_PATH="articles/${FILEBASE}.docx"
```

#### Step 9a: Markdown Output

Use the `Write` tool to write the article as markdown to `$MD_PATH` — title as H1, thesis as an
italic line below it, section headings as H2 (only when `totalWords > 1500`), inline citations kept
exactly as they appear. Exact structure template and full rules: see
`references/docx-generation.md#step-9a-markdown-output`.

#### Step 9a.5: Hebrew Punctuation Validation (mandatory quality gate)

Before generating the DOCX, run the deterministic punctuation validator over the markdown file just written:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate-hebrew-punctuation.py "$MD_PATH"
```

This checks logical bracket/paren/quote balance and flags mixed gershayim/straight-quote characters and likely-missing bidi marks around embedded Latin/digit runs — the exact class of defect that causes mismatched parentheses and quotation marks in the rendered DOCX.

- **If the script exits non-zero**, review each reported violation and fix the source markdown (do not proceed to DOCX generation with known punctuation defects still present).
- **If the script exits 0**, continue to Step 9b.

This gate is mandatory for any article containing Hebrew text — it is not optional and must not be skipped even under time pressure.

#### Step 9a.6: Citation Floor (mandatory quality gate)

The per-paragraph auditor is a **presence** check — it verifies that claims which *are* cited are cited correctly. It is structurally blind to a paragraph that cites nothing, and the self-review scorecard's 1–10 "Citation Completeness" dimension cannot separate 15 footnotes from 30. Absence needs its own counting gate (`VER-18`), and the count is arithmetic, not judgement.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gate.py citation-floor "$MD_PATH" \
  --sources .academic-helper/sources.json --json
```

Only **secondary** citations count toward the floor: primary sources are quoted inline in this field, so a raw citation count reads healthy on an article carrying almost no scholarly engagement. Floors live in `thresholds.json > citationFloor` — never hardcode them here.

- **Exit 1** — the article is under a floor. Do not ship it. Either the argument genuinely lacks scholarly engagement (send the thin sections back through Step 6 with the gate's per-section counts), or citations were dropped in synthesis — check Step 8's revision notes.
- **Exit 2** — the gate could not run (missing `sources.json`, unreadable markdown). Fix the cause; an unrun gate is not a passed gate.
- **Exit 0** — continue to Step 9b.

#### Step 9b: DOCX Output

Write the article data to a JSON file, then run the standalone DOCX generator script:

1. **Write the article JSON** using the `Write` tool to `/tmp/aw-article-data.json` — never inline
   Python/heredoc (Hebrew text causes UTF-8 encoding errors in heredocs). Exact JSON schema and
   population rules (footnote structuring, `format` object, `totalWords`, `isRtl`): see
   `references/docx-generation.md#step-9b-docx-output--article-json-schema`.

2. **Generate the DOCX:**

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/generate-docx.py --input /tmp/aw-article-data.json --output "$DOCX_PATH"
```

The script handles all RTL formatting, directional marks, citation parentheses splitting, and conditional section titles deterministically.

Log output completion:

**Close the run in the gate ledger.** Until this runs, the `gate-enforce` Stop hook treats the run
as still in flight and will keep blocking the end of the turn:

```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path('.academic-helper/session-state.json')
if p.exists():
    d = json.loads(p.read_text())
    if isinstance(d.get('run'), dict):
        d['run']['completed'] = True
        p.write_text(json.dumps(d, indent=2, ensure_ascii=False))
PY
```

Report completion to the researcher — word count, citation count, section count, language, and a
per-check summary of quality-gate outcomes. Exact template: see
`references/docx-generation.md#closing-report-template`.
