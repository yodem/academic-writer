---
name: ingest-book
description: "Upload a whole academic book — a large or scanned PDF, a multi-volume set, or an EPUB — into the author's Trove library as one book with its printed page numbers preserved, a nested navigable table of contents where every entry jumps to its real page and carries a content hint, and a page-1 reading-and-citation guide. Use when the author says 'upload this book', 'ingest these volumes', 'combine these PDFs into one book', 'ingest this EPUB', or when the input is 100+ pages, over ~50MB, or a scanned PDF, and to repair an existing book whose sidebar is an unusable flat list of 'page N' entries. Do NOT use for a single article, paper or chapter — use /academic-writer:ingest."
user-invocable: true
allowed-tools: [Bash, Read, Write, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.2.0", summary: "Upload a whole book (multi-volume, scanned or EPUB) to the source library with a navigable hinted table of contents and a citation guide."}
---

# Ingest a whole book

Turn a whole book — often a large, multi-volume, scanned PDF — into one Trove book that reads page-by-page faithfully AND has a real navigable table of contents: a nested tree where every unit, section and subsection jumps to its actual page. This is the book-scale sibling of `/academic-writer:ingest` (single article or chapter); what makes book scale different is PDFs too big for the Read tool, scan watermarks and RTL bidi noise, several volumes to merge, and — the part everyone gets wrong — making the ToC actually navigate.

Throughout: preserve the ORIGINAL printed page numbers (**cite the printed page, never the Trove page**), give every ToC entry a hint of up to 3 sentences, and make page 1 a "How to read and cite this book" guide.

## 0. Pre-flight

1. Read `.academic-helper/profile.md`. If it does not exist, say nothing is set up yet and point at `/academic-writer:setup` or `/academic-writer:init`; stop.
2. If the profile's Tools section has `"trove": { "enabled": false }` (or the older `"candlekeep"` key), say the source library is disabled and it can be enabled with `/academic-writer:update-tools`; stop.
3. Check the library CLI: run `trove items list --json` (some installations call the same CLI `trove`). If missing, point at `/academic-writer:health`; stop.

## Critical: the ToC is metadata, not page content

ToC rule: one entry per page, "Title - hint", nested in tree order (siblings by page; lesson pages under תמלולי שיעורים). Every page of the book is the start page of its own `Title - hint` entry, nested by level (for a reading that sits in a course book: source level 2, its sections level 3), in page order. After applying the ToC to a course's book, audit it from the plugin repository checkout (repo-local tools, not shipped in the installed plugin): `python3 tools/toc_audit.py --course <slug>`.

Trove's sidebar/outline is built from **ToC metadata** you attach with `trove items enrich <id> --toc '[{"title","page","level"}]'`. It is NOT built from the markdown headings inside a page. A beautiful ToC written into page 1 as `##`/`###` headings makes every entry link back to page 1 — the single most common failure here. Read `references/toc-mechanism.md` before any ToC work, and before "fixing" a flat ToC.

## Bundled scripts

All three encode the tedious, error-prone parts as deterministic code (run from anywhere with absolute paths; each has `-h`). They assume a **PDF** source; for an EPUB see `references/epub-sources.md`.

- `scripts/extract_pdf.py` — PDF → markdown, one `# <label> N` per page, with DRM watermarks and Unicode bidi markers stripped.
- `scripts/build_crosswalk.py` — derive each page's Trove number, per volume, from the uploaded file (Trove skips blank pages, so this cannot be eyeballed).
- `scripts/build_toc_enrich.py` — assemble the `--toc` metadata (printed→Trove with interpolation, nesting levels, hints) and optionally apply it.

**Step 0 — Anna's Archive first, for a published work.** Before any OCR, search Anna's Archive for the work: use the `annas-archive-ebooks` skill when it is installed, otherwise search by title, author and ISBN. For a chapter or article, look for the whole book or journal issue. If a copy of the **same edition** exists (same publisher, year and printed pagination), use its text layer or EPUB text, keep the printed page numbers exactly, and skip OCR. Run Gemini OCR (`aw ocr`) only when there is no matching copy or the copy has no usable text. Record the outcome for each item: `annas: found-used`, `annas: found-wrong-edition` or `annas: not-found`.

OCR (reading the text out of a scanned page) — of body pages or ToC pages — uses the plugin's own reader, `aw ocr` (Gemini, see `/academic-writer:ocr`), unless the author picks another engine. For a scan, ask once with `AskUserQuestion`, in plain words, who should read the pages and say that the pages go to that service: **the plugin's own reader (Gemini)** (default, best for many pages and Hebrew with vowel marks), **Claude** (a few pages, difficult layouts; Anthropic, on the author's Claude plan), **Codex** (only if installed; on the author's Codex plan), or **Tesseract on this computer** (free, nothing leaves the computer, weaker on scans and mixed Hebrew and English). The steps for Claude, Codex and Tesseract are in `${CLAUDE_PLUGIN_ROOT}/skills/ocr/references/engines.md`. For a course reading the default is Claude. Never move pages to another engine on your own: mark unclear pages "OCR, not image-verified" and, if Gemini might read them better, ask with `AskUserQuestion` whether those pages may be sent to Gemini (their text goes to Google). Record the engine used (`OCR engine: <name>`) on the reading page, next to any "OCR, not image-verified" warning.
For library and Kotar readings (in copyright) the author has already chosen Gemini OCR for the course, so use `aw ocr` directly when step 0 finds no usable copy; for any other reading follow the engine choice in this paragraph, and never move pages to another engine without asking.

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" ocr \
  --input <pdf|image> --lang <he|en|mixed> --run <run-id> \
  --format detailed --out <project-local-output.md>
```

**OCR failure handling** (all seen on real runs):

- **Orientation.** Phone scans can render upside down or sideways. Render the first page as an image and read it before trusting OCR; rotate a *copy* and OCR that — never modify the source.
- **One page per call.** Multi-page OCR calls can die on the model's output limit (`MAX_TOKENS`). For scanned pages, pass each page (or a small `--pages` range) in its own `aw ocr` call.
- **Silent truncation.** OCR can report "high" confidence on a page it truncated to a few hundred characters. Compare each page's output length against the page image's text density; a dense page that comes back two lines long is truncated — re-OCR it, and flag it to the author if it stays short.

## Workflow

Five phases; finish and sanity-check each before the next, so a failure is easy to localize. To add a reading to a book that already exists, see "Adding to a book you already have" below instead of Phases B and C.

### Phase A — Survey & Extract

1. **Survey.** Identify the source format — an EPUB takes a much shorter path (`references/epub-sources.md`) and skips Phase C's OCR/crosswalk. Identify files, language/script, number of volumes, and roughly where each volume's ToC pages sit. Get the bibliographic metadata: full title, author(s), one-line description. For large or scanned PDFs, work through the script below rather than reading the whole PDF (you can still render a few pages as images with `pdftoppm` to eyeball structure).
2. **Extract each volume** to clean markdown:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/extract_pdf.py" VOL1.pdf /tmp/vol1.md --page-label "עמוד מקורי"
   ```
   Each `# <label> N` becomes one Trove page; `N` is the PDF page index. Scan the output for leftover scan-junk, adding `--extra-watermark "substr"` / `--drop-solo "Name"` until pages are clean. Keep body text faithful; garbled transliteration from the original scan is acceptable in the body — ToC titles get fixed in Phase C.

*Gate:* extracted pages are clean and page labels match the printed numbering you expect.

### Phase B — Combine & Upload

3. **Combine volumes** into one file: reserve page 1 for the reading guide (fleshed out in Phase C), then for each volume a divider page followed by that volume's pages. Restart page numbering at 1 per volume — `build_crosswalk.py` detects volume boundaries from those resets.
4. **Upload** with `trove items import` — it creates the book and uploads in chunks that cut only at `# ` boundaries (30 MB ceiling; `trove items create` has no `--file` flag, and whole-document `put --file` caps at 1 MB). Record the BOOK_ID it prints.
   ```bash
   trove items import /tmp/combined.md --title "<title>" --no-session
   trove items enrich <BOOK_ID> --author "<authors>" --description "<one-line>" --no-session
   ```

**Never delete or overwrite an existing book.** If the author wants to replace an earlier upload, ask for explicit confirmation, and delete the old book only after the new one passes the read-back below; before deleting, match the old item's id and title exactly against `trove items list --json`.

*Gate:* the reported page count matches what you predicted from the source structure. A mismatch means a stray `# ` split a page — find it before enriching, because every later ToC target is now off by one.

### Phase C — OCR & Enrich

5. **Transcribe the ToC pages** with `aw ocr` (one page or small range per call; watch orientation and truncation as above), then write the entries yourself as a JSON array per volume — `/tmp/toc_entries_v1.json` — one object per ToC row:
   ```json
   {"type": "section", "label": "1.3", "title": "הלוגוס", "page": 101,
    "hint": "הדיון מציג את מושג הלוגוס ומסביר את תפקידו בפרק."}
   ```
   `page` is the PRINTED page from the book's ToC; `type` is one of volume/unit/section/subsection/subsubsection/appendix/frontmatter/endmatter. **The hint is mandatory** — up to 3 sentences describing the entry's content, in the document's language. If a long ToC needs several OCR calls, concatenate the arrays. If ToC entries are missing hints, write them from the content before proceeding.
6. **Build the crosswalk** (printed → Trove page):
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/build_crosswalk.py" /tmp/combined.md --page-label "עמוד מקורי" --out /tmp/crosswalk.json
   ```
   Find each volume's **offset** (`stored = printed + offset`): take a ToC entry with a known printed page, read Trove pages (`trove items read <id>:<ck>`) until you find that content, and compute the difference. Verify 2–3 anchors per volume (first chapter, a famous mid-book section, the index). If anchors disagree by more than one page, do not guess — surface the conflicting anchors to the author and ask which printed page to trust. A confidently-wrong ToC is worse than none.
7. **Build and apply the navigable ToC.** Write a small config (schema and example in `build_toc_enrich.py`'s header) mapping each volume to its entries file, offset, divider Trove page, and title, then:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/build_toc_enrich.py" \
     --config /tmp/toc_config.json --crosswalk /tmp/crosswalk.json \
     --out /tmp/toc_enrich.json --apply <BOOK_ID>
   ```
   Levels: volume=1, unit=2, section=3, subsection=4, sub-subsection=5; appendices/glossary/index=3. Include the appendices, glossary and any combined index — readers specifically want those findable.
8. **Flesh out page 1** as the "How to read and cite this book" guide, built from `${CLAUDE_PLUGIN_ROOT}/skills/ingest/references/reading-page-template.md` (English or Hebrew variant). It carries the full bibliographic record, how the printed page markers work and the rule **cite the printed page, never the Trove page**, the covered pages and gaps, and footnote templates in **three** citation styles: Chicago notes-bibliography (first note + short note), the Hebrew academic convention (שם המחבר, שם הספר, מקום תשנ״ה, עמ׳ N; short form for subsequent notes), and a third style chosen from the profile's `citationStyle` (MLA or APA) so the author's own style always appears. For a primary text it also carries the structural-locus form (chapter/premise/paragraph). Rewrite it in place with `trove items put <BOOK_ID>:1 --file /tmp/reading-guide.md --no-session`. **`put` makes Trove rebuild the whole table of contents from the page headings, so every hint and level is lost: run step 7's command with `--apply <BOOK_ID>` again right after it, and always as the last write to the book.**

### Phase D — Read-back (mandatory)

Never say "uploaded" without this. Run:

```bash
trove items get <BOOK_ID> --no-session
trove items toc <BOOK_ID> --no-session
trove items read <BOOK_ID>:1 --no-session
trove items read <BOOK_ID>:<anchor-ck> --no-session
```

and check all four:

1. **Page count** — total pages equal what you predicted from the source structure (1 reading guide + divider and content pages).
2. **Hints** — every ToC entry carries a hint; depth is present (sub-subsections where the book has them); volume dividers and end-matter appear.
3. **Page 1** — is the "How to read and cite this book" guide with the bibliographic record and all three citation styles.
4. **Printed-page markers and anchors** — content pages carry the printed-page label, and 2–3 spot-checked anchors land on the right content.

Any failed check is a failed upload: report it plainly, fix and re-verify. Wrong page targets almost always mean a wrong offset — fix it and rerun step 7; re-enriching is cheap and non-destructive. Only then tell the author the book is in the library.

### Phase E — Index for PageIndex (only when the author uses it)

After the read-back passes, when a PageIndex helper is ready, index the same book so PageIndex can find pages in it too: the outline is built from the **same hinted table of contents** that is now in Trove, with a short Gemini summary per entry. Ask first and show the Gemini estimate (the dry run gives the number of calls and characters); skip silently when PageIndex is not set up. The Trove upload is already complete and a failure here never undoes it. Details, the question to ask and the failure list: `${CLAUDE_PLUGIN_ROOT}/skills/ingest/references/index-for-pageindex.md`. The command, after the author agreed:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library index \
  --trove-id <BOOK_ID> --run <run-id> [--summaries gemini|hints|none]
```

A book whose table of contents is still flat (`page N` entries) has no hints to build from: repair it first (Troubleshooting below), because PageIndex would otherwise have to find the structure itself with Gemini, which needs the full helper and cannot be priced ahead.

## Adding to a book you already have

When the author wants a reading or volume added to an item that already exists in Trove, do not create a new book. Follow `${CLAUDE_PLUGIN_ROOT}/skills/ingest/references/existing-item.md`: snapshot the table of contents, append the new pages with `trove items append`, re-apply the merged table of contents **last**, run the read-back there, then Phase E for the whole item. Never write new content with `trove items put <id>:<page>`: it resets the whole table of contents and loses every hint and level.

## Troubleshooting

- **ToC links land on the wrong pages** — the offset is wrong. Re-read a known printed page, recompute `offset = stored − printed`, rerun step 7. Re-enrich is non-destructive.
- **Page count came back higher than expected** — a body line starting with `#` became a page break. Find it, escape it, re-import; do not enrich first.
- **A volume's pages didn't map** — `build_crosswalk.py` detects volumes by the page-number reset to 1. If a volume doesn't restart numbering, give it a distinct `--page-label` and crosswalk it separately.
- **`trove items enrich --toc` prints `✓ Enriched` then panics** — a CLI display bug truncating a non-ASCII description on a UTF-8 char boundary. The write already succeeded; ignore it and confirm with `trove items toc <id>`.
- **`pdftoppm`/`pdftotext` unavailable** — install poppler with the user's permission (`/academic-writer:setup` asks before installing), or fall back to PyMuPDF (`fitz`).
- **Indexing for PageIndex failed, but the Trove upload is complete** — run the same `aw library index --trove-id <BOOK_ID>` command again (see the failure list in `references/index-for-pageindex.md` in the ingest skill); it is repeatable and reuses summaries already paid for.
- **Coverage assertion fails while every structural check passes (EPUB)** — see `references/epub-sources.md`: the slicing model is wrong, not the sanitizing.

## Key rules

- **Faithful body text.** Reproduce page content as-is. The author holds a license to the original for personal study; summarizing or paraphrasing without being asked both corrupts the source and oversteps that license.
- **Verify the crosswalk with anchors.** Interpolation plus a wrong offset silently points entries at the wrong pages — always check live content before done.
- **Always pass `--no-session`** on every `trove` command.
- **Never delete or overwrite an existing book** without explicit user confirmation, and only after the new one reads back correctly.

## Boundary with /academic-writer:ingest

This skill is for **whole books**: 100+ pages, multi-volume sets, EPUBs, scanned PDFs, and repairing an existing book's flat ToC. For a single article, paper or chapter, use `/academic-writer:ingest` — it is a shorter page-preserving upload with the same citation-guide page 1 and read-back.
