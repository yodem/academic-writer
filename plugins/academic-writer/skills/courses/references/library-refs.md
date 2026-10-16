# Course references and bookmarks: runbook

For the operator running the `courses` skill who needs to find the works a course cites, get them into the course book, and keep each course's Chrome bookmark folder current. Part A covers references (find, look up, download, OCR, index); Part B covers the bookmark folders and their nightly step.

## Prerequisites and scope

- A registry: `ACADEMIC_COURSES_DIR` or `~/.academic-writer/courses/<term>/`, with `term.json` and one `<slug>.json` per course (see `SKILL.md`).
- `pandoc` on the PATH. `refs.py extract` shells out to it; `status`, `chores` and `index` do not need it.
- The `trove` CLI, for book edits. Check `trove auth whoami --no-session` first.
- A Chrome window signed in to the BIU library proxy, for the download steps only. Lookups need no login.
- Book writes happen one at a time, after the owner confirms no other session is writing to that book.

Built versus planned, as of this runbook:

| Piece | State |
|---|---|
| `refs.py` subcommands `extract`, `lookup`, `status`, `chores`, `index` | Built (`src/scripts/courses/refs.py`) |
| `add-source --origin library` | Built (`ORIGINS` in `courses.py`) |
| `courses.py bookmarks` with `--print-script`, `--check`, apply | Built (`src/scripts/courses/bookmarks.py`) |
| Bookmark items for Trove (book and reading pages) | Not built: `TROVE_URL_FORM` is `None`, so those items are left out (B2) |
| Nightly `bookmarks` step after the digest | Built in `scripts/courses-daily.sh.example` |
| Kotar image download by token | Recipe in A6, proven by hand; not scripted |

## Part A: references

### A1. Find the cited works

Inputs for each course, all under the registry:

- every `.docx`, `.pptx` and `.pdf` in `sources/<slug>/`;
- `lessons/<slug>/*/transcript.txt`;
- the syllabus and the course opening, when they name readings.

`refs.py extract` reads `.docx` and `.pptx` through `pandoc -t markdown`, so footnotes come out as `[^n]`. It skips `.pdf` because `pandoc` cannot read PDFs; check PDFs by hand. Transcript mentions are spoken, so every candidate from a transcript is recorded as `(transcript, unverified)`.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/courses/refs.py" --term <term> extract <slug>
```

The default run prints the candidates and one sanity line per file: its `עמ'` or `pp.` hit count next to the refs it produced. The two should roughly match; a large gap means a source was missed or a footnote was not parsed. Nothing is written until you re-run with `--write`, and `--only KEY` (repeatable) writes just the keys you confirmed. An existing ref's status is never overwritten.

### A2. The record: `refs/<slug>.json`

```json
{
  "course": "<slug>",
  "_note": "<free text>",
  "refs": [
    {
      "key": "<author>-<year>-<short-slug>",
      "citation": "<citation as the course gives it>",
      "pages_cited": "<pages>",
      "role": "quoted",
      "found_in": "<file or lesson; add (transcript, unverified) for spoken mentions>",
      "status": "pending",
      "note": ""
    }
  ]
}
```

- `key` is the dedupe key. Do not rename it after it is written.
- `role` is one of:
  - `quoted`: text the lesson quotes;
  - `expansion`: an optional reading the course offers for further study;
  - `assignment`: a researcher an assignment names, who must be remembered for the exam;
  - `required`: a reading the course requires.
- `status` is one of `pending`, `online`, `downloaded`, `ingested`, `kotar`, `print-only`, `not-found`. A6 to A8 say what each one needs next.
- Fields that `lookup --set` adds: `target_url` (for `online`), `call_number` (for `print-only`), `trove_url` (for `ingested`).

### A3. The `refs.py` subcommands

Every command takes `--term <term>` (or the `ACADEMIC_TERM` variable) and optionally `--registry <dir>`.

