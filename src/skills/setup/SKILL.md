---
name: setup
description: "First-time setup for Academic Writer — creates researcher profile, detects integrations, analyzes writing style from past articles"
user-invocable: true
allowedTools: [Bash, Read, Write, Glob, Grep, AskUserQuestion]
---

# Academic Writer Setup

Quick onboarding wizard. Creates the researcher profile, detects integrations, and optionally fingerprints writing style. For deeper initialization (full 25-dimension style analysis, source indexing), run `/academic-writer:init`.

## Phase 0: Preflight

Run silently before anything else:

```bash
mkdir -p past-articles .academic-writer .cognetivy/runs .cognetivy/events
```

If cognetivy is available, start a setup run:
```bash
echo '{"phase": "setup"}' > /tmp/aw-setup-input.json
cognetivy run start --input /tmp/aw-setup-input.json --name "Academic Writer Setup"
```
Capture the `run_id` for logging at each step.

Check for existing profile:
```bash
cat .academic-writer/profile.json 2>/dev/null && echo "EXISTS" || echo "NOT_FOUND"
```

If EXISTS, load and show current settings, then:

```python
AskUserQuestion(questions=[{
  "question": "A profile already exists. What would you like to do?",
  "header": "Existing profile detected",
  "options": [
    {
      "label": "Update existing profile",
      "description": "Keep existing data, modify only selected fields.",
      "markdown": "```\nUpdate Mode\n───────────\n✓ Existing settings preserved\n→ Only re-run steps you choose\n```"
    },
    {
      "label": "Start fresh",
      "description": "Delete and recreate from scratch.",
      "markdown": "```\nFresh Start\n───────────\n⚠ Current profile will be replaced\n→ Walk through all steps again\n```"
    }
  ],
  "multiSelect": false
}])
```

---

## Phase 1: Detect Integrations

Run ALL detection commands in **one parallel batch**:

```python
# PARALLEL
Bash(command="command -v ck >/dev/null 2>&1 && echo 'ck: DETECTED' || echo 'ck: NOT_FOUND'")
Bash(command="curl -s --max-time 3 http://localhost:8000/health 2>/dev/null && echo 'vectorless: RUNNING' || echo 'vectorless: NOT_RUNNING'")
Bash(command="command -v cognetivy >/dev/null 2>&1 && echo 'cognetivy: DETECTED' || echo 'cognetivy: NOT_FOUND'")
Bash(command="command -v nlm >/dev/null 2>&1 && nlm login --check 2>/dev/null && echo 'notebooklm: DETECTED' || echo 'notebooklm: NOT_FOUND'")
```

**If vectorless NOT_RUNNING on port 8000:**

```python
AskUserQuestion(questions=[{
  "question": "Agentic-Search-Vectorless didn't respond on port 8000. What port is it running on?",
  "header": "Vectorless port",
  "options": [
    {"label": "Skip — not running right now", "description": "You can enable it later with /academic-writer:update-tools."}
  ],
  "multiSelect": false
}])
```

Retry with the provided port; save to `tools.agentic-search-vectorless.port`.

MongoDB Agent Skills is auto-configured silently — do not show it to the user.

---

## Phase 2: Profile Setup

### Field of Study

```python
AskUserQuestion(questions=[{
  "question": "What is your field of study and area of specialization?",
  "header": "Step 1 — Field of Study",
  "options": []
}])
```

> "The more specific, the better. Examples: *Early Modern Jewish Philosophy*, *Talmudic Literature*, *Biblical Studies — Pentateuch*"

### Article Language

