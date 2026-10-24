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

The registry root is `$ACADEMIC_COURSES_DIR`; otherwise it lives under the researcher's home folder (`home.py show` prints it). Registries from before the home folder existed (the legacy `~/.academic-writer/courses/<term>/`) keep working until the researcher runs the migration: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/home_migrate.py" --home <home> --data-dir "${CLAUDE_PLUGIN_DATA}" [--daily-script <path>]` previews first and changes nothing. Show the preview, and add `--apply` only after the researcher says yes. Apply records the home pointer, copies the registry, and rewrites the legacy paths inside the registry, the helper scripts (nightly, sync, lock) and the launchd plists, keeping a backup of each; it deletes nothing. It prints the `launchctl` lines that reload a changed plist; `--reload-launchd` runs them. `courses.py` reads `term.json` and one `<slug>.json` per course. Resolve the script as `${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py`. The registry is user data and must not be committed to a project.

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

When the researcher asks, create the course folders inside the home folder (one folder per course, then register each with `home.py register --type course`). Never create them unasked, and never outside home.

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

**Download only: nothing is OCR'd or text-extracted automatically (user rule 2026-10-19).** A new course file or a fetched reading is only downloaded to the right place: the `sources/<slug>/` snapshot, Drive and NotebookLM (`courses.py add-source`), or a ref marked `downloaded` with its `download_path`. No Trove text upload, no Gemini call, no OCR happens as a side effect of the nightly run, `watch-lemida`, `refs.py fetch` / `fetch-queue` or a lesson flow (lesson transcripts are not OCR and are unaffected). The student chooses what to extract on the dashboard ("חילוץ טקסט", see "Extract on request"). For Google Docs, export native DOCX; the text of a docx is read only when the student asks. When a method other than `auto` is not named, ask with `AskUserQuestion` which engine reads a scan, saying plainly that with Gemini the page text goes to Google; never move a page to another engine on your own. When extracting Hebrew from two-column pages, join columns right to left and preserve reading order. Flag unclear text instead of silently reconstructing it.

## Table of contents rule

ToC rule: one entry per page, "Title - hint", nested in tree order (siblings by page; lesson pages under תמלולי שיעורים).