| Command | What it does | Exit |
|---|---|---|
| `extract <slug> [--write] [--only KEY] [--json]` | Lists citation candidates from sources and transcripts; `--write` adds them as `pending` refs | 0; 2 on a refs error |
| `lookup <slug> [--key K] [--query Q]` | Prints up to three Primo hits per pending ref as JSON. Changes nothing | 0 |
| `lookup <slug> --set K --status S [--note N] [--target-url U] [--trove-url T] [--call-number C]` | Records your decision. `--status` is required; `online` needs `--target-url` | 0; 2 on error |
| `status [<slug> \| --all]` | Counts per status | 0 only when nothing is `pending`; 1 otherwise |
| `chores <slug> [--apply]` | Plans one chore per `kotar`, `print-only` and `not-found` ref. `--apply` adds them with `courses.py chores add` | 0 |
| `index <slug>` | Prints the `מקורות נזכרים` page as markdown, rendered from `refs.json` | 0 |

`status` is the gate: a course's refs count as done only when `status <slug>` exits 0.

### A4. Lookup and Primo classification

`lookup` queries the BIU Primo public API, which needs no login:

```
GET https://biu.primo.exlibrisgroup.com/primaws/rest/pub/pnxs?q=any,contains,<query>&vid=972BIU_INST:BIUNDE&tab=Everything&scope=MyInst_and_CI&inst=972BIU_INST&skipDelivery=N
```

From each hit it reads `delivery.availability` (`fulltext`, `available_in_library`, `not_restricted`), then the Alma CTO record for the services. The script proposes; you decide.

- **Choose the hit yourself.** Confirm the author, title and year. A query can return other works first (a Kaufmann citation did), so pick the right work or record `not-found`; never take the first hit.
- **Classify by package:**

  | Package in the CTO record | Status |
  |---|---|
  | `Kotar` | `kotar` |
  | JSTOR, Taylor & Francis, Brill, Magnes and similar | `online`, with `--target-url` set to the OpenAthens redirector link |
  | No services, but `available_in_library` | `print-only`, with `--call-number` from `delivery.holding` |
  | Anything else | Look further (A5, no-hit path) |

- **No hit:** try a title fragment, then the publisher or journal site (JANES is open access), Google Scholar, and RAMBI. For a book chapter, Anna's Archive is the last resort. Never use Anna's Archive for a Kotar item. When nothing is found, record `not-found`.

### A5. Downloads (Chrome only)

Use Chrome only for the steps a script cannot do: a logged-in download, a terms page, a captcha.

1. Open the ref's `target_url` in the signed-in Chrome.
2. A JSTOR terms page appears once. The user accepts it; get their OK first.
3. A JSTOR PDF opens in the viewer. Save it from the page, not from a link:
   ```js
   const blob = await (await fetch(location.href)).blob();
   const a = document.createElement('a');
   a.href = URL.createObjectURL(blob);
   a.download = '<key>.pdf';
   a.click();
   ```
4. Move each download into its own new, empty directory before you open it. Run any Python that reads it with `python3 -I`.
5. Check the page count and that the text is readable before you record `downloaded`.
6. After two failed tries, stop and make a `manual` chore (A8).

Record each result with `refs.py --term <term> lookup <slug> --set <key> --status downloaded --note "<where it is>"`.

### A6. Kotar: fetch the cited pages

Kotar items are read through the user's own BIU licence, for their own study. Fetch only the cited pages. Use this token route; add a chore only after two failures.

