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

## Notifications first

Before the courses, read the user's Lemida notifications: they list every announcement, forum post and due-date reminder across all courses, including posts in forums the course walk does not open. The page `message/output/popup/notifications.php` fills its list by script, so read it through Moodle's own AJAX service from a signed-in Lemida tab (`javascript_tool`, keep the leading `await`):

```js
await (async () => {
  const r = await fetch(M.cfg.wwwroot + '/lib/ajax/service.php?sesskey=' + M.cfg.sesskey + '&info=message_popup_get_popup_notifications',
    {method: 'POST', credentials: 'include', body: JSON.stringify([{index: 0, methodname: 'message_popup_get_popup_notifications', args: {limit: 50, offset: 0, useridto: 0}}])});
  const j = await r.json();
  return j[0].error ? 'error' : j[0].data.notifications.map(n => [n.component, n.timecreated, n.subject, (n.contexturl || '').replace(/[?&=#]/g, ' ')].join(' | ')).join('\n');
})()
```

URLs come back with `?`, `&`, `=` and `#` replaced by spaces, because the browser tool blocks output that looks like URL query data. Each `mod_forum` row names one post (`discuss.php d <discussion> p<post>`); match it to a course by the subject's course-name prefix and the course JSON's `name`. Open every post from the last 14 days, whether or not its discussion is in `watch_seen` (a new post can arrive in a thread already seen, and a forum the course walk does not open has no other check), read it, and route it (below). This pass keeps no seen state of its own: it is safe to repeat because a reading chore is keyed by its post, so a second run updates the same chore and a chore the student closed stays closed. Report each post in the run summary. A `mod_assign` row points at an assignment (`assign/view.php id <cmid>`): make sure it has its `assignment` chore.

## Per course

Use `course/view.php?id=<lemida_course_id>` (the id from the course JSON; never match courses by display name).

1. **Walk every section.** Open the course page, expand every collapsed section (for example מבוא, מבוא לקורס, then the weekly sections), and scroll to the end. Extract one `course` PageData with all sections and their modules (`cmid` from the `id=` of each module link, `type` from the module class such as resource, assign, forum, url, zoom, lti).
2. **Diff.** `courses.py watch-diff <slug> --pages <file>` prints the diff as JSON: `new_modules`, `new_sections`, `new_discussions`, `reply_growth`, `new_assigns`, `changed_assigns`, `last_content_section`, `suspect`. `last_content_section` is the last section that has content; the next night continues from it, so there is no need to open older sections in detail unless the diff lists them. Without `--apply` the command changes nothing.
3. **Announcements.** Always open the `לוח הודעות` forum, extract a `forum` page (and a `discussion` page for each new or grown thread), and report every new post: subject, author, date, a short excerpt. Read every new post for readings: a post that assigns reading gets a `reading` chore (below) before its id is applied as seen.
4. **Route each new item** (below), then **advance** the seen state only for what succeeded: `courses.py watch-diff <slug> --pages <file> --apply --ok module:<cmid> discussion:<id> section:<id> assign:<cmid> ...`. Ids are namespaced by entity type because a module cmid and a discussion id can be equal. A bare id is accepted only when it names exactly one kind in the diff; an ambiguous one exits 2 with the candidates. `--apply` without `--ok` exits 2. A module whose `add-source` stopped before NotebookLM finished (status `drive_done` or `uploaded`) is not treated as seen and returns the next night. Ids not named stay unseen and return tomorrow.
5. After all courses: `courses.py chores digest`.

### A `suspect` result

`suspect: true` means the course page looks incomplete (fewer modules than `declared_module_count`, or fewer than already known), so its sections are ignored and seen state must not advance from it. Do this:

1. Re-open the page, expand every section, scroll fully, and extract again. Retry once.
2. If it is still suspect, add a `manual` chore naming the course and stop that course; do not guess.
3. Re-baseline only when the course really shrank (the lecturer removed items) and the user agrees. The library function `watch_diff.baseline(pages)` builds a seen-state that marks everything on the pages as seen; there is no CLI command for it, so say so in the chore rather than editing the registry by hand. (Open question: a `watch-diff --baseline` option would make this a command.)

## Item types

