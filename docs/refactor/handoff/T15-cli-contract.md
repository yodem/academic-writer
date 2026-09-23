# T15 CLI contract (fixed by the lead before the T15a/T15b split)

All commands take the global `--data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "${CLAUDE_PROJECT_DIR}"` like every `aw` call.
Default artifact paths are under `<project>/.academic-helper/`: `outline.json`, `author-intent.json`, `evidence.json`, `sources.json`, `drafts/<unitId>.md`.
Every command prints one JSON object on stdout. Failures are named (`ERROR <step>: …` on stderr, non-zero exit).

| Command | Behaviour | Exit |
|---|---|---|
| `aw draft --outline <f> --run <id> [--unit <id>] [--feedback-file <f>]` | Without `--unit`: drafts every body unit in topological `dependsOn` order, then `intro`/`conclusion` last. With `--unit`: redrafts only that unit (auditor feedback from `--feedback-file`). Writes `drafts/<unitId>.md`, runs the code gates. Prints `{drafted:[unitId], failures:[{unit, gate, detail}]}`. | 0 ok, 2 any gate failure, 1 error |
| `aw synthesize --outline <f> --run <id>` | Paragraph-level transition edits only; applies them to `drafts/*.md` in code. Prints `{edits:[{unitId, paragraphIndex, before, after, reason}], applied:n}`. | 0 / 1 |
| `aw edit --text-file <f> (--instruction <text> \| --instruction-file <f>) --lang <he\|en> --run <id> [--out <f>]` | Port of MCP `edit` (`existing_text`, `edit_instruction`, `target_language`). Prints `{revised_text}`; with `--out` also writes the file. | 0 / 1 |
| `aw ocr --input <pdf\|image\|dir> --lang <he\|en\|mixed> --run <id> [--pages <range>] [--format concise\|detailed] [--out <f.md>]` | Port of MCP `gemini_ocr` (`document_path`, `page_range`, `target_language`, `response_format`). Prints `{pages:[{page_number, text, is_born_digital, confidence?, notes?}], truncated, truncation_message?}`; with `--out` writes the concatenated text. | 0 / 1 |

Draft gate names (the `gate` field): `citation-not-in-sources`, `quote-not-in-evidence`, `style-banned`, `style-capped`, `word-bounds`.
