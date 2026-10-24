---
name: revise
description: "Read the Word comments and tracked changes the author left on a generated draft, group them, confirm each group, then update the article and the voice and feedback stores. Use when the author has commented on or tracked-changed a .docx from this plugin. Not for new instructions without a Word file (use /academic-writer:edit)."
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.12.0"}
---

# Revise a reviewed draft

Fold the author's Word review back into the article. Confirm every group with the author before anything is applied: their comments are instructions, but your grouping of them is a guess.

## 0. Record the run

Use one run ID for the whole review, e.g. `revise-ashkenazi-creation-20261015-1430` (Latin letters, digits and hyphens only). Record the run and register the workspace before anything else:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --project-dir "$CLAUDE_PROJECT_DIR" --data-dir "${CLAUDE_PLUGIN_DATA}" activity start --flow revise --run-id <id>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/home.py" --data-dir "${CLAUDE_PLUGIN_DATA}" register --path "$CLAUDE_PROJECT_DIR" --type project
```

`activity start` writes its opening line once per run. If `home.py register` says no home folder is set, skip it and tell the researcher once. The `aw revise` commands below record their own `read`, `update-draft` and `update-stores` steps.

## 1. Read the review

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/docx-read-review.py" <file.docx> --json > .academic-helper/review-items.json
```

Save the JSON inside the current project, then classify it (use the same `--run <id>`):

```bash
aw revise classify --items .academic-helper/review-items.json --run <id> --data-dir "$CLAUDE_PLUGIN_DATA" --project-dir "$CLAUDE_PROJECT_DIR"
```

## 2. Confirm with the author

Show the grouped items and the proposed action for each, in plain language. Ask for confirmation one group at a time with `AskUserQuestion`. Write a plan JSON that contains only the confirmed items.

## 3. Apply

```bash
aw revise apply --plan <plan.json> --data-dir "$CLAUDE_PLUGIN_DATA" --project-dir "$CLAUDE_PROJECT_DIR"
```

What happens to each kind of item:

- **Text edit**: applied to the article markdown using its exact `file`, `before` and `after`.
- **Argument question**: added to `.academic-helper/revise-todo.md`, for the `/academic-writer:write` or `/academic-writer:edit` loop to resolve.
- **Voice signal**: appended to the shared `voice/pairs.jsonl`; style-word and terminology proposals are written to their store files only after confirmation.
- **Plugin defect**: appended to `${CLAUDE_PLUGIN_DATA}/feedback/ledger.jsonl` so the plugin can be improved.

The command prints which items were applied and which were deferred.

## 4. Rebuild the Word file and report

Regenerate the Word document the way `/academic-writer:write` built it: run `aw docx` with the same outline and output arguments (it rebuilds `.academic-helper/runs/<id>/article.json` and calls `generate-docx.py` for you). If there is no outline, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/generate-docx.py" --input <article.json> --output <file.docx>` on the last run's article JSON. Then tell the author, in four short lists: what was edited, what went to the voice store, what went to the plugin feedback ledger, and what is still open in `revise-todo.md`.

Finally, end the run: `"${CLAUDE_PLUGIN_ROOT}/bin/aw" --project-dir "$CLAUDE_PROJECT_DIR" --data-dir "${CLAUDE_PLUGIN_DATA}" activity end --run-id <id> --exit OK` (use `--exit ERROR` if a step failed and you stop). Ending a run that `aw revise apply` already ended is a no-op.
