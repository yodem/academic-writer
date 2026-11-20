---
name: courses
description: "One entry point for the student's academic term and courses, run one phase at a time. Use when setting up an academic term from a schedule, validating course resources, syncing the LMS (Moodle) materials, or running the daily course scan (term, the default), when the student wants to see their courses at a glance, what is due this week or which readings are missing (dashboard), or when processing a course recording into a structured Hebrew lesson note or resuming queued NotebookLM lesson transcripts with --pending (lesson-notes)."
user-invocable: true
argument-hint: "<phase> [args]"
allowed-tools: [Bash, Read, Write, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.2.0"}
---

# Academic Writer: courses

This skill is a router. Pick one phase, read its file, and follow it. Load one phase file at a time; a phase may hand off to a sibling phase as rule 5 says.

## Phases

| Phase | When to use | File |
|---|---|---|
| `term` | Set up a term from a schedule, validate course resources, sync the LMS (Moodle), run the daily scan and its steps such as `extract-handoff`, `trove-notes` and `calendar-sync` (the default) | `phases/term.md` |
| `dashboard` | Open the local course dashboard: what is due next, whether readings are ready, what is new, a week agenda and a page per course | `phases/dashboard.md` |
| `lesson-notes` | Turn a course recording's NotebookLM transcript into a structured Hebrew Trove lesson note; `--pending` resumes queued transcripts | `phases/lesson-notes.md` |

## Resolved paths

These values are filled in when this skill loads. A phase file's own `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}` and `$CLAUDE_PROJECT_DIR` are NOT filled in, and the shell may not define them.

- Skill directory: `${CLAUDE_SKILL_DIR}`
- Plugin root: `${CLAUDE_PLUGIN_ROOT}`
- Plugin data: `${CLAUDE_PLUGIN_DATA}`
- Project directory: the session's working directory (run `pwd` once to get it)

When a phase shows a shell command, replace those four names with the values above before running it (or `export` them in the same command). When you dispatch a subagent, give it these four values in the prompt.

## How to run

1. If the first word of the arguments is a phase in the table, that is the phase. Everything after it is the phase's arguments. This rule wins over every rule below.
2. No arguments at all (a bare `/academic-writer:courses`): run `term`, always, without asking or inferring.
3. The arguments start with a word that is not a phase and name one of the term's own steps (`extract-handoff`, `trove-notes`, `calendar-sync`, `validate`): run `term` with all the arguments.
4. Anything else is a request in the student's words: infer the phase from the request (seeing courses at a glance is `dashboard`, a recording or transcript is `lesson-notes`, anything else is `term`). If two phases fit, ask the student which one. Do not guess.
5. Read exactly one file, `${CLAUDE_SKILL_DIR}/phases/<phase>.md`, and follow it as if it were this skill's body. The one exception: when that phase names a sibling phase file of this router to continue with, read that file too, only at that point. A phase file is read as plain text, so the `${...}` variables inside it are not filled in for you: use the values under "Resolved paths" below.

## Shared by the phases

`references/` holds what several phases read: the course-book layout and ToC rules, the Lemida watcher notes and the library-refs runbook. A phase names the one it needs.
