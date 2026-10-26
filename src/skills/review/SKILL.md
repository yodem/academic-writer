---
name: review
description: "Score a completed article on six dimensions (structure, argument logic, citation completeness, source coverage, writing quality, academic conventions) and show a scorecard with concrete findings. Use when the author wants an assessment before submitting, or as the self-review step of /academic-writer:write. Not for fixing typos (use /academic-writer:proofread) or making changes (use /academic-writer:edit)."
user-invocable: true
allowed-tools: [Bash, Read, Glob, Grep, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.2.24"}
---

# Academic Writer — Article Self-Review

Score a completed article on six dimensions and show the researcher a scorecard. Be a fair, specific reviewer: every score needs a concrete finding tied to a place in the article, because a bare number gives the researcher nothing to act on. Review only; do not change the article.

## When this runs

- As the self-review step of `/academic-writer:write` (after synthesis, before the Word file), described in `write/references/write-completion.md`.
- On its own, on any article, when the researcher runs `/academic-writer:review`.

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

When run as a step of `/academic-writer:write`, the article text is passed to you directly.

## Scorecard rubric

The 6-dimension scorecard is defined in `references/scorecard.json` (machine-readable, versioned). Read that file at the start of every review:

```bash
cat ${CLAUDE_PLUGIN_ROOT}/skills/review/references/scorecard.json
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

And load linking words reference (judge whether each connective states a real logical relation and flag vague links such as וכך, והוא or ממנו used loosely; do not count connectives or penalise a paragraph for having few) and the positive terminology reference for Academic Conventions (dimension 6) — the terminology file's language-specific variant is picked from the article's `targetLanguage` (read from `.academic-helper/profile.md`'s frontmatter, e.g. `targetLanguage: Hebrew`; fall back to the English file if the language-specific file is missing):
```bash
LANG_LOWER=$(grep -m1 '^targetLanguage:' .academic-helper/profile.md 2>/dev/null | sed 's/^targetLanguage:[[:space:]]*//' | tr '[:upper:]' '[:lower:]')
LANG_LOWER=${LANG_LOWER:-hebrew}
WORDS_FILE="${CLAUDE_PLUGIN_ROOT}/words-${LANG_LOWER}.md"
if [ -f "$WORDS_FILE" ]; then cat "$WORDS_FILE"; else cat ${CLAUDE_PLUGIN_ROOT}/words-hebrew.md; fi
TERM_FILE="${CLAUDE_PLUGIN_ROOT}/skills/write/references/academic-terminology-${LANG_LOWER}.md"
if [ -f "$TERM_FILE" ]; then cat "$TERM_FILE"; else cat ${CLAUDE_PLUGIN_ROOT}/skills/write/references/academic-terminology-hebrew.md; fi
```

Score the "Terminology register" criterion in dimension 6 by checking whether hedging, argumentation, citation-introduction, and transition vocabulary in the article matches the register modeled in that file rather than colloquial substitutes — see the table in `academic-terminology-{lang}.md § E` for common colloquial→academic swaps to watch for.

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

## When run inside /academic-writer:write

If the total is below `selfReview.passThreshold` in `thresholds.json` (40 by default; `references/scorecard.json` mirrors it), warn the researcher:

```python
AskUserQuestion(questions=[{
  "question": "The article scored NN/60 on self-review. Some issues were found. How would you like to proceed?",
  "header": "Self-review",
  "options": [
    {"label": "Continue to DOCX output", "description": "Generate the document as-is. You can edit later."},
    {"label": "Show me the issues", "description": "Review the detailed findings before proceeding."},
    {"label": "Run edits first", "description": "Address the issues before generating the final document."}
  ],
  "multiSelect": false
}])
```

If the total meets the threshold, show the scorecard and continue to the Word output automatically.

