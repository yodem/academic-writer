---
name: write
description: "Write a new academic article. Conversational pipeline: subject → sources → deep read → thesis → outline → write → audit → .docx"
user-invocable: true
allowedTools: [Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion]
agents: [deep-reader, architect, section-writer, auditor, synthesizer]
---

# Academic Writer — Write Article

You are an academic writing assistant for a Humanities researcher.


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

## PHASE 1: CONVERSATIONAL (Steps 1–5, human-in-the-loop)


```bash
# Validate wf_write_article has nodes — if empty, re-register from plugin cache
if [ "$_AW_NODES" -eq 0 ]; then
  _AW_DIR=$(find ~/.claude/plugins/cache -name "wf_write_article.json" -path "*/workflows/*" 2>/dev/null | head -1 | xargs dirname 2>/dev/null)
fi
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


**If Candlekeep is enabled**, enrich all items then list them:

```bash
# Enrich all items first (extracts title, author, description, TOC)
ck items list --json | python3 -c "import sys,json; [print(i['id']) for i in json.load(sys.stdin)]" | while read id; do ck items enrich "$id"; done
ck items list --json
```

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
- **Step 2**: Ingest into vectorless (if enabled)
- **Step 3**: Query each document for subject coverage and arguments


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

- Skip the architect agent call entirely
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


---

### Step 6: Ingestion Sync


If both Candlekeep and Agentic-Search-Vectorless are enabled, ensure selected sources are ingested. First check what's already there, then ingest any missing ones:

```bash
# List already-ingested documents
bash plugins/academic-writer/scripts/vectorless-list.sh
```

For each selected source not yet ingested, read from Candlekeep and ingest:

```bash
# For each DOC_ID in selected sources:
CONTENT=$(ck items read "DOC_ID:all")
TITLE=$(ck items list --json | python3 -c "import sys,json; items=json.load(sys.stdin); [print(i.get('title','DOC_ID')) for i in items if i['id']=='DOC_ID']")
bash plugins/academic-writer/scripts/vectorless-ingest.sh --name "$TITLE" --content "$CONTENT"
```

**If Agentic-Search-Vectorless is not enabled**, skip this step — the deep-reader already read the sources via Candlekeep.

Log completion:

---

### Step 7: Parallel Section Writing + Auditing

**CRITICAL: Use the Agent tool to spawn one `section-writer` subagent per section. Call the Agent tool multiple times in a single response — one call per section — so all sections write in parallel.**


For each section in the approved outline, the Agent tool prompt must include:
- `section`: the section spec (title, description, argument role, suggested sources, paragraph count)
- `sectionIndex`: the section number
- `totalSections`: total section count
- `thesis`: the article thesis
- `articleStructure`: the researcher's structure conventions
- `citationStyle`: from the profile
- `targetLanguage`: from the profile
- `targetWordCount`: the requested article length (so each section is sized proportionally)
- `tools`: the enabled tools
- `priorSectionTexts`: text of all previously completed sections (for repetition awareness)
- `outlineOverview`: full outline titles and roles
- `userDraftParagraphs`: (if `userDraftAsOutline = true`) the user's draft text for this section — agents expand this rather than writing from scratch

**NOTE:** Do NOT pass `styleFingerprint`, `linkingWords`, `sourcesRegistry`, or `evidenceOwnership` in the prompt — section-writer agents load all four directly from disk to reduce context size:
- Fingerprint from `.academic-helper/profile.md`
- Linking words from `plugins/academic-writer/words.md`
- Source registry from `.academic-helper/sources.json` (deep-reader output)
- Evidence ownership map from `.academic-helper/evidence-ownership.json` (architect output)

Each section-writer handles a **per-paragraph skill pipeline** internally:

|---|-------|-------------|---------------|
| 1 | **Draft** | Query RAG (mandatory) + write paragraph using ONLY retrieved context. Enforce paragraph word ceiling (fingerprint mean+stdev, capped at 220 words). Back-reference any evidence not owned by this section. Metadata for citations MUST come from `sources.json` — never infer; mark `[?]` if absent or low-confidence. | `section_N_p_M_draft` |
| 2 | **Style Compliance** | Re-read fingerprint + `representativeExcerpts`, score 10 dimensions, fix deviations | `section_N_p_M_style_compliance` |
| 3 | **Hebrew Grammar** | Check grammar, spelling, academic register | `section_N_p_M_hebrew_grammar` |
| 4 | **Academic Language** | Check academic vocabulary level and linking words usage | `section_N_p_M_academic_language` |
| 5 | **Language Purity** | Detect and fix ALL embedded foreign-language terms in running text | `section_N_p_M_language_purity` |
| 6 | **Anti-AI Check** | Load `anti-ai-patterns-${targetLanguage_lower}.md` and detect/fix AI writing patterns. Score 5 dimensions, threshold 35/50. | `section_N_p_M_anti_ai` |
| 7 | **Repetition Check** | Check words, phrases, arguments vs. prior text + formulaic-pattern cap sweep against the language blacklist + evidence re-description guard via ownership map | `section_N_p_M_repetition_check` |
| 8 | **Citation Audit** | Auditor agent verifies every citation against RAG + page + Check D metadata integrity (hard gate for high-confidence mismatches; `[NEEDS REVIEW: <field>]` tag for low-confidence) | `section_N_p_M_citation_audit` |

After receiving each section-writer result, mark node complete:

The auditor is a HARD GATE:
- Queries RAG for each factual claim (if enabled)
- Verifies author + work + page via `ck items read` (if enabled)
- Runs Check D: compares every citation field (year, journal, publisher, title spelling) against `.academic-helper/sources.json`
  - High-confidence registry field mismatches citation → REJECT (`metadata_mismatch: <field>`)
  - Low-confidence / absent registry field → APPROVE with `[NEEDS REVIEW: <field>]` tag inline
- If unverified → REJECT → section-writer rewrites and re-runs all skills (max 3 attempts)
- If still failing after 3 → flag for researcher review

The `[NEEDS REVIEW: <field>]` marker persists into the final article output so the researcher can see exactly which fields need manual verification. It appears inline in citations, e.g., `(Cohen, Title, 2019 [NEEDS REVIEW: year], p. 45)`.

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
- Argument coherence, logical flow, transitions
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

**If score < 40/60**, ask whether to proceed or address issues first (using `AskUserQuestion`).
**If score >= 40/60**, show the scorecard and continue to DOCX output.

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

Use the `Write` tool to write the article as markdown to `$MD_PATH`. Structure:

```markdown
# ARTICLE_TITLE

