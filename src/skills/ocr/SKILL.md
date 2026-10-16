---
name: ocr
description: "Turn a scanned PDF or photographed page (or a folder of them) into plain text, choosing who reads the pages: the bundled Gemini reader (default), Claude, Codex or Tesseract on this computer; pages that already contain text are extracted directly. Use when the author has a scan, photo or screenshot of a source and needs its text before research or writing. Takes a file or folder path."
user-invocable: true
allowed-tools: [Bash, Read, Write, Glob, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.2.0", summary: "Turn a scan or photo into plain text with Gemini, Claude, Codex or Tesseract, your choice."}
---

# Academic Writer — OCR

OCR (optical character recognition) reads the text out of a scanned or photographed page. Transcribe a PDF, an image, or a folder of them. OCR copies the source text exactly: it never corrects, modernises or paraphrases it, because the text may later be quoted as evidence.

**Step 0 — Anna's Archive first, for a published work.** Before any OCR, search Anna's Archive for the work: use the `annas-archive-ebooks` skill when it is installed, otherwise search by title, author and ISBN. For a chapter or article, look for the whole book or journal issue. If a copy of the **same edition** exists (same publisher, year and printed pagination), use its text layer or EPUB text, keep the printed page numbers exactly, and skip OCR. Run Gemini OCR (`aw ocr`) only when there is no matching copy or the copy has no usable text. Record the outcome for each item: `annas: found-used`, `annas: found-wrong-edition` or `annas: not-found`.

**Who reads the pages is the author's choice.** Ask once with `AskUserQuestion`, in plain words, and say where the pages go (skip the question when the author already named an engine):

| Choice | Who reads the pages | Good for |
|---|---|---|
| **The plugin's own reader (Gemini)** (default) | Google, with the author's Gemini key | many pages, Hebrew with vowel marks, tables |
| **Claude** | Anthropic, in this session | a few pages, hard layouts |
| **Codex** | OpenAI, if the `codex` program is installed | sparing Claude or Gemini quota |
| **On this computer (Tesseract)** | nothing leaves the computer; free | clean print, private material; weaker on scans and vowel marks |

The commands and rules for Claude, Codex and Tesseract are in `${CLAUDE_PLUGIN_ROOT}/skills/ocr/references/engines.md`; read it when the author picks one of them. For course readings Claude goes first. Whatever engine the author chose, never move a page to another engine on your own: mark unclear pages "OCR, not image-verified" and, if Gemini might read a page better, ask with `AskUserQuestion` whether that page may be sent to Gemini (its text goes to Google). Record which engine produced the text. The steps below are for the plugin's own reader.

For library and Kotar readings (in copyright) Gemini is the default (user ruling 2026-10-16): use `aw ocr` directly when step 0 finds no usable copy; for any other reading ask which engine first. For scans, Gemini produces the page text. Tesseract runs only as a silent hallucination check (similarity vs the Gemini text) and its text never enters a source. Pages that drift past the gate are flagged for the user. Pages where Gemini returns empty (a copyright/recitation block) are marked "blocked" and surfaced: never fall back to Claude-vision transcription and never substitute Tesseract text.

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
