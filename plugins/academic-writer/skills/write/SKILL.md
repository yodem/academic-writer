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

Before any drafting and before the "Voice profile load" step below, verify the shared voice
store actually has real content. The authoritative store is `${CLAUDE_PLUGIN_DATA}/voice/`
(`profile.json` field `authorVoice`, or populated `rules.md` plus `exemplars.jsonl`); legacy
projects may still pass via `AUTHOR_VOICE.md` in the project root:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check-voice-populated.py AUTHOR_VOICE.md --data-dir "${CLAUDE_PLUGIN_DATA}"
```

- **Exit 0** (populated shared store or legacy file): continue to the "Voice profile load" step immediately below.
- **Exit 1** (stub/missing): **STOP the `/write` pipeline** — do not proceed to Step 1 or spawn
  any agent. Tell the user: "Your voice profile isn't set up yet. Run `/academic-writer:voice` to
  build it, then re-run `/write`."
- **Exit 2** (usage/encoding/corrupt-store error): also **STOP**. Exit 2 is treated as a block, not success —
  fail closed, since we cannot confirm voice is populated. Tell the user: "Your voice store could
  not be read/parsed — check it for corruption, or run `/academic-writer:voice` to regenerate it."

This gate is authoritative for all three outcomes; it replaces any older warn-and-continue
behavior for this condition.
<!-- END voice-precondition-gate -->

### Voice profile load (first step of every run)

1. Run `${CLAUDE_PLUGIN_ROOT}/skills/voice/voice-sync.sh pull "${CLAUDE_PLUGIN_DATA}" "$PWD"` — pulls the latest
   shared voice store from CandleKeep (last-write-wins). **Check its exit code and surface its stdout/stderr** rather than
   silently continuing: exit 0 means it synchronized successfully; any other exit code is a real
   failure — say so before proceeding, don't let Step 2 quietly read stale voice data as if the pull
   had happened.
2. Do not read `AUTHOR_VOICE.md` into the prompt. The shared voice bundle in `${CLAUDE_PLUGIN_DATA}/voice/`
   is loaded by `aw draft` and `aw synthesize` for every drafting/synthesis call.
3. The drafting prompt (`aw draft`'s `write-draft.md`) is written to weight `## Academic-specific`
   rules higher when they conflict with `## Core voice` rules; everything else applies as written.

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

The full `styleFingerprint` object lives in `profile.md`, which `aw draft` and `aw synthesize` read directly from disk — not summarized, and not something you pass in a prompt. It must stay populated at every stage.

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
  - "Expand my draft using sources" — use their structure as the approved outline; skip the architect's outline generation (Step 5); record their draft text as `userDraftParagraphs` per unit in the outline so the W3 drafting step (`aw draft`) has it as the starting point to expand and anchor in sources
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
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --project-dir "$CLAUDE_PROJECT_DIR" --data-dir "${CLAUDE_PLUGIN_DATA}" evidence build \
  --sources <comma-separated-source-ids> --sefaria <comma-separated-references> \
  --intent "$CLAUDE_PROJECT_DIR/.academic-helper/author-intent.json" --run <run-id>