1. Open the Kotar viewer for the book through the OpenAthens proxy host. Its book id comes from the URL; keep it out of shipped files.
2. Kotar page indices are not printed page numbers. The print validator in the print dialog's iframe (`CheckPageStart(null, {Value})`) says which labels are valid. Map label to index once per book; the offset comes after the front matter. Never press "send" in Chrome's native print preview: it freezes the browser tool.
3. In the signed-in viewer tab, `fetch()` the print-pages URL for the range, in batches of at most 10 pages (Kotar's own print limit). Parse the `<img src>` values and save them through a blob `a.download`. The image host is cross-origin, so the page cannot read the bytes itself.
4. Each image URL carries a `gPageToken`. Fetch the image with `curl -L`, with no cookies; `-L` follows the http-to-https redirect. The `nStep` parameter sets the size: step 9 gives about 1354 × 1807 pixels, and steps 10 and above return a small placeholder.
5. Merge the images in page order into one PDF, then OCR it (A7).

The browser tool may refuse output that contains query strings, so report counts, not URLs.

### A7. OCR and ingest

- OCR: Claude vision first, after `pdftoppm -r 150`. Send pages Claude flags as unreadable to the bundled Gemini OCR (`/academic-writer:ocr`).
- Never trust `pdftotext` on JSTOR Hebrew text layers: they come out reversed.
- Ingest the file as a library source:
  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py" add-source <file> --course <slug> --origin library --origin-ref <key>
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py" check-source <slug> --sha <sha8>
  ```
  `check-source` must exit 0. Then follow `SKILL.md` (Course sources) for `source-done` and the Trove placement.
- Record the ref as `ingested` with `--trove-url` pointing to its appendix page.

### A8. Chores for what cannot be downloaded

`refs.py --term <term> chores <slug>` plans them; `--apply` adds them.

| Ref status | Chore kind | What the chore asks for |
|---|---|---|
| `kotar` | `kotar-source` | Download the cited pages from Kotar |
| `print-only` | `manual` | Get the print copy from the library, with the call number |
| `not-found` | `manual` | Find the work; the citation is in the text |

Chores are deduplicated on course, kind and `ref` (`refs:<slug>:<key>`), so a re-run does not add a second one. Show them with `courses.py chores digest`.

### A9. The index page and the book layout

Each course book ends with a `מקורות נזכרים` section: an index page with one line per ref (citation, role, status, where it was cited, and a Trove page link for ingested refs), followed by one appendix page per ingested article.

- Generate the index with `refs.py --term <term> index <slug>`. It is rendered from `refs.json`, so regenerate it rather than editing it by hand. Keep its "Load this page when:" line.
- The appendices live in the `חומרי קריאה` section. `add-source` writes each source at level 2 under the level-1 `חומרי קריאה` entry (`READINGS` in `trove_source.py`, line 24). So the only new page is the index.
- Every page needs its own ToC entry titled `Title - hint`, in page order. Level-1 blocks sit in page order too. The Changelog once sat after `חומרי קריאה` (out of order, page 3 after page 4); `trove_source.py` now sorts top-level blocks by first page, and `tests/tools/test_trove_source.py` covers it.

#### Writing pages and the ToC

`trove items append` and `trove items put` regenerate the book's ToC, which flattens any hand-built sidebar. So, for an ordinary book:

1. Extend the ToC plan (`toc-work/<slug>.plan.json`) and the hints file first.
2. Write the pages: `trove items append <id>`, or `trove items put <id>:<page>` to replace one page.
3. Re-apply the plan with `trove items enrich`, taking the version to start from via `trove items history --json`.
4. Run `python3 tools/toc_audit.py --course <slug>` and wait for exit 0.

Books whose assignment blocks are built by `assignment_toc.py` follow different rules:

- **Never re-apply `toc-work/<slug>.plan.json` over them.** Their level-1 blocks ("מקורות ראשוניים", "מקורות משניים") repeat start pages on purpose, so re-applying the plan breaks page order and removes the blocks. `assignment_toc.py` lives in the course-book tools checkout, not in this plugin.
- Run `assignment_toc.py` **without** `--base-toc`: it reads the live ToC and strips only its own blocks. Skip it when no task or spec changed. Use `--base-toc` only right after a `trove items put`, which writes the snapshot it starts from.

`toc_audit.py` exempts entries under level-1 titles that start with "מקורות ראשוניים" or "מקורות משניים" from its duplicate and order checks. `מקורות נזכרים` is not exempt: it is an index page, and it must pass those checks.

## Part B: Chrome bookmark folders

`courses.py bookmarks [<slug> | --all] [--print-script] [--check]` rebuilds each course's Chrome folder through AppleScript. It replaces the folder's items, so running it twice changes nothing the second time.

### B1. The folder

- Root: `Bookmarks bar › BIU <term>`, where `<term>` is the term name from `term.json`.
- Course folder: the course's `name`.
- The root and course folders are created when missing. The course's existing items are deleted and re-created.

### B2. The items

This is the built behaviour in `bookmarks.py` (`plan`). Items are added in this order, and an item with an empty title or URL is left out.

| # | Item | URL | State |
|---|---|---|---|
| 1 | NotebookLM | `https://notebooklm.google.com/notebook/<notebook_id>` | Built, when `notebook_id` is set |
| 2 | Trove book | from `trove_url(book_id)` | Not built: `TROVE_URL_FORM` is `None`, so no URL is produced |
| 3 | Lemida | `<term lemida.base_url>/course/view.php?id=<lemida_course_id>` | Built, when both are set |
| 4 | Current task | `<base_url>/mod/view.php?id=<ref>` | Built, when the task's `ref` is numeric. The task is the course's open chore with the earliest `due_at`; undated chores come after the dated ones |
| 5 | That task's readings | one item per `core_texts` entry that matches a source title and has a Trove `book_id` and `page` | Not built yet: it needs the Trove URL form. Until then, no reading items are added |

So today a course gets up to three items (1, 3 and 4), not the five the spec asks for. To finish items 2 and 5, confirm a Trove URL form that the repo's other skills already use, set `TROVE_URL_FORM` to a template with `{book_id}` and `{page}` placeholders, and add a test. Do not guess the form.

### B3. Commands and exit codes

| Command | What it does | Exit |
|---|---|---|
| `courses.py bookmarks --all --print-script` | Prints the AppleScript and exits; Chrome is not touched | 0 |
| `courses.py bookmarks --all --check` | Read-only; compares the Chrome folder with what applying would write | 0 when up to date; 1 when applying would change Chrome |
| `courses.py bookmarks --all` | Applies through `osascript` | 0 written; 5 when Chrome is not running or `osascript` fails; 2 on a usage error (give a slug or `--all`) |

Chrome must be open for the apply and check runs. The generated script escapes `"` and `\`, keeps Hebrew text, and gives byte-identical output for the same registry.

To open a course's items, right-click its folder in Chrome's bookmarks bar and choose "Open all in new tab group".

### B4. The nightly step

`scripts/courses-daily.sh.example` runs `courses.py bookmarks --all` right after the digest (`chores digest`), as step g. Exit 5 is logged and is not fatal, and the script's exit status does not change. With `COURSES_DRY=1` the step prints its planned command as a `PLAN:` line. The live nightly script is maintained separately, not by this plugin.

## Verification

Run these from the plugin checkout, against the registry:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/courses/refs.py" --term <term> status --all   # 0 when nothing is pending
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py" bookmarks --all --print-script > /dev/null   # 0; Chrome untouched
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py" bookmarks --all --check   # 0 when up to date
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py" check-source <slug> --sha <sha8>
python3 tools/toc_audit.py --course <slug>
```

Pass means exit 0 on the command's own output. A `pending` ref, a changed Chrome folder or a failing audit is reported as a failure, not as work in progress.

Unknown, not yet verified:

- The Trove URL form for book and page links (B2).
- Whether the Kotar image route works for every book; the recipe in A6 was proven on one book.
- The "Open all in new tab group" step is the user's own Chrome workflow; the repo does not test it.

## Related

- `SKILL.md`: the registry, `add-source`, `check-source` and the nightly scan.
- `course-book.md`: the book layout and the ToC rule.
- `lemida-watch.md`: the Chrome watcher, which also drives the signed-in browser.