*ARTICLE_THESIS*

## תקציר

[Abstract text from Step 8.5]

[If dual-language: second abstract under its own heading]

## Section Title (only if totalWords > 1500)

Paragraph 1 text with inline citations...

Paragraph 2 text...

## Next Section Title

...
```

**Rules:**
- Title as `# H1`, thesis as italic line below it
- Section headings as `## H2` — but only include them if `totalWords > 1500` (same rule as DOCX)
- Paragraphs separated by blank lines
- Keep all inline citations exactly as they appear (e.g., `(Author, Title, p. N)`)
- No extra formatting beyond what the article text already contains

#### Step 9b: DOCX Output

Write the article data to a JSON file, then run the standalone DOCX generator script:

1. **Write the article JSON** using the Write tool to `/tmp/aw-article-data.json`. Use this exact schema — do NOT write inline Python to construct it:

```json
{
  "title": "ARTICLE_TITLE from synthesizer",
  "thesis": "ARTICLE_THESIS or null",
  "abstract": {
    "primary": "Abstract text in targetLanguage (from Step 8.5)",
    "secondary": "Optional abstract in second language, or null"
  },
  "sections": [
    {
      "title": "Section title",
      "paragraphs": [
        {
          "text": "Paragraph body with NO inline parenthetical citations.",
          "footnotes": [
            { "after": "substring in text to anchor the superscript marker", "text": "Author, Title (Pub, 2024), p. 42." }
          ]
        }
      ]
    }
  ],
  "format": {
    "font": "from profile.outputFormatPreferences.font or David",
    "bodySize": 11,
    "titleSize": 16,
    "headingSize": 13,
    "lineSpacing": 1.5,
    "margins": 1.0,
    "isRtl": true
  },
  "totalWords": 0
}
```

**Rules:**
- Use the `Write` tool to write this file — never use Python heredoc or `python3 -c` to construct JSON (Hebrew text causes UTF-8 encoding errors in heredocs)
- Populate `sections` from the synthesizer output — each section's title and paragraph list
- Paragraphs use the structured form `{text, footnotes[]}`. Strip the parenthetical citations out of `text` and move each citation into `footnotes[]` with `after` set to a unique substring in `text` where the marker should appear. The DOCX generator renders them as native Word footnotes (superscript in body, text at page bottom). Plain strings are still accepted for backward compatibility (no footnotes)
- Dependency: requires `lxml` (`pip install lxml`) in addition to `python-docx`
- Read `outputFormatPreferences` from the profile and fill in the `format` object
- Set `totalWords` to the actual word count (controls section title visibility — hidden when under 1500 words)
- Set `isRtl` based on `targetLanguage` (true for Hebrew, false for English)

2. **Generate the DOCX:**

```bash
python3 plugins/academic-writer/scripts/generate-docx.py --input /tmp/aw-article-data.json --output "$DOCX_PATH"
```

The script handles all RTL formatting, directional marks, citation parentheses splitting, and conditional section titles deterministically.

Log output completion:


Report to researcher:
> "Done! Your article has been saved to:
> - `articles/FILEBASE.docx` (formatted document)
> - `articles/FILEBASE.md` (markdown)
>
> Word count: [N] words
> Citations: [N] ([citationStyle] format)
> Sections: [N]
> Language: [targetLanguage]
>
> Quality checks applied per paragraph:
> - Style fingerprint compliance: avg [N]/5 score, [N] adjustments
> - Hebrew grammar: [N] issues fixed
> - Language purity: [N] foreign-term violations fixed
> - Repetition: [N] instances fixed
> - Citation audits: [N] claims verified, [N] rejections resolved
>
