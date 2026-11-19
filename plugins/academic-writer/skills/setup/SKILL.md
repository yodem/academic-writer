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

## How to run

1. If the first word of the arguments is a phase in the table, that is the phase. Everything after it is the phase's arguments. This rule wins over every rule below.
2. No arguments at all (a bare `/academic-writer:setup`): run `setup`, always, without asking or inferring.
3. The arguments are a single bare word that is not in the table: print the table and stop.
4. Anything else is a request in the author's words, whose first word is not a phase: infer the phase from the request. If two phases fit, ask the author which one. Do not guess.
5. Read exactly one file, `${CLAUDE_SKILL_DIR}/phases/<phase>.md`, and follow it as if it were this skill's body. The one exception: when that phase names a sibling phase file of this router to continue with, read that file too, only at that point. The paths inside it that start with `${CLAUDE_SKILL_DIR}` or `${CLAUDE_PLUGIN_ROOT}` are already correct.

## Light phases

`update-field` and `help` ran on a small, fast model before. Run each as one subagent, not inline: dispatch ONE subagent with the Agent tool, `model: haiku` (add `effort: low` for `update-field`), whose prompt gives the absolute path `${CLAUDE_SKILL_DIR}/phases/<phase>.md` (tell it to read and follow that file) and the arguments, then relay its result to the author. Every other phase runs inline.

## Phases that were by name only

`setup`, `init` and `voice` were never offered to the model on its own: run them only when the author typed that phase (or the bare `/academic-writer:setup`). Do not start them from a loose request; suggest the command instead.
