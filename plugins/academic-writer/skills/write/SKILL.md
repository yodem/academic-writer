---
name: write
description: "Write a new academic article. Conversational pipeline: subject → sources → deep read → thesis → outline → write → audit → .docx. Use when starting a new article from scratch — subject, sources, thesis, outline, draft."
user-invocable: true
allowed-tools: [Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion]
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

### W0: Capture author intent

Read `.academic-helper/research-brief.md` when it exists. Seed the thesis from its `## Thesis Direction` section, then ask the author to state or revise the thesis in their own words using `AskUserQuestion` and accept free-text wording. Confirm the core text source, the argument moves, and passages that must appear. Save `.academic-helper/author-intent.json` with the exact thesis text, `coreTextSourceId`, `moves`, and `mustUse`, following `${CLAUDE_PLUGIN_ROOT}/skills/write/references/author-intent.schema.json`. Do not paraphrase or improve the author's thesis in this artifact.

### W1: Build evidence

Start evidence extraction in the background while planning continues. Pass the selected source IDs, core text references, author intent path, run ID, and the required `--project-dir` and `--data-dir` arguments:

```bash
aw --project-dir "$CLAUDE_PROJECT_DIR" --data-dir "${CLAUDE_PLUGIN_DATA}" evidence build \
  --sources <comma-separated-source-ids> --sefaria <comma-separated-references> \
  --intent "$CLAUDE_PROJECT_DIR/.academic-helper/author-intent.json" --run <run-id>
```

The command writes `.academic-helper/evidence.json`. Wait for it to finish, show the author the extracted passage IDs, and let them choose any required `mustUse` passages. Update `author-intent.json` with those IDs while preserving the thesis verbatim. An extraction error is a failed stage; do not continue with a missing or partial evidence file.

### W2: Co-author and validate the outline

**PHASE 1: CONVERSATIONAL planning phase (human-in-the-loop).** The author reviews and refines every claim. Iterate until the researcher says the claims are ready; never infer approval from silence.

Spawn `architect` with the author-intent file and evidence file paths. The architect writes `.academic-helper/outline.json` directly using `${CLAUDE_PLUGIN_ROOT}/skills/write/references/outline.schema.json`; it preserves the intent thesis verbatim. It may offer up to `thresholds.json > write.outlineMaxAlternatives` clearly labelled alternatives for discussion, but never substitutes one into the artifact unless the author edits the intent first.

For every section, show its claim to the author and record explicit approval in that section's `approved` field. For each claim, invoke `aw decide outline.support` with a focused question and context containing the claim and evidence support note. Use `supported` or `unsupported` as the fallback according to the architect's support assessment. Include `--label approved` or `--label rejected` after the author's response. This logged decision is advisory; only the author's approval sets `approved` and the gate decides whether writing may proceed.

```bash
aw --project-dir "$CLAUDE_PROJECT_DIR" --data-dir "${CLAUDE_PLUGIN_DATA}" decide outline.support \
  --question "Does this section claim follow from the cited passages and advance the thesis?" \
  --options supported,unsupported --context-file <claim-context-file> \
  --fallback <supported-or-unsupported> --run <run-id> --label <approved-or-rejected>

python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gate.py" outline-v2 \
  --outline "$CLAUDE_PROJECT_DIR/.academic-helper/outline.json" \
  --intent "$CLAUDE_PROJECT_DIR/.academic-helper/author-intent.json" \
  --evidence "$CLAUDE_PROJECT_DIR/.academic-helper/evidence.json"
```

The gate must exit `0` before drafting. Exit `1` means revise the outline or approval state and rerun the gate. Exit `2` means the gate could not run; repair the inputs and rerun. See `references/write-intent-outline.md` for artifact examples and recovery details.

Legacy v1 outlines remain supported for existing projects: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gate.py argument-graph <outline.json>` validates their argument graph, and `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gate.py stale-evidence-ownership <outline.json> --evidence-ownership <evidence-ownership.json>` validates their ownership map. In that legacy flow, Do NOT proceed to Step 6 until all four checks pass. The Workflow tool path still uses `workflows/write-sections.js`; Fallback when the Workflow tool is unavailable, run the same section sequence through the sequential fallback. AUDIT_MODE: external; control flow only is duplicated.

The old 15-agent dynamic workflow size guideline and `/config` advice apply only to legacy deployments; the current plugin cannot define runtime workflow fan-out in the user's configuration.

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

### Completion steps

Follow the synthesis, abstract, self-review, and output procedures in
`references/write-completion.md`. Keep the approved section text and citations intact.
