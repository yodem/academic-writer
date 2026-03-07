---
name: academic-writer-init
description: "Analyze the researcher's writing style from past articles and complete the Academic Writer profile."
user-invocable: true
---

# Academic Writer — Init

## Step 0: Check Profile

```bash
cat .academic-writer/profile.json 2>/dev/null && echo "EXISTS" || echo "NOT_FOUND"
```

**If NOT_FOUND:**
> "No profile found. Please run the setup first:
>
> ```
> npx github:yodem/academic-writer
> ```
>
> This will configure your language, citation style, and tools interactively. Then come back and run `/academic-writer-init` again."

Stop here if no profile.

**If EXISTS:** Load the profile, then continue.

---

## Step 1: Confirm Settings

Read `.academic-writer/profile.json` and confirm the loaded settings with the researcher:

> "I loaded your profile:
>
> - **Field**: [fieldOfStudy]
> - **Language**: [targetLanguage]
> - **Citation style**: [citationStyle]
> - **Tools enabled**: [list enabled tools]
>
> Does this look right? (yes / no — if no, run `npx github:yodem/academic-writer` to update)"

If no, stop. If yes, continue.

---

## Step 1.5: Enrich Candlekeep Sources (if enabled)

**Skip if `tools.candlekeep.enabled` is false.**

```bash
ck items list --json
```

For every item returned, run enrichment to extract title, author, description, and table of contents:

```bash
# For each item ID:
ck items enrich ITEM_ID
```

Tell the researcher:
> "Enriching your Candlekeep sources — extracting titles, authors, and table of contents. This ensures the writing pipeline has accurate metadata..."

After enrichment completes, continue.

---

## Step 2: Writing Style Analysis

Tell the researcher:
> "Now I'll analyze your writing style from your past articles.
>
> Make sure your published papers are in the **`past-articles/`** folder (PDF or DOCX). These files are used only locally — never uploaded anywhere.
>
> Tell me when you're ready, or if the folder is already populated."

Once confirmed:

```bash
ls past-articles/
```

If the folder is empty, prompt:
> "The `past-articles/` folder is empty. Please add 5–10 of your published papers (PDF or DOCX) and let me know when done."

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
9. Argument progression (inductive or deductive)
10. How evidence is introduced and analyzed after quoting
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

## Step 3: Save Fingerprint

After researcher approval, update `.academic-writer/profile.json` using the Write tool — merge the `styleFingerprint` field into the existing profile. Do NOT overwrite the other fields.

```json
{
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
  }
}
```

`representativeExcerpts` must contain actual verbatim text from the researcher's work — not descriptions.

---

## Confirmation

> "You're all set! Your writing style has been captured and saved.
>
> Run `/academic-writer` anytime to start writing an article."
