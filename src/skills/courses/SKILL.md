---
name: courses
description: "Use when setting up an academic term from a schedule, validating course resources, syncing your LMS (Moodle) materials, or running the daily course scan."
user-invocable: true
allowedTools: [Bash, Read, Write, AskUserQuestion]
metadata: {author: "Academic Writer", version: "0.1.0"}
---

# Academic Writer — Courses

Set up and maintain one Drive folder, NotebookLM notebook, and Trove manuscript for each course. Course identities, external resource IDs, naming templates, LMS settings, and local paths belong in the user's private registry, never in this plugin.

## Registry and configuration

The registry root is `$ACADEMIC_COURSES_DIR`; otherwise use `~/.academic-writer/courses/<term>/`. `courses.py` reads `term.json` and one `<slug>.json` per course. Resolve the script as `${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py`. The registry is user data and must not be committed to a project.

Document and preserve these `term.json` fields:

- `term`: display name or academic-term key.
- `timezone`: IANA time zone used to interpret recording and slot times.
- `semesters`: A/B objects with inclusive `start` and `end` dates; yearly slots are active in either configured semester.
- `naming`: `drive`, `notebook`, and `manuscript` templates. Template context includes course fields and `term`.
- `drive_subject_folders`: subject-folder labels mapped to Drive folder IDs; `drive_remote` is the rclone remote name.
- `lemida`: `base_url`, optional `keychain_service` (default `academic-writer-lemida`) and `keychain_account`; the token remains in the OS keychain.
- `voice_memos_dir`: local recording directory; `local_root`: local LMS download root.
- `notebook_source_limit`: maximum sources to allow before stopping (default 45).
- `state.last_voice_memo_scan`: last completed scan boundary, stored as an ISO timestamp.

Each course JSON has `slug`, `code`, `name`, `lecturer`, `slots` (`day`, `start`, `end`, `semester`), `drive_subject_folder`, `drive_folder_id`, `notebook_id`, `manuscript_id`, `book_id`, `lemida_course_id`, `lemida_seen`, and `lessons`. `manuscript_id` identifies the Trove manuscript; `book_id` identifies the manuscript's Trove book/item. Lesson records include date, audio SHA-256, NotebookLM source ID, Trove page, and status. Keep unknown schedule details marked for review; do not infer a course, time, or ID.

## Set up a term from a schedule

1. Inspect the schedule and run a dry parse:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py" import-docx "/path/to/schedule.docx" --dry-run
   ```

2. Present a table with course name, code, lecturer, day, hours, semester, proposed Drive subject folder, notebook title, and manuscript title. Identify tentative/admin entries and unresolved slots. Ask the user to confirm the courses and subject-folder choices before creating anything.
3. After confirmation, create the registry directory and `term.json`, then one JSON per confirmed course. Naming defaults: Drive folder and NotebookLM notebook use the course name exactly; manuscript uses the configured template (for example `Personal · <term> · <course name>`). Do not put real IDs in skill text or examples.
4. For each missing resource, create a Drive folder named exactly as the course under its configured subject folder using the Drive connector's `create_file` with folder MIME type; create a notebook with `nlm notebook create "<course name>" --json`; check `trove auth whoami --no-session` for the plan/quota, then create a Trove manuscript with `trove ms create "<manuscript title>" --instructions "<configured LMS course ID, Drive URL, and reading-extraction rules>" --json --no-session`. Ask before renaming or replacing any existing resource. Record returned IDs immediately in the course JSON.
5. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py" validate`. Resolve each mismatch by renaming the external resource after asking; never make a wrong resource appear valid by changing the registry's expected name. Repeat until exit 0.

## Validate existing resources

Run `courses.py validate` (add `--json` when machine-readable output is useful). It checks each configured Drive folder, NotebookLM notebook, and Trove manuscript by ID and expected name. Report all mismatches. Do not silently repair or delete resources.

## LMS and readings

Use `courses.py lemida-sync --dry-run` to preview API changes when a Lemida token is available in the OS keychain; otherwise use the user's browser session to inspect their LMS (Moodle). Download PDFs and DOCX files; list Zoom, forum, and videostream entries by name. Never bulk-download LTI/Perusall readings: capture pages on demand about a week before the lesson. Keep copyrighted readings only in the user's own Drive and Trove, in the relevant course's manuscript.

For scanned readings, use Claude vision OCR: render with `pdftoppm -r 150`, then inspect the PNG pages. Do not use Gemini for course readings. For Google Docs, export native DOCX and convert with `pandoc`. When extracting Hebrew from two-column pages, join columns right to left and preserve reading order. Flag unclear text instead of silently reconstructing it.

## Daily scan

`courses.py daily` scans Voice Memos since `state.last_voice_memo_scan`, maps each recording from its timestamp to a configured course slot, syncs changed Lemida resources, and reports queued lesson jobs. Out-of-slot, ambiguous, or out-of-semester recordings need human review; never guess. A scan boundary advances only after the Voice Memos scan completes.

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
