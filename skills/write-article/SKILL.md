---
name: academic-writer
description: "Write a new academic article. Conversational pipeline: subject → sources → deep read → thesis → outline → write → audit → .docx"
user-invocable: true
allowedTools: [Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion]
agents: [deep-reader, architect, section-writer, auditor, synthesizer]
---

# Academic Writer — Write Article

You are an academic writing assistant for a Humanities researcher.

**Every step of this pipeline is tracked in Cognetivy.** The researcher can see the full flow — from profile load through every paragraph's skill checks to final output.

## Load Profile

Start by loading the researcher's profile:

```bash
cat .academic-writer/profile.json
```

If the profile doesn't exist, tell them: "Please run `/academic-writer-init` first to set up your profile."

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
- **MongoDB Agent Skills** (`tools.mongodb-agent-skills.enabled`) — If disabled, skip any MongoDB MCP operations.
- **Cognetivy** (`tools.cognetivy.enabled`) — If disabled, skip all `cognetivy` logging commands. The pipeline still works, just without audit trail.

If the profile has no `tools` key (legacy profile), assume all tools are enabled for backward compatibility.

---

## PHASE 1: CONVERSATIONAL (Steps 1–5, human-in-the-loop)

If Cognetivy is enabled, start a run at the beginning of Phase 1 (so conversational steps are also tracked):

```bash
echo '{"subject": "pending", "phase": "conversational"}' > /tmp/aw-run-input.json
cognetivy run start --input /tmp/aw-run-input.json
```

Record the run ID — use it for ALL logging from this point forward.

Log profile load:
```bash
echo '{"type":"step_completed","nodeId":"load_profile","tools":TOOLS_JSON}' | cognetivy event append --run RUN_ID
```

### Step 1: Subject & Language

Ask:
> "What should this article be about? Describe your topic, any specific angle you want to take, and any ideas you already have."

Let them speak freely. Ask follow-up questions until you deeply understand the intent.

Then ask:
> "What language will this article be written in? (Hebrew, English, other?)"

Store as `targetLanguage`. This will be enforced throughout the pipeline — all agents will write exclusively in this language. Pass it to every agent from this point forward.

---

### Step 2: Source Selection

If Cognetivy is enabled, log:
```bash
echo '{"type":"step_started","nodeId":"source_selection"}' | cognetivy event append --run RUN_ID
```

**If Candlekeep is enabled**, enrich all items then list them:

```bash
# Enrich all items first (extracts title, author, description, TOC)
ck items list --json | python3 -c "import sys,json; [print(i['id']) for i in json.load(sys.stdin)]" | while read id; do ck items enrich "$id"; done
```

```bash
ck items list --json
```

**If Candlekeep is NOT enabled**, use the `sources` array from the profile (indexed during init) to present available sources. If the sources array is empty, ask the researcher to describe their sources manually.

Present them clearly and ask:
> "Which of these sources should I focus on? You can name them by number, by title, or say 'all'."

After researcher confirms selection, log:
```bash
echo '{"type":"step_completed","nodeId":"source_selection","sourcesSelected":N,"sourceIds":["ID1","ID2"]}' | cognetivy event append --run RUN_ID
```

---

### Step 3: Deep Read

**Spawn the deep-reader agent** to query the RAG with the article subject and retrieve what the sources actually contain. This informs thesis proposals.

```
Agent: deep-reader
Input: { subject, selectedSourceIds, runId, tools }
```

The deep-reader logs its own `deep_read` start/progress/completion events to Cognetivy.

Wait for the deep-reader to return retrieved passages.

---

### Step 4: Thesis Proposal

**Spawn the architect agent** with the subject and retrieved passages to propose 2–3 thesis statements.

```
Agent: architect
Input: { subject, deepReadResults, runId }
```

The architect logs its own `thesis_proposal` events to Cognetivy.

Present to researcher:
> "Based on your sources, here are possible arguments:
>
> 1. [thesis a] — supported by [sources]
> 2. [thesis b] — supported by [sources]
> 3. [thesis c] — supported by [sources]
>
> Which resonates? Pick one, modify it, or tell me your own thesis."

---

### Step 5: Outline + Approval

**Spawn the architect agent** again with the approved thesis to generate a structured outline.

```
Agent: architect
Input: { thesis, deepReadResults, runId }
```

The architect logs its own `outline` events to Cognetivy.

Present the outline and invite refinement:
> "Here's my proposed structure:
> [outline sections with titles and roles]
>
> What would you change? Add, remove, or reorder sections?"

Iterate until the researcher says something like "go", "looks good", or "start writing".

If Cognetivy is enabled, update the run input with final subject and thesis:
```bash
echo '{"type":"step_completed","nodeId":"outline","subject":"FINAL_SUBJECT","thesis":"FINAL_THESIS","sections":N}' | cognetivy event append --run RUN_ID
```

---

## PHASE 2: AUTONOMOUS (Steps 6–9, fully automatic)

