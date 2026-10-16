---
name: courses
description: "Use when setting up an academic term from a schedule, validating course resources, syncing your LMS (Moodle) materials, or running the daily course scan."
user-invocable: true
allowed-tools: [Bash, Read, Write, AskUserQuestion]
metadata: {author: "Academic Writer", version: "0.1.0"}
---

# Academic Writer — Courses

Set up and maintain one Drive folder, NotebookLM notebook, and Trove book for each course (a plain book, not a manuscript; its layout and ToC rules are in `references/course-book.md`). Course identities, external resource IDs, naming templates, LMS settings, and local paths belong in the user's private registry, never in this plugin.

## Registry and configuration

The registry root is `$ACADEMIC_COURSES_DIR`; otherwise use `~/.academic-writer/courses/<term>/`. `courses.py` reads `term.json` and one `<slug>.json` per course. Resolve the script as `${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py`. The registry is user data and must not be committed to a project.

Document and preserve these `term.json` fields:

- `term`: display name or academic-term key.
- `timezone`: IANA time zone used to interpret recording and slot times.
- `semesters`: A/B objects with inclusive `start` and `end` dates; yearly slots are active in either configured semester.
- `naming`: `drive`, `notebook`, and `book` templates (a legacy `manuscript` template is used for the book title when `book` is absent). Template context includes course fields and `term`.
- `drive_subject_folders`: subject-folder labels mapped to Drive folder IDs; `drive_remote` is the rclone remote name.
- `lemida`: `base_url`, optional `keychain_service` (default `academic-writer-lemida`) and `keychain_account`; the token remains in the OS keychain.
- `voice_memos_dir`: local recording directory; `local_root`: local LMS download root.
- `notebook_source_limit`: maximum sources to allow before stopping (default 45).
- `state.last_voice_memo_scan`: last completed scan boundary, stored as an ISO timestamp.

Each course JSON has `slug`, `code`, `name`, `lecturer`, `slots` (`day`, `start`, `end`, `semester`), `drive_subject_folder`, `drive_folder_id`, `notebook_id`, `book_id`, `lemida_course_id`, `lemida_seen`, and `lessons`. `book_id` identifies the course's Trove book; course books have no manuscript, so they never appear in other sessions' manuscript lists. Lesson records include date, audio SHA-256, NotebookLM source ID, Trove page, and status. Keep unknown schedule details marked for review; do not infer a course, time, or ID.

## Set up a term from a schedule

1. Inspect the schedule and run a dry parse:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py" import-docx "/path/to/schedule.docx" --dry-run
   ```

2. Present a table with course name, code, lecturer, day, hours, semester, proposed Drive subject folder, notebook title, and book title. Identify tentative/admin entries and unresolved slots. Ask the user to confirm the courses and subject-folder choices before creating anything.
3. After confirmation, create the registry directory and `term.json`, then one JSON per confirmed course. Naming defaults: Drive folder and NotebookLM notebook use the course name exactly; the book uses the configured template (for example `Personal · <term> · <course name>`). Do not put real IDs in skill text or examples.
4. For each missing resource, create a Drive folder named exactly as the course under its configured subject folder using the Drive connector's `create_file` with folder MIME type; create a notebook with `nlm notebook create "<course name>" --json`; check `trove auth whoami --no-session` for the plan/quota, then create the course book as `references/course-book.md` describes (`trove items create`, never `trove ms create`). Ask before renaming or replacing any existing resource. Record returned IDs immediately in the course JSON.
5. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py" validate`. Resolve each mismatch by renaming the external resource after asking; never make a wrong resource appear valid by changing the registry's expected name. Repeat until exit 0.

## Validate existing resources

Run `courses.py validate` (add `--json` when machine-readable output is useful). It checks each configured Drive folder, NotebookLM notebook, and Trove book by ID and expected name. `tools/book_audit.py` checks that page 1 of each book carries the Drive, NotebookLM and Lemida ids. Report all mismatches. Do not silently repair or delete resources.

## LMS and readings

Use `courses.py lemida-sync --dry-run` to preview API changes when a Lemida token is available in the OS keychain; otherwise use the user's browser session to inspect their LMS (Moodle). Download PDFs and DOCX files; list Zoom, forum, and videostream entries by name. Never bulk-download LTI/Perusall readings: capture pages on demand about a week before the lesson. Keep copyrighted readings only in the user's own Drive and Trove, in the relevant course's book.

For scanned readings, OCR with Claude vision first: render with `pdftoppm -r 150`, then inspect the PNG pages. Never send a page to Gemini on your own: mark pages Claude flags as unreadable or low-confidence "OCR, not image-verified" and, if Gemini's OCR (the bundled `/academic-writer:ocr`) might read a page better, ask with `AskUserQuestion` whether this page may be sent to Gemini, saying its text goes to Google. Record which engine produced the text in the job. For Google Docs, export native DOCX and convert with `pandoc`. When extracting Hebrew from two-column pages, join columns right to left and preserve reading order. Flag unclear text instead of silently reconstructing it.

