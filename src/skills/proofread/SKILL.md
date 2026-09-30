---
name: proofread
description: "Proofread a finished article (Markdown or Word) for typos, wrong words, grammar and editorial issues, producing a corrected copy, a report and an editorial memo without touching the original. Use when the author asks to proofread, spell-check or polish a finished article. Not for rewriting content (use /academic-writer:edit) or scoring quality (use /academic-writer:review)."
allowed-tools: [Bash, Read]
user-invocable: true
context: fork
model: sonnet
effort: medium
metadata: {author: "Yotam Fromm", version: "0.4.0"}
---

# Proofread an article

Run `aw proofread` on the article and show its summary. The command does all the work: it finds typos and term errors, suggests language fixes, checks that each fix keeps the meaning, writes an editorial memo, and saves the output files. It never edits the source article, so the author always keeps their original.

## Run

For a Markdown article, run the plugin command with a run id and an output folder. Always pass the plugin data directory and the project directory:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" proofread "path/to/article.md" \
  --run "proofread-<run-id>" --out "proofread-output" \
  --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$CLAUDE_PROJECT_DIR"
```

- Add `--venue <slug>` when the author names a journal or venue.
- Add `--only mechanical`, `--only language` or `--only editorial` when the author wants just one pass (mechanical = typos and punctuation; language = wording and grammar; editorial = the memo on clarity and flow).
- Do not read or print the article into the conversation. The command writes the detailed results to the output folder; copying the article here would only cost time and tokens.

The command validates its list of changes before applying them. The same check can be run on its own:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gate.py" changes-schema "proofread-output/changes.json" --json
```

For a Word document, convert it to Markdown with `pandoc` first, run `aw proofread` on that Markdown, then build a Word file with tracked changes from the original and the corrected text:

```bash
pandoc "path/to/article.docx" -t markdown -o "proofread-output/article.md"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build-tracked-docx.py" \
  --original "path/to/article.docx" \
  --final-text "proofread-output/proofed.md" \
  --changes "proofread-output/changes.json" \
  --output "proofread-output/proofed.docx"
```

## Show the result

Show the short JSON summary that `aw proofread` prints, then links to `proofed.md`, `report.md` and `memo.md` in the output folder (and `proofed.docx` for Word input). Remind the author the original is untouched. Explain that suggestions the checker rejected ("refuted") are still listed in `changes.json` and the report, so the author can review them too.
