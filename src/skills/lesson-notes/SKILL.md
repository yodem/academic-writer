---
name: lesson-notes
description: "Use when processing a course recording into a structured Hebrew lesson note, or when resuming queued NotebookLM lesson transcripts with --pending."
user-invocable: true
allowed-tools: [Bash, Read, Write, AskUserQuestion]
metadata: {author: "Academic Writer", version: "0.1.0"}
---

# Academic Writer — Lesson Notes

Turn NotebookLM's transcript of a course recording into one concise, structured Trove page. This is a lesson note, not a transcript. Read the whole transcript in one pass because arguments and references can recur across the lesson.

## Arguments

- `<audio file>` — ingest and process one recording.
- `--pending` — process each job in `<registry>/queue/`; unattended mode skips anything requiring a person and records it in `logs/pending-<date>.md`.
- `--course <slug>` — explicitly select a configured course.
- `--source-id <id>` — reuse a NotebookLM source already in that course's notebook.

Resolve the registry as described in `/academic-writer:courses`. Resolve the script as `${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py`.

## Ingest or resume

1. For an audio argument, find its course with `courses.py map <audio>` (or take `--course`), then run `courses.py add-source <audio> --course <slug> --json` (a recording is a source: snapshot, Drive, notebook, then the lesson). It maps the recording's creation time against the weekly schedule, uploads audio to the selected course's NotebookLM notebook (unless a source ID was supplied), obtains the NotebookLM transcript, and writes a queue job. NotebookLM is the transcript source of record; do not substitute another transcription service.

   **Zoom transcript without a download.** When the host shares a Zoom transcript (speaker names and timestamps) but disabled recording download, save it as a `.txt` file and run `courses.py add-source <file> --transcript --course <slug> --date <YYYY-MM-DD> [--time <HHMM>] --json` (a source like any other: snapshot, Drive, notebook, then the lesson); it needs no recording-time mapping, uploads the text itself to the course notebook, and uses the file as the transcript (`transcript_source: file` in meta.json). Such transcripts do carry timestamps and named speakers, so the page may use `[HH:MM:SS]` anchors in the flow and claims, but treat its speaker names as device labels, not people: the classroom microphone is usually logged under the lecturer's name, so students in the room appear as the lecturer. Attribute by content (the lecturer leads, explains, assigns; questions, objections and self-introductions come from students), name a student only when the name is said aloud, and say so in the page's transcript-quality line; every other rule is unchanged.
2. If no course matches, multiple courses match, or the semester/slot is unclear, ask the user to choose. In `--pending` or unattended mode, skip and log the ambiguity; never guess.
3. For each queue job, read `transcript.txt` completely, its `meta.json`, the course JSON, the course-book rules (`../courses/references/course-book.md`), the book ToC (`trove items toc <book_id> --no-session`), and the course index page. Follow those rules and the existing changelog conventions.
4. If transcript passages cannot be understood, mark them `[לא ברור]`; never reconstruct them. NotebookLM transcripts may lack speaker labels, so attribute only what the audio/transcript supports.

## Wispr Flow lectures

The nightly job runs `courses.py wispr-scan` before `--pending`. It opens Wispr Flow's database read-only, keeps finished meetings, and matches each recording's local start/end to one course slot (weekday, semester dates, start no more than 20 minutes early, overlap of at least 30 minutes or half the recording). A match is written as a speaker-labelled text transcript plus Wispr's summary and queued like a Zoom transcript (`add-source --transcript`), so this skill processes it as usual; the summary is a hint and the transcript is the source. If a lesson for that course and date already exists (a voice memo, say), the Wispr transcript is only kept as an `alternates` entry on that lesson in `lessons/<slug>/<lesson_key>/wispr-<id>.txt`; never replace an existing Trove page from it. A meeting that matches no course or several is never opened: only its id, times and reason go to `digest/wispr-unmatched.json` for the dashboard. Imported meeting ids live in `term.json` `state.wispr_seen` and in each lesson's `wispr_meeting_id`. `courses.py wispr-scan --dry-run --json` previews it.

## Write one lesson page

Write a single Hebrew Markdown page with exactly one top-level heading:

```markdown
# שיעור <n> · <date> · <course name>

> Load this page when: working on the <date> lesson of <course name> — its arguments, positions, questions or assignments.

- קורס: <course name>
- מרצה: <lecturer as configured>
- תאריך: <date>
- משך: <duration, or לא צוין>
- מקור: NotebookLM · <notebook title> · <source id>
- מפתח שיעור: <lesson_key>
- איכות תמלול: תמלול NotebookLM בעברית, ללא תוויות דוברים; קטעים לא ברורים סומנו [לא ברור].

## תקציר
<3–6 sentences: topic, central movement, and where the lesson ended>

## מהלך השיעור
1. <opening/admin only when it matters>
2. <topic/text, argument development, and transitions in order>

## טענות וטיעונים
- **<claim>** — <supporting steps>; <holder>. “<short grounding quote>”.

## עמדות ודוברים
- **<speaker/position>** — <position and context>. Name a student only when the name is said aloud; otherwise use סטודנט/סטודנטית. Present unknown-speaker statements as opinions, not facts.

## שאלות ודיונים
- <question> → <answer or outcome>; mark unresolved issues פתוח.

## מטלות, קריאה ומועדים
- <next reading, assignment, deadline, exam information, or course requirement; write לא הוזכרו only if none were mentioned>

## מושגים
- **<term>** — <one-line gloss>.

## לקריאה נוספת
- <texts and thinkers mentioned>
```

