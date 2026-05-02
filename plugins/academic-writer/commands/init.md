---
description: First-time setup for the Academic Writer. Configures researcher profile, analyzes writing style from past articles, and indexes research sources.
allowed-tools: [Bash, Read, Write, Glob, Grep, AskUserQuestion]
---

# Auto-generated from skills/init/SKILL.md


# Academic Writer — Initialization Wizard

Personalized onboarding that creates your researcher profile, detects available integrations, analyzes your writing style, and indexes your research sources.

## The Five Phases

| Phase | What | Output |
|-------|------|--------|
| 0. Preflight | Create folders, detect existing profile | Workspace ready |
| 1. Integrations | Auto-detect tools, let you choose | `tools` config |
| 2. Profile | Field, language, citation style | Core profile |
| 3. Style Analysis | Read past articles, build fingerprint | `styleFingerprint` + `articleStructure` |
| 4. Sources | Index Candlekeep library | `sources` array |


## Phase 0: Preflight

Run silently before saying anything:

```bash
mkdir -p past-articles .academic-helper .cognetivy/runs .cognetivy/events
```

Migrate any legacy profile from `.academic-writer/profile.json` → `.academic-helper/profile.md`:

```bash
python3 << 'PYTHON'
import os, json
from datetime import datetime

old_path = '.academic-writer/profile.json'
new_path = '.academic-helper/profile.md'
if os.path.exists(old_path) and not os.path.exists(new_path):
    with open(old_path) as f:
        p = json.load(f)
    scalar_keys = ['fieldOfStudy', 'citationStyle', 'targetLanguage', 'updatedAt', 'createdAt']
    list_keys = ['abstractLanguages', 'analyzedArticles']
    json_sections = [
        ('tools', 'Tools'), ('outputFormatPreferences', 'Output Format Preferences'),
        ('styleFingerprint', 'Style Fingerprint'), ('articleStructure', 'Article Structure'),
        ('sources', 'Sources'),
    ]
    lines = ['# Academic Writer Profile', '', '---']
    for k in scalar_keys:
        if k in p and p[k] is not None:
            lines.append(f'{k}: {p[k]}')
    for k in list_keys:
        v = p.get(k) or []
        if not v:
            lines.append(f'{k}: []')
        else:
            lines.append(f'{k}:')
            for item in v:
                lines.append(f'  - {item}')
    lines.append('---')
    lines.append('')
    for k, heading in json_sections:
        if k in p and p[k] is not None:
            lines.extend([f'## {heading}', '', '```json',
                          json.dumps(p[k], indent=2, ensure_ascii=False), '```', ''])
    os.makedirs('.academic-helper', exist_ok=True)
    with open(new_path, 'w') as f:
        f.write('\n'.join(lines))
    print(f"Migrated profile to {new_path}")
PYTHON
```

Check for existing profile:

```bash
cat .academic-helper/profile.md 2>/dev/null && echo "EXISTS" || echo "NOT_FOUND"
```

**If EXISTS**: Use `AskUserQuestion`:

```python
AskUserQuestion(questions=[{
  "question": "You already have an Academic Writer profile. What would you like to do?",
  "header": "Existing profile detected",
  "options": [
    {
      "label": "Update my profile",
      "description": "Keep existing data, modify selected fields only.",
      "markdown": "```\nUpdate Mode\n───────────\n✓ Field of study preserved\n✓ Style fingerprint preserved\n✓ Sources preserved\n→ Re-run only the steps you choose\n```"
    },
    {
      "label": "Start fresh",
      "description": "Delete the current profile and rebuild from scratch.",
      "markdown": "```\nFresh Start\n───────────\n⚠ Existing profile will be replaced\n⚠ Style fingerprint will be cleared\n⚠ Sources will be cleared\n→ Walk through all 4 phases again\n```"
    }
  ],
  "multiSelect": false
}])
```

If **Update**, ask which phases to re-run (multiSelect: true) with options: "Integrations", "Profile (field/language/citation)", "Style Analysis", "Sources". Run only selected phases, then save.

Then greet the user:
> "Welcome to Academic Writer! I'll walk you through setup in a few steps.
>
> Your workspace folders are ready:
> - **`past-articles/`** — drop 5–10 of your published papers here (PDF or DOCX) so I can learn your writing style
> - `.academic-helper/` — your profile (auto-managed)
>
> Let's start."


## Phase 1: Integration Detection

Run ALL detection commands in **one parallel batch**:

```python
# PARALLEL — launch all at once
Bash(command="command -v ck >/dev/null 2>&1 && echo 'DETECTED' || echo 'NOT_DETECTED'")
Bash(command="curl -s --max-time 3 http://localhost:8000/health 2>/dev/null && echo 'DETECTED' || echo 'NOT_DETECTED'")
Bash(command="command -v cognetivy >/dev/null 2>&1 && echo 'DETECTED' || echo 'NOT_DETECTED'")
Bash(command="command -v nlm >/dev/null 2>&1 && nlm login --check 2>/dev/null && echo 'DETECTED' || echo 'NOT_DETECTED'")
```

**Vectorless port fallback**: if port 8000 returns `NOT_DETECTED`, ask:

```python
AskUserQuestion(questions=[{
  "question": "Agentic-Search-Vectorless didn't respond on port 8000. What port is it running on?",
  "header": "Vectorless port",
  "options": [
    {"label": "Skip for now", "description": "You can enable it later with /academic-writer:update-tools."}
  ],
  "multiSelect": false
}])
```

If the researcher provides a port number, retry `curl http://localhost:<PORT>/health`. Save the port to `tools.agentic-search-vectorless.port`.

