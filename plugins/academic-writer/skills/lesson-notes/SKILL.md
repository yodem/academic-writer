---
name: lesson-notes
description: "Use when processing a course recording into a structured Hebrew lesson note, or when resuming queued NotebookLM lesson transcripts with --pending."
user-invocable: true
allowedTools: [Bash, Read, Write, AskUserQuestion]
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

1. For an audio argument, run `courses.py ingest <audio> [--course <slug>] [--source-id <id>] --json`. It maps the recording's creation time against the weekly schedule, uploads audio to the selected course's NotebookLM notebook (unless a source ID was supplied), obtains the NotebookLM transcript, and writes a queue job. NotebookLM is the transcript source of record; do not substitute another transcription service.
2. If no course matches, multiple courses match, or the semester/slot is unclear, ask the user to choose. In `--pending` or unattended mode, skip and log the ambiguity; never guess.
3. For each queue job, read `transcript.txt` completely, its `meta.json`, the course JSON, the manuscript instructions (`trove ms show <manuscript_id> --no-session`), the book ToC (`trove items toc <book_id> --no-session`), and the course index page. Follow the manuscript's instructions and existing changelog conventions.
4. If transcript passages cannot be understood, mark them `[לא ברור]`; never reconstruct them. NotebookLM transcripts may lack speaker labels, so attribute only what the audio/transcript supports.

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

Key every step on the book's current structure (`trove items toc <book_id> --json --no-session`), never on whether this is the first lesson.

1. If the book has no page-1 course index (a `Course · <course name>` page), append one first: course details from the course JSON, a `> Load this page when:` line, what the course is about, and a units list.
2. If the ToC has no level-1 `תמלולי שיעורים` entry, append a `# תמלולי שיעורים` entry page explaining the course (subject, lecturer, central questions), how lesson pages are built, and their limits. If it exists but its course explanation is still a placeholder, rewrite that page once the first lesson gives enough to explain the course.
3. Append the lesson page with `trove items append <book_id> -f <page.md> --no-session`, then read the ToC to get its page number. Add a dated line to the changelog page if the manuscript has one, and add the lesson to the units list on page 1 and on the entry page.
4. To change an existing page use `trove items put <book_id>:<page> -f <file> --expect-version <V> --no-session`, where `V` is `currentVersion` from `trove items history <book_id> --json --no-session` read just before the put.
5. **Last**, rebuild the sidebar with `trove items enrich <book_id> --toc '<full-json-array>' --no-session`. Both `append` and `put` regenerate the sidebar from headings and flatten it, so this step always comes after every content write. Send the complete array (it replaces the sidebar): page-1 index level 1, `תמלולי שיעורים` level 1, each lesson level 2 directly after it in date order titled `שיעור <n> · <date>`, then every other existing page at its level. Never delete pages.
6. Record the lesson with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/courses/courses.py" lesson-done <slug> <lesson_key> --page <N>`, then verify that lesson with `courses.py check-lesson <slug> <lesson_key>` (exit 0 = done and nested). Only then move the queue file to `queue/done/`.

## Report and unattended behavior

Report course, lesson key, Trove page number, counts of claims/questions/terms, and any unclear spans omitted. In `--pending`/unattended mode, never ask questions: skip ambiguous jobs and jobs needing resource changes, and list each in `<registry>/logs/pending-<date>.md` with a reason. Continue processing independent valid jobs.
