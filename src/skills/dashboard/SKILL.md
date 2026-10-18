---
name: dashboard
description: "Open the local course dashboard: one page that shows, for every course in the term, what is due next, whether its readings are ready, and what is new, with a week agenda and a page per course. Use when the student asks to see their courses at a glance, what is due this week, which readings are missing, or to open the dashboard. Runs on 127.0.0.1 only. Not for setting up courses or syncing Lemida (use /academic-writer:courses)."
user-invocable: true
allowed-tools: [Bash, Read]
metadata: {author: "Academic Writer", version: "0.1.0"}
---

# Academic Writer — Course dashboard

A local page for the course registry that `/academic-writer:courses` maintains. The server is `courses.py dashboard` (`${CLAUDE_PLUGIN_ROOT}/scripts/courses/dashboard.py`): Python standard library only, listening on `127.0.0.1` and nowhere else.

## Start it

1. Start the server in the background (the Bash tool's `run_in_background`), so this session stays free:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py" --data-dir "${CLAUDE_PLUGIN_DATA}" dashboard --no-open
   ```

   Pass `--term <name>` when the registry holds more than one term, and `--port N` to try another port first (default 8787; a busy port falls back to a free one).
2. Read the first line of its output: `Dashboard: http://127.0.0.1:<port>/?key=<key>`. Print that URL for the student, or open it with `open "<url>"` (macOS) when they asked you to open it.
3. Tell them, in one or two sentences:
   - It is local only: it listens on 127.0.0.1, and the key in the URL is the password for this run (a new key every start). The page keeps working from a cookie after the first load.
   - The page updates by itself when the registry changes; there is nothing to refresh.
   - Stopping the background job stops the page.

If the output says there is no registry yet, the page shows an empty state; suggest `/academic-writer:courses` to set up the term.

## What the page does, and what it leaves to Claude

- **Overview, agenda, course page.** Read-only views of `term.json`, the course files, `links.json`, `refs/`, the chores store, `digest/wispr-unmatched.json` (time only) and the nightly log.
- **"I submitted" / "I read"** marks the task submitted through `tasks.py` (the same as `courses.py task submit`) and closes its chores; the 5-second undo calls `courses.py task unsubmit`.
- **"Fetch selected"** only writes a job to `REG/queue/fetch/<timestamp>-<course>.json` with the ref keys (and the task, when there is one). The page never fetches anything. The nightly run drains the queue with `refs.py fetch-queue` (the fetch chain per ref, results written into the job, finished jobs moved to `REG/queue/fetch/done/`; anything that needs the signed-in browser becomes a chore). The page tells the student that Claude will do it in the nightly run, never that it is done.
- **Dragging a reading** to another day in the agenda is stored in that browser only; the registry is not changed.

Never edit registry files to make the page look different; fix the data through the courses commands.
