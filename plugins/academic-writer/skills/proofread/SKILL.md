---
name: proofread
description: "Use when a finished article needs deterministic typo, language, and editorial proofreading with a visible corrected copy and report."
allowed-tools: [Bash, Read]
user-invocable: true
context: fork
model: sonnet
effort: medium
metadata: {author: "Yotam Fromm", version: "0.4.0"}
---

# Proofread an article

The purpose of this skill is to run `aw proofread` on the article and show you its summary. The CLI handles typo and term detection, language suggestions, meaning verification, the editorial memo, and output files. It never edits the source article.

## Run

For a Markdown article, run the plugin binary with the required run id and output directory. Always pass the plugin data directory and current project directory:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" proofread "path/to/article.md" \
  --run "proofread-<run-id>" --out "proofread-output" \
  --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$CLAUDE_PROJECT_DIR"
```

Add `--venue <slug>` when a venue is specified. Add `--only mechanical`, `--only language`, or `--only editorial` when the researcher asks for one pass. Do not read or print the article into the conversation; the CLI writes the detailed artifacts to the output directory.

The CLI validates the emitted change contract before applying it. The equivalent standalone gate is:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gate.py" changes-schema "proofread-output/changes.json" --json
```

For a Word document, convert it to Markdown with the installed `pandoc` command first, run `aw proofread` on that Markdown, then pass the original document and corrected Markdown to `build-tracked-docx.py` to create a tracked-changes document:

```bash
pandoc "path/to/article.docx" -t markdown -o "proofread-output/article.md"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build-tracked-docx.py" \
  --original "path/to/article.docx" \
  --final-text "proofread-output/proofed.md" \
  --changes "proofread-output/changes.json" \
  --output "proofread-output/proofed.docx"
```

## Show the result

Display the short JSON summary printed by `aw proofread`, followed by links to `proofed.md`, `report.md`, and `memo.md` in the output directory. Keep the source untouched. Explain that findings marked refuted remain listed in `changes.json` and the report for review.
