---
name: edit-section
description: "Quick edit of a single section — rewrite, expand, cut, fix citations, or adjust style. Faster than full article edit. Use when changing one specific section only — faster than full edit."
user-invocable: true
allowed-tools: [Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion, ]
metadata: {author: "Yotam Fromm", version: "0.2.19"}
---

# Academic Writer — Edit Section

Use this command for one focused section. For article-wide changes, use `/academic-writer:edit`.

Read the selected section, preserve its citations, and ask for an instruction if none was provided. Write the section and instruction to temporary files inside the project. Run:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" edit \
  --text-file <section-file> --instruction-file <instruction-file> --lang <he|en> --run <run-id> --out <output-file>
```

Use `--instruction <text>` for a short instruction. Choose `--lang` from the project profile or ask the author. Review the returned `revised_text` and output file before applying it. If factual claims or citations changed, send all paragraphs in the section to the `auditor` in one batched call. Only PASS paragraphs with their `taggedText` may replace the accepted text; correct and re-audit failures.
