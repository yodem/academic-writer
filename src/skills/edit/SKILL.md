---
name: edit
description: "Edit a previously written article — revise sections, fix citations, adjust tone, restructure arguments, or rewrite passages. Use when revising an article that's already drafted — multiple sections, restructuring, or major changes."
user-invocable: true
allowed-tools: [Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.2.19"}
---

# Academic Writer — Edit Article

Revise an existing article or selected passages with the `aw edit` CLI. Use this skill for edits across several passages or broad tone, structure, or evidence changes. Use `/academic-writer:edit-section` for one focused section.

## Run the edit

Read the target article and ask what should change if the author has not specified an instruction. Preserve claims and citations unless the requested change requires revisiting them. Save the selected text and instruction in project-local temporary files, then invoke the CLI directly:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" edit \
  --text-file <text-file> --instruction-file <instruction-file> --lang <he|en> --run <run-id> --out <output-file>
```

Use `--instruction <text>` instead of `--instruction-file` for a short instruction. Choose the language from `.academic-helper/profile.md` or ask the author. The command prints `{"revised_text":"..."}` and writes the output file when `--out` is supplied. Read the result and show the author what changed before replacing their source.

For factual or citation changes, send the complete edited unit to the `auditor` agent in one batched call covering every paragraph. The auditor remains the hard gate. Commit `taggedText` only for PASS paragraphs; correct and re-audit failed paragraphs before accepting them.
