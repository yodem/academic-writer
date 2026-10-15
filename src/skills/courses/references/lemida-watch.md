# Nightly Lemida watcher (Chrome): procedure

Read this when running the nightly watch of the user's LMS (Moodle, "Lemida"). The summary is in `../SKILL.md`. Reader: the agent running the watch, in the user's signed-in Chrome through `claude-in-chrome` (load its tools with ToolSearch first; invoke the `claude-in-chrome` skill before using them).

## Why Chrome

Moodle's REST API is blocked by a Radware Bot Manager captcha: calls return an HTML captcha page instead of JSON. The user's signed-in Chrome session is the only route. Never ask for the password or put it in a file. If Chrome is closed or the session shows a login or captcha page, add a `manual` chore (`courses.py chores add`) and stop that course.

Claude only extracts; Python decides. Claude produces PageData JSON, `courses.py watch-diff` decides what is new, and Claude then routes only what the diff names.

## PageData shapes (input of `watch-diff --pages`)

`--pages` is a JSON file holding a list of pages. Every page has `kind` and `url`. Required keys (from `watch_diff.validate_page`; a missing key fails closed with `WatchSchemaError`):

| `kind` | Required keys | Used for |
|---|---|---|
| `course` | `sections`, `declared_module_count` (int) | `sections` is a list of `{id, name, modules}`; each module has `cmid`, `name`, `type` |
| `forum` | `discussions` | each discussion has `id`, `replies` (count) |
| `discussion` | `id`, `text` | one post |
| `assign` | `cmid`, `text`, `time_left_text`, `due_text` | an assignment page; add `title` when present |

`declared_module_count` is the number of activities the page itself claims (for example from the course index or section counters). It is how a half-loaded page is detected.

## Per course

Use `course/view.php?id=<lemida_course_id>` (the id from the course JSON; never match courses by display name).

1. **Walk every section.** Open the course page, expand every collapsed section (for example מבוא, מבוא לקורס, then the weekly sections), and scroll to the end. Extract one `course` PageData with all sections and their modules (`cmid` from the `id=` of each module link, `type` from the module class such as resource, assign, forum, url, zoom, lti).
2. **Diff.** `courses.py watch-diff <slug> --pages <file>` prints the diff as JSON: `new_modules`, `new_sections`, `new_discussions`, `reply_growth`, `new_assigns`, `changed_assigns`, `last_content_section`, `suspect`. `last_content_section` is the last section that has content; the next night continues from it, so there is no need to open older sections in detail unless the diff lists them. Without `--apply` the command changes nothing.
3. **Announcements.** Always open the `לוח הודעות` forum, extract a `forum` page (and a `discussion` page for each new or grown thread), and report every new post: subject, author, date, a short excerpt.
4. **Route each new item** (below), then **advance** the seen state only for what succeeded: `courses.py watch-diff <slug> --pages <file> --apply --ok <id> <id> ...` (cmids, discussion ids, section ids). `--apply` without `--ok` exits 2. Ids not named stay unseen and return tomorrow.
5. After all courses: `courses.py chores digest`.

### A `suspect` result

`suspect: true` means the course page looks incomplete (fewer modules than `declared_module_count`, or fewer than already known), so its sections are ignored and seen state must not advance from it. Do this:

1. Re-open the page, expand every section, scroll fully, and extract again. Retry once.
2. If it is still suspect, add a `manual` chore naming the course and stop that course; do not guess.
3. Re-baseline only when the course really shrank (the lecturer removed items) and the user agrees. The library function `watch_diff.baseline(pages)` builds a seen-state that marks everything on the pages as seen; there is no CLI command for it, so say so in the chore rather than editing the registry by hand. (Open question: a `watch-diff --baseline` option would make this a command.)

## Item types

Every downloaded file goes through the source contract in `../SKILL.md` ("Course sources"): `courses.py add-source <file> --course <slug> --origin lemida --origin-ref cm:<cmid> [--title T]` puts it in the Drive course folder under the section's subfolder, NotebookLM and Trove (under `חומרי קריאה`), then `courses.py check-source <slug> --sha <sha8>` must exit 0.

