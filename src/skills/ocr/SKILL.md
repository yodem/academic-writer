---
name: ocr
description: "Turn a scanned PDF or photographed page (or a folder of them) into plain text with the bundled Gemini reading tool; pages that already contain text are extracted directly. Use when the author has a scan, photo or screenshot of a source and needs its text before research or writing. Takes a file or folder path."
user-invocable: true
allowed-tools: [Bash, Read, Write, Glob]
metadata: {author: "Yotam Fromm", version: "0.1.0"}
---

# Academic Writer — OCR

OCR (optical character recognition) reads the text out of a scanned or photographed page. Transcribe a PDF, an image, or a folder of them with `aw ocr`. OCR copies the source text exactly: it never corrects, modernises or paraphrases it, because the text may later be quoted as evidence.

**Step 0 — Anna's Archive first, for a published work.** Before any OCR, search Anna's Archive for the work: use the `annas-archive-ebooks` skill when it is installed, otherwise search by title, author and ISBN. For a chapter or article, look for the whole book or journal issue. If a copy of the **same edition** exists (same publisher, year and printed pagination), use its text layer or EPUB text, keep the printed page numbers exactly, and skip OCR. Run Gemini OCR (`aw ocr`) only when there is no matching copy or the copy has no usable text. Record the outcome for each item: `annas: found-used`, `annas: found-wrong-edition` or `annas: not-found`.

For library and Kotar readings (in copyright), use this Gemini OCR directly when step 0 finds no usable copy. For other course readings it is the escalation engine, not the first try: read the pages with Claude vision first (`pdftoppm -r 150`), and use `aw ocr` when Claude flags pages as unreadable or low-confidence or the text is degraded. Record which engine produced the text.

1. If the author gave no path, ask for the file or folder.
2. Choose the language: `he`, `en` or `mixed`. Take it from `.academic-helper/profile.md`, or ask when the source language is unclear.
3. Write the output under a project folder named `ocr-output/`, and run:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" ocr \
  --input <pdf|image|directory> --lang <he|en|mixed> --run <run-id> \
  --format concise --out <project-local-output.md>
```

- Add `--pages <range>` to process only some pages.
- Use `--format detailed` when the author wants notes on layout, footnotes and tables.
- For a folder, process one file at a time and write a separate output file for each document.

4. The command returns one record per page with whether the page already had digital text, a confidence level and notes. Report these faithfully: tell the author which pages were low-confidence, skipped or failed, so they know which pages to check against the original.
5. Never overwrite the source file.
