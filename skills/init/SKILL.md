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

### B. Validate required tools

**IMPORTANT:** All three tools below must be available before proceeding. Check each one. If any is missing, guide the user through setup and **do not continue** until all are confirmed working.

#### 1. Candlekeep (`ck` CLI)

```bash
command -v ck >/dev/null 2>&1 && echo "FOUND" || echo "NOT_FOUND"
```

If NOT_FOUND, tell the researcher:
> "Candlekeep is required — it's your cloud document library for source PDFs.
>
> Install it from: https://github.com/romiluz13/candlekeep
>
> Follow the README setup instructions, then let me know when `ck` is available in your terminal."

Wait for confirmation and re-check before continuing.

#### 2. MongoDB Agent Skills (MCP server)

Check if the MongoDB agent skills MCP server is configured:

```bash
# Check Claude MCP settings for mongodb-agent-skills
cat ~/.claude/settings.json 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    servers = d.get('mcpServers', {})
    # Look for mongodb-related MCP server
    found = any('mongo' in k.lower() for k in servers)
    print('FOUND' if found else 'NOT_FOUND')
except:
    print('NOT_FOUND')
"
```

If NOT_FOUND, also check project-level settings:

```bash
cat .mcp.json 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    servers = d.get('mcpServers', {})
    found = any('mongo' in k.lower() for k in servers)
    print('FOUND' if found else 'NOT_FOUND')
except:
    print('NOT_FOUND')
"
```

If still NOT_FOUND, tell the researcher:
> "The MongoDB Agent Skills MCP server is required for database-backed research operations.
>
> Set it up from: https://github.com/romiluz13/mongodb-agent-skills
>
> Follow the README to configure it as an MCP server in Claude, then let me know when it's ready."

Wait for confirmation and re-check before continuing.

#### 3. Hybrid-Search-RAG / Agentic-Search-Vectorless

```bash
curl -s --max-time 3 http://localhost:8000/health 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print('RUNNING')
except:
    print('NOT_RUNNING')
"
```

If NOT_RUNNING, tell the researcher:
> "The Hybrid-Search-RAG server (Agentic-Search-Vectorless) is required for semantic search and citation verification.
>
> Set it up from: https://github.com/romiluz13/Agentic-Search-Vectorless
>
> Follow the README to install and start the server, then let me know when it's running on port 8000."

Wait for confirmation and re-check before continuing.

### C. All prerequisites confirmed

Only after ALL three tools are confirmed working, tell the researcher:
> "All prerequisites are set up:
> - ✓ Candlekeep
> - ✓ MongoDB Agent Skills
> - ✓ Hybrid-Search-RAG
>
> Let's configure your profile!"

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

## Step 4: Research Sources in Candlekeep

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

Then sync each document to the search index:

```bash
curl -s http://localhost:8000/v1/status | python3 -c "import sys,json; d=json.load(sys.stdin); print('RAG ready' if d.get('initialized') else 'RAG not ready')"
```

If RAG is ready, for each document get its full text and ingest it:

```bash
# For each document ID from ck items list:
ck items get DOCUMENT_ID | curl -s -X POST http://localhost:8000/v1/ingest \
  -H "Content-Type: application/json" \
  -d "{\"documents\": [$(python3 -c \"import sys,json; print(json.dumps(sys.stdin.read()))\" <<<$(ck items get DOCUMENT_ID))], \"ids\": [\"DOCUMENT_ID\"]}"
```

Track the sync in Cognetivy:
```bash
cognetivy run start --input /tmp/aw-init-input.json
```

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
- `sources` — the minimal metadata array built in Step 4 (id, title, type only — **never** raw Candlekeep JSON)
- `createdAt` / `updatedAt` — current ISO timestamp

---

## Confirmation

Summarize:
> "You're all set! Here's your profile:
>
> - **Field**: [field]
> - **Citation style**: [style]
> - **Writing style**: [2-3 sentence summary of fingerprint]
> - **Sources indexed**: [count] documents
>
> Run `/academic-writer` anytime to start writing an article."
