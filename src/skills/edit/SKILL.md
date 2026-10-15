---
name: edit
description: "Revise an article you already drafted: several passages at once, tone, structure, argument order or evidence. Use when the author asks to rework, restructure or rewrite parts of an existing article. Not for one section (use /academic-writer:edit-section), Word comments (use /academic-writer:revise), typos (use /academic-writer:proofread) or a new article (use /academic-writer:write)."
user-invocable: true
allowed-tools: [Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.2.19"}
---

# Academic Writer — Edit Article

Revise an existing article, or selected passages from it, with the `aw edit` command. This skill is for changes that span several passages or the whole article (tone, structure, evidence). For one focused section, hand off to `/academic-writer:edit-section`.

## 1. Understand the change

1. Read the target article. If the author named no file, list `articles/*.md` and ask which one.
2. If the author has not said what should change, ask in plain words, for example: "What would you like to change: the tone, the order of the argument, a specific passage, or the sources used?"
3. Keep every claim and citation the author did not ask to change. The citations were verified by the auditor; rewriting them casually would undo that check.

## 2. Run the edit

Save the selected text and the instruction to temporary files inside the project (never outside it), then run:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" edit \
  --text-file <text-file> --instruction-file <instruction-file> --lang <he|en> --run <run-id> --out <output-file>
```

- For a one-line instruction you may pass `--instruction <text>` instead of `--instruction-file`.
- Take the language from `.academic-helper/profile.md` (`targetLanguage`); ask the author if it is missing.
- The command prints `{"revised_text":"..."}` and, with `--out`, writes the output file.

## 3. Check and apply

1. Show the author what changed (a short before/after of each changed passage) before you replace anything in their article.
2. If the edit touched a factual claim or a citation, send the whole edited unit to the `auditor` agent in one single batched call covering every paragraph, with `runId: <run-id>` (the `--run` value used for `aw edit`) in the prompt. The auditor is the plugin's only hard gate for citations, so it must see edited facts before they are accepted.
3. Commit the auditor's `taggedText` for PASS paragraphs only. Correct FAIL or PARTIAL paragraphs and audit them again before accepting them.
4. Tell the author which passages changed and whether any paragraph still carries a `[NEEDS REVIEW: ...]` tag they should check by hand.