NotebookLM transcripts carry no timestamps, so the flow is ordered, not timed; never invent clock times. Quotes ground claims; keep each quote short (about 20 words maximum) and as transcribed, correcting only obvious transcription slips (a doubled word, a swapped letter) without changing content; drop any claim without a supporting transcript span. Name a thinker, study or text only when the transcript names it or the reference is unambiguous. Preserve all assignments, next-week readings, deadlines, exam details, and course requirements even when they were brief or administrative. Use “לא הוזכרו” only when none occurred. Distinguish the lecturer (the voice that leads, explains, and assigns), named thinkers/texts, students, and unidentified speakers. Sarcasm becomes its literal claim only when clear; otherwise omit it.

Drop greetings, small talk, audio/Zoom trouble, jokes, banter, unsupported personal anecdotes, false starts, and repeated restatements. Do not invent facts, names, quotes, timestamps, or duration; write לא צוין for a duration the metadata does not give.

## Append and rebuild the ToC

ToC rule: one entry per page, "Title - hint", nested in tree order (siblings by page; lesson pages under תמלולי שיעורים).


Key every step on the book's current structure (`trove items toc <book_id> --json --no-session`), never on whether this is the first lesson.

**Resume, don't repeat.** Every lesson page carries its key in the header block (`- מפתח שיעור: <lesson_key>`). Before writing anything for a queue job, look up its lesson in the course JSON by `lesson_key`; if it has no `trove_page`, also run `courses.py find-lesson-page <slug> <lesson_key>` (exact match on the key line; prints the page number, exit 3 if none) in case an earlier run appended it without recording it. If either finds the page, do not append it again: record it with `lesson-done ... --status appended` if needed, then redo the rest of step 3 idempotently (add the changelog line and the units-list entries on page 1 and the entry page only if they are missing), then step 5 (rebuild the ToC with that page nested) and step 6, archiving the job only when `check-lesson` exits 0. If it still fails, leave the job queued and log the reason.

1. If the book has no page-1 course index (a `Course · <course name>` page), append one first: course details from the course JSON, a `> Load this page when:` line, what the course is about, and a units list.
2. If the ToC has no level-1 `תמלולי שיעורים` entry, append a `# תמלולי שיעורים` entry page explaining the course (subject, lecturer, central questions), how lesson pages are built, and their limits. If it exists but its course explanation is still a placeholder, rewrite that page once the first lesson gives enough to explain the course.
3. Append the lesson page with `trove items append <book_id> -f <page.md> --no-session`, read the ToC to get its page number, and record it at once with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py" lesson-done <slug> <lesson_key> --page <N> --status appended`. Add a dated line to the `Course · Changelog` page, and add the lesson to the units list on page 1 and on the entry page.
4. To change an existing page use `trove items put <book_id>:<page> -f <file> --expect-version <V> --no-session`, where `V` is `currentVersion` from `trove items history <book_id> --json --no-session` read just before the put.
5. **Last**, rebuild the sidebar with `trove items enrich <book_id> --toc '<full-json-array>' --no-session`. Both `append` and `put` regenerate the sidebar from headings and flatten it, so this step always comes after every content write. Send the complete array (it replaces the sidebar) following the ToC rule below: every page has its own entry titled `Title - hint`, in page order, with the Changelog page in its page position. Page-1 index level 1, `תמלולי שיעורים` level 1, each lesson level 2 directly after it in date order titled `שיעור <n> · <date> - <hint>`, then every other existing page at its level (readings under `חומרי קריאה`: source level 2, its sections level 3). Never delete pages.
6. Audit the book from the plugin repository checkout (the tools are repo-local, not shipped in the installed plugin): `python3 tools/toc_rebuild.py --course <slug>` (dry run, then `--apply`), then `python3 tools/toc_audit.py --course <slug>`. Then verify that lesson with `courses.py check-lesson <slug> <lesson_key>` (exit 0 = nested), then mark it done with `courses.py lesson-done <slug> <lesson_key> --page <N>` and only then move the queue file to `queue/done/`.

## Report and unattended behavior

Report course, lesson key, Trove page number, counts of claims/questions/terms, and any unclear spans omitted. In `--pending`/unattended mode, never ask questions: skip ambiguous jobs and jobs needing resource changes, and list each in `<registry>/logs/pending-<date>.md` with a reason. Continue processing independent valid jobs.
