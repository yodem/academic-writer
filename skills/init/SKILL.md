---
name: academic-writer-init
description: "First-time setup for the Academic Writer. Configures researcher profile, analyzes writing style from past articles, and indexes research sources."
user-invocable: true
---

# Academic Writer — Initialization

You are setting up a researcher's Academic Writer profile. Be warm, clear, and non-technical. Explain why each step matters.

## Step 0: Initialize Folders

Run this silently before saying anything to the user:

```bash
mkdir -p past-articles .academic-writer .cognetivy/runs .cognetivy/events
```

Then greet the user:
> "Welcome to Academic Writer setup! I'll walk you through 4 quick steps.
>
> I've created your workspace folders:
> - **`past-articles/`** — drop 5–10 of your published papers here (PDF or DOCX) so I can learn your writing style
> - `.academic-writer/` — your profile (auto-managed)
>
> Let's get started."

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

**2. Agentic-Search-Vectorless** (`agentic-search-vectorless`)
- *What it does:* Vectorless semantic search — fast relevance scoring without embeddings
- *Type:* Local service (HTTP) or local repo
- *Repo:* `../Agentic-Search-Vectorless/`
- *Detection:*
```bash
(ls ../Agentic-Search-Vectorless/src 2>/dev/null && echo "REPO_DETECTED") || echo "NOT_DETECTED"
```

- *What it does:* Deep semantic + keyword retrieval (BM25 + vector) for citation search and verification
- *Type:* Local service (HTTP) or local repo
- *Detection:*
```bash
```

**4. MongoDB Agent Skills** (`mongodb-agent-skills`)
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

