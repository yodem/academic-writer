---
name: academic-writer-init
description: "First-time setup for the Academic Writer. Configures researcher profile, analyzes writing style from past articles, and indexes research sources."
user-invocable: true
---

# Academic Writer — Initialization

You are setting up a researcher's Academic Writer profile. Be warm, clear, and non-technical.

## Step 0: Create Folders (silent)

Run this before saying anything:

```bash
mkdir -p past-articles .academic-writer .cognetivy/runs .cognetivy/events
cat .academic-writer/profile.json 2>/dev/null && echo "EXISTS" || echo "NOT_FOUND"
```

If profile EXISTS, ask: "You already have a profile. Would you like to update it or start fresh?"

Then greet the user:
> "Welcome to Academic Writer setup! I'll walk you through 5 quick steps.
>
> I've created your workspace folders:
> - **`past-articles/`** — drop 5–10 of your published papers here (PDF or DOCX) so I can learn your writing style
> - `.academic-writer/` — your profile (auto-managed)
>
> Let's get started."

---

## Step 1 of 5: Field of Study

Ask:
> "**Step 1 of 5 — Field of Study**
> What is your field of study and area of specialization?
>
> The more specific the better — for example, *'Early Modern Jewish Philosophy'* is more useful than *'Philosophy'*."

Record their answer.

---

## Step 2 of 5: Article Language