```

The command writes `.academic-helper/evidence.json`. Wait for it to finish, show the author the extracted passage IDs, and let them choose any required `mustUse` passages. Update `author-intent.json` with those IDs while preserving the thesis verbatim. An extraction error is a failed stage; do not continue with a missing or partial evidence file.

### W2: Co-author and validate the outline

**PHASE 1: CONVERSATIONAL planning phase (human-in-the-loop).** The author reviews and refines every claim. Iterate until the researcher says the claims are ready; never infer approval from silence.

Spawn `architect` with the author-intent file and evidence file paths. The architect writes `.academic-helper/outline.json` directly using `${CLAUDE_PLUGIN_ROOT}/skills/write/references/outline.schema.json`; it preserves the intent thesis verbatim. It may offer up to `thresholds.json > write.outlineMaxAlternatives` clearly labelled alternatives for discussion, but never substitutes one into the artifact unless the author edits the intent first.

For every section, show its claim to the author and record explicit approval in that section's `approved` field. For each claim, invoke `aw decide outline.support` with a focused question and context containing the claim and evidence support note. Use `supported` or `unsupported` as the fallback according to the architect's support assessment. Include `--label approved` or `--label rejected` after the author's response. This logged decision is advisory; only the author's approval sets `approved` and the gate decides whether writing may proceed.

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --project-dir "$CLAUDE_PROJECT_DIR" --data-dir "${CLAUDE_PLUGIN_DATA}" decide outline.support \
  --question "Does this section claim follow from the cited passages and advance the thesis?" \
  --options supported,unsupported --context-file <claim-context-file> \
  --fallback <supported-or-unsupported> --run <run-id> --label <approved-or-rejected>

python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gate.py" outline-v2 \
  --outline "$CLAUDE_PROJECT_DIR/.academic-helper/outline.json" \
  --intent "$CLAUDE_PROJECT_DIR/.academic-helper/author-intent.json" \
  --evidence "$CLAUDE_PROJECT_DIR/.academic-helper/evidence.json"
```

The gate must exit `0` before drafting. Exit `1` means revise the outline or approval state and rerun the gate. Exit `2` means the gate could not run; repair the inputs and rerun. See `references/write-intent-outline.md` for artifact examples and recovery details.

Legacy v1 outlines remain supported for existing projects: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gate.py argument-graph <outline.json>` validates their argument graph, and `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gate.py stale-evidence-ownership <outline.json> --evidence-ownership <evidence-ownership.json>` validates their ownership map. Do not proceed to W3 until every check for the outline version in use passes.

### W3: Draft the article

`aw draft` owns the drafting order and the model call — it drafts every body unit in topological
`dependsOn` order, then drafts `intro` and `conclusion` last (from the body units' claim
sentences), reading `outline.json`, `author-intent.json`, `evidence.json`, `sources.json`, the
voice bundle, and `thresholds.json > models["write.draft"]` itself. You do not dispatch units one
layer at a time — one call drafts the whole outline, and it runs long enough (multiple model
calls in sequence) that it belongs in the background:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --project-dir "$CLAUDE_PROJECT_DIR" --data-dir "${CLAUDE_PLUGIN_DATA}" draft \
  --outline "$CLAUDE_PROJECT_DIR/.academic-helper/outline.json" --run <run-id>
```

Run this via the Bash tool with `run_in_background: true`, then poll for its completion rather than
blocking the turn on it. It writes `drafts/<unitId>.md` for every unit as it finishes and prints one
JSON object on stdout: `{"drafted": [unitId, ...], "failures": [{"unit", "gate", "detail"}, ...]}`.

- **Exit 0, empty `failures`** — every unit passed its code gates (citation keys in `sources.json`,
  every quoted span verbatim in `evidence.json`, the `style-words.json` banned/capped rules, and the
  `thresholds.json > writerUnit` word bounds). Continue to W4.
- **Exit 2** — one or more units failed a code gate. `failures[]` names the unit and the gate
  (`citation-not-in-sources`, `quote-not-in-evidence`, `style-banned`, `style-capped`,
  `word-bounds`). Each such failure counts as one rewrite cycle for that unit (see W4) — write a
  feedback file naming the gate and detail, then redraft with `--unit`.
- **Exit 1** — a real error (missing input, model failure). Stop and report it; `aw draft` never
  falls back silently to a different model.

### W4: Batched citation audit, then rewrite failed units

Once W3 finishes (all units drafted, or as many as could be), audit every unit's draft. **Use the
Agent tool to spawn one `auditor` subagent per unit — call the Agent tool multiple times in a
single response so every unit is audited in parallel.** Each call is a single batched call over
every paragraph in that unit's `drafts/<unitId>.md` (the 847c831 shape: one auditor spawn per unit,
not one per paragraph) — see `${CLAUDE_PLUGIN_ROOT}/agents/auditor.md` for the exact input/output
contract, including the `taggedText` field the auditor returns for each passed paragraph.

