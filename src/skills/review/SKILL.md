---
name: review
description: "Self-review quality gate — scores a completed article on 6 dimensions (structure, argument logic, citation completeness, source coverage, writing quality, academic conventions) and presents a scorecard before final output."
user-invocable: true
allowedTools: [Bash, Read, Glob, Grep, AskUserQuestion]
---

# Academic Writer — Article Self-Review

A structured quality gate that scores a completed article on 6 dimensions and presents a scorecard to the researcher.

## When to Use

- Automatically invoked as Step 8.7 in the write-article pipeline (between Synthesis and DOCX Output)
- Can be run standalone on any article: `/academic-writer:review`

## Load Profile

```bash
cat .academic-helper/profile.md
```

If no profile, tell the researcher to run `/academic-writer:init` first.

## Input

When run standalone, ask:
> "Which article would you like to review? Provide the path to a markdown (.md) file in `articles/`."

List available articles:
```bash
ls articles/*.md 2>/dev/null
```

Read the selected article with the `Read` tool.

When invoked as a pipeline step, the article text is passed directly.

## Scorecard rubric

The 6-dimension scorecard is defined in `references/scorecard.json` (machine-readable, versioned). Read that file at the start of every review:

```bash
cat plugins/academic-writer/skills/review/references/scorecard.json
```

For each dimension:
1. Score 0–10 against the listed `criteria`.
2. Sum the dimension scores.
3. Compare to `scoring.passThreshold` (default 40). Below threshold → researcher review required.

The scorecard is the single source of truth — do not score on dimensions not listed there, and do not change weights inline. To adjust scoring, edit `references/scorecard.json` and bump its `version` field.

Also check the researcher's style fingerprint for Writing Quality (dimension 5):

```bash
python3 -c "
import re, json
content = open('.academic-helper/profile.md').read()
m = re.search(r'## Style Fingerprint\n+\x60\x60\x60json\n(.*?)\n\x60\x60\x60', content, re.DOTALL)
print(m.group(1) if m else 'null')
"
```

And load linking words reference for Academic Conventions (dimension 6):
```bash
cat plugins/academic-writer/words.md
```

## Scorecard Output

Present the results as a clear scorecard:

```
╔══════════════════════════════════════════════════════╗
║              ARTICLE REVIEW SCORECARD               ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  1. Structure (מבנה)              N/10               ║
║     [brief finding]                                  ║
║                                                      ║
║  2. Argument Logic (הגיון טיעוני)  N/10               ║
║     [brief finding]                                  ║
║                                                      ║
║  3. Citation Completeness (ציטוטים) N/10              ║
║     [brief finding]                                  ║
║                                                      ║
║  4. Source Coverage (כיסוי מקורות)  N/10               ║
║     [brief finding]                                  ║
║                                                      ║
║  5. Writing Quality (איכות כתיבה)  N/10               ║
║     [brief finding]                                  ║
║                                                      ║
║  6. Academic Conventions (מוסכמות)  N/10              ║
║     [brief finding]                                  ║
║                                                      ║
╠══════════════════════════════════════════════════════╣
║  TOTAL:  NN/60                                       ║
║  GRADE:  [Excellent/Good/Needs Work/Poor]            ║
╚══════════════════════════════════════════════════════╝
```

**Grade thresholds:**
- 50–60: Excellent — ready for submission
- 40–49: Good — minor improvements recommended
- 30–39: Needs Work — specific issues to address
- Below 30: Poor — significant revision needed

## Detailed Findings

After the scorecard, list specific issues found:

> **Issues to address:**
> 1. [Dimension] — [specific issue and location]
> 2. ...
>
> **Strengths:**
> 1. [Dimension] — [what works well]
> 2. ...

## When Run as Pipeline Step (Step 8.7)

If the score is below 40, warn the researcher:

```python
AskUserQuestion(questions=[{
  "question": "The article scored NN/60 on self-review. Some issues were found. How would you like to proceed?",
  "header": "Self-Review Results",
  "options": [
    {"label": "Continue to DOCX output", "description": "Generate the document as-is. You can edit later."},
    {"label": "Show me the issues", "description": "Review the detailed findings before proceeding."},
    {"label": "Run edits first", "description": "Address the issues before generating the final document."}
  ],
  "multiSelect": false
}])
```

If score is 40+, show the scorecard and continue to DOCX output automatically.

