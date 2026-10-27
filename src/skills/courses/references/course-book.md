# The course book

Each course has one plain Trove book (the course JSON's `book_id`), and no manuscript. Course books are read and
written only by `/academic-writer:courses` and `/academic-writer:lesson-notes`, through the registry's `book_id`;
other sessions are not told about them. These are the rules every write follows.

## Layout

- **Page 1, `Course · <course name>`:** the course index. It states what the course is and starts with a
  `> Load this page when:` line. It names where each unit, lesson and reading sits in the book, and carries the id
  lines that `tools/book_audit.py` checks: `תיקיית Drive: <link>`, `מחברת NotebookLM: <id>` and
  `למדה: מזהה <id>` (or `למדה: אין` when the course has no Lemida id).
- **`תמלולי שיעורים`:** the lesson entry page, which explains the course. Each lesson page
  (`שיעור NN · <date>`, written by `/academic-writer:lesson-notes`) sits under it in the sidebar.
- **`Course · Changelog`:** dated entries (new uploads, assignment deadlines, changes), newest first. Never delete
  an earlier entry.
- **`חומרי קריאה`:** the list of readings and where each one sits in the book. One chapter per unit or lesson,
  holding the extracted reading text, lecture notes and a short summary. Readings are cited by their printed page.
- Every page heading starts with its chapter prefix and ` · ` (for example `Unit 03 · <title>`; course-wide
  pages use `Course · `), and every page keeps a `> Load this page when:` line.

## Table of contents

One entry per page, written as `Title - hint`, nested in tree order: siblings in page order, lesson pages under
`תמלולי שיעורים`, readings (with their sections) under `חומרי קריאה`. Trove builds the sidebar from the ToC
metadata (`trove items enrich <book_id> --toc ...`), not from headings in the pages. Rebuild it with
`tools/toc_rebuild.py` after appending pages; `tools/toc_audit.py --all` must exit 0.

**Replacing a page resets the whole ToC.** `trove items put <book_id>:<page>` makes Trove regenerate the book's
ToC from the page headings: every hint and the nesting are lost, for all pages, not just the edited one. After a
`put`, run `toc_rebuild.py --course <slug> --hints <registry>/toc-work/hints.json --apply` and confirm with
`toc_audit.py --course <slug>`. The rebuild keeps the title, hint and level of every page whose heading is unchanged
from the last applied plan (`<registry>/toc-work/<slug>.plan.json`, which records each page's heading); never delete
or hand-edit that file. `--prior <plan>` restores from an older plan copy. A course title that contains " - " needs an en dash (" – ") in
its ToC title and a real hint after it.

## Extraction

Nothing is extracted automatically. A downloaded source or reading is turned into text only when the student asks on the
dashboard ("חילוץ טקסט"; see `../SKILL.md`, "Extract on request"). `auto` reads a docx with python-docx (or pandoc) and a PDF
text layer with pymupdf per page, keeping printed page numbers (never `pdftotext` on Hebrew); a scan is read with Claude
vision. Gemini OCR (`/academic-writer:ocr`) and Tesseract run only when the student chose them for that item. Google Docs are
exported natively.

## Creating a book for a new course

`trove items create "<title from the term's naming template>" -d "<one line: what the course is>" -c "<page 1>" --json --no-session`,
then record the returned id as `book_id` in the course JSON and run `courses.py validate`. Do not create a
manuscript for it.
