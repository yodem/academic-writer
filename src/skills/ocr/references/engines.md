# OCR engines: who reads the pages

Used by `/academic-writer:ocr`, `/academic-writer:ingest` and `/academic-writer:ingest-book` when the source is a scan or a photo. All four engines follow the same rules, so the text can be quoted as evidence later:

- Copy the text exactly. Never correct, modernise, paraphrase or summarise it.
- Check the orientation of the first page before anything else; rotate a **copy**, never the source.
- One page per call. Check each page's length against how dense the page looks: a dense page that comes back two or three lines long is truncated; read it again and tell the author if it stays short.
- Tell the author which pages are unclear, short or failed. Never switch engine on your own: a page goes to a different engine (above all to Gemini, which sends the text to Google) only after the author says yes to that question. Mark an unclear word in square brackets instead of guessing it.
- Never overwrite the source file. Write results under the project's `ocr-output/` folder.
- Say which engine produced the text (`OCR engine: <name>`), wherever the text is stored next.

## Which engine: the tier order (measured 2026-10-20)

`aw ocr` picks the engine itself unless the author named one (`--engine gemini|claude|local`), and its output says which engine ran and why (`engine`, `engine_reason`):

1. **Gemini** (`gemini-3.8-flash`), when a Google API key is set. It ties Claude on accuracy down to 100 dpi, and it is the more accurate reader below 100 dpi and on canonical texts (the vocalized Bible), which Claude refuses to transcribe whole.
2. **Claude** (Opus, on the author's Claude plan), when there is no Google key. It is accuracy-equal at 100 dpi and up, and the fastest and most consistent of the strong readers. Pages under 100 dpi come back flagged "low resolution: verify".
3. **On this computer** (Tesseract), when neither is available, or when the author wants nothing to leave the computer. It is free, but it makes 2-5% letter errors on Hebrew and about 23% on English pages, so its text is marked "OCR, not image-verified".

Measured on 52 page images (Hebrew and English academic pages at 200, 150, 100 and 75 dpi, blurred and compressed; the vocalized Bible; 10 real scans from 74 to 600 dpi) plus 15 two-column pages, one page per call, letters-only error rate:

| Engine | Error, 100-200 dpi | Error, 75 dpi | Two-column pages | Refuses |
|---|---|---|---|---|
| gemini-3.8-flash | about 0.3% | 0.3% | right order, 0.1-1.4% | rarely: one copyrighted English page |
| Claude Opus 5.5 | about 0.3% | 0.95% (guesses words) | right order, 0-1% | every full page of the vocalized Bible |
| gemini-2.5-flash (the old route) | 3.5-5.3% | 4.8% | not tested | |
| Tesseract | 1.3-5% Hebrew, about 23% English | 18% | right order, 1-9% | never |

Two-column pages need no special handling: every model kept the columns in reading order, and cutting the page into columns first made results worse. Tell the author the tier that ran, in plain words, before showing the text.

Ask, with `AskUserQuestion`, only when the author wants a different engine than the tier order gives, and say where the pages go:

| Engine | Who reads the pages | Cost and privacy |
|---|---|---|
| **Gemini** (the plugin's own reader) | Google, with the author's Gemini key | uses the Gemini key; pages are sent to Google (on Google's free tier Google may use them to improve its products) |
| **Claude** | Anthropic | uses the author's Claude plan; pages are sent to Anthropic |
| **Codex** | OpenAI, through the Codex program | uses the author's Codex plan; pages are sent to OpenAI |
| **Tesseract** | this computer only | free; nothing leaves the computer |

## Gemini, Claude or Tesseract through `aw ocr`

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" ocr \
  --input <pdf|image|directory> --lang <he|en|mixed> --run <run-id> \
  [--engine auto|gemini|claude|local] --format detailed --out <project-local-output.md>
```

Add `--pages <range>` for some pages. Pages that already contain text are extracted without any engine. A page an engine refuses comes back empty and marked "blocked"; it is never filled in from another engine without asking the author.

## Claude reading page images in this session (by hand)

`aw ocr --engine claude` is the measured Claude path. Read pages by hand only for a few pages the author wants checked against the image.

1. Turn each page into a picture (needs poppler's `pdftoppm`; `/academic-writer:setup` installs it after asking):

```bash
mkdir -p ocr-output/pages
pdftoppm -r 150 -png -f <page> -l <page> <source.pdf> ocr-output/pages/page
```

   The pictures are named `page-<N>.png`, with leading zeros in a long document (`page-007.png`); list the folder to see the exact names.
2. Read the picture with the Read tool, one page at a time, and write what is printed on it into `ocr-output/<name>.md`, one `# Page N` heading per page. Footnotes stay under the page they belong to. For two-column Hebrew pages, read the right column first.
3. (A Gemini "blocked" page is never transcribed here without asking.) Report every page you could not read with confidence, and mark it "OCR, not image-verified". **Never send a page to Gemini (or to any other engine) on your own, even for a course reading:** the author chose Claude, and Gemini would send the page text to Google. If another engine might read a page better, ask with `AskUserQuestion` whether this page may be sent to Gemini, saying plainly that its text goes to Google; only on a yes, run `aw ocr` for that page alone. The same rule applies to every switch of engine (Claude, Codex, Tesseract, Gemini): ask first.

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