### Present Results

```python
AskUserQuestion(questions=[{
  "question": "Here are the tools I found. Which would you like to enable?",
  "header": "Integration setup",
  "options": [
    {
      "label": "Candlekeep",
      "description": "✓ Detected  (or ✗ Not found — install from github.com/romiluz13/candlekeep)",
      "markdown": "```\nCandlekeep\n──────────\nType:    CLI (ck)\nWhat:    Cloud document library\nBest for: Storing and searching your source PDFs\nStatus:  ✓ Detected\n```"
    },
    {
      "label": "Agentic-Search-Vectorless",
      "description": "✓ Running on port 8000  (or ✗ Not running)",
      "markdown": "```\nAgentic-Search-Vectorless\n─────────────────────────\nType:    Local HTTP service\nWhat:    Fast semantic search for citations\nBest for: Finding exact page numbers and passages\nStatus:  ✓ Running on :8000\n```"
    },
    {
      "label": "Cognetivy",
      "description": "✓ Detected  (or ✗ Not found — run: npm install -g cognetivy)",
      "markdown": "```\nCognetivy\n─────────\nType:    CLI\nWhat:    Workflow tracking and audit trail\nBest for: Logging every pipeline step for review\nStatus:  ✓ Detected\n\nSetup (if not installed):\n  npm install -g cognetivy\n  timeout 5 cognetivy init --workspace-only\n```"
    },
    {
      "label": "NotebookLM",
      "description": "✓ Detected  (or ✗ Not found — run: npm install -g notebooklm-mcp-cli)",
      "markdown": "```\nNotebookLM\n──────────\nType:    MCP server (nlm CLI)\nWhat:    AI-powered source Q&A, audio overviews,\n         study guides, research discovery\nBest for: Querying indexed sources with AI,\n          generating audio summaries\nStatus:  ✓ Detected\n\nSetup (if not installed):\n  npm install -g notebooklm-mcp-cli\n  nlm login\n```"
    }
  ],
  "multiSelect": true
}])
```

**Rules:**
- Pre-check options that were detected.
- If a tool is not detected and the researcher selects it, show the setup URL and walk them through installation. Re-run detection after they confirm, before proceeding.
- Store final selection as the `tools` object (used in Phase 4).


## Phase 2: Researcher Profile

### Step 1 of 4 — Field of Study

```python
AskUserQuestion(questions=[{
  "question": "What is your field of study and area of specialization?",
  "header": "Step 1 of 4 — Field of Study",
  "options": []
}])
```

Show examples below the question:
> "The more specific, the better. Examples:
> - *Early Modern Jewish Philosophy*
> - *Talmudic Literature and Rabbinic Thought*
> - *Medieval Hebrew Poetry*
> - *Biblical Studies — Pentateuch*"

Record the free-text answer as `fieldOfStudy`.


### Step 2 of 4 — Article Language