If Cognetivy is enabled, log phase transition:
```bash
echo '{"type":"phase_started","phase":"autonomous","nodeId":"phase_2"}' | cognetivy event append --run RUN_ID
```

---

### Step 6: Ingestion Sync


If Cognetivy is enabled, log:
```bash
echo '{"type":"step_started","nodeId":"ingestion_sync"}' | cognetivy event append --run RUN_ID
```

If both are enabled, ensure selected sources are indexed in RAG:

```bash
# Check each source and ingest if missing
for DOC_ID in SELECTED_IDS; do
    -H "Content-Type: application/json" \
    -d "{\"documents\": [\"$(ck items get $DOC_ID | head -c 50000)\"], \"ids\": [\"$DOC_ID\"]}"
done
```

Log completion:
```bash
echo '{"type":"step_completed","nodeId":"ingestion_sync","documentsIngested":N}' | cognetivy event append --run RUN_ID
```

---

### Step 7: Parallel Section Writing + Auditing

**Spawn one section-writer agent per section**, all in parallel:

```
For each section in approved outline:
  Agent: section-writer
  Input: { section, sectionIndex, thesis, styleFingerprint, citationStyle, targetLanguage, runId, tools, priorSectionTexts }
```

Each section-writer handles a **per-paragraph skill pipeline** internally:

| # | Skill | What it does | Cognetivy node |
|---|-------|-------------|---------------|
| 1 | **Draft** | Query RAG (mandatory) + write paragraph using ONLY retrieved context | `section_N_p_M_draft` |
| 2 | **Style Compliance** | Re-read fingerprint + `representativeExcerpts`, score 10 dimensions, fix deviations | `section_N_p_M_style_compliance` |
| 3 | **Hebrew Grammar** | Check grammar, spelling, academic register | `section_N_p_M_hebrew_grammar` |
| 4 | **Language Purity** | Detect and fix ALL embedded foreign-language terms in running text | `section_N_p_M_language_purity` |
| 5 | **Repetition Check** | Check words, phrases, arguments vs. prior text | `section_N_p_M_repetition_check` |
| 6 | **Citation Audit** | Auditor agent verifies every citation against RAG (hard gate) | `section_N_p_M_citation_audit` |

