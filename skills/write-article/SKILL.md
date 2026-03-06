---
name: academic-writer
description: "Write a new academic article. Conversational pipeline: subject → sources → deep read → thesis → outline → write → audit → .docx"
user-invocable: true
allowedTools: [Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion]
agents: [style-analyzer, deep-reader, architect, section-writer, auditor, synthesizer]
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

### Tool Awareness

Read the `tools` object from the profile. Throughout this workflow, **only use tools that are enabled**:

- **Candlekeep** (`tools.candlekeep.enabled`) — If disabled, skip `ck` commands. Source listing/selection steps should use any available sources from the profile's `sources` array instead.
- **Hybrid-Search-RAG** (`tools.hybrid-search-rag.enabled`) — If disabled, skip all RAG queries (`curl http://localhost:8000/...`). The deep-reader and auditor agents cannot run without RAG — warn the researcher and write without automated citation verification.
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

### Step 1: Subject

Ask:
> "What should this article be about? Describe your topic, any specific angle you want to take, and any ideas you already have."

Let them speak freely. Ask follow-up questions until you deeply understand the intent.

---

### Step 2: Source Selection

If Cognetivy is enabled, log:
```bash
echo '{"type":"step_started","nodeId":"source_selection"}' | cognetivy event append --run RUN_ID
```

**If Candlekeep is enabled**, list available sources live:

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

**Skip this step if both Candlekeep and Hybrid-Search-RAG are disabled.**

If Cognetivy is enabled, log:
```bash
echo '{"type":"step_started","nodeId":"ingestion_sync"}' | cognetivy event append --run RUN_ID
```

If both are enabled, ensure selected sources are indexed in RAG:

```bash
# Check each source and ingest if missing
for DOC_ID in SELECTED_IDS; do
  ck items get $DOC_ID | curl -s -X POST http://localhost:8000/v1/ingest \
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
  Input: { section, sectionIndex, thesis, styleFingerprint, citationStyle, runId, tools, priorSectionTexts }
```

Each section-writer handles a **per-paragraph skill pipeline** internally:

| Skill | What it does | Cognetivy node |
|-------|-------------|---------------|
| **Draft** | Query RAG + write paragraph with style fingerprint | `section_N_p_M_draft` |
| **Hebrew Grammar** | Check grammar, spelling, academic register | `section_N_p_M_hebrew_grammar` |
| **Repetition Check** | Check words, phrases, arguments vs. prior text | `section_N_p_M_repetition_check` |
| **Citation Audit** | Auditor agent verifies every footnote (hard gate) | `section_N_p_M_citation_audit` |

Every skill for every paragraph is logged as a separate Cognetivy event. The researcher sees:
- Which paragraph is being written
- Which skill is currently running
- Pass/fail/fixed status for each check
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
- Style consistency — tone matches fingerprint throughout?
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

Use Python to generate the .docx with proper Chicago footnotes:

```bash
python3 << 'EOF'
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
import json

doc = Document()
# Set Times New Roman, 12pt, 1-inch margins
# Title, sections, footnotes, bibliography
# ... (assembled from synthesizer output)
doc.save("OUTPUT_PATH")
EOF
```

Log DOCX completion:
```bash
echo '{"type":"step_completed","nodeId":"docx_output","filePath":"OUTPUT_PATH","wordCount":N,"footnotes":N,"sections":N}' | cognetivy event append --run RUN_ID
```

Complete the Cognetivy run:
```bash
echo '{"type":"run_completed","status":"completed","output":{"filePath":"OUTPUT_PATH","wordCount":N,"footnotes":N,"sections":N,"hebrewGrammarFixes":N,"repetitionFixes":N,"auditRewrites":N}}' | cognetivy event append --run RUN_ID
```

Report to researcher:
> "Done! Your article has been saved to:
> `~/Desktop/FILENAME.docx`
>
> Word count: [N] words
> Citations: [N] footnotes
> Sections: [N]
>
> Quality checks applied per paragraph:
> - Hebrew grammar: [N] issues fixed
> - Repetition: [N] instances fixed
> - Citation audits: [N] claims verified
>
> Full pipeline audit trail is available in Cognetivy (run ID: [RUN_ID])."
