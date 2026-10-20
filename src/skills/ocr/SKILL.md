---
name: ocr
description: "Turn a scanned PDF or photographed page (or a folder of them) into plain text. Each page goes to the cheapest reader that matched Gemini in a measured test: free readers on this computer when two of them agree, else Claude on the author's plan, else Gemini when a Google key is set (for pages Claude refuses or that are under 100 dpi); Codex on request. Pages that already contain text are extracted directly. Use when the author has a scan, photo or screenshot of a source and needs its text before research or writing. Takes a file or folder path."
user-invocable: true
allowed-tools: [Bash, Read, Write, Glob, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.3.0", summary: "Turn a scan or photo into plain text: free readers when they agree, then Claude, then Gemini for the pages Claude cannot read."}
---

# Academic Writer — OCR

OCR (optical character recognition) reads the text out of a scanned or photographed page. Transcribe a PDF, an image, or a folder of them. OCR copies the source text exactly: it never corrects, modernises or paraphrases it, because the text may later be quoted as evidence.

**Step 0 — Anna's Archive first, for a published work.** Before any OCR, search Anna's Archive for the work: use the `annas-archive-ebooks` skill when it is installed, otherwise search by title, author and ISBN. For a chapter or article, look for the whole book or journal issue. If a copy of the **same edition** exists (same publisher, year and printed pagination), use its text layer or EPUB text, keep the printed page numbers exactly, and skip OCR. OCR only when there is no matching copy or the copy has no usable text. Record the outcome for each item: `annas: found-used`, `annas: found-wrong-edition` or `annas: not-found`.

**Who reads the pages: the cheapest reader that matches Gemini, page by page (measured 2026-10-20).** `aw ocr` picks the reader for each page unless the author named one, and every page says which one read it (`engine`):

| Step | Reader | When | Why |
|---|---|---|---|
| 1 | **On this computer** (Surya and Tesseract) | Surya is installed (it needs an NVIDIA graphics card) | when the two free readers agree on 98% of the letters, Surya's text matched Gemini on every test page; free, and nothing leaves the computer |
| 2 | **Claude** (Opus) | the free readers disagree or Surya is not installed | as accurate as Gemini from 100 dpi up, on the author's Claude plan |
| 3 | **Gemini** (`gemini-3.8-flash`) | a Google API key is set, and Claude refused the page, answered far shorter than the page, or the page is under 100 dpi | the only reader of the vocalized Bible (Claude refuses it) and the better reader under 100 dpi |
| 4 | **Tesseract only** | no Claude and no Google key | free and private, but 2-5% letter errors on Hebrew |

With a Google key set, only the pages in step 3 go to Google; without one, those pages keep the free reading, marked low confidence. The measured numbers, the two-column findings and the Codex option are in `${CLAUDE_PLUGIN_ROOT}/skills/ocr/references/engines.md`. Tell the author, in plain words, which reader read which pages and where they went (Gemini: Google; Claude: Anthropic; Surya and Tesseract: nowhere). If the author asks for one reader for every page, pass `--engine gemini|claude|local`.

Course readings are never OCR'd automatically (user rule 2026-10-19): the student asks for extraction on the dashboard ("חילוץ טקסט"). Beyond the steps above, never move a page to another reader on your own: a page that comes back "blocked" or "low confidence" stays as it is until the author says otherwise. Ask with `AskUserQuestion` before sending it anywhere else, saying where it goes (with Gemini, its text goes to Google). A page Gemini refused is never filled in from another reader without asking. Record which engine produced the text (`OCR engine: <name>`).

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
