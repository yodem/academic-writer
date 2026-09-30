---
name: present
description: "Turn a finished article into follow-on materials: a conference talk outline, a journal submission abstract with keywords, a book chapter proposal, and (with NotebookLM) an audio overview or study guide. Use when the author asks for a talk, abstract, proposal or study materials based on an article they completed."
user-invocable: false
allowed-tools: [Bash, Read, Write, Glob, Grep, AskUserQuestion, mcp__notebooklm-mcp__notebook_create, mcp__notebooklm-mcp__source_add, mcp__notebooklm-mcp__studio_create, mcp__notebooklm-mcp__studio_status, mcp__notebooklm-mcp__download_artifact]
metadata: {author: "Yotam Fromm", version: "0.2.23"}
---

# Academic Writer — Post-Article Deliverables

Generate presentation materials and submission documents from a completed article. Everything you write must come from the article itself: do not add claims, sources or findings the article does not contain, because the author will present these materials under their name.

## Load Profile

```bash
cat .academic-helper/profile.md
```

Extract `targetLanguage` and `fieldOfStudy`.

## Select Article

```bash
ls articles/*.md 2>/dev/null
```

If there is more than one article, list them and ask which one to use (by number or name). With up to four articles you may offer them as `AskUserQuestion` options; with more, ask in plain conversation.

Read the selected article with the `Read` tool. Extract its thesis, section structure, and key arguments.

## Select Deliverable

`AskUserQuestion` allows at most four options, so offer these (multi-select; NotebookLM extras are offered afterwards, only when enabled):

```python
AskUserQuestion(questions=[{
  "question": "What would you like to generate from this article?",
  "header": "Deliverable",
  "options": [
    {"label": "Conference talk", "description": "Outline for a 20-30 minute talk, with speaker notes and likely questions"},
    {"label": "Journal abstract", "description": "150-300 word structured abstract plus 5-7 keywords, ready to paste"},
    {"label": "Chapter proposal", "description": "1-2 page proposal to grow this article into a book chapter"},
    {"label": "NotebookLM extras", "description": "Audio overview or study guide (needs NotebookLM enabled)"}
  ],
  "multiSelect": true
}])
```

If "NotebookLM extras" is chosen, ask which of the two (audio overview, study guide, or both).

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

## Audio Overview (NotebookLM)

**Skip if `tools.notebooklm.enabled` is false.** Tell the researcher: "NotebookLM isn't turned on yet. Ask me to update your tools and I'll help you connect it; then I can make an audio overview."

> **If the NotebookLM tools (`mcp__notebooklm-mcp__*`, supplied by the separate NotebookLM connector the author installs) are not available, skip this whole section and say so** — these two branches are optional deliverables, not part of the core output. Check for the tools before starting; do not half-run the sequence.

1. **Create a notebook** for this article using the `mcp__notebooklm-mcp__notebook_create` MCP tool with the article title
2. **Add the article** as a source using the `mcp__notebooklm-mcp__source_add` MCP tool (paste the article markdown content)
3. **Generate audio overview** using the `mcp__notebooklm-mcp__studio_create` MCP tool with type "audio"
4. **Check status** using the `mcp__notebooklm-mcp__studio_status` MCP tool — audio generation may take a few minutes
5. **Download** the audio file using the `mcp__notebooklm-mcp__download_artifact` MCP tool when ready

Tell the author: "Your audio overview is being generated; it can take a few minutes. I'll check on it, or you can ask me later." When it is ready, download it next to the article in `articles/`.

## Study Guide (NotebookLM)

**Skip if `tools.notebooklm.enabled` is false.** Tell the researcher: "NotebookLM isn't turned on yet. Ask me to update your tools and I'll help you connect it; then I can make a study guide."

1. **Reuse the notebook** created for Audio Overview, or create one if it doesn't exist
2. **Generate study guide** using the `mcp__notebooklm-mcp__studio_create` MCP tool with type "study guide"
3. **Check status** and **download** when ready using the `mcp__notebooklm-mcp__studio_status` and `mcp__notebooklm-mcp__download_artifact` MCP tools

Save the study guide content to `articles/[article-name]-study-guide.md`.

## Completion

> "Generated:
> - [list of deliverables created with file paths]
>
> All files are in the `articles/` directory."
