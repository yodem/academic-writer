---
name: revise
description: "Read Word comments and tracked changes, confirm grouped revisions, and update article and feedback stores. Use when you've commented on or tracked-changed a draft in Word."
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.12.0"}
---

# Revise a reviewed draft

Use `src/scripts/docx-read-review.py <file.docx> --json` to read comments and tracked changes. Save the JSON in the current project, then classify it with `aw revise classify --items <items.json> --run <id> --data-dir "$CLAUDE_PLUGIN_DATA" --project-dir "$CLAUDE_PROJECT_DIR"`.

Show the author the grouped items and proposed actions. Ask for confirmation per group. Create a plan JSON containing confirmed items and run `aw revise apply --plan <plan.json>` with the same path arguments.

Text edits are applied to the article markdown using their exact `file`, `before`, and `after` proposal. Argument questions go to `.academic-helper/revise-todo.md` for the `/write` or `/edit` unit loop. Accepted voice signals append to the shared `voice/pairs.jsonl`; style-word and terminology proposals are written to their respective store files only after confirmation. Plugin defects append to `${CLAUDE_PLUGIN_DATA}/feedback/ledger.jsonl`.

After applying changes, regenerate the Word document with `src/scripts/generate-docx.py`. Tell the author what was edited, what went to the voice store, what went to the plugin ledger, and what remains in revise-todo.md.