**5. Cognetivy** (`cognetivy`)
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
> | 2 | Agentic-Search-Vectorless | ✓ Detected / ✗ Not found | Vectorless semantic search |
> | 4 | MongoDB Agent Skills | ✓ Detected / ✗ Not found | Database-backed research ops |
> | 5 | Cognetivy | ✓ Detected / ✗ Not found | Workflow audit trail |
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
    "agentic-search-vectorless": { "enabled": true, "path": "../Agentic-Search-Vectorless" },
    "mongodb-agent-skills": { "enabled": false },
    "cognetivy": { "enabled": true, "version": "detected" }
  }
}
```

Only include `"version": "detected"` for tools that were successfully detected. Omit the version key for disabled tools.

---

## Step 1: Field of Study

Ask:
> "**Step 1 of 4 — Field of Study**
> What is your field of study and area of specialization?
>
> The more specific, the better — for example, *'Early Modern Jewish Philosophy'* is more useful than *'Philosophy'*."

Record their answer.

---

## Step 1.5: Article Language

Present as a numbered menu:
> "**Step 2 of 4 — Article Language**
> What language will you write your articles in?
>
> 1. Hebrew
> 2. English
> 3. Other (you'll specify)
>
> Type a number:"

Store as `targetLanguage`. This is enforced throughout the pipeline — all agents write exclusively in this language, and the language purity check rejects any embedded foreign-language text in the body prose.

---

## Step 2: Citation Style

Present as a numbered menu:
> "**Step 3 of 4 — Citation Style**
> Which citation style do you use in your work?
>
> 1. Inline Parenthetical — `(Author, Title, Page)` in running text *(recommended for Hebrew)*
> 2. Chicago/Turabian — footnotes *(most common in English Humanities)*
> 3. MLA
> 4. APA
>
> Type a number (1–4):"

Map selection to value: 1 → `inline-parenthetical`, 2 → `chicago`, 3 → `mla`, 4 → `apa`

---

## Step 3: Past Articles for Style Analysis

Tell the researcher:
> "**Step 4 of 4 — Writing Style**
> I need to learn your writing style so articles I produce sound like *you*, not a generic AI.
>
> Place 5–10 of your published papers in the **`past-articles/`** folder I created for you (PDF or DOCX). These files are used only to analyze your style — never uploaded anywhere.
>
> Tell me when you've added your files."

Once they confirm, analyze their writing style by reading the files:

```bash
ls past-articles/
```

For each file, extract text:
- PDF: `python3 -c "import sys; import pdfplumber; [print(p.extract_text()) for p in pdfplumber.open(sys.argv[1]).pages]" past-articles/FILENAME 2>/dev/null || strings past-articles/FILENAME | head -500`
- DOCX: `python3 -c "import docx; d=docx.Document('past-articles/FILENAME'); [print(p.text) for p in d.paragraphs]" 2>/dev/null`

Analyze the combined text to create a **detailed Style Fingerprint**. This fingerprint is the single most important artifact in the profile — it is loaded and checked against **every paragraph** and the **entire article** during writing. Be thorough.

### A. Sentence-Level Analysis

1. **Average sentence length** — Count words per sentence across all articles. Give the mean and range (e.g., "22 words average, range 8–45").
2. **Sentence structure variety** — Does the writer favor simple/compound/complex sentences? What's the rough ratio? (e.g., "60% complex, 25% compound, 15% simple")
3. **Sentence openers** — What patterns do they use to start sentences? (e.g., "Often leads with subordinate clauses: 'Although X, Y...'", "Frequently uses participial phrases: 'Drawing on X, the author...'")
4. **Passive voice frequency** — rare / occasional / frequent. Give examples from their writing.

### B. Vocabulary & Register

5. **Vocabulary complexity** — simple / moderate / complex / highly-complex. Note any distinctive word choices or preferences.
6. **Academic register level** — How formal? Do they ever use informal constructions? Do they use first person ("I argue") or impersonal ("it can be argued")?
7. **Field-specific jargon** — List the specialized terms they use regularly and how they introduce them (with or without definition, in quotes, italicized, etc.)
8. **Hebrew academic conventions** (if applicable) — Note any Hebrew terms, transliteration style, use of Hebrew quotes, direction of Hebrew insertions in English text or vice versa.

### C. Paragraph & Argument Structure

9. **Paragraph structure pattern** — Describe in detail. (e.g., "topic sentence → evidence quote → close reading of quote → theoretical framing → forward link")
10. **Paragraph length** — Average word count per paragraph. Range.
11. **Argument progression** — How does the writer build arguments across paragraphs? (e.g., "inductive: examples first, then generalization" or "deductive: claim, then evidence")
12. **How they introduce evidence** — Do they quote extensively, paraphrase, or summarize? How do they set up quotes? (e.g., "As X argues, '...'" vs. "X's claim that '...' reveals...")
13. **How they analyze evidence** — What does the writer do AFTER quoting? (e.g., "always follows quotes with close reading", "draws connection to thesis within same paragraph")

### D. Tone & Voice

14. **Tone descriptors** — 5–7 adjectives that capture their voice. (e.g., "measured, precise, cautiously argumentative, occasionally polemical, deeply engaged")
15. **Authorial stance** — How present is the author? Do they assert confidently ("This demonstrates...") or hedge ("This appears to suggest...")? List their common hedging/asserting phrases.
16. **Engagement with other scholars** — How do they treat opposing views? (e.g., "generous restatement before critique", "direct refutation", "strategic concession then pivot")

### E. Transitions & Flow

17. **Preferred transition phrases** — List the 10–15 most frequent transitions. Group by function:
    - Addition: (e.g., "moreover", "furthermore", "יתרה מכך")
    - Contrast: (e.g., "however", "nevertheless", "אולם")
    - Causation: (e.g., "consequently", "thus", "לפיכך")
    - Exemplification: (e.g., "for instance", "notably", "למשל")
    - Conclusion: (e.g., "ultimately", "in sum", "לסיכום")
18. **Section-level transitions** — How do they bridge between major sections? (e.g., "ends section with a question that the next section answers", "uses a transitional paragraph")

### F. Citation Style & Density

19. **Citation density** — sparse / moderate / dense. How many footnotes per paragraph on average?
20. **Citation integration** — How are citations woven into prose? (e.g., "citations appear mid-sentence as evidence", "citations cluster at end of analytical passages")
21. **Quote length preference** — Does the writer prefer short embedded quotes, block quotes, or paraphrases?

### G. Rhetorical Patterns

22. **Rhetorical patterns** — List the 3–5 most common. (e.g., "close reading", "comparative analysis", "historicization", "thesis-antithesis-synthesis", "genealogical tracing")
23. **Opening moves** — How do they typically open articles? (e.g., "starts with an anecdote", "opens with a puzzle or contradiction", "begins with historiographic review")
24. **Closing moves** — How do they typically close? (e.g., "returns to opening image", "widens implications", "poses open question")

### H. Representative Excerpts

25. **5 representative excerpts** (2–3 sentences each) that best capture the writer's voice. Choose excerpts that demonstrate:
    - Their typical analytical move
    - Their strongest argumentative voice
    - Their handling of evidence
    - Their transition style
    - Their most distinctive stylistic trait

**Show the full fingerprint to the researcher** and ask for corrections before saving:
> "Here's the writing style I extracted from your articles. Please review — is this accurate? Anything you'd like me to adjust?"

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

Once confirmed, list them and **enrich all items**:

```bash
ck items list --json
```

**Run `ck items enrich` on every item** — this extracts title, author, description, and table of contents from each document so the writing pipeline can use accurate metadata:

```bash
# For each item ID returned above:
ck items enrich ITEM_ID
```

Tell the researcher while enrichment runs:
> "Enriching your sources — extracting titles, authors, and table of contents from each document. This may take a moment..."

After enrichment, re-list to get updated metadata:

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
  "styleFingerprint": {
    "sentenceLevel": {
      "averageLength": "22 words, range 8-45",
      "structureVariety": "60% complex, 25% compound, 15% simple",
      "commonOpeners": ["subordinate clause", "participial phrase"],
      "passiveVoice": "occasional",
      "passiveVoiceExamples": []
    },
    "vocabularyAndRegister": {
      "complexity": "complex",
      "registerLevel": "formal, impersonal (avoids first person)",
      "fieldJargon": [],
      "hebrewConventions": ""
    },
    "paragraphStructure": {
      "pattern": "topic sentence → evidence quote → close reading → theoretical framing → forward link",
      "averageLength": "150 words, range 100-220",
      "argumentProgression": "deductive",
      "evidenceIntroduction": "sets up with 'As X argues' then quotes",
      "evidenceAnalysis": "close reading immediately after quote"
    },
    "toneAndVoice": {
      "descriptors": [],
      "authorStance": "cautiously assertive with hedging",
      "commonHedges": [],
      "commonAssertions": [],
      "engagementWithScholars": "generous restatement before critique"
    },
    "transitions": {
      "preferred": {
        "addition": [],
        "contrast": [],
        "causation": [],
        "exemplification": [],
        "conclusion": []
      },
      "sectionBridging": "ends with question answered by next section"
    },
    "citations": {
      "density": "moderate",
      "footnotesPerParagraph": 2,
      "integrationStyle": "mid-sentence as evidence",
      "quoteLengthPreference": "short embedded quotes"
    },
    "rhetoricalPatterns": {
      "common": [],
      "openingMoves": "",
      "closingMoves": ""
    },
    "representativeExcerpts": []
  },
  "tools": {
    "candlekeep": { "enabled": true, "version": "detected" },
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
- `targetLanguage` — from Step 1.5
- `citationStyle` — from Step 2 (`inline-parenthetical` / `chicago` / `mla` / `apa`)
- `outputFormatPreferences` — font, size, spacing settings (ask the researcher if they want to customize; otherwise use defaults: David, 11pt, 1.5 spacing, 1" margins, justified, RTL for Hebrew)
- `styleFingerprint` — all values from Step 3 analysis. **`representativeExcerpts` must contain actual verbatim text passages from the researcher's past work** (2–3 sentences each), not just descriptions — these are the style targets used by every section-writer.
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