- Every page of a course book has its own ToC entry titled `Title - hint` (a non-empty content hint after ` - `).
- Nesting: the course page is level 1; `תמלולי שיעורים` is level 1 with each lesson at level 2; `חומרי קריאה` is level 1, each source level 2, its sections level 3.
- Entries run in page order, and the Changelog page sits in page order too, not at the end by default.
- After writing pages, from the plugin repository checkout (these tools live in the repo's `tools/` and are not shipped in the installed plugin): `python3 tools/toc_rebuild.py --course <slug>` (dry run; review the plan), then `--apply`, then `python3 tools/toc_audit.py --course <slug>`. Exit 0 from the audit means every page starts exactly one hinted entry in order. Where the checkout is not available, apply the same rule by hand with `trove items enrich` and check `courses.py check-lesson` / `check-source`.

## Course sources

Every source (a Lemida file, an email attachment, a recording) follows one contract. Each reaches Drive and NotebookLM when it is added, and Trove when the student chooses to extract it; `check-source` proves it.

1. **Register.** `courses.py add-source <file> --course <slug> [--title T] [--origin lemida|email|recording|other] [--origin-ref R]`. It dedupes by sha256, copies the file into the course Drive folder by kind (`00 כללי/`, `שיעורים/שיעור NN/`, `קריאות/<citation>/`, `מטלות/מטלה N/`, `לא ממוין/`; `src/scripts/courses/drive_layout.py`) under its Chicago name (`naming.py`), records its `drive_path`, adds it to the course notebook under the same name (exit 4 when the notebook is at its source limit), and writes a Trove job under `queue/sources/`. A rerun resumes from the missing step. That Trove job waits: `queue/sources/*.json` is never drained by the nightly script, by `watch-lemida` or by any skill step, and only the file the student chose on the dashboard ("חילוץ טקסט") is extracted and then ingested. Recordings and transcripts are sources too: `add-source` copies them to Drive, adds them to NotebookLM through `ingest`, and records them (`kind: media`) with their lesson; their Trove home is the lesson page (`--transcript --date D [--time HHMM]` for a text transcript), and `check-source` verifies Drive, NotebookLM and the lesson. To move sources already in Drive into this layout, run `courses.py drive-reorg --course SLUG` (or `--all`): it prints the manifest of moves and NotebookLM renames and changes nothing; `--apply` makes them and logs each move to `logs/drive-reorg-<stamp>.jsonl`.
2. **Extract the text only when the student chose this file** (an `extract-handoff` run, below; otherwise stop after step 1). Read the job file for `kind` and `pages`. `refs.py extract-queue` has already read what python can: docx with python-docx (pandoc if missing), a PDF text layer with pymupdf per page, keeping printed page numbers. Never use `pdftotext` on Hebrew: it garbles right-to-left text, headings and footnotes. What python could not read is a handoff file for you: a scanned PDF or image is read with Claude vision (`pdftoppm -r 150`, then Read each page image); Gemini (`aw ocr`) or Tesseract only when the student named that engine for the item. Hebrew RTL two-column pages: join right column, then left. Flag unclear text instead of reconstructing it, and record the engine used.
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

- **References (`refs.py`).** Finds the works a course cites (footnotes, lesson text, transcripts), looks each one up in the BIU library, records a status per ref in `refs/<slug>.json`, and renders the `מקורות נזכרים` index page. `refs.py status` exits 0 only when no ref is pending. Before extracting a scan the student asked for, check Anna's Archive for the same edition (never for Kotar items); when Anna's Archive answers with its browser check the outcome is `blocked` and the ref gets a chore to search it in Chrome. Nothing is OCR'd automatically: scans are read on request (Claude vision by default; Gemini or Tesseract only when chosen, see `references/library-refs.md` A7). Kotar pages come from `/academic-writer:kotar-fetch`; the ref stays `kotar` until it reports. Downloads that need the signed-in browser are steps the runbook describes.
- **Sources per task.** Tasks live in `<slug>.json` `tasks[]` (id = the chore id, or `s-<spec key>`); refs and sources may carry `tasks: [ids]`. `refs.py`/`courses.py task list|show|link|submit|unsubmit` read and write them, `courses.py migrate-tasks --dry-run` links the existing specs, and `refs.py fetch --course X --ref KEY` runs Anna's Archive, the BIU lookup and the download/Kotar step in order, logging each to `fetch_log`. See `references/library-refs.md` (A10).
- **Exams, colours, recordings link.** An exam is a chore of kind `exam` (`due_at` is the exam date and time, optional `room` and `material`); it becomes a task `{kind: "exam", due_at, room?, material?}` in `<slug>.json` `tasks[]`. A course file may carry `color`, one of the eight `course-*` names; a course without one gets the next free hue in order of `slug`. `links.json` may carry `wispr_url` per course (the recordings link). Each unmatched Wispr meeting in `digest/wispr-unmatched.json` carries `course_guess`, the one course whose slot contains the meeting start, or `null`.
- **Dashboard.** `/academic-writer:dashboard` (`courses.py dashboard`) shows every course on one local page (127.0.0.1 only); its "fetch selected" button writes jobs to `REG/queue/fetch/*.json`. The nightly script drains them with `refs.py fetch-queue [--dry-run] [--json]` (also runnable by hand): the fetch chain per ref, per-ref results into the job, finished jobs to `REG/queue/fetch/done/`. A job whose refs all errored stays with an `attempts` counter and is retried the next night; after 3 attempts it moves to `done/` with status `failed`. Anything that needs the signed-in browser stays a chore for the user. Its "חילוץ טקסט" button (a checkbox per downloaded source or reading that has no extracted text, plus a method: `auto` (default), `claude-vision`, `gemini-ocr`, `tesseract`) writes a job to `REG/queue/extract/<ts>-<course>.json`; the page extracts nothing and shows queued items as "ממתין לחילוץ טקסט". See "Extract on request".
- **Book lock.** One writer per Trove course book: `~/.academic-writer/bin/book-lock.sh acquire <slug> <session> "<what>"` before the first write (exit 1 means held; do other work), held through writes, ToC repair and `toc_audit`. A lock older than 3 hours goes to the user; never break it. Details and the ToC repair per book are in the runbook (A0, A9).
- **Bookmark folders (`courses.py bookmarks`).** Rebuilds `Bookmarks bar › BIU <term> › <course>` in Chrome through AppleScript. It replaces the folder's items, so re-running it is safe. Chrome must be open. It is no longer part of the nightly script (AppleScript folder creation crashed Chrome); the course dashboard replaces it. Trove items are not built yet (no confirmed Trove URL form), so each folder currently holds the NotebookLM, Lemida and current-task items only.

## Nightly Lemida watcher (Chrome)

Moodle's REST API answers every call with a Radware Bot Manager captcha page, so the nightly watch drives the user's already signed-in Chrome with `claude-in-chrome`. Never ask for or store the user's password. Full procedure: `references/lemida-watch.md`. The run is complete only when its coverage file says so. Do all of this, then write the coverage file; `courses.py lemida-coverage-check` (step `lemida-coverage` of the nightly job) fails the run for any gap.

- **Notifications, all of them.** Open `https://lemida.biu.ac.il/message/output/popup/notifications.php` in the signed-in tab and scroll until every notification in the window (the last 14 days) is loaded. Open each one (a post, an assignment, a reminder), read it, route it, and record its id. A notification you did not open is a gap.
- **Every new assignment.** Each `mod/assign` page the watch finds new (the diff's `new_assigns`, or one a notification names) is opened and gets its `assignment` chore, with its core texts.
- **Coverage file.** Write `REG/logs/lemida-coverage-<YYYY-MM-DD>.json` (REG is the term directory; `logs/` exists after the first run) with exactly this shape:

  ```json
  {"date": "YYYY-MM-DD",
   "courses": {"<slug>": {"visited": true, "new_assign_modules": [101], "assign_handled": [101]}},
   "notifications": {"page": "https://lemida.biu.ac.il/message/output/popup/notifications.php", "listed": [1, 2], "opened": [1, 2]}}
  ```

  `visited` is true only after the course page was walked (step 1 below); `new_assign_modules` are the assign ids that were new that night, `assign_handled` the ones whose chore was written. `listed` is every notification id in the window, `opened` the ids you opened. Write the file even when the run hit an error, so the gap is named, and say in the run summary which part failed. If Chrome is closed the nightly job does not start this watch at all: the check then reports the missing file, which is the failure the chore already names.

Then, per course with a `lemida_course_id` (every active course needs one; a course without one gets a `manual` chore `lemida-id-<slug>` from the coverage check):

1. Open `course/view.php?id=<lemida_course_id>` and walk every section; extract one PageData JSON per section, forum and assignment, then run `courses.py watch-diff <slug> --pages <json>`. The diff remembers the last section with content, so each night continues from it to find new content.
2. Always read the `לוח הודעות` (announcements) forum and report new posts. A post that says what to read for a lesson gets a `reading` chore (ref `d<discussion>-p<post>`, one per post, core texts, due at that lesson's start), which the dashboard shows as a reading task.
3. Download `pdf`, `docx`, `pptx` and link items from their `pluginfile.php` URL, never `/mod/resource/view.php`. Zoom recordings: try to download; otherwise use Zoom's transcript and reduce it to the lecturer's main ideas.
4. Perusall items: download the pdf twin in the same section (no OCR); with no twin, add a `perusall-capture` chore.
5. Assignments: read the time left and the task, name the core texts, confirm each exists in the course sources, and add an `assignment` chore (for a text on Kotar, run `/academic-writer:kotar-fetch` for the cited pages; add a `kotar-source` chore only if that fails). Forums the user must post in get a `forum-post` chore.
6. Route every downloaded item through `courses.py add-source`, run `check-source`, advance seen state with `watch-diff --apply --ok <kind:id> ...` (`module:`, `assign:`, `discussion:`, `section:`) only after routing succeeded, and end with `courses.py chores digest`.

## Extract on request

Extraction is opt-in. The student ticks downloaded sources or readings on the course page of the dashboard and clicks "חילוץ טקסט" with a method; the dashboard writes `REG/queue/extract/<ts>-<course>.json` (`{course, items: [{kind: source|ref, key|sha8, method}], created_at}`). The nightly script then runs `refs.py extract-queue [--dry-run] [--json]` (`src/scripts/courses/extract.py`), which plans each item and drains the queue:

- `auto` (default): docx -> python-docx or pandoc; a PDF with a text layer -> pymupdf, per page, with the printed page number kept; a scanned PDF or image -> Claude vision. A quality gate checks each Hebrew page (reversed final letters, runs of single letters, glyph junk, a Latin page in a Hebrew document); a page that fails goes to Claude vision with the reason recorded.
- `claude-vision`: you read the page images. `gemini-ocr` and `tesseract` run only when the job names them for that item (Gemini sends the pages to Google; say so in the report).
- Python items are written to `REG/extracted/<slug>/<kind>-<key>.md` (one `## עמוד N` heading per page) and the job moves to `queue/extract/done/`. Items for you are files in `REG/queue/extract/handoff/` (file, pages, method, reason, `out` path, instruction). A source the student chose that still has its `add-source` Trove job is listed in `REG/queue/extract/ingest/`.

**`/academic-writer:courses extract-handoff`** (the nightly's Claude step, run only when handoff or ingest files exist): for each handoff file, extract the pages as its instruction says and write them to its `out` path, then delete nothing by hand (a handoff disappears once `out` exists). For each ingest file, once the text exists, place it in Trove per "Course sources" step 3 and finish with `source-done` and `check-source`. Never start from `queue/sources/` on your own: it is not a to-do list. Report what was extracted, by which engine, and every page you could not read.

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

### Nightly schedule

The nightly run is optional and the time is the researcher's choice. Resolve `courses.py` as above and ask which time they want, or whether they want no schedule:

- `courses.py nightly status [--json]` shows whether it is scheduled, the time, the plist, the script and the last run.
- `courses.py nightly set --time HH:MM` writes (or updates, keeping a backup) the launchd plist and loads it. On a system without launchd it prints a cron line instead. It needs the daily script (start from `scripts/courses-daily.sh.example`); say what the time is before running it.
- `courses.py nightly off` unloads the schedule and renames the plist to `.plist.disabled`; the nightly then runs only on demand.
- `courses.py nightly run-now [--dry]` runs the nightly script once in the foreground; `--dry` only prints the planned commands.

Logs go under the registry's `logs/` directory.

## Operational safeguards

- If a Chrome download stalls, inspect `~/Downloads`; after two failed attempts, stop and ask. A same-named old file is not proof that this term's download succeeded.
- Resolve duplicate LMS names by course ID, not display name alone.
- Never report a download complete based on a stale local match.
- Never expose credentials, IDs, personal paths, or schedule contents in plugin files or logs.