```python
AskUserQuestion(questions=[{
  "question": "What language will you write your articles in?",
  "header": "Step 2 of 4 — Article Language",
  "options": [
    {
      "label": "Hebrew",
      "description": "Right-to-left, David font, inline-parenthetical citations recommended.",
      "markdown": "```\nHebrew Mode\n───────────\nDirection:  RTL\nFont:       David 11pt\nCitations:  (מחבר, כותרת, עמ' N) in running text\nPurity:     Foreign terms must be transliterated\n```"
    },
    {
      "label": "English",
      "description": "Left-to-right, Times New Roman, Chicago/MLA/APA supported.",
      "markdown": "```\nEnglish Mode\n────────────\nDirection:  LTR\nFont:       Times New Roman 12pt\nCitations:  Chicago, MLA, or APA\n```"
    },
    {
      "label": "Other",
      "description": "You'll specify the language name.",
      "markdown": "```\nOther Language\n──────────────\n→ You'll type the language name\n→ RTL/LTR detected from language\n→ Citation style: your choice\n```"
    }
  ],
  "multiSelect": false
}])
```

Store as `targetLanguage`. If "Other", ask for the language name with a follow-up `AskUserQuestion`.


### Step 3 of 4 — Citation Style

```python
AskUserQuestion(questions=[{
  "question": "Which citation style do you use in your academic work?",
  "header": "Step 3 of 4 — Citation Style",
  "options": [
    {
      "label": "Inline Parenthetical (Recommended for Hebrew)",
      "description": "(Author, Title, Page) in running text — no footnotes required.",
      "markdown": "```\nInline Parenthetical\n────────────────────\nExample:\n  כפי שטוען לוי (לוי, משנת הנפש, עמ' 42), הרעיון\n  המרכזי הוא...\n\nWhen to use:\n  ✓ Hebrew articles\n  ✓ Short citation format\n  ✓ Dense citation density\n```"
    },
    {
      "label": "Chicago / Turabian",
      "description": "Footnotes with full bibliography — most common in English Humanities.",
      "markdown": "```\nChicago / Turabian\n──────────────────\nExample footnote:\n  ¹ Levy, The Soul's Teaching, 42.\n\nWhen to use:\n  ✓ English Humanities articles\n  ✓ History, Philosophy, Literature\n  ✓ Requires bibliography section\n```"
    },
    {
      "label": "MLA",
      "description": "Parenthetical with Works Cited page.",
      "markdown": "```\nMLA\n───\nExample: (Levy 42)\n\nWhen to use:\n  ✓ Literature and language studies\n  ✓ Humanities with Works Cited\n```"
    },
    {
      "label": "APA",
      "description": "(Author, Year) style — more common in social sciences.",
      "markdown": "```\nAPA\n───\nExample: (Levy, 2019, p. 42)\n\nWhen to use:\n  ✓ Social sciences\n  ✓ Psychology, Education, Linguistics\n```"
    }
  ],
  "multiSelect": false
}])
```

Map selection: Inline → `inline-parenthetical`, Chicago → `chicago`, MLA → `mla`, APA → `apa`.


### Step 3b of 4 — Abstract Languages

```python
AskUserQuestion(questions=[{
  "question": "Do your articles need abstracts? Some journals require dual-language abstracts.",
  "header": "Abstract Languages",
  "options": [
    {
      "label": "Primary language only",
      "description": "Abstract in the article's language only.",
      "markdown": "```\nSingle Abstract\n───────────────\nAbstract in: [targetLanguage]\nCommon for: Most journals\n```"
    },
    {
      "label": "Hebrew + English",
      "description": "Dual-language abstracts — common for Israeli journals.",
      "markdown": "```\nDual Abstract\n─────────────\nAbstracts in: Hebrew + English\nCommon for: Israeli journals,\n            academic theses\n```"
    },
    {
      "label": "No abstract needed",
      "description": "Skip abstract generation.",
      "markdown": "```\nNo Abstract\n───────────\nAbstracts will not be generated.\nYou can enable later with\n/academic-writer:init (Update)\n```"
    }
  ],
  "multiSelect": false
}])
```

Store as `abstractLanguages` array:
- Primary only → `["Hebrew"]` (or whatever `targetLanguage` is)
- Hebrew + English → `["Hebrew", "English"]`
- No abstract → `[]`


### Step 4 of 4 — Writing Style

```python
AskUserQuestion(questions=[{
  "question": "To write articles that sound like you, I need to analyze your past work. Have you added papers to the past-articles/ folder?",
  "header": "Step 4 of 4 — Writing Style",
  "options": [
    {
      "label": "Yes, my papers are ready",
      "description": "Analyze them now to extract your writing fingerprint.",
      "markdown": "```\nStyle Analysis\n──────────────\n→ Reads PDF and DOCX files in past-articles/\n→ Analyzes 25 style dimensions:\n   sentence length, structure, vocabulary,\n   paragraph patterns, transitions, citations,\n   rhetorical moves, tone, intro/conclusion style\n→ Shows you the fingerprint before saving\n→ You can correct anything before it's stored\n```"
    },
    {
      "label": "Skip for now",
      "description": "Profile will be saved without a style fingerprint. Articles will use generic academic style.",
      "markdown": "```\nSkip Style Analysis\n───────────────────\n⚠ Articles won't match your voice yet\n→ Add papers to past-articles/ anytime\n→ Re-run: /academic-writer:init\n   (choose 'Update' → 'Style Analysis')\n```"
    }
  ],
  "multiSelect": false
}])
```

**If "Yes, my papers are ready"**, run:

```bash
ls past-articles/
```

**Step 1: Computational extraction** — Run the metrics extraction script to get hard numbers.

First fetch the **shared Hebrew baseline** from CandleKeep (book *Hebrew Linguistic Reference*, mirrored on GitHub at [yodem/hebrew-linguistics-data](https://github.com/yodem/hebrew-linguistics-data); the same book is read by the `hebrew-book-producer` plugin so both share one source of truth):

```bash
mkdir -p .ctx
ck items get cmomjonvy0fdmk30zwef79c48 > .ctx/hebrew-linguistic-reference.md
```

Then run the extractor:

```bash
python3 plugins/academic-writer/scripts/extract-style-metrics.py \
  --input past-articles/ \
  --aggregate \
  --baseline .ctx/hebrew-linguistic-reference.md \
  --contrastive \
  --json \
  --output /tmp/style-metrics.json
