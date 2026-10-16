---
name: ingest
description: "Upload a single academic article or book chapter into the author's Trove library with its printed page numbers preserved, a hinted table of contents, and a page-1 reading-and-citation guide, so research and writing can cite it by the printed page. Use when the author says 'upload this article', 'ingest this paper or chapter', shares a source that is not yet in Trove, or hands you a file with printed page markers or footnotes. Do NOT use for a whole book, a multi-volume set, an EPUB, a 100+ page PDF, or repairing a flat table of contents — use /academic-writer:ingest-book."
user-invocable: true
allowed-tools: [Bash, Read, Write, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.2.0", summary: "Upload one article or chapter to the source library with printed page numbers, hinted contents and a citation guide."}
---

# Ingest an article or chapter

Academic articles and chapters have their own printed page numbers (e.g. 409–415 in a journal). Trove numbers pages sequentially from 1, so without care a reader would cite the wrong page. This skill uploads the source with every printed page number preserved, a hinted contents list, and a **page-1 "How to read and cite this book" guide** with ready-made footnote templates in three citation styles. The rule the whole skill serves: **cite the printed page, never the Trove page.**

## 1. Pre-flight

1. Read `.academic-helper/profile.md`. If it does not exist, say nothing is set up yet and point at `/academic-writer:setup` or `/academic-writer:init`; stop.
2. If the profile's Tools section has `"trove": { "enabled": false }` (or the older `"candlekeep"` key), say the source library is disabled and it can be enabled with `/academic-writer:update-tools`; stop.
3. Check the library CLI: run `trove items list --json` (some installations call the same CLI `trove`). If the command is missing, say the library tool is not installed and point at `/academic-writer:health`; stop.

## 2. Get the text

- **Markdown or text**: read it directly.
- **Word (.docx)**: convert with `pandoc "<file>" -t markdown`; if pandoc is missing, extract the text with Python's `zipfile` and a tag strip.
- **PDF, scan or photo**: a PDF page that already has text is extracted directly; a scan or photo needs OCR (reading the text out of the picture). Use the plugin's own OCR unless the author picks another engine (see "OCR options" below):

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" ocr \
  --input <pdf|image|directory> --lang <he|en|mixed> --run <run-id> \
  --format detailed --out <project-local-output.md>
```

Take `--lang` from the profile's `targetLanguage` when the source language is unclear. Never modify or overwrite the source file.

**OCR options.** For a scan, ask once with `AskUserQuestion` which reader to use, in plain words, and say that the pages are sent to the service that reads them:

| Choice | Who reads the pages | Good for |
|---|---|---|
| **The plugin's own reader (Gemini)** (default) | Google, with your Gemini key | many pages, Hebrew with vowel marks, tables |
| **Claude** | Anthropic, on your Claude plan | a few pages, difficult layouts |
| **Codex** | OpenAI, on your Codex plan (only if Codex is installed) | sparing your Claude or Gemini quota |
| **On this computer (Tesseract)** | nothing leaves your computer; free | clean print, privacy; weaker on scans, vowel marks and mixed Hebrew and English |

The steps for Claude, Codex and Tesseract are in `${CLAUDE_PLUGIN_ROOT}/skills/ocr/references/engines.md`. Whatever the engine, the same rules below apply, and the reading page records which engine produced the text (`OCR engine: <name>`) next to the "OCR, not image-verified" warning.

**OCR failure handling** (each of these has happened on real runs):

- **Orientation.** Phone scans can render upside down or sideways. Render the first page as an image and read it before trusting OCR; if it is rotated, rotate a copy (e.g. `pdftoppm` + image rotation, or `sips -r 180` on a copy) and OCR the rotated copy. Never touch the original.
- **One page per call.** A multi-page OCR call can die on the model's output limit (`MAX_TOKENS`) and produce nothing or partial output. For scanned PDFs or photo folders, pass each page (or a small `--pages` range) in its own `aw ocr` call.
- **Silent truncation.** OCR can report "high" confidence on a page it truncated to a few hundred characters. Compare each page's output length against the page image's text density: a dense printed page that comes back two or three lines long is truncated — re-OCR that page and, if it stays short, flag it to the author instead of uploading it as if complete.
- Report every low-confidence or failed page to the author; do not hide it behind the overall command result.

## 3. Split into printed pages

Identify the printed page boundaries in the text. Page markers can appear as `page NNN:`, `--- page NNN ---`, `עמ' N`, `p. N`, or a bare number line at the block's end. Then:

- **Page number vs footnote number.** A page number is a bare numeric line that fits the printed-page *sequence* (e.g. 24, 25, 26, 27, 31, 32 …). A numeral that breaks the sequence — a footnote number, an apparatus line counter (5, 10, 15, 20), a manuscript folio marker — is not a page number: keep it in place as body data. When two readings are possible, use position (page numbers sit at the very top or very bottom of a block) and the surrounding sequence, and record the choice in the reading page's notes.
- **Non-continuous ranges.** A single file can mix an editor's introduction with commentary and skip whole ranges (e.g. 24–27, 31–45, 160–185). That is fine: each covered printed page becomes a page; record the covered ranges and the gaps on page 1.
- If the structure is genuinely ambiguous, show the author the candidate boundaries and ask.
- Never modify body text: reproduce it verbatim, including awkward wording and typographical errors. Footnotes stay with their page, under a `### Footnotes` heading, with the original numbering preserved.

## 4. Build the document

One `# ` header per Trove page.

- **Page 1** is the "How to read and cite this book" guide, built from `${CLAUDE_PLUGIN_ROOT}/skills/ingest/references/reading-page-template.md` (English or Hebrew variant as fits the source). It carries the full bibliographic record, the marker rule (`page NNN:` / `(orig. N)` — cite the printed page, never the Trove page), the covered pages and gaps, and footnote templates in **three** citation styles: Chicago notes-bibliography (first note + short note), the Hebrew academic convention (שם המחבר, שם הספר, מקום תשנ״ה, עמ׳ N; short form for subsequent notes), and a third style chosen from the profile's `citationStyle` (MLA or APA) so the author's own style always appears. For a primary text it also carries the structural-locus form (chapter/premise/paragraph). OCR pages not verified against the image get the exact `OCR, not image-verified` warning named in the template.
- **Pages 2+** are the content pages, one per printed page:

```markdown
# Original Page 160  (Hebrew source: # עמוד מקורי 160)
**[Original print page: 160]**
[body text verbatim]
### Footnotes
**1.** [footnote text]
```

- The page-1 contents list gives every page an entry in the form `- Page N (orig. M) - [hint of up to 3 sentences describing the entry's content]`, in the document's language. The hint is mandatory and describes content, not just the first line.

## 5. Upload

```bash
trove items import /tmp/article-ingest.md --title "<title>" --no-session
trove items enrich <BOOK_ID> --author "<author>" --description "<one-sentence description>" --no-session
```

Use `trove items import` (it uploads in chunks and handles real documents); `trove items create` has no `--file` flag and whole-document `put --file` caps at 1 MB. Record the `BOOK_ID` it prints. If the upload fails, keep the assembled file and give the author its path.

Then store the contents list as table-of-contents metadata too, so the sidebar and PageIndex read the same outline (the page-1 list alone is only text). One entry per page, page 1 (the reading guide) included, `Title - hint`, level 1, `page` = the Trove page:

```bash
trove items enrich <BOOK_ID> --toc '[{"title":"How to read and cite this book - <hint>","page":1,"level":1},{"title":"Original page 160 - <hint>","page":2,"level":1}]' --no-session
```

(Hebrew source: `עמוד מקורי 160 - <hint>`.) Replacing a page later with `trove items put` resets this list, so apply it last.

**Never delete or overwrite an existing book.** If the author wants to replace an earlier upload, ask for explicit confirmation, and delete the old book only after the new one passes the read-back below; before deleting, match the old item's id and title exactly against `trove items list --json`.

## 6. Read-back (mandatory)

Never say "uploaded" without this. Run:

```bash
trove items get <BOOK_ID> --no-session
trove items toc <BOOK_ID> --no-session
trove items read <BOOK_ID>:2 --no-session
```

and check all four:

1. **Page count** — total pages equal 1 (reading guide) + number of printed pages.
2. **Hints** — every contents entry carries a hint.
3. **Page 1** — is the "How to read and cite this book" guide with the bibliographic record and all three citation styles.
4. **Printed-page markers** — content pages carry `[Original print page: NNN]` (or the Hebrew equivalent) and the printed numbers match the source's sequence.

Any failed check is a failed upload: report it plainly with what you found, fix it and re-verify. Only then tell the author the source is in the library, citing the printed page range they can now cite.

## 7. Index for PageIndex (only when the author uses it)

After the read-back passes, when a PageIndex helper is ready, index the same text so PageIndex can find pages in it too. Ask first, with the Gemini estimate; skip silently when PageIndex is not set up. The Trove upload is already complete and a failure here never undoes it. Details, the question to ask and the failure list: `${CLAUDE_PLUGIN_ROOT}/skills/ingest/references/index-for-pageindex.md`. The command, after the author agreed:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library index \
  --trove-id <BOOK_ID> --run <run-id> [--summaries gemini|hints|none]
```

## Adding to a book you already have

When the author wants this reading added to an item that already exists in Trove (a course book, a collected volume), do not create a new book. Follow `${CLAUDE_PLUGIN_ROOT}/skills/ingest/references/existing-item.md`: snapshot the table of contents, append the new pages with `trove items append`, re-apply the merged table of contents last, run the read-back there, then step 7 for the whole item. Never write new content with `trove items put`; it resets the table of contents.

## Boundary with /academic-writer:ingest-book

This skill is for **one article, paper or chapter** (any length up to a full issue-length article). For a whole book, a multi-volume set, an EPUB, a 100+ page PDF, or repairing an existing book's flat table of contents, use `/academic-writer:ingest-book` — it builds a nested navigable ToC and handles volume merging.
