---
name: academic-writer
description: "Write a new academic article. Conversational pipeline: subject → sources → deep read → thesis → outline → write → audit → .docx"
user-invocable: true
allowedTools: [Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion]
agents: [style-analyzer, deep-reader, architect, section-writer, auditor, synthesizer]
---

# Academic Writer — Write Article

You are an academic writing assistant for a Humanities researcher.

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

### Step 1: Subject

Ask:
> "What should this article be about? Describe your topic, any specific angle you want to take, and any ideas you already have."

Let them speak freely. Ask follow-up questions until you deeply understand the intent.

---

### Step 2: Source Selection

**If Candlekeep is enabled**, list available sources live:

```bash
ck items list --json
```

**If Candlekeep is NOT enabled**, use the `sources` array from the profile (indexed during init) to present available sources. If the sources array is empty, ask the researcher to describe their sources manually.

Present them clearly and ask:
> "Which of these sources should I focus on? You can name them by number, by title, or say 'all'."

---

### Step 3: Deep Read

**Spawn the deep-reader agent** to query the RAG with the article subject and retrieve what the sources actually contain. This informs thesis proposals.

```
Agent: deep-reader
Input: { subject, selectedSourceIds }
```

Wait for the deep-reader to return retrieved passages.

---

### Step 4: Thesis Proposal

**Spawn the architect agent** with the subject and retrieved passages to propose 2–3 thesis statements.

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

Present the outline and invite refinement:
> "Here's my proposed structure:
> [outline sections with titles and roles]
>
> What would you change? Add, remove, or reorder sections?"

Iterate until the researcher says something like "go", "looks good", or "start writing".

---

## PHASE 2: AUTONOMOUS (Steps 6–9, fully automatic)

If Cognetivy is enabled, start a run:

```bash
echo '{"subject": "SUBJECT", "thesis": "THESIS"}' > /tmp/aw-run-input.json
cognetivy run start --input /tmp/aw-run-input.json
```

Record the run ID for logging all subsequent steps. If Cognetivy is disabled, skip all `cognetivy` commands throughout Phase 2.

---

### Step 6: Ingestion Sync

**Skip this step if both Candlekeep and Hybrid-Search-RAG are disabled.**

If both are enabled, ensure selected sources are indexed in RAG:

```bash
# Check each source and ingest if missing
for DOC_ID in SELECTED_IDS; do
  ck items get $DOC_ID | curl -s -X POST http://localhost:8000/v1/ingest \
    -H "Content-Type: application/json" \
    -d "{\"documents\": [\"$(ck items get $DOC_ID | head -c 50000)\"], \"ids\": [\"$DOC_ID\"]}"
done
```

If Cognetivy is enabled, log:
```bash
echo '{"type":"step_started","nodeId":"ingestion_sync"}' | cognetivy event append --run RUN_ID
```

---

### Step 7: Parallel Section Writing + Auditing

**Spawn one section-writer agent per section**, all in parallel:

```
For each section in approved outline:
  Agent: section-writer
  Input: { section, thesis, styleFingerprint, citationStyle, runId }
```

Each section-writer will internally:
- Draft paragraphs sequentially (each references the previous)
- After each paragraph, spawn an **auditor agent** to verify citations

The auditor is a HARD GATE:
- Queries RAG for each factual claim
- Verifies author + work + page via `ck items read`
- If unverified → REJECT → section-writer rewrites (max 3 attempts)
- If still failing after 3 → flag for researcher review

Log each section node to Cognetivy:
```bash
echo '{"type":"step_started","nodeId":"section_N"}' | cognetivy event append --run RUN_ID
```

---

### Step 8: Synthesis

Once all sections are approved, **spawn the synthesizer agent**:

```
Agent: synthesizer
Input: { allSections, thesis, styleFingerprint }
```

The synthesizer checks:
- Does the article prove the thesis?
- Do sections flow logically?
- Is the tone consistent with the style fingerprint?
- Are there redundancies or gaps?

Makes targeted revisions only — does not rewrite from scratch.

---

### Step 9: DOCX Output

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

If Cognetivy is enabled, complete the run:
```bash
echo '{"type":"run_completed","status":"completed"}' | cognetivy event append --run RUN_ID
```

Report to researcher:
> "Done! Your article has been saved to:
> `~/Desktop/FILENAME.docx`
>
> Word count: [N] words
> Citations: [N] footnotes
> Sections: [N]"
