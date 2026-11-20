---
name: setup
description: "One entry point for first-run setup and care of Academic Writer, run one phase at a time. Use when the author has just installed the plugin or something seems missing (setup), asks whether the plugin is healthy or ready (health), turns Trove, NotebookLM or PageIndex on or off or switches the library route (update-tools), says their research field changed (update-field), wants drafts to sound more like them or has added finished papers to past-articles/ (learn), asks what the plugin can do or which command to run (help), or wants the full illustrated guide, a tutorial or an overview (intro). Full onboarding (init) and the voice profile (voice) are run by name only."
user-invocable: true
argument-hint: "<phase> [args]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, Agent, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.2.0"}
---

# Academic Writer: setup and care

This skill is a router. Pick one phase, read its file, and follow it. Load one phase file at a time; a phase may hand off to a sibling phase as rule 5 says.

## Phases

| Phase | When to use | File |
|---|---|---|
| `setup` | First-run setup for researchers with no technical background: checks each tool, asks before installing, walks through a free Gemini key, ends with a sample paragraph (the default; by name only) | `phases/setup.md` |
| `init` | Full onboarding: researcher profile, writing style from past articles, research library, Gemini; `--quick` for a fast pass (by name only) | `phases/init.md` |
| `health` | Check that Academic Writer is ready: profile, tools, connections, Gemini key and past articles, with a plain fix for anything missing | `phases/health.md` |
| `update-tools` | Turn Trove or NotebookLM on or off, change the library route (Trove, PageIndex or both), set up PageIndex, without redoing the full setup | `phases/update-tools.md` |
| `update-field` | Change the research field in the profile, keeping every other setting | `phases/update-field.md` |
| `voice` | Build or update the voice profile: import old voice files, choose exemplar paragraphs, derive writing rules, sync to Trove (by name only) | `phases/voice.md` |
| `learn` | Refresh the voice store from newly added past articles and from the author's own rewrites of drafts | `phases/learn.md` |
| `help` | Short overview of Academic Writer and its commands, with the three first steps for a new user | `phases/help.md` |
| `intro` | Open the full illustrated guide in the browser, then a five-line summary | `phases/intro.md` |

## Resolved paths

These values are filled in when this skill loads. A phase file's own `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}` and `$CLAUDE_PROJECT_DIR` are NOT filled in, and the shell may not define them.

- Skill directory: `${CLAUDE_SKILL_DIR}`
- Plugin root: `${CLAUDE_PLUGIN_ROOT}`
- Plugin data: `${CLAUDE_PLUGIN_DATA}`
- Project directory: the session's working directory (run `pwd` once to get it)

When a phase shows a shell command, replace those four names with the values above before running it (or `export` them in the same command). When you dispatch a subagent, give it these four values in the prompt.

## How to run

1. If the first word of the arguments is a phase in the table, that is the phase. Everything after it is the phase's arguments. This rule wins over every rule below.
2. No arguments at all (a bare `/academic-writer:setup`): run `setup`, always, without asking or inferring.
3. The arguments are a single bare word that is not in the table: print the table and stop.
4. Anything else is a request in the author's words, whose first word is not a phase: infer the phase from the request. If two phases fit, ask the author which one. Do not guess.
5. Read exactly one file, `${CLAUDE_SKILL_DIR}/phases/<phase>.md`, and follow it as if it were this skill's body. The one exception: when that phase names a sibling phase file of this router to continue with, read that file too, only at that point. A phase file is read as plain text, so the `${...}` variables inside it are not filled in for you: use the values under "Resolved paths" below.

## Light phases

`update-field` and `help` ran on a small, fast model before. Run each as one subagent, not inline: dispatch ONE subagent with the Agent tool, `model: haiku` (add `effort: low` for `update-field`), whose prompt gives the absolute path `${CLAUDE_SKILL_DIR}/phases/<phase>.md` (tell it to read and follow that file), the four resolved paths and the arguments, then relay its result to the author. Every other phase runs inline.

A subagent cannot talk to the author, so collect every answer here first. For `update-field`: ask the author for the new field of study in this conversation (if the arguments after the phase already hold it, use that), confirm it back in one line, then put it in the subagent prompt as `New field: <answer>` and tell it not to ask anything. When it returns, read `.academic-helper/profile.md` yourself and check that `fieldOfStudy:` holds the new field; if it does not, say so and fix it rather than relaying a success.

## Phases that were by name only

`setup`, `init` and `voice` were never offered to the model on its own: run them only when the author typed that phase (or the bare `/academic-writer:setup`). Do not start them from a loose request; suggest the command instead.
