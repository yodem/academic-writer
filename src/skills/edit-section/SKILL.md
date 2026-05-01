---
name: edit-section
description: "Quick edit of a single section — rewrite, expand, cut, fix citations, or adjust style. Faster than full article edit. Use when changing one specific section only — faster than full edit."
user-invocable: true
allowedTools: [Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion]
agents: [section-writer, auditor]
---

# Academic Writer — Edit Section

> **Do NOT use this skill** for multi-section edits, restructuring, or full-article tone changes — use `/academic-writer:edit` instead.

A fast, focused edit for a single section of an article. Use this instead of `/academic-writer:edit` when you know exactly which section needs work.

## Load Profile

```bash
cat .academic-helper/profile.md
```

**Load the full `styleFingerprint`** — edits must maintain the researcher's voice.

---

## Identify the Section

Ask:
> "Which section do you want to edit? Give me the section title, number, or paste the text."

If the article is in a file:
```bash
python3 -c "import docx; d=docx.Document('FILE_PATH'); [print(p.text) for p in d.paragraphs]"
```

Parse the target section and all surrounding sections (needed for repetition checking and transition context).

---

## Understand the Edit

Ask:
> "What should I change in this section?"

Common edit types:
- **Rewrite** — "Make this clearer" / "Rewrite paragraph 3"
- **Expand** — "Add more evidence for the claim about X"
- **Cut** — "This is too long, trim it"
- **Fix citations** — "Check all the footnotes"
- **Adjust style** — "This doesn't sound like me"
- **Add paragraph** — "Add a paragraph about X between paragraphs 2 and 3"
- **Remove paragraph** — "Delete the paragraph about X"

---

## Execute the Edit

### For rewrites / expansions / new paragraphs:

**Use the Agent tool to spawn a `section-writer` subagent** with the full pipeline (draft → style compliance → Hebrew grammar → repetition check → citation audit).

Pass as prompt: the section (title, current text, edit instructions, suggested sources), sectionIndex, thesis, styleFingerprint, citationStyle, tools, priorSectionTexts (text of adjacent sections for repetition awareness).

If the researcher wants to expand with new evidence, **first use the Agent tool to spawn research subagents in parallel** — call the Agent tool multiple times in a single response:
- One subagent for RAG queries on the expansion topic
- One subagent for Candlekeep reads for relevant documents

Then feed results to the section-writer.

### For citation fixes:

**Use the Agent tool to spawn an `auditor` subagent** for each paragraph. Pass as prompt: the paragraph text, sectionIndex, paragraphIndex, tools.

Apply fixes, re-audit until all pass.

### For cuts:

1. Identify which sentences/paragraphs to remove
2. Check that no critical argument steps are lost
3. Check that remaining transitions still work
4. Re-run style compliance on the shortened section
5. Show the researcher what was cut before finalizing

### For style adjustments:

1. Re-read `styleFingerprint`
2. Score every paragraph on 10 fingerprint dimensions
3. Fix any dimension scoring ≤3
4. Use `representativeExcerpts` as targets
5. Show before/after for the researcher

---

## Output

Show the revised section with a change summary:

> **Section "[title]" — revised:**
>
> [Full revised text with footnotes]
>
> **Changes:**
> - Paragraph 2: [what changed]
> - Paragraph 4 (new): [added with citations from X, Y]
> - Citations: [N] verified, [N] corrected
>
> **Skills applied:**
> - Style compliance: avg [N]/5
> - Hebrew grammar: [N] issues fixed
> - Repetition: [N] instances resolved
> - Citation audit: [N] claims verified
>
> Would you like me to export the full updated article as .docx?

---

