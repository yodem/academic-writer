---
name: academic-writer-review
description: "Self-review quality gate — scores a completed article on 6 dimensions (structure, argument logic, citation completeness, source coverage, writing quality, academic conventions) and presents a scorecard before final output."
user-invocable: true
allowedTools: [Bash, Read, Glob, Grep, AskUserQuestion]
---

# Academic Writer — Article Self-Review

A structured quality gate that scores a completed article on 6 dimensions and presents a scorecard to the researcher.

## When to Use

- Automatically invoked as Step 8.7 in the write-article pipeline (between Synthesis and DOCX Output)
- Can be run standalone on any article: `/academic-writer-review`

## Load Profile

```bash
cat .academic-writer/profile.json
```

If no profile, tell the researcher to run `/academic-writer-init` first.

## Input

When run standalone, ask:
> "Which article would you like to review? Provide the path to a markdown (.md) file in `articles/`."

List available articles:
```bash
ls articles/*.md 2>/dev/null
```

Read the selected article with the `Read` tool.

When invoked as a pipeline step, the article text is passed directly.

## Review Checklist (6 Dimensions)

Score each dimension **1–10**. Present detailed findings for each.

### 1. Structure (מבנה)

- Does the introduction open with `במאמר זה` / `בדף זה` / `במחקר זה`?
- Does the introduction contain a roadmap of the article's sections?
- Does the conclusion open with `לסיכום` / `מכל האמור עולה כי` / `בסיכומו של דבר`?
- Does the conclusion return to the thesis?
- Are sections ordered logically?
- Is paragraph count per section balanced (not wildly uneven)?

**Score 10:** All conventions met, logical order, balanced sections.
**Score 1:** Missing intro/conclusion conventions, illogical order.

### 2. Argument Logic (הגיון טיעוני)

- Does each section advance the thesis?
- Are there logical gaps between sections?
- Do topic sentences clearly state the section's argument?
- Is there a clear progression (not circular reasoning)?
- Does the conclusion follow from the body?

**Score 10:** Every section advances thesis, no gaps, clear progression.
**Score 1:** Sections don't connect to thesis, circular logic, gaps.

### 3. Citation Completeness (שלמות ציטוטים)

- Does every factual claim have a citation?
- Are there orphan citations (cited but never discussed)?
- Is citation format consistent throughout?
- Are page numbers present where expected?
- Are author names and work titles consistent across citations?

**Score 10:** Every claim cited, consistent format, no orphans.
**Score 1:** Multiple uncited claims, inconsistent format.

### 4. Source Coverage (כיסוי מקורות)

- Are all sources from the outline actually used in the article?
- Is any single source over-relied upon (>40% of citations)?
- Are sources distributed across sections appropriately?
- Are opposing viewpoints represented?

**Score 10:** All sources used, balanced distribution, counter-arguments present.
**Score 1:** Sources missing, over-reliance on one source.

### 5. Writing Quality (איכות כתיבה)

Check against the researcher's style fingerprint:

```bash
cat .academic-writer/profile.json | python3 -c "import sys,json; fp=json.load(sys.stdin).get('styleFingerprint'); print(json.dumps(fp, indent=2, ensure_ascii=False) if fp else 'null')"
```

- Does the writing match the researcher's voice?
- Is sentence length varied?
- Are there grammar or spelling issues?
- Is the language register consistently academic?
- Are there language purity violations (foreign terms in body text)?

**Score 10:** Matches fingerprint perfectly, no issues.
**Score 1:** Generic voice, grammar issues, register inconsistencies.

### 6. Academic Conventions (מוסכמות אקדמיות)

Load linking words reference:
```bash
cat plugins/academic-writer/words.md
```

- Are linking words varied (not repeating the same connector)?
- Are linking words used in correct semantic context?
- Is paragraph length appropriate (not too short, not too long)?
- Is formal register maintained throughout?
- Are transitions between sections smooth?

**Score 10:** Rich variety of connectors, appropriate lengths, smooth transitions.
**Score 1:** Repetitive connectors, choppy transitions.

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

## Cognetivy Logging

If Cognetivy is enabled:
```bash
echo '{"type":"step_started","nodeId":"self_review"}' | cognetivy event append --run RUN_ID
```

After scoring:
```bash
echo '{"type":"step_completed","nodeId":"self_review","totalScore":NN,"maxScore":60,"grade":"GRADE","dimensions":{"structure":N,"argumentLogic":N,"citationCompleteness":N,"sourceCoverage":N,"writingQuality":N,"academicConventions":N}}' | cognetivy event append --run RUN_ID
```
