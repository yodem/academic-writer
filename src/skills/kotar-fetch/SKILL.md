---
name: kotar-fetch
description: "Download the cited pages of a book on Kotar (CET, through the Bar-Ilan OpenAthens proxy) as one PDF in printed-page order, for the author's own study. Use when a course reading, an assignment's core text or a `kotar-source` chore points at a Kotar book (`kotar` in the URL, `nBookID=`), or a Primo record links to Kotar. Needs a Chrome tab signed in to the Kotar viewer. Not for books on disk (use /academic-writer:ingest-book) or other publisher readers."
user-invocable: true
allowed-tools: [Bash, Read, Write]
metadata: {author: "Yotam Fromm", version: "0.1.0"}
---

# Academic Writer — Kotar Fetch

Kotar shows a book as page images, one per page token. A token can only be read from a signed-in viewer tab, so the browser does exactly one thing: list the tokens. Everything else is a script: `${CLAUDE_PLUGIN_ROOT}/scripts/kotar/kotar_fetch.py` (below, `kf`).

**Scope:** only the cited pages or chapter, for the author's own study under their institution's licence. Never a whole book.

## 0. Anna's Archive first

**Step 0 — Anna's Archive first, for a published work.** Before fetching from Kotar and before any OCR, search Anna's Archive for the work: use the `annas-archive-ebooks` skill when it is installed, otherwise search by title, author and ISBN. For a chapter or article, look for the whole book or journal issue. If a copy of the **same edition** exists (same publisher, year and printed pagination), use its text layer or EPUB text, keep the printed page numbers exactly, and skip OCR. Run Gemini OCR (`aw ocr`) only when there is no matching copy or the copy has no usable text. Record the outcome for each item: `annas: found-used`, `annas: found-wrong-edition` or `annas: not-found`. A same-edition copy also makes the Kotar fetch unnecessary; fetch from Kotar only when it is `found-wrong-edition` or `not-found`.

## 1. Book id

- A Kotar URL carries it: `Viewer.aspx?nBookID=<id>`.
- Otherwise use the Primo record (`primaws/rest/pub/pnxs`, no login needed): its `pnx.links.backlink` entries look like `kotar.co.il/KotarApp/Viewer.aspx?nBookID=<id>$$D<volume label>`. Pick the volume that holds the cited pages.
- Open the viewer in Chrome: `https://kotar-cet-ac-il.eu1.proxy.openathens.net/KotarApp/Viewer.aspx?nBookID=<id>`. If it lands on a login page, ask the author to sign in and wait.

## 2. Tokens (the only browser step)

**Never open the viewer's print dialog or press its "שלח" button.** Chrome's native print preview freezes claude-in-chrome.

1. Print the snippet: `python3 kf tokens-js <book_id> <start_idx> <end_idx>`. It fetches `PrintPages.aspx` with the tab's credentials in batches of at most 10 pages (Kotar's own print limit), reads every `<img src>` for `gPageToken=<uuid>`, and returns the uuids **with dashes replaced by spaces**. The browser tool blocks output that looks like URL query data, and a blob download is held by Chrome's "multiple downloads" prompt, so do not change that format.
2. Run it with `javascript_tool` in the viewer tab. Keep its leading `await`: without it the tool returns `{}` for the pending promise. Save the returned text verbatim to `<out_dir>/tokens.txt`.

Indices are not printed page numbers. On a new book, fetch a small probe (2–3 indices near the cited pages), read the printed number on the image, and get a first guess with `python3 kf offset <index> <printed> --pages <A-B>`. That guess is only a guess: plates can shift the mapping anywhere in a range. Some books number their plates (Gilad's plates are pp. 322 and 324, so the offset holds). Others, such as אנציקלופדיה מקראית, insert unnumbered plates (`לוח יח`) that shift every later index. An encyclopedia page carries two numbered columns, so use `--step 2` and number the page by its first column.

## 3. Pages, verify, merge

```bash
python3 kf fetch <out_dir> --tokens-file <out_dir>/tokens.txt --start-idx <I> --first-page <A> [--step 2] --last-page <B>
python3 kf peek <out_dir>                     # strips of the header and footer of every batch's first and last image
python3 kf check <out_dir> --seen <I>:<A> --seen <idx>:<n|plate> ...
python3 kf merge <out_dir> ~/Downloads/<refs-key>.pdf
```

- `fetch` curls each token with no cookies at `nStep=9` (about 1341×1807 JPEG). Higher steps return a 6 KB placeholder, so each page must be a JPEG over 20 KB. A failure is retried once, then listed, and the command exits 1. Images are named `iNNNN.jpg` by Kotar index, so book order survives plates. `manifest.json` records each fetch as a segment (start index, the printed page expected there, the step) with its batches of 10.
- **Verify the first AND the last image of every batch. Never assume the mapping.** Read the printed numbers off `peek`'s sheet (or the images themselves) and pass every one to `check` as `--seen IDX:PRINTED`, or `IDX:plate` for an unnumbered plate. `check` compares each against the expected number and exits 1 on any end it has not seen, any mismatch, any failed page, or a range that stops short of `--last-page`.
- **On a mismatch, re-probe; never guess.** Peek every image in that batch to find where the numbering moved. Then either declare the unnumbered plates (`check --plate IDX`), which shifts the expected numbers after them, or, when the numbering jumps, fetch again from the first wrong index as a new segment with the printed page actually seen there. Seeing a plate where a page was expected stays a mismatch until you declare it. When plates use up indices, `check` reports the range as short: fetch the next indices as another segment and check again.
- `merge` refuses to run until `check` has passed. Any new `fetch` clears that pass. It writes one PDF in index order (PIL; no img2pdf or ImageMagick needed).

## 4. After

- Report: ref, book id, printed pages, PDF path, any plates and any failed pages.
- **Transcription and upload (the author's rule for library and Kotar readings, which are in copyright and fetched under the author's own licence):**
  - The text comes from Gemini OCR with `/academic-writer:ocr`, not from Claude transcribing the page images.
  - It goes to the course's Trove book (with `/academic-writer:ingest`) and to its NotebookLM notebook with exact printed pagination: one marker per printed page, or per column for an encyclopedia.
  - The original PDF goes to the course's Drive folder.
  - If a tool or the classifier still blocks a step, stop that item and report it. Never work around the block.
- Course-book writes go through the book's writer lock (the term's `WRITERS.md`), at the reading's place in the `חומרי קריאה` section.
- If a book is not on Kotar, or a fetch still fails after one retry, add a `kotar-source` chore (`courses.py chores add --kind kotar-source ...`) saying what to fetch by hand.