```python
AskUserQuestion(questions=[{
  "question": "What language will you write your articles in?",
  "header": "Step 2 — Article Language",
  "options": [
    {
      "label": "Hebrew",
      "description": "RTL, David font, inline-parenthetical citations.",
      "markdown": "```\nHebrew Mode\n───────────\nDirection:  RTL\nFont:       David 11pt\nCitations:  (מחבר, כותרת, עמ' N)\n```"
    },
    {
      "label": "English",
      "description": "LTR, Times New Roman, Chicago/MLA/APA.",
      "markdown": "```\nEnglish Mode\n────────────\nDirection:  LTR\nFont:       Times New Roman 12pt\n```"
    },
    {
      "label": "Other",
      "description": "You'll type the language name in the next prompt.",
      "markdown": "```\nOther\n─────\n→ Type the language name\n→ RTL/LTR auto-detected\n```"
    }
  ],
  "multiSelect": false
}])
```

### Citation Style

```python
AskUserQuestion(questions=[{
  "question": "Which citation style do you use?",
  "header": "Step 3 — Citation Style",
  "options": [
    {
      "label": "Inline Parenthetical (Recommended for Hebrew)",
      "description": "(Author, Title, Page) in running text.",
      "markdown": "```\nExample: (לוי, משנת הנפש, עמ' 42)\n```"
    },
    {
      "label": "Chicago / Turabian",
      "description": "Footnotes with full bibliography.",
      "markdown": "```\nExample footnote: ¹ Levy, Soul's Teaching, 42.\n```"
    },
    {
      "label": "MLA",
      "description": "Parenthetical with Works Cited.",
      "markdown": "```\nExample: (Levy 42)\n```"
    },
    {
      "label": "APA",
      "description": "(Author, Year) — more common in social sciences.",
      "markdown": "```\nExample: (Levy, 2019, p. 42)\n```"
    }
  ],
  "multiSelect": false
}])
```

### Tool Selection

```python
AskUserQuestion(questions=[{
  "question": "Which integrations would you like to enable?",
  "header": "Step 4 — Tools",
  "options": [
    {
      "label": "Candlekeep",
      "description": "✓ Detected  /  ✗ Not found",
      "markdown": "```\nCandlekeep\n──────────\nType:  CLI (ck)\nWhat:  Cloud document library\n```"
    },
    {
      "label": "Agentic-Search-Vectorless",
      "description": "✓ Running  /  ✗ Not running",
      "markdown": "```\nAgentic-Search-Vectorless\n─────────────────────────\nType:  Local HTTP service\nWhat:  Fast semantic citation search\n```"
    },
    {
      "label": "Cognetivy",
      "description": "✓ Detected  /  ✗ Not found",
      "markdown": "```\nCognetivy\n─────────\nType:  CLI\nWhat:  Workflow audit trail\n\nInstall: npm install -g cognetivy\nInit:    cognetivy init\n```"
    },
    {
      "label": "NotebookLM",
      "description": "✓ Detected  /  ✗ Not found",
      "markdown": "```\nNotebookLM\n──────────\nType:  MCP server (nlm CLI)\nWhat:  AI-powered source Q&A,\n       audio overviews, study guides\n\nInstall: npm install -g notebooklm-mcp-cli\nAuth:    nlm login\n```"
    }
  ],
  "multiSelect": true
}])
```

Pre-check tools that were detected. MongoDB Agent Skills is silently included always.

---

## Phase 3: Style Fingerprint (Optional)

Check for past articles:

```bash
ls past-articles/ 2>/dev/null | wc -l
```

```python
AskUserQuestion(questions=[{
  "question": "Found N papers in past-articles/. Analyze them for style fingerprinting?",
  "header": "Writing style (optional)",
  "options": [
    {
      "label": "Yes, analyze my writing style (Recommended)",
      "description": "Extracts your voice across 25 dimensions so articles sound like you.",
      "markdown": "```\nStyle Analysis\n──────────────\n→ Reads PDF and DOCX in past-articles/\n→ Analyzes 25 dimensions:\n   sentence patterns, vocabulary,\n   paragraph structure, transitions,\n   citation density, rhetorical moves\n→ Shows fingerprint before saving\n→ You can correct anything\n```"
    },
    {
      "label": "Skip for now",
      "description": "Articles will use generic academic style until you run this.",
      "markdown": "```\nSkip\n────\n⚠ No style fingerprint yet\n→ Add papers to past-articles/ anytime\n→ Re-run: /academic-writer:init\n```"
    }
  ],
  "multiSelect": false
}])
```

If no files found, show only the "Skip" option with instructions to add papers.

If "Yes": analyze across all 25 dimensions (sentence level, vocabulary, paragraph structure, tone, transitions, citation style, rhetorical patterns, representative excerpts, article structure). Show fingerprint summary and confirm before saving.

---

## Phase 4: Save Profile

Use the Write tool to create `.academic-writer/profile.json`:

```json
{
  "fieldOfStudy": "FIELD",
  "targetLanguage": "Hebrew",
  "citationStyle": "inline-parenthetical",
  "outputFormatPreferences": {
    "font": "David",
    "bodySize": 11,
    "titleSize": 16,
    "headingSize": 13,
    "lineSpacing": 1.5,
    "marginInches": 1.0,
    "alignment": "justify",
    "rtl": true
  },
  "styleFingerprint": null,
  "tools": {
    "candlekeep": { "enabled": true },
    "agentic-search-vectorless": { "enabled": true, "port": 8000 },
    "mongodb-agent-skills": { "enabled": true },
    "cognetivy": { "enabled": true },
    "notebooklm": { "enabled": false }
  },
  "sources": [],
  "createdAt": "ISO_TIMESTAMP",
  "updatedAt": "ISO_TIMESTAMP"
}
```

If Cognetivy is enabled, register workflows:

```bash
cognetivy workflow set --file plugins/academic-writer/workflows/wf_write_article.json
cognetivy workflow set --file plugins/academic-writer/workflows/wf_edit_article.json
cognetivy workflow set --file plugins/academic-writer/workflows/wf_edit_section.json
cognetivy workflow set --file plugins/academic-writer/workflows/wf_research.json
cognetivy workflow set --file plugins/academic-writer/workflows/wf_setup.json
cognetivy collection-schema set --file plugins/academic-writer/workflows/collection-schemas.json
```

Complete the Cognetivy run:
```bash
cognetivy run complete --run <run_id>
```

---

## Completion

```python
AskUserQuestion(questions=[{
  "question": "Setup complete. What would you like to do next?",
  "header": "You're all set!",
  "options": [
    {
      "label": "Write my first article → /academic-writer:write",
      "description": "Start the writing pipeline now.",
      "markdown": "```\n/academic-writer:write\n────────────────\nConversational pipeline:\nsubject → sources → thesis\n→ outline → write → .docx\n```"
    },
    {
      "label": "Run deeper initialization → /academic-writer:init",
      "description": "Full style analysis (25 dimensions) and source indexing.",
      "markdown": "```\n/academic-writer:init\n─────────────────────\n→ Deep 25-dimension fingerprint\n→ Article structure analysis\n→ Candlekeep source indexing\n```"
    },
    {
      "label": "Done for now",
      "description": "Profile saved. Run /academic-writer:write anytime.",
      "markdown": "```\nKey commands:\n  /academic-writer:write         ← write\n  /academic-writer:health  ← check\n  /academic-writer:update-tools ← change tools\n```"
    }
  ],
  "multiSelect": false
}])
```

Show summary table:

> | Setting | Value |
> |---------|-------|
> | Field | [field] |
> | Language | [language] |
> | Citation style | [style] |
> | Tools enabled | [list] |
> | Style fingerprint | ✓ Analyzed / — Skipped |
