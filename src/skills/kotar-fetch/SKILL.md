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

## 1. Book id

- A Kotar URL carries it: `Viewer.aspx?nBookID=<id>`.
- Otherwise use the Primo record (`primaws/rest/pub/pnxs`, no login needed): its `pnx.links.backlink` entries look like `kotar.co.il/KotarApp/Viewer.aspx?nBookID=<id>$$D<volume label>`. Pick the volume that holds the cited pages.
- Open the viewer in Chrome: `https://kotar-cet-ac-il.eu1.proxy.openathens.net/KotarApp/Viewer.aspx?nBookID=<id>`. If it lands on a login page, ask the author to sign in and wait.

## 2. Tokens (the only browser step)

**Never open the viewer's print dialog or press its "שלח" button.** Chrome's native print preview freezes claude-in-chrome.

1. Print the snippet: `python3 kf tokens-js <book_id> <start_idx> <end_idx>`. It fetches `PrintPages.aspx` with the tab's credentials in batches of at most 10 pages (Kotar's own print limit), reads every `<img src>` for `gPageToken=<uuid>`, and returns the uuids **with dashes replaced by spaces**. The browser tool blocks output that looks like URL query data, and a blob download is held by Chrome's "multiple downloads" prompt, so do not change that format.
2. Run it with `javascript_tool` in the viewer tab. Keep its leading `await`: without it the tool returns `{}` for the pending promise. Save the returned text verbatim to `<out_dir>/tokens.txt`.

Indices are not printed page numbers. On a new book, first fetch a small probe batch (2–3 indices near the cited pages), look at the page image to read its printed number, and compute the offset: `python3 kf offset <index> <printed> --pages <A-B>` prints the offset and the index range for printed pages A–B. Plates can sit inside the sequence. Some books number them (Gilad's plates are pp. 322 and 324, so the offset holds); others, such as אנציקלופדיה מקראית, insert unnumbered plates (`לוח יח`) that shift every later index. When the range is more than a few pages, check every page's running header, not only the first and last, and fetch the extra indices that the plates cost. An encyclopedia page carries two numbered columns: map the cited columns to pages the same way.

## 3. Pages, check, merge

```bash
python3 kf fetch <out_dir> --tokens-file <out_dir>/tokens.txt --first-page <A>
python3 kf merge <out_dir> ~/Downloads/<refs-key>.pdf
```

- `fetch` curls each token with no cookies at `nStep=9` (about 1341×1807 JPEG). Higher steps return a 6 KB placeholder, so each page must be a JPEG over 20 KB. Failures are retried once, then listed, and the command exits 1. Pages are named `pNNNN.jpg` by printed page, and `manifest.json` records the result.
- **Verify by eye** before merging: Read the first and last page images and confirm their printed page numbers are A and B. A wrong first page means a wrong offset: recompute it and fetch again.
- `merge` writes one PDF in printed-page order (PIL; no img2pdf or ImageMagick needed).

## 4. After

- Report: ref, book id, printed pages, PDF path, any failed pages.
- To put the PDF in a course book, use `/academic-writer:ingest` under the book's writer lock (the term's `WRITERS.md`), at the reading's place in the `חומרי קריאה` section, with printed page numbers kept.
- If a book is not on Kotar, or the fetch still fails after one retry, add a `kotar-source` chore (`courses.py chores add --kind kotar-source ...`) saying what to fetch by hand.