## Table of contents rule

ToC rule: one entry per page, "Title - hint", nested in tree order (siblings by page; lesson pages under תמלולי שיעורים).

- Every page of a course book has its own ToC entry titled `Title - hint` (a non-empty content hint after ` - `).
- Nesting: the course page is level 1; `תמלולי שיעורים` is level 1 with each lesson at level 2; `חומרי קריאה` is level 1, each source level 2, its sections level 3.
- Entries run in page order, and the Changelog page sits in page order too, not at the end by default.
- After writing pages, from the plugin repository checkout (these tools live in the repo's `tools/` and are not shipped in the installed plugin): `python3 tools/toc_rebuild.py --course <slug>` (dry run; review the plan), then `--apply`, then `python3 tools/toc_audit.py --course <slug>`. Exit 0 from the audit means every page starts exactly one hinted entry in order. Where the checkout is not available, apply the same rule by hand with `trove items enrich` and check `courses.py check-lesson` / `check-source`.

## Course sources

Every source (a Lemida file, an email attachment, a recording) follows one contract. Each reaches Drive, NotebookLM and Trove, and `check-source` proves it.

1. **Register.** `courses.py add-source <file> --course <slug> [--title T] [--origin lemida|email|recording|other] [--origin-ref R]`. It dedupes by sha256, copies the file to the course Drive folder, adds it to the course notebook (exit 4 when the notebook is at its source limit), and writes a Trove job under `queue/sources/`. A rerun resumes from the missing step. Recordings and transcripts are sources too: `add-source` copies them to Drive, adds them to NotebookLM through `ingest`, and records them (`kind: media`) with their lesson; their Trove home is the lesson page (`--transcript --date D [--time HHMM]` for a text transcript), and `check-source` verifies Drive, NotebookLM and the lesson.
2. **Extract the text** (read the job file for `kind` and `pages`). docx: `pandoc`. Born-digital PDF: `pdftotext` per page, keeping the printed page numbers. Scanned PDF (no text layer): `pdftoppm -r 150` and Claude vision first; never send a page to Gemini on your own: mark pages Claude flags unreadable or low-confidence "OCR, not image-verified" and, if the bundled Gemini OCR (`/academic-writer:ocr`) might help, ask with `AskUserQuestion` whether this page may be sent to Gemini, saying its text goes to Google; record the engine used. pptx: slide text from the pptx XML. Hebrew RTL two-column pages: join right column, then left. Flag unclear text instead of reconstructing it.
3. **Place it in Trove.**
   - **40 pages or fewer:** pages go in the course book under a level-1 `חומרי קריאה` entry page (create it if missing). One level-2 entry per source, titled `Title - hint`. Level-3 hinted entries for its sections, one per page. The source's first page opens with `> Load this page when:` and a short reading guide: the thesis or claims, the structure, and how to cite by printed page.
   - **More than 40 pages:** its own Trove book through `/academic-writer:ingest-book` (nested hinted ToC, page-1 reading guide), plus a hinted level-2 pointer page in the course book, titled with the source title.
   - **A source and its translation are a pair:** ingest both and cross-link them in their guides.
   - Links that cannot be downloaded (licensed viewers, the library catalogue) and assignments go on the course page as notes.
4. **Rebuild the course book ToC last** with `enrich`; `append` and `put` flatten the sidebar. Take the version from `trove items history --json`. Then audit it (see "Table of contents rule").
5. **Close.** `courses.py source-done <slug> <sha8> --trove <book_id>:<page>`, then `courses.py check-source <slug> --sha <sha8>`. It exits 0 only when the file is in Drive, the source is in NotebookLM, and Trove nests the source under `חומרי קריאה`. A course with no sources prints "no sources".

Copyrighted readings stay in the user's own Drive, NotebookLM and Trove.

Note on placement: `add-source` writes its source under the level-1 `חומרי קריאה` entry (`READINGS` in `trove_source.py`), so a course's appendix section is that entry, and the references index is the only new page.

## Course references and bookmark folders

Two jobs that build on the registry. Full procedure in `references/library-refs.md`.

- **References (`refs.py`).** Finds the works a course cites (footnotes, lesson text, transcripts), looks each one up in the BIU library, records a status per ref in `refs/<slug>.json`, and renders the `מקורות נזכרים` index page. `refs.py status` exits 0 only when no ref is pending. Before any OCR, check Anna's Archive for the same edition (never for Kotar items). Hebrew OCR is Tesseract, then gated Gemini correction, never Gemini alone. Kotar pages come from `/academic-writer:kotar-fetch`; the ref stays `kotar` until it reports. Downloads that need the signed-in browser are steps the runbook describes.
- **Sources per task.** Tasks live in `<slug>.json` `tasks[]` (id = the chore id, or `s-<spec key>`); refs and sources may carry `tasks: [ids]`. `refs.py`/`courses.py task list|show|link|submit` read and write them, `courses.py migrate-tasks --dry-run` links the existing specs, and `refs.py fetch --course X --ref KEY` runs Anna's Archive, the BIU lookup and the download/Kotar step in order, logging each to `fetch_log`. See `references/library-refs.md` (A10).
- **Book lock.** One writer per Trove course book: `~/.academic-writer/bin/book-lock.sh acquire <slug> <session> "<what>"` before the first write (exit 1 means held; do other work), held through writes, ToC repair and `toc_audit`. A lock older than 3 hours goes to the user; never break it. Details and the ToC repair per book are in the runbook (A0, A9).
- **Bookmark folders (`courses.py bookmarks`).** Rebuilds `Bookmarks bar › BIU <term> › <course>` in Chrome through AppleScript. It replaces the folder's items, so re-running it is safe. Chrome must be open. The nightly script runs it after the digest and logs a failure without stopping. Trove items are not built yet (no confirmed Trove URL form), so each folder currently holds the NotebookLM, Lemida and current-task items only.

## Nightly Lemida watcher (Chrome)

Moodle's REST API answers every call with a Radware Bot Manager captcha page, so the nightly watch drives the user's already signed-in Chrome with `claude-in-chrome`. Never ask for or store the user's password. Full procedure: `references/lemida-watch.md`. In outline, per course with a `lemida_course_id`:

1. Open `course/view.php?id=<lemida_course_id>` and walk every section; extract one PageData JSON per section, forum and assignment, then run `courses.py watch-diff <slug> --pages <json>`. The diff remembers the last section with content, so each night continues from it to find new content.
2. Always read the `לוח הודעות` (announcements) forum and report new posts.
3. Download `pdf`, `docx`, `pptx` and link items from their `pluginfile.php` URL, never `/mod/resource/view.php`. Zoom recordings: try to download; otherwise use Zoom's transcript and reduce it to the lecturer's main ideas.
4. Perusall items: OCR the pdf twin in the same section; with no twin, add a `perusall-capture` chore.
5. Assignments: read the time left and the task, name the core texts, confirm each exists in the course sources, and add an `assignment` chore (for a text on Kotar, run `/academic-writer:kotar-fetch` for the cited pages; add a `kotar-source` chore only if that fails). Forums the user must post in get a `forum-post` chore.
6. Route every downloaded item through `courses.py add-source`, run `check-source`, advance seen state with `watch-diff --apply --ok <kind:id> ...` (`module:`, `assign:`, `discussion:`, `section:`) only after routing succeeded, and end with `courses.py chores digest`.

## Daily scan

`courses.py daily` checks exactly this, in order:

1. **Voice Memos** since `state.last_voice_memo_scan`: each recording is mapped from its timestamp to a configured course slot and routed through `add-source` (Drive, NotebookLM, lesson). Out-of-slot, ambiguous, or out-of-semester recordings need human review; never guess. The scan boundary advances only after the scan completes.
2. **Lemida content**, for every course with a `lemida_course_id`: new or changed resources and folders are downloaded and routed through `add-source` (origin `lemida`, ref `cm:<cmid>`); recordings go to ingest. Seen state is `lemida_seen`.
3. **Lemida announcements and forums**, same courses: forums are listed, posts are tracked individually in `lemida_seen_posts` (unseen or edited posts are processed), and attachments are downloaded to a temporary path and routed through `add-source` (ref `forum:<discussionid>`). Each announcement is reported with subject, author, date, a 300-character excerpt and where its attachments went.
4. **Lemida notifications** for the token's user, newer than `state.last_notification_time` in `term.json` (subject, link, time, read flag). The state advances only after a successful run.
5. **Queued lesson jobs** left for `lesson-notes --pending`.

A failure for one course, forum, post or notification never stops the others, and seen-state advances only for what succeeded. Each run writes its own `logs/lemida-<date>-<HHMMSS>.json` (full data) and `.md` (new announcements per course, new notifications, new content, errors) before any seen-state advances, and appends a section to the same-day digest `logs/lemida-<date>.md`; a course that fails for any reason is recorded as an error and the next course still runs; `daily` prints the `.md` path, and `daily --json` prints one JSON document.

To configure a Lemida token, the user obtains a mobile-app token while signed into their LMS at its `admin/tool/mobile/launch.php?service=moodle_mobile_app&passport=<n>&urlscheme=moodlemobile` endpoint, follows the redirect's base64 `token=` value, and decodes `site_id:::token`. Have the user type it into their keychain (never ask them to paste it into chat):

```bash
security add-generic-password -s academic-writer-lemida -a <user> -w
```

For launchd scheduling, create a user-owned plist with a placeholder label, run `courses.py daily`, then invoke `claude -p "/academic-writer:lesson-notes --pending"`. Keep logs under the registry's `logs/` directory; show the plist and schedule before loading it.

## Operational safeguards

- If a Chrome download stalls, inspect `~/Downloads`; after two failed attempts, stop and ask. A same-named old file is not proof that this term's download succeeded.
- Resolve duplicate LMS names by course ID, not display name alone.
- Never report a download complete based on a stale local match.
- Never expose credentials, IDs, personal paths, or schedule contents in plugin files or logs.
