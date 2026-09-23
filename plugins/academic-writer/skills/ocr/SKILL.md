---
name: ocr
description: "OCR a scanned PDF or image (or a directory of them) into clean plain-text markdown via the bundled Gemini vision tool. Skips Gemini entirely for born-digital pages (extracted directly). Use when you have a scanned source — an old article, a photographed archival page, a screenshot of a source — and want its text extracted before using it in research or writing. Takes a path to a file or directory as its argument."
user-invocable: true
allowed-tools: [Bash, Read, Write, Glob, Bash]
metadata: {author: "Yotam Fromm", version: "0.1.0"}
---

# Academic Writer — OCR

Transcribe a PDF, image, or directory of supported files with `aw ocr`. OCR preserves the source text; it does not correct or paraphrase it. Ask for a path if the author did not provide one. Choose `he`, `en`, or `mixed` from the profile, or ask when unclear.

Write output under a project-local `ocr-output/` directory and run:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" ocr \
  --input <pdf|image|directory> --lang <he|en|mixed> --run <run-id> \
  --format concise --out <project-local-output.md>
```

Use `--pages <range>` when processing a specific page range and `--format detailed` when detailed output is requested. The command returns page records with born-digital status, confidence, and notes; surface these faithfully. For a directory, process each file sequentially and write a separate output file per document. Never overwrite the source. Report errors and uncertain or skipped pages explicitly.
