---
name: ocr
description: "Turn a scanned PDF or photographed page (or a folder of them) into plain text. The reader is picked in a measured tier order: Gemini when a Google key is set, else Claude on the author's plan, else Tesseract on this computer; Codex on request. Pages that already contain text are extracted directly. Use when the author has a scan, photo or screenshot of a source and needs its text before research or writing. Takes a file or folder path."
user-invocable: true
allowed-tools: [Bash, Read, Write, Glob, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.3.0", summary: "Turn a scan or photo into plain text: Gemini, then Claude, then Tesseract, by what is available."}
---

# Academic Writer — OCR

OCR (optical character recognition) reads the text out of a scanned or photographed page. Transcribe a PDF, an image, or a folder of them. OCR copies the source text exactly: it never corrects, modernises or paraphrases it, because the text may later be quoted as evidence.

**Step 0 — Anna's Archive first, for a published work.** Before any OCR, search Anna's Archive for the work: use the `annas-archive-ebooks` skill when it is installed, otherwise search by title, author and ISBN. For a chapter or article, look for the whole book or journal issue. If a copy of the **same edition** exists (same publisher, year and printed pagination), use its text layer or EPUB text, keep the printed page numbers exactly, and skip OCR. OCR only when there is no matching copy or the copy has no usable text. Record the outcome for each item: `annas: found-used`, `annas: found-wrong-edition` or `annas: not-found`.

**Who reads the pages: the tier order, measured 2026-10-20.** `aw ocr` picks the reader unless the author named one, and says which one ran:

| Tier | Reader | When | Why |
|---|---|---|---|
| 1 | **Gemini** (`gemini-3.8-flash`) | a Google API key is set | as accurate as Claude at 100 dpi and up; more accurate below 100 dpi and on canonical texts such as the vocalized Bible, which Claude refuses |
| 2 | **Claude** (Opus) | no Google key | as accurate as Gemini at 100 dpi and up, on the author's Claude plan; pages under 100 dpi come back flagged "verify" |
| 3 | **On this computer** (Tesseract) | neither is available, or the author wants nothing to leave the computer | free and private, but 2-5% letter errors on Hebrew |

The measured numbers, the two-column findings and the Codex option are in `${CLAUDE_PLUGIN_ROOT}/skills/ocr/references/engines.md`. Tell the author, in plain words, which reader ran and where the pages went (Gemini: Google; Claude: Anthropic; Tesseract: nowhere). If the author asks for a different reader, pass `--engine gemini|claude|local`.

Course readings are never OCR'd automatically (user rule 2026-10-19): the student asks for extraction on the dashboard ("חילוץ טקסט"). Whatever reader ran, never move a page to another reader on your own: a page a reader refused or could not read comes back marked "blocked" or "low resolution: verify"; ask with `AskUserQuestion` before sending that page to another reader, saying where it goes (with Gemini, its text goes to Google). Record which engine produced the text (`OCR engine: <name>`).

1. If the author gave no path, ask for the file or folder.
2. Choose the language: `he`, `en` or `mixed`. Take it from `.academic-helper/profile.md`, or ask when the source language is unclear.
3. Write the output under a project folder named `ocr-output/`, and run:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" ocr \
  --input <pdf|image|directory> --lang <he|en|mixed> --run <run-id> \
  [--engine auto|gemini|claude|local] --format concise --out <project-local-output.md>
```

- Add `--pages <range>` to process only some pages.
- Use `--format detailed` when the author wants notes on layout, footnotes and tables.
- For a folder, process one file at a time and write a separate output file for each document.

4. The command returns the reader it used (`engine`, `engine_reason`) and one record per page with whether the page already had digital text, a confidence level and notes. Report these faithfully: tell the author which pages were low-confidence, skipped or failed, so they know which pages to check against the original.
5. Never overwrite the source file.