```

The extractor reads the baseline JSON code block embedded in the `08-style-fingerprint-baseline` chapter of the cached markdown, so there is no separate JSON file in the plugin's `references/` folder.

Read the results:
```bash
cat /tmp/style-metrics.json
```

This gives you 30+ numerical metrics (sentence length, passive voice, transitions, etc.) and contrastive scores showing what's distinctive about this researcher vs. baseline academic Hebrew.

**Step 2: Text extraction for qualitative analysis** — For each file, extract text:
- PDF: `python3 -c "import sys; import pdfplumber; [print(p.extract_text()) for p in pdfplumber.open(sys.argv[1]).pages]" past-articles/FILENAME 2>/dev/null || strings past-articles/FILENAME | head -500`
- DOCX: `python3 -c "import docx; d=docx.Document('past-articles/FILENAME'); [print(p.text) for p in d.paragraphs]" 2>/dev/null`

**Step 3: Qualitative analysis** — Read the text and computational metrics. Analyze across the qualitative dimensions (C–I below) that the script cannot compute: paragraph formula, tone, rhetorical patterns, templates, representative excerpts.

Show the combined fingerprint summary (computational + qualitative) and confirm before saving:

```python
AskUserQuestion(questions=[{
  "question": "Here's the writing fingerprint I extracted. Is this accurate?",
  "header": "Style fingerprint review",
  "options": [
    {"label": "Looks good — save it", "description": "Profile will be saved with this fingerprint."},
    {"label": "I'd like to adjust some things", "description": "Tell me what to change and I'll update before saving."}
  ],
  "multiSelect": false
}])
```

### 25-Dimension Style Analysis

#### A. Sentence-Level
1. Average sentence length (mean + range in words)
2. Sentence structure variety (% complex/compound/simple)
3. Common sentence openers (patterns)
4. Passive voice frequency + examples

#### B. Vocabulary & Register
5. Vocabulary complexity (simple/moderate/complex/highly-complex)
6. Academic register level + first vs. impersonal person
7. Field-specific jargon (list + how introduced)
8. Hebrew academic conventions (if applicable)

#### C. Paragraph & Argument Structure
9. Paragraph structure pattern (detailed step-by-step)
10. Average paragraph length (words + range)
11. Argument progression (inductive/deductive/other)
12. How evidence is introduced
13. How evidence is analyzed after quoting

#### D. Tone & Voice
14. Tone descriptors (5–7 adjectives)
15. Authorial stance + common hedging/asserting phrases
16. Engagement with other scholars

#### E. Transitions & Flow
17. Preferred transition phrases (grouped by function: addition, contrast, causation, exemplification, conclusion)
18. Section-level transition patterns

#### F. Citation Style & Density
19. Citation density (sparse/moderate/dense + footnotes/paragraph average)
20. Citation integration style
21. Quote length preference

#### G. Rhetorical Patterns
22. Rhetorical patterns (3–5 most common)
23. Opening moves (how they start articles)
24. Closing moves (how they end articles)

#### H. Representative Excerpts
25. 5 verbatim excerpts (2–3 sentences each) showing: analytical move, argumentative voice, evidence handling, transition style, most distinctive trait

#### I. Article Structure Analysis
26. Typical section inventory (in order)
27. Introduction conventions (opening pattern, elements, element order, roadmap?, typical length)
28. Conclusion conventions (opening pattern, elements, restatement?, implications?, closing pattern, typical length)
29. Paragraph formula (topic sentence style, evidence presentation, analysis type, closing move, full sequence)
30. Section transition patterns (bridging style, transitional paragraphs?, explicit signposting?)


## Phase 3: Research Sources

**If Candlekeep is enabled:**

```python
AskUserQuestion(questions=[{
  "question": "Let's index your research library. Have you added sources to Candlekeep yet?",
  "header": "Research sources",
  "options": [
    {
      "label": "Yes, index my sources now",
      "description": "I'll enrich and index everything in your Candlekeep library.",
      "markdown": "```\nSource Indexing\n───────────────\n→ Lists all items in your library\n→ Runs ck items enrich on each\n   (extracts title, author, TOC)\n→ Saves minimal metadata to profile\n   (id, title, type only)\n```"
    },
    {
      "label": "Skip — I'll add sources later",
      "description": "Run /academic-writer:init again (choose Update → Sources) after adding items.",
      "markdown": "```\nSkip Sources\n────────────\n⚠ Articles won't have source metadata yet\n→ Add sources with: ck items add file.pdf\n→ Then re-run this step\n```"
    }
  ],
  "multiSelect": false
}])
```

If **"Yes"**: list and enrich all items:

```bash
ck items list --json
```

For each item ID:
```bash
ck items enrich ITEM_ID
```

Tell the researcher: "Enriching your sources — extracting titles, authors, and table of contents from each document. This may take a moment..."

After enrichment, re-list and build the sources array (id + title + type only — never raw JSON).

**If Candlekeep is NOT enabled**: set sources to `[]`.


## Phase 4: Save Profile + Register Workflows

Use the Write tool to save `.academic-helper/profile.md`:

```markdown
# Academic Writer Profile

