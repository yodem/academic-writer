# OCR engines: who reads the pages

Used by `/academic-writer:ocr`, `/academic-writer:ingest` and `/academic-writer:ingest-book` when the source is a scan or a photo. All four engines follow the same rules, so the text can be quoted as evidence later:

- Copy the text exactly. Never correct, modernise, paraphrase or summarise it.
- Check the orientation of the first page before anything else; rotate a **copy**, never the source.
- One page per call. Check each page's length against how dense the page looks: a dense page that comes back two or three lines long is truncated; read it again and tell the author if it stays short.
- Tell the author which pages are unclear, short or failed. Mark an unclear word in square brackets instead of guessing it.
- Never overwrite the source file. Write results under the project's `ocr-output/` folder.
- Say which engine produced the text (`OCR engine: <name>`), wherever the text is stored next.

Ask once, with `AskUserQuestion`, in plain words, and say where the pages go:

| Engine | Who reads the pages | Best for | Cost and privacy |
|---|---|---|---|
| **Gemini** (the plugin's own reader, the default) | Google, with the author's Gemini key | many pages, Hebrew with vowel marks, tables | uses the Gemini key; pages are sent to Google (on Google's free tier Google may use them to improve its products) |
| **Claude** | Anthropic, in this session | a few pages, hard layouts; the usual first choice for course readings | uses the author's Claude plan; pages are sent to Anthropic |
| **Codex** | OpenAI, through the Codex program | an author who has Codex and wants to spare Claude or Gemini | uses the author's Codex plan; pages are sent to OpenAI |
| **Tesseract** | this computer only | clean print, private material, no key | free; nothing leaves the computer; weaker on scans, vowel marks and mixed Hebrew and English |

## Gemini (the plugin's own reader)

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" ocr \
  --input <pdf|image|directory> --lang <he|en|mixed> --run <run-id> \
  --format detailed --out <project-local-output.md>
```

Add `--pages <range>` for some pages. Pages that already contain text are extracted without the model.

## Claude reading page images

1. Turn each page into a picture (needs poppler's `pdftoppm`; `/academic-writer:setup` installs it after asking):

```bash
mkdir -p ocr-output/pages
pdftoppm -r 150 -png -f <page> -l <page> <source.pdf> ocr-output/pages/page
```

   The pictures are named `page-<N>.png`, with leading zeros in a long document (`page-007.png`); list the folder to see the exact names.
2. Read the picture with the Read tool, one page at a time, and write what is printed on it into `ocr-output/<name>.md`, one `# Page N` heading per page. Footnotes stay under the page they belong to. For two-column Hebrew pages, read the right column first.
3. Report every page you could not read with confidence. For a course reading, escalate those pages to Gemini.

## Codex reading page images

Only when the `codex` program is installed (`command -v codex`). Make the page pictures as above, then, one page per call:

```bash
codex exec -s read-only -i ocr-output/pages/page-<N>.png "Transcribe this scanned page exactly. Do not correct, translate or summarise. Reply with the page text only."
```

Take the reply as the page text and save it yourself into `ocr-output/<name>.md`. Check that the reply is only the page text, with no commentary of Codex's own, and apply the length check above.

## Tesseract on this computer

Only when `tesseract` is installed (`command -v tesseract`); installing it needs the author's permission, as `/academic-writer:setup` explains for other tools. It also needs the language data for the page's language: `heb` for Hebrew, `eng` for English (`tesseract --list-langs` shows what is there). One page per call:

```bash
tesseract ocr-output/pages/page-<N>.png ocr-output/page-<N> -l heb+eng
```

The text lands in `ocr-output/page-<N>.txt`. Expect more mistakes on scans, vowel marks and mixed right-to-left and left-to-right lines: mark the whole result as `OCR, not image-verified` and offer to read the doubtful pages again with another engine.