Every downloaded file goes through the source contract in `../SKILL.md` ("Course sources"): `courses.py add-source <file> --course <slug> --origin lemida --origin-ref cm:<cmid> [--title T]` puts it in the Drive course folder under the section's subfolder and in NotebookLM, and queues a Trove job in `queue/sources/` that is never drained here. Routing is download only: no OCR, no text extraction, no Trove text upload. The student chooses what to extract on the dashboard (`../SKILL.md`, "Extract on request"). The drive and NotebookLM part of `courses.py check-source <slug> --sha <sha8>` is checked now; the Trove part waits for that choice.

- **pdf, docx, pptx.** Use the `pluginfile.php` link; a scripted fetch of `/mod/resource/view.php` is blocked and returns a page, not the file. Get the real link from the page's file anchor, download in Chrome, then route it through `add-source` as above. Do not read its text: a scanned or born-digital pdf, docx or pptx is extracted only when the student asks.
- **External links (url modules).** Record them on the course page as notes, and read each target URL (the anchor on `mod/url/view.php`). If the target is a downloadable pdf, treat it as above. Licensed viewers and catalogues cannot be downloaded. A Kotar target (`kotar` in the host, often through the `openathens.net` proxy) is a reading: run `/academic-writer:kotar-fetch` for the pages the course names, which saves them as one PDF to treat as above. Only if that fails, add `courses.py chores add --course <slug> --kind kotar-source --ref <cmid> --title "<reading>" --text "<Kotar URL, pages if the course names them, why the fetch failed>"`.
- **Zoom recordings** (`biu-ac-il.zoom.us/rec/...`). Try to download the recording so the user can extract its audio; if it downloads, route it as a recording source (`add-source`, `kind: media`). If the host disabled download, use Zoom's transcript: save it as `.txt` and run `courses.py add-source <file> --transcript --course <slug> --date <YYYY-MM-DD> [--time <HHMM>]`. The recording covers the whole lesson, with humor, asides and other speakers, and the transcript will misspell names. When summarising: identify the lecturer (the voice who teaches; confirm from the course JSON's `lecturer`), extract the main ideas, keep meaningful asides (marked as asides), set other speakers apart, and mark doubtful names or passages `[לא ברור]` instead of correcting them.
- **Zoom meeting links** (`mod/zoom`, or a url to `zoom.us/j/...`; a live session, not a recording). Nothing to download: note the link and its date on the course page, add no chore, and mark the item seen. Only a recording (`/rec/`) is a source.
- **Perusall** (`app.perusall.com`, an LTI item). The original pdf usually sits in the same section: if it does, download and route it like any pdf (no OCR). If there is no pdf twin, add a chore and do nothing else with the item: `courses.py chores add --course <slug> --kind perusall-capture --ref cm:<cmid> --title "<reading>" --text "Capture the text with Google Lens into the course Drive folder (section subfolder)"`. When the user says the capture is done, route the captured file with `add-source` and mark the chore done (`chores done <id>`).
- **Assignments** (`mod/assign`). Extract an `assign` page: the `הזמן שנותר` text (`time_left_text`), the due date (`due_text`) and the task text. Identify the core texts (for example "pages 308-322 of Dan's chapter on Sefer ha-Qanah; the article A kabbalistic reading") and confirm each exists in the course's sources or in the section. If a core text points to Kotar, run `/academic-writer:kotar-fetch` for its pages; add a `kotar-source` chore only if that fails. Always add an `assignment` chore: `courses.py chores add --course <slug> --kind assignment --ref <cmid> --title "<assignment>" --time-left-text "<...>" --due-text "<...>" --core-text "<text 1>" --core-text "<text 2>"`. A changed deadline or task (`changed_assigns`) updates the same chore (same course, kind and ref).
- **Readings announced in a post** (an announcement or forum post that says what to read for a lesson, such as "לקראת שיעור הבא, נא לקרוא ..."). Add a `reading` chore per post: `courses.py chores add --course <slug> --kind reading --ref d<discussion id>-p<post id> --title "<post subject>" --text "<what to read, as the post says it>" --core-text "<text 1>" --core-text "<text 2>" --due-at <start of the lesson it is for, ISO with offset>`. The lesson is the one the post names (a date), or else the course's next lesson after the post (its `slots`). Then treat each core text like an assignment's: confirm it is in the course's sources or section, and run `/academic-writer:kotar-fetch` for a Kotar text with named pages. A `reading` chore becomes a reading task on the dashboard; the student closes it with "I read".
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
