---
name: academic-writer-init
description: "First-time setup for the Academic Writer. Configures researcher profile, analyzes writing style from past articles, and indexes research sources."
user-invocable: true
---

# Academic Writer — Initialization

You are setting up a researcher's Academic Writer profile. Be warm, clear, and non-technical. Explain why each step matters.

## Step 0: Initialize Folders

Create the necessary directories automatically (if they don't exist):

```bash
mkdir -p past-articles .academic-writer .cognetivy/runs .cognetivy/events
```

These folders are ready for your use:
- `past-articles/` — Drop your 5–10 published papers here (for style analysis)
- `.academic-writer/` — Your profile and internal data (auto-managed)
- `.cognetivy/` — Workflow audit trail (auto-managed)

---

## Prerequisites Check

### A. Check for existing profile

Before starting, verify the profile doesn't already exist:

```bash
cat .academic-writer/profile.json 2>/dev/null && echo "EXISTS" || echo "NOT_FOUND"
```

If profile EXISTS, ask: "You already have a profile set up. Would you like to update it, or start fresh?"

### B. Tool Registry — detect and select integrations

Academic Writer supports several external tools. Not all are required — the researcher picks the ones they use. Present the **Available Tools Registry** and auto-detect which are already installed.

#### Tool Registry

The following is the master list of supported tools. For each tool, run the detection command. Then present the results to the user as a checklist.

**1. Candlekeep** (`candlekeep`)
- *What it does:* Cloud document library for source PDFs and research materials
- *Type:* CLI
- *Setup:* https://github.com/romiluz13/candlekeep
- *Detection:*
```bash
command -v ck >/dev/null 2>&1 && echo "DETECTED" || echo "NOT_DETECTED"
```

**2. Hybrid-Search-RAG / Agentic-Search-Vectorless** (`hybrid-search-rag`)
- *What it does:* Deep semantic + keyword retrieval for citation search and verification
- *Type:* Local service (HTTP)
- *Setup:* https://github.com/romiluz13/Agentic-Search-Vectorless
- *Detection:*
```bash
curl -s --max-time 3 http://localhost:8000/health 2>/dev/null && echo "DETECTED" || echo "NOT_DETECTED"
```

**3. MongoDB Agent Skills** (`mongodb-agent-skills`)
- *What it does:* Database-backed research operations via MCP server
- *Type:* MCP server
- *Setup:* https://github.com/romiluz13/mongodb-agent-skills
- *Detection:*
```bash
# Check both user-level and project-level MCP settings
(cat ~/.claude/settings.json 2>/dev/null; cat .mcp.json 2>/dev/null) | python3 -c "
import sys, json
found = False
for line in sys.stdin.read().split('}{'):
    try:
        d = json.loads('{' + line.strip('{}') + '}')
        servers = d.get('mcpServers', {})
        if any('mongo' in k.lower() for k in servers):
            found = True
    except: pass
print('DETECTED' if found else 'NOT_DETECTED')
"
```

**4. Cognetivy** (`cognetivy`)
- *What it does:* Workflow tracking and audit trail for pipeline steps
- *Type:* CLI
- *Setup:* Built-in with this plugin (see `.cognetivy/` directory)
- *Detection:*
```bash
command -v cognetivy >/dev/null 2>&1 && echo "DETECTED" || echo "NOT_DETECTED"
```

#### Present results and let the user choose

After running all detection commands, present the results:

> "Here are the integrations Academic Writer supports. I've auto-detected what you have installed:
>
> | # | Tool | Status | What it does |
> |---|------|--------|-------------|
> | 1 | Candlekeep | ✓ Detected / ✗ Not found | Cloud document library |
> | 2 | Hybrid-Search-RAG | ✓ Detected / ✗ Not found | Semantic search & citation verification |
> | 3 | MongoDB Agent Skills | ✓ Detected / ✗ Not found | Database-backed research ops |
> | 4 | Cognetivy | ✓ Detected / ✗ Not found | Workflow audit trail |
>
> Which tools would you like to enable? You can pick by number, name, or say 'all detected'.
>
> For any tool marked ✗ that you'd like to use, I'll help you set it up."

**Rules:**
- The user does NOT have to enable all tools. Any combination is valid.
- If a user wants a tool that's not detected, show them the setup URL and walk them through installation. Re-run detection after they confirm setup.
- Only proceed once the user has confirmed their final tool selection.
- You can update enabled tools later with `/academic-writer-update-tools`.

#### Store the selection

Build a `tools` object for the profile (used in Step 5). For each tool, store:

```json
{
  "tools": {
    "candlekeep": { "enabled": true, "version": "detected" },
    "hybrid-search-rag": { "enabled": true, "version": "detected" },
    "mongodb-agent-skills": { "enabled": false },
    "cognetivy": { "enabled": true, "version": "detected" }
  }
}
```

Only include `"version": "detected"` for tools that were successfully detected. Omit the version key for disabled tools.

---

## Step 1: Field of Study

Ask:
> "What is your field of study and area of specialization?"

Prompt for specificity — "Early Modern History" is more useful than "History." Record their answer.

---

## Step 2: Citation Style

Ask:
> "Which citation style do you use in your work?"

Present options:
- **Chicago/Turabian** (most common in Humanities — footnotes)
- **MLA**
- **APA**

---

## Step 3: Past Articles for Style Analysis

Tell the researcher:
> "I need to learn your writing style so the articles I help produce sound like *you*, not like a generic AI.
>
> Please place 5–10 of your previously published articles or papers in this folder:
> `past-articles/`
>
> Supported formats: PDF, DOCX
>
> These files are used **only** to analyze your style — they are never uploaded anywhere.
> Tell me when you're ready."

Once they confirm, analyze their writing style by reading the files:

```bash
ls past-articles/
```

For each file, extract text:
- PDF: `python3 -c "import sys; import pdfplumber; [print(p.extract_text()) for p in pdfplumber.open(sys.argv[1]).pages]" past-articles/FILENAME 2>/dev/null || strings past-articles/FILENAME | head -500`
- DOCX: `python3 -c "import docx; d=docx.Document('past-articles/FILENAME'); [print(p.text) for p in d.paragraphs]" 2>/dev/null`

Analyze the combined text to create a **Style Fingerprint**:

Look for:
1. Average sentence length (word count)
2. Vocabulary complexity (simple / moderate / complex / highly-complex)
3. Tone descriptors (3–5 adjectives: e.g., "measured", "polemical", "discursive", "analytical")
4. Common transition phrases (list the most frequent)
5. Paragraph structure pattern (e.g., "topic sentence → evidence → analysis → forward link")
6. Citation density (sparse / moderate / dense)
7. Passive voice (rare / occasional / frequent)
8. Rhetorical patterns (e.g., "close reading", "comparative analysis", "thesis-antithesis-synthesis")
9. Three representative excerpts (1–2 sentences each) that best capture their voice

---

## Step 4: Research Sources

**This step adapts based on which tools the researcher enabled in the Prerequisites Check.**

### If Candlekeep is enabled:

Tell the researcher:
> "Now let's set up your research library. These are the books, articles, and primary sources you cite in your work.
>
> Add them to Candlekeep using:
> ```
> ck items add your-source.pdf
> ```
>
> Tell me when you've added your sources."

Once confirmed, list them:

```bash
ck items list --json
```

Parse the JSON output and build a **sources array** with only the metadata you need for the profile. For each item, extract:
- `id` — the Candlekeep document ID
- `title` — the document title
- `type` — the document type (pdf, docx, etc.)

**IMPORTANT:** Store only the minimal metadata above in the profile. Do NOT dump the raw `ck items list --json` output into the profile — that will break the JSON structure.

Build the sources array like this (in memory, for Step 5):
```json
[
  { "id": "DOC_ID_1", "title": "Document Title 1", "type": "pdf" },
  { "id": "DOC_ID_2", "title": "Document Title 2", "type": "pdf" }
]
```

### If Candlekeep is NOT enabled:

Tell the researcher:
> "Since Candlekeep is not enabled, you can provide source files directly in the `past-articles/` folder or manage sources manually.
>
> If you'd like to add Candlekeep later, run `/academic-writer-update-tools`."

Set the sources array to `[]` for the profile.

### If Hybrid-Search-RAG is enabled — sync sources to search index:

```bash
curl -s http://localhost:8000/v1/status | python3 -c "import sys,json; d=json.load(sys.stdin); print('RAG ready' if d.get('initialized') else 'RAG not ready')"
```

If RAG is ready and Candlekeep is also enabled, for each document ingest it:

```bash
# For each document ID from ck items list:
ck items get DOCUMENT_ID | curl -s -X POST http://localhost:8000/v1/ingest \
  -H "Content-Type: application/json" \
  -d "{\"documents\": [$(python3 -c \"import sys,json; print(json.dumps(sys.stdin.read()))\" <<<$(ck items get DOCUMENT_ID))], \"ids\": [\"DOCUMENT_ID\"]}"
```

### If Cognetivy is enabled — track the sync:

```bash
cognetivy run start --input /tmp/aw-init-input.json
```

If Cognetivy is NOT enabled, skip this logging step silently.

---

## Step 5: Save Profile

Save the complete profile:

Use the Write tool to create `.academic-writer/profile.json` with the following structure. Replace all placeholder values with the actual data you collected in the previous steps.

**IMPORTANT:** Use the Write tool (not bash heredoc) to avoid JSON escaping issues. Build the JSON carefully as a valid object.

```json
{
  "fieldOfStudy": "FIELD_HERE",
  "citationStyle": "chicago",
  "styleFingerprint": {
    "averageSentenceLength": 0,
    "vocabularyComplexity": "complex",
    "toneDescriptors": [],
    "preferredTransitions": [],
    "paragraphStructure": "",
    "citationDensity": "moderate",
    "passiveVoiceFrequency": "occasional",
    "rhetoricalPatterns": [],
    "sampleExcerpts": []
  },
  "tools": {
    "candlekeep": { "enabled": true, "version": "detected" },
    "hybrid-search-rag": { "enabled": true, "version": "detected" },
    "mongodb-agent-skills": { "enabled": false },
    "cognetivy": { "enabled": true, "version": "detected" }
  },
  "sources": [
    {
      "id": "DOC_ID",
      "title": "Document Title",
      "type": "pdf"
    }
  ],
  "createdAt": "TIMESTAMP",
  "updatedAt": "TIMESTAMP"
}
```

- `fieldOfStudy` — from Step 1
- `citationStyle` — from Step 2
- `styleFingerprint` — all values from Step 3 analysis
- `tools` — the tool registry from Prerequisites Check step B (only enabled/version for each tool)
- `sources` — the minimal metadata array built in Step 4 (id, title, type only — **never** raw Candlekeep JSON). Empty `[]` if Candlekeep is not enabled.
- `createdAt` / `updatedAt` — current ISO timestamp

---

## Confirmation

Summarize:
> "You're all set! Here's your profile:
>
> - **Field**: [field]
> - **Citation style**: [style]
> - **Writing style**: [2-3 sentence summary of fingerprint]
> - **Enabled tools**: [list enabled tool names]
> - **Sources indexed**: [count] documents (or 'none — Candlekeep not enabled')
>
> Run `/academic-writer` anytime to start writing an article.
> Run `/academic-writer-update-tools` to add or remove integrations later."