- **pdf, docx, pptx.** Use the `pluginfile.php` link; a scripted fetch of `/mod/resource/view.php` is blocked and returns a page, not the file. Get the real link from the page's file anchor, download in Chrome, then follow "Extract the text" in `../SKILL.md` (docx `pandoc`, pptx slide XML, born-digital pdf `pdftotext`). A scanned pdf is read with Claude vision first (`pdftoppm -r 150`); escalate pages Claude flags unreadable or low-confidence, or degraded text, to the bundled Gemini OCR (`/academic-writer:ocr`), and record the engine used in the job.
- **External links (url modules).** Record them on the course page as notes, and read each target URL (the anchor on `mod/url/view.php`). If the target is a downloadable pdf, treat it as above. Licensed viewers and catalogues cannot be downloaded. A Kotar target (`kotar` in the host, often through the `openathens.net` proxy) is a reading: search Anna's Archive for the book, and if it is not found add `courses.py chores add --course <slug> --kind kotar-source --ref <cmid> --title "<reading>" --text "<Kotar URL, pages if the course names them>"`.
- **Zoom recordings** (`biu-ac-il.zoom.us/rec/...`). Try to download the recording so the user can extract its audio; if it downloads, route it as a recording source (`add-source`, `kind: media`). If the host disabled download, use Zoom's transcript: save it as `.txt` and run `courses.py add-source <file> --transcript --course <slug> --date <YYYY-MM-DD> [--time <HHMM>]`. The recording covers the whole lesson, with humor, asides and other speakers, and the transcript will misspell names. When summarising: identify the lecturer (the voice who teaches; confirm from the course JSON's `lecturer`), extract the main ideas, keep meaningful asides (marked as asides), set other speakers apart, and mark doubtful names or passages `[לא ברור]` instead of correcting them.
- **Perusall** (`app.perusall.com`, an LTI item). The original pdf usually sits in the same section: if it does, OCR and ingest it like any pdf. If there is no pdf twin, add a chore and do nothing else with the item: `courses.py chores add --course <slug> --kind perusall-capture --ref cm:<cmid> --title "<reading>" --text "Capture the text with Google Lens into the course Drive folder (section subfolder)"`. When the user says the capture is done, ingest the captured file with `add-source` (NotebookLM and Trove) and mark the chore done (`chores done <id>`).
- **Assignments** (`mod/assign`). Extract an `assign` page: the `הזמן שנותר` text (`time_left_text`), the due date (`due_text`) and the task text. Identify the core texts (for example "pages 308-322 of Dan's chapter on Sefer ha-Qanah; the article A kabbalistic reading") and confirm each exists in the course's sources or in the section. If a core text points to Kotar, search Anna's Archive (the `annas-archive-ebooks` skill when installed); if it is not found, add a `kotar-source` chore. Always add an `assignment` chore: `courses.py chores add --course <slug> --kind assignment --ref <cmid> --title "<assignment>" --time-left-text "<...>" --due-text "<...>" --core-text "<text 1>" --core-text "<text 2>"`. A changed deadline or task (`changed_assigns`) updates the same chore (same course, kind and ref).
- **Forums the user must post in** (a `mod/forum` that requires a submission). Add `courses.py chores add --course <slug> --kind forum-post --ref <cmid or discussion id> --title "<forum>" --text "<what to post, by when>"`. Do not post for the user.

Refs: always pass the bare cmid as `--ref` (`courses.py` also folds `cm:<cmid>` and Moodle URLs into it).

- **Signed out** (the dashboard `lemida.biu.ac.il/my/`, or every course, redirects to login or guest access): add exactly `courses.py chores add --course general --kind manual --ref lemida-signin --title "Sign in to Lemida in Chrome"` and stop the scan. Any other sign-in ref is folded into this one chore.
- **Not enrolled** (one course shows the enrolment page while other courses load): add `courses.py chores add --course <slug> --kind manual --ref lemida-no-access --title "Lemida: no access to <slug>"` and continue with the next course. A fresh registration can take a day or two to reach Lemida.

Unattended runs (`claude -p`, the nightly job): nobody can answer, so never end with a question or hold a batch back for approval. Route every item you can, add a chore for each one you cannot, and apply seen state only for the items you routed or chored.

## Chrome downloads

- Downloads land in `~/Downloads`; a same-named old file is not proof that this download worked. Check the modification time.
- `chrome://downloads` cannot be read through the page tools: run `open -a "Google Chrome" chrome://downloads` and take a `screencapture` to see the list.
- After two failed downloads of one item, stop trying and add a chore (`manual`, or `perusall-capture` / `kotar-source` when they fit) saying what to fetch by hand.

## Ending a run

`courses.py chores digest` writes the digest of open chores. Report: new announcements, items routed (with `check-source` results), chores added, courses that errored or were `suspect`. A failure for one course never stops the others.