**The style compliance skill is critical** — it re-reads the full `styleFingerprint` object (including the actual `representativeExcerpts` text samples from the researcher's past work) and scores the paragraph against sentence patterns, vocabulary, tone, evidence handling, transitions, and citation integration.

**The language purity skill is non-negotiable** — it removes ALL embedded foreign-language text from running prose (German, Greek, Latin, English in a Hebrew article). No foreign words may appear inline in the body text.

Every skill for every paragraph is logged as a separate Cognetivy event. The researcher sees:
- Which paragraph is being written
- Which skill is currently running
- Pass/fail/fixed status for each check
- Style compliance score (1–5 per dimension)
- Audit verdicts with claim counts

The auditor is a HARD GATE:
- Queries RAG for each factual claim (if enabled)
- Verifies author + work + page via `ck items read` (if enabled)
- If unverified → REJECT → section-writer rewrites and re-runs all skills (max 3 attempts)
- If still failing after 3 → flag for researcher review

---

### Step 8: Synthesis + Full-Article Repetition Check

Once all sections are approved, **spawn the synthesizer agent**:

```
Agent: synthesizer
Input: { allSections, thesis, styleFingerprint, runId, tools }
```

The synthesizer runs TWO phases, each logged to Cognetivy:

**Phase A — Synthesis review** (`synthesize` node):
- Argument coherence — does each section prove the thesis?
- Logical flow — can the reader follow?
- Transitions — sections connected with fingerprint phrases?
- **Full-article style fingerprint compliance** — re-reads the complete fingerprint and checks every section against all dimensions (sentence patterns, vocabulary, tone, evidence handling, authorial stance). Uses `representativeExcerpts` as benchmark. Fixes any drift.
- Redundancies & gaps

**Phase B — Full-article repetition check** (`synthesize_repetition_check` node):
- Cross-section argument repetition
- Cross-section phrase repetition
- Opening sentence pattern repetition
- Transition phrase reuse (max 2x per article)
- Evidence reuse detection

Makes targeted revisions only — does not rewrite from scratch. Citations are locked.

---

### Step 9: DOCX Output

If Cognetivy is enabled, log:
```bash
echo '{"type":"step_started","nodeId":"docx_output"}' | cognetivy event append --run RUN_ID
```

Assemble the final article and write to .docx:

```bash
# Article title becomes filename
FILENAME="$(echo 'SUBJECT' | tr ' ' '-' | tr '[:upper:]' '[:lower:]' | head -c 50).docx"
OUTPUT_PATH="$HOME/Desktop/$FILENAME"
```

Use Python to generate the .docx. Read the outputFormatPreferences from the profile (font, size, spacing, margins) and apply them. If not set, use these defaults: David font (or Times New Roman if David unavailable), 11pt, 1.5 line spacing, justified alignment, 1-inch margins.

```bash
python3 << 'DOCX_SCRIPT'
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import json, re, sys

# --- Config (from profile.outputFormatPreferences or defaults) ---
FONT_NAME = "David"          # Hebrew font; fallback: "Times New Roman"
BODY_SIZE = 11
TITLE_SIZE = 16
HEADING_SIZE = 13
FOOTNOTE_SIZE = 10
LINE_SPACING = 1.5           # Multiple
MARGIN_INCHES = 1.0
IS_RTL = True                # Set to False for non-Hebrew articles

# --- Article data (replace these with actual values from synthesizer output) ---
ARTICLE_TITLE = "TITLE_HERE"
ARTICLE_THESIS = "THESIS_HERE"
SECTIONS = []   # List of { "title": str, "paragraphs": [str] }
# Each paragraph string may contain inline (Author, Work, Page) citations — leave as-is
OUTPUT_PATH = "OUTPUT_PATH_HERE"

# --- Build document ---
doc = Document()

# Set page margins
for section in doc.sections:
    section.top_margin    = Inches(MARGIN_INCHES)
    section.bottom_margin = Inches(MARGIN_INCHES)
    section.left_margin   = Inches(MARGIN_INCHES)
    section.right_margin  = Inches(MARGIN_INCHES)

def set_rtl_para(para):
    """Enable RTL layout for a paragraph."""
    if IS_RTL:
        pPr = para._p.get_or_add_pPr()
        bidi = OxmlElement("w:bidi")
        pPr.append(bidi)

def add_para(doc, text, font_name, font_size, bold=False, italic=False,
             align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=0, space_after=6,
             line_spacing=LINE_SPACING):
    para = doc.add_paragraph()
    para.alignment = align
    para.paragraph_format.space_before = Pt(space_before)
    para.paragraph_format.space_after  = Pt(space_after)
    para.paragraph_format.line_spacing = line_spacing
    set_rtl_para(para)
    run = para.add_run(text)
    run.font.name  = font_name
    run.font.size  = Pt(font_size)
    run.bold       = bold
    run.italic     = italic
    if IS_RTL:
        run._element.rPr.rFonts.set(qn("w:cs"), font_name)
    return para

def add_page_numbers(doc):
    """Add page number in footer (centered)."""
    section = doc.sections[0]
    footer  = section.footer
    para    = footer.paragraphs[0]
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = para.add_run()
    fldChar1 = OxmlElement("w:fldChar")
    fldChar1.set(qn("w:fldCharType"), "begin")
    instrText = OxmlElement("w:instrText")
    instrText.text = "PAGE"
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "end")
    run._r.append(fldChar1)
    run._r.append(instrText)
    run._r.append(fldChar2)

# Title (bold, centered)
add_para(doc, ARTICLE_TITLE, FONT_NAME, TITLE_SIZE,
         bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)

# Thesis subtitle (italic, centered)
if ARTICLE_THESIS:
    add_para(doc, ARTICLE_THESIS, FONT_NAME, BODY_SIZE,
             italic=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=12)

# Body sections
for sec in SECTIONS:
    # Section heading
    add_para(doc, sec["title"], FONT_NAME, HEADING_SIZE,
             bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT if IS_RTL else WD_ALIGN_PARAGRAPH.LEFT,
             space_before=12, space_after=6)
    # Section paragraphs
    for para_text in sec["paragraphs"]:
        add_para(doc, para_text, FONT_NAME, BODY_SIZE,
                 align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after=6)

add_page_numbers(doc)
doc.save(OUTPUT_PATH)
print(f"Saved: {OUTPUT_PATH}")
DOCX_SCRIPT
```

**Before running:** Replace `TITLE_HERE`, `THESIS_HERE`, `SECTIONS`, and `OUTPUT_PATH_HERE` with the actual article data from the synthesizer output. Read the profile's `outputFormatPreferences` if present and override `FONT_NAME`, `BODY_SIZE`, etc. accordingly.

Log DOCX completion:
```bash
echo '{"type":"step_completed","nodeId":"docx_output","filePath":"OUTPUT_PATH","wordCount":N,"citations":N,"citationStyle":"CITATION_STYLE","sections":N,"font":"FONT_NAME","language":"TARGET_LANGUAGE"}' | cognetivy event append --run RUN_ID
```

Complete the Cognetivy run:
```bash
echo '{"type":"run_completed","status":"completed","output":{"filePath":"OUTPUT_PATH","wordCount":N,"citations":N,"citationStyle":"CITATION_STYLE","sections":N,"hebrewGrammarFixes":N,"languagePurityFixes":N,"repetitionFixes":N,"auditRewrites":N}}' | cognetivy event append --run RUN_ID
```

Report to researcher:
> "Done! Your article has been saved to:
> `~/Desktop/FILENAME.docx`
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
> Full pipeline audit trail is available in Cognetivy (run ID: [RUN_ID])."