Present as a numbered menu:
> "**Step 2 of 5 — Article Language**
> What language will you write your articles in?
>
> 1. Hebrew
> 2. English
> 3. Other (you'll specify)
>
> Type a number:"

Store as `targetLanguage`. All agents write exclusively in this language — foreign terms must be transliterated or footnoted, never inline.

---

## Step 3 of 5: Citation Style

Present as a numbered menu:
> "**Step 3 of 5 — Citation Style**
> Which citation style do you use in your work?
>
> 1. Inline Parenthetical — `(Author, Title, Page)` in running text *(recommended for Hebrew)*
> 2. Chicago/Turabian — footnotes *(most common in English Humanities)*
> 3. MLA
> 4. APA
>
> Type a number (1–4):"

Map selection: 1 → `inline-parenthetical`, 2 → `chicago`, 3 → `mla`, 4 → `apa`

---

## Step 4 of 5: Data Services

Run all detection commands in parallel:

```bash
# 1. Candlekeep
command -v ck >/dev/null 2>&1 && echo "CK_DETECTED" || echo "CK_NOT_DETECTED"

# 2. Agentic-Search-Vectorless (local repo)
ls ../Agentic-Search-Vectorless/src 2>/dev/null && echo "VECTORLESS_DETECTED" || echo "VECTORLESS_NOT_DETECTED"


# 4. Cognetivy
command -v cognetivy >/dev/null 2>&1 && echo "COGNETIVY_DETECTED" || echo "COGNETIVY_NOT_DETECTED"
```

Present results as a numbered interactive menu:
> "**Step 4 of 5 — Data Services**
> I've detected which research tools are available. Toggle on/off with numbers:
>
> | # | Tool | Status | What it does |
> |---|------|--------|-------------|
> | 1 | Candlekeep | ✓/✗ | Cloud document library for source PDFs |
> | 2 | Agentic-Search-Vectorless | ✓/✗ | Fast vectorless semantic search |
> | 4 | Cognetivy | ✓/✗ | Workflow audit trail |
>
> Type numbers to enable/disable, or press Enter to accept. Type 'all' to enable everything detected."

**Rules:**
- User can enable any combination. No tool is required.
- Store the final selection in `tools` for the profile.

Store results:
```json
{
  "candlekeep": { "enabled": true },
  "agentic-search-vectorless": { "enabled": true, "path": "../Agentic-Search-Vectorless" },
  "cognetivy": { "enabled": false }
}
```

---

## Step 5 of 5: Writing Style

Tell the researcher:
> "**Step 5 of 5 — Writing Style**
> I need to learn your writing style so articles I produce sound like *you*, not a generic AI.
>
> Place 5–10 of your published papers in the **`past-articles/`** folder I created for you (PDF or DOCX). These files are used only to analyze your style — never uploaded anywhere.
>
> Tell me when you've added your files."

Once they confirm:

```bash
ls past-articles/
```

For each file, extract text:
- PDF: `python3 -c "import sys; import pdfplumber; [print(p.extract_text()) for p in pdfplumber.open(sys.argv[1]).pages]" past-articles/FILENAME 2>/dev/null || strings past-articles/FILENAME | head -500`
- DOCX: `python3 -c "import docx; d=docx.Document('past-articles/FILENAME'); [print(p.text) for p in d.paragraphs]" 2>/dev/null`

Analyze the combined text to produce a **Style Fingerprint**. Extract:
1. Average sentence length (words), range
2. Sentence structure variety (% complex / compound / simple)
3. Common sentence openers
4. Passive voice frequency + examples
5. Vocabulary complexity and register (formal/informal, first person or not)
6. Field-specific jargon and how it's introduced
7. Paragraph structure pattern (e.g., "topic sentence → evidence → close reading → forward link")
8. Average paragraph length (words), range
9. Argument progression style (inductive or deductive)
10. How evidence is introduced and analyzed
11. Tone descriptors (5–7 adjectives)
12. Common hedging and asserting phrases
13. Preferred transitions grouped by function (addition / contrast / causation / exemplification / conclusion)
14. Citation density and integration style
15. Rhetorical patterns (close reading, comparative analysis, etc.)
16. Opening and closing moves
17. 5 verbatim representative excerpts (2–3 sentences each) capturing: analytical voice, argument style, evidence handling, transitions, most distinctive trait

Show the fingerprint to the researcher:
> "Here's the writing style I extracted from your articles. Does this look accurate? Anything to adjust?"

---

## Save Profile

Use the Write tool to create `.academic-writer/profile.json`:

```json
{
  "fieldOfStudy": "FIELD_FROM_STEP_1",
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
      "averageLength": "",
      "structureVariety": "",
      "commonOpeners": [],
      "passiveVoice": "",
      "passiveVoiceExamples": []
    },
    "vocabularyAndRegister": {
      "complexity": "",
      "registerLevel": "",
      "fieldJargon": [],
      "hebrewConventions": ""
    },
    "paragraphStructure": {
      "pattern": "",
      "averageLength": "",
      "argumentProgression": "",
      "evidenceIntroduction": "",
      "evidenceAnalysis": ""
    },
    "toneAndVoice": {
      "descriptors": [],
      "authorStance": "",
      "commonHedges": [],
      "commonAssertions": [],
      "engagementWithScholars": ""
    },
    "transitions": {
      "preferred": {
        "addition": [],
        "contrast": [],
        "causation": [],
        "exemplification": [],
        "conclusion": []
      },
      "sectionBridging": ""
    },
    "citations": {
      "density": "",
      "integrationStyle": "",
      "quoteLengthPreference": ""
    },
    "rhetoricalPatterns": {
      "common": [],
      "openingMoves": "",
      "closingMoves": ""
    },
    "representativeExcerpts": []
  },
  "tools": {
    "candlekeep": { "enabled": false },
    "agentic-search-vectorless": { "enabled": false, "path": "../Agentic-Search-Vectorless" },
    "mongodb-agent-skills": { "enabled": false },
    "cognetivy": { "enabled": false }
  },
  "sources": [],
  "createdAt": "TIMESTAMP",
  "updatedAt": "TIMESTAMP"
}
```

Replace all placeholder values with what you collected. `representativeExcerpts` must contain actual verbatim text from the researcher's work.

---

## Confirmation

> "You're all set! Here's your profile:
>
> - **Field**: [field]
> - **Language**: [language]
> - **Citation style**: [style]
> - **Data services**: [list enabled tools]
> - **Writing style**: [2–3 sentence summary of fingerprint]
>
> Run `/academic-writer` anytime to start writing an article."