The auditor is the only mandatory hard gate, and it always runs — nothing in this pipeline
substitutes for it or skips it. (`aw draft` may separately run the `write.audit_prescreen` and
`write.voice_check` Jev points per paragraph as logged-only signals; neither one gates or replaces
the Claude auditor call here.)

For each unit's batch of `results`:
- Every `PASS` paragraph: write its `taggedText` back into `drafts/<unitId>.md` at that paragraph's
  position (this is where a `[NEEDS REVIEW: <field>]` tag actually lands in the committed text).
- Any `FAIL`/`PARTIAL` paragraph, or any paragraph the auditor omitted or listed twice (an ERROR,
  never a silent pass): collect its `feedback` (or, for an omitted/duplicate index, a note saying
  so) into a feedback file for that unit, e.g. a JSON array of `{paragraphIndex, feedback}`.
- A unit with any collected feedback — from the auditor above, or from a W3 code-gate `failures[]`
  entry — gets redrafted:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --project-dir "$CLAUDE_PROJECT_DIR" --data-dir "${CLAUDE_PLUGIN_DATA}" draft \
  --outline "$CLAUDE_PROJECT_DIR/.academic-helper/outline.json" --run <run-id> \
  --unit <unitId> --feedback-file <path-to-feedback.json>
```

Re-audit only the redrafted unit (one more batched `auditor` call over just its paragraphs), and
repeat. Track rewrite attempts **per unit**, reading the ceiling at runtime rather than inlining it:

```bash
python3 -c "import json;print(json.load(open('${CLAUDE_PLUGIN_ROOT}/thresholds.json'))['rewriteCycles']['max'])"
```

A unit that still has failing paragraphs after `rewriteCycles.max` attempts ships with those
paragraphs tagged `[NEEDS REVIEW: unresolved after rewrite]` in `drafts/<unitId>.md`, rather than
looping forever — note this in the closing report (W6) so the author knows exactly which
paragraphs to check by hand.

### W5: Synthesize

Once every unit's draft is final (audited, or capped at the rewrite limit), run the diff synthesis
pass. It reads all of `drafts/*.md` in outline order and proposes paragraph-level transition edits
only — it never rewrites a paragraph from scratch, and citations are untouched:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --project-dir "$CLAUDE_PROJECT_DIR" --data-dir "${CLAUDE_PLUGIN_DATA}" synthesize \
  --outline "$CLAUDE_PROJECT_DIR/.academic-helper/outline.json" --run <run-id>
```

It prints `{"edits": [{unitId, paragraphIndex, before, after, reason}, ...], "applied": n}` and
applies the edits to `drafts/*.md` itself — there is nothing further for you to write back. Non-zero
exit is a real error; stop and report it. (`aw synthesize` may run the `synthesize.needs_bridge`
Jev point per section boundary as an internal signal for which boundaries to consider; it does not
change what you do here.)

### W6: Output and handoff

Follow the abstract and self-review procedures in `references/write-completion.md`, then create the
DOCX in code from the synthesized drafts in outline order. Keep the audited text and citations intact.
Call `aw docx` with `--data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD"`, the outline, run id,
output path, and optional title/cover/abstract/format JSON files. The command writes the article JSON
under `.academic-helper/runs/<id>/article.json` and invokes `scripts/generate-docx.py`.

After the DOCX is written, close the loop with the author: tell them to open the `.docx`, add Word
comments or tracked changes anywhere they want something revisited, and then run
`/academic-writer:revise` to fold those comments back into the draft and feedback stores. Mention
any unit that hit the W4 rewrite cap by name, since those paragraphs need the author's attention
regardless of whether they added a comment.
