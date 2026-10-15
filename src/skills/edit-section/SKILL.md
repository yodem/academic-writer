---
name: edit-section
description: "Quick revision of one section of an existing article: rewrite, expand, shorten, fix its citations or adjust its style. Use when the author points at a single section or passage to change. Not for article-wide changes (use /academic-writer:edit), Word comments (use /academic-writer:revise) or typo checks (use /academic-writer:proofread)."
user-invocable: true
allowed-tools: [Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.2.19"}
---

# Academic Writer — Edit Section

Revise one focused section. For changes across the whole article, hand off to `/academic-writer:edit`.

1. Read the section the author chose. If it is unclear which one, list the article's headings and ask.
2. If the author gave no instruction, ask what they want: rewrite, expand, shorten, fix a citation, or change the style.
3. Write the section and the instruction to temporary files inside the project, then run:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" edit \
  --text-file <section-file> --instruction-file <instruction-file> --lang <he|en> --run <run-id> --out <output-file>
```

- Choose one run ID for this edit, e.g. `edit-ashkenazi-creation-20261015-1430` (a short English label, then the date and time). Use only Latin letters, digits and hyphens: transliterate a Hebrew title or use a short English label, because the library refuses any other character in an id. Use the same `<run-id>` for the auditor.
- For a short instruction you may use `--instruction <text>` instead.
- Take `--lang` from `.academic-helper/profile.md`, or ask the author.

4. Read the returned `revised_text` and the output file. Show the author the before/after before applying it.
5. Keep the section's citations unless the author asked to change them. If a factual claim or citation changed, send every paragraph of the section to the `auditor` agent in one batched call, with `runId: <run-id>` (the `--run` value used for `aw edit`) in the prompt: the auditor is the only gate that checks citations against the real sources.
6. Replace the accepted text only with PASS paragraphs and their `taggedText`. Correct and re-audit any FAIL or PARTIAL paragraph first.