fieldOfStudy: FIELD_HERE
citationStyle: inline-parenthetical
targetLanguage: Hebrew
abstractLanguages:
  - Hebrew
analyzedArticles: []
createdAt: ISO_TIMESTAMP
updatedAt: ISO_TIMESTAMP

## Tools

```json
{
  "candlekeep": { "enabled": true },
  "agentic-search-vectorless": { "enabled": true, "port": 8000 },
  "cognetivy": { "enabled": true },
  "notebooklm": { "enabled": false }
}
` ` `

## Output Format Preferences

```json
{
  "font": "David",
  "bodySize": 11,
  "titleSize": 16,
  "headingSize": 13,
  "lineSpacing": 1.5,
  "marginInches": 1.0,
  "alignment": "justify",
  "rtl": true
}
` ` `

## Style Fingerprint

```json
{ ... full 25-dimension fingerprint object ... }
` ` `

## Article Structure

```json
{ ... article structure object ... }
` ` `

## Sources

```json
[]
` ` `
```

(Replace ` ` ` with actual backtick triplets when writing the file.)

**If Cognetivy is enabled**, register all workflows:

```bash
cognetivy workflow set --file plugins/academic-writer/workflows/wf_write_article.json
cognetivy workflow set --file plugins/academic-writer/workflows/wf_edit_article.json
cognetivy workflow set --file plugins/academic-writer/workflows/wf_edit_section.json
cognetivy workflow set --file plugins/academic-writer/workflows/wf_research.json
cognetivy workflow set --file plugins/academic-writer/workflows/wf_setup.json
cognetivy collection-schema set --file plugins/academic-writer/workflows/collection-schemas.json
```


## Completion

```python
AskUserQuestion(questions=[{
  "question": "Setup is complete. What would you like to do next?",
  "header": "You're all set!",
  "options": [
    {
      "label": "Write my first article",
      "description": "Launch /academic-writer:write to start writing.",
      "markdown": "```\nWrite Article\n─────────────\n→ /academic-writer:write\n→ Conversational pipeline:\n   subject → sources → thesis\n   → outline → write → .docx\n```"
    },
    {
      "label": "Check system health",
      "description": "Run /academic-writer:health to verify everything is working.",
      "markdown": "```\nHealth Check\n────────────\n→ /academic-writer:health\n→ Verifies: profile, tools,\n   agents, Cognetivy, sources\n```"
    },
    {
      "label": "I'm done for now",
      "description": "Profile saved. Run /academic-writer:write anytime to start writing.",
      "markdown": "```\nProfile saved to:\n  .academic-helper/profile.md\n\nKey commands:\n  /academic-writer:write         ← write an article\n  /academic-writer:health  ← check everything\n  /academic-writer:update-tools ← change integrations\n```"
    }
  ],
  "multiSelect": false
}])
```

Show a summary table:

> | Setting | Value |
> |---------|-------|
> | Field | [field] |
> | Language | [language] |
> | Citation style | [style] |
> | Style fingerprint | ✓ Analyzed / — Skipped |
> | Sources indexed | [N] documents |
> | Tools enabled | [list] |
