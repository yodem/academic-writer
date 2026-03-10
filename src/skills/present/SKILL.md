---
name: academic-writer-present
description: "Post-article deliverables — generate conference presentation outlines, journal submission summaries, and book chapter proposals from a completed article."
user-invocable: true
allowedTools: [Bash, Read, Write, Glob, Grep, AskUserQuestion]
---

# Academic Writer — Post-Article Deliverables

Generate presentation materials and submission documents from a completed article.

## Load Profile

```bash
cat .academic-writer/profile.json
```

Extract `targetLanguage` and `fieldOfStudy`.

## Select Article

```bash
ls articles/*.md 2>/dev/null
```

If multiple articles exist:
```python
AskUserQuestion(questions=[{
  "question": "Which article would you like to create deliverables for?",
  "header": "Select Article",
  "options": []
}])
```

Read the selected article with the `Read` tool. Extract its thesis, section structure, and key arguments.

## Select Deliverable

```python
AskUserQuestion(questions=[{
  "question": "What would you like to generate from this article?",
  "header": "Deliverable Type",
  "options": [
    {
      "label": "Conference Presentation Outline",
      "description": "20-30 minute talk outline with argument flow",
      "markdown": "```\nConference Presentation\n───────────────────────\nOutput: Structured outline for oral delivery\nLength: 20-30 min talk (~2500 words spoken)\nFocus:  Argument flow, not full text\nFormat: Markdown with speaker notes\n```"
    },
    {
      "label": "Journal Submission Abstract",
      "description": "Structured abstract for journal submission",
      "markdown": "```\nJournal Abstract\n────────────────\nOutput: 150-300 word abstract\nParts:  Topic, method, findings, contribution\nFormat: Ready to paste into submission form\n```"
    },
    {
      "label": "Book Chapter Proposal",
      "description": "Proposal to develop this article into a book chapter",
      "markdown": "```\nBook Chapter Proposal\n─────────────────────\nOutput: 1-2 page proposal\nParts:  Chapter summary, fit with volume,\n        expanded scope, bibliography\nFormat: Markdown\n```"
    },
    {
      "label": "All of the above",
      "description": "Generate all three deliverables"
    }
  ],
  "multiSelect": true
}])
```

## Conference Presentation Outline

Generate in `targetLanguage`:

```markdown
# [Article Title] — Conference Presentation

## Talk Structure (20-30 min)

### Opening (3 min)
- Hook: [engaging opening tied to a key source or question]
- Research question: [from article]
- Why this matters: [significance in 2 sentences]

### Background (5 min)
- [Key context the audience needs]
- [State of the field — what's been said]
- [The gap this research fills]

### Argument (15 min)
#### Point 1: [from section X]
- Key evidence: [strongest citation]
- Speaker note: [how to present this]

#### Point 2: [from section Y]
- Key evidence: [strongest citation]
- Speaker note: [how to present this]

#### Point 3: [from section Z]
- Key evidence: [strongest citation]
- Speaker note: [how to present this]

### Conclusion (5 min)
- Main finding: [thesis restated for oral delivery]
- Implications: [wider significance]
- Open question: [for Q&A]

## Anticipated Questions
1. [likely question] — [suggested response]
2. [likely question] — [suggested response]
3. [likely question] — [suggested response]
```

Save to `articles/[article-name]-presentation.md`.

## Journal Submission Abstract

Generate a structured abstract (150-300 words) in `targetLanguage`:

1. **Topic & research question** (1-2 sentences)
2. **Methodology & sources** (1-2 sentences)
3. **Main findings** (2-3 sentences)
4. **Contribution to the field** (1 sentence)

Also generate keywords (5-7) from the article content.

Save to `articles/[article-name]-abstract.md`.

## Book Chapter Proposal

Generate in `targetLanguage`:

```markdown
# Chapter Proposal: [Expanded Title]

## Chapter Summary
[2-3 paragraphs expanding the article's argument for a book chapter]

## How This Chapter Fits
[1 paragraph on how it connects to broader themes in the field]

## Expanded Scope
[What would be added beyond the article — new sources, deeper analysis, additional sections]

## Proposed Length
[Word count estimate, typically 8,000-12,000 words]

## Key Sources
[Bibliography of primary and secondary sources]
```

Save to `articles/[article-name]-chapter-proposal.md`.

## Completion

> "Generated:
> - [list of deliverables created with file paths]
>
> All files are in the `articles/` directory."
