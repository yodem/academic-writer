---
name: write
description: "One entry point for the article workflow, run one phase at a time. Use when the author wants to brainstorm a research question, write a new article from scratch, edit a drafted article or one section of it, fold Word comments and tracked changes back in, proofread a finished article, score it before submission, check a claim against their sources, prepare a talk, abstract or chapter proposal, or see the progress of a running article."
user-invocable: true
argument-hint: "<phase> [args]"
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, Agent, Workflow, AskUserQuestion, mcp__notebooklm-mcp__notebook_create, mcp__notebooklm-mcp__source_add, mcp__notebooklm-mcp__studio_create, mcp__notebooklm-mcp__studio_status, mcp__notebooklm-mcp__download_artifact]
metadata: {author: "Yotam Fromm", version: "0.3.0"}
---

# Academic Writer: the article workflow

This skill is a router. Pick one phase, read its file, and follow it. Never load more than one phase file per run.

## Phases

| Phase | When to use | File |
|---|---|---|
| `new` | Write a new article from scratch: topic, sources, evidence, thesis, outline, drafting, citation audit, Word file | `phases/new.md` |
| `ideate` | Brainstorm: turn a vague topic into a sharp research question and save a research brief | `phases/ideate.md` |
| `edit` | Revise a drafted article across several passages: tone, structure, argument order or evidence | `phases/edit.md` |
| `edit-section` | Quick revision of one section or passage of an existing article | `phases/edit-section.md` |
| `revise` | Read Word comments and tracked changes on a generated draft and update the article: `<file.docx> [--editor [original.docx]]` | `phases/revise.md` |
| `proofread` | Proofread a finished article for typos, wrong words and grammar, with a corrected copy and a report | `phases/proofread.md` |
| `review` | Score a completed article on six dimensions before submission | `phases/review.md` |
| `research` | Check a claim or ask what the author's sources say, with verified quotations only | `phases/research.md` |
| `present` | Turn a finished article into a talk outline, abstract with keywords, chapter proposal or study materials | `phases/present.md` |
| `watch` | Show what Academic Writer is doing right now: current step, progress and anything rejected | `phases/watch.md` |

## How to run

1. If the first word of the arguments is a phase in the table, that is the phase. Everything after it is the phase's arguments. This rule wins over every rule below.
2. No arguments at all (a bare `/academic-writer:write`): run `new`, always, without asking or inferring.
3. The arguments are a single bare word that is not in the table: print the table and stop.
4. Anything else is a request in the author's words, whose first word is not a phase: infer the phase from the request. If two phases fit, ask the author which one. Do not guess.
5. Read exactly one file, `${CLAUDE_SKILL_DIR}/phases/<phase>.md`, and follow it as if it were this skill's body. The paths inside it that start with `${CLAUDE_SKILL_DIR}` or `${CLAUDE_PLUGIN_ROOT}` are already correct.

## Forked phases

`proofread` and `research` ran in their own context before. Run each as one subagent, not inline: dispatch ONE subagent with the Agent tool, `model: sonnet` and `effort: medium`, whose prompt gives the absolute path `${CLAUDE_SKILL_DIR}/phases/<phase>.md` (tell it to read and follow that file) and the arguments, then relay its result to the author. Every other phase runs inline.

## Before `new` (short form, full text in `phases/new.md`)

- Voice gate: before Step 1, check the author's voice store in `${CLAUDE_PLUGIN_DATA}/voice/`. When it is missing or empty, ask whether to build it first with `/academic-writer:setup voice`; on "Build my voice first" stop. The exact check and answers are in the "Voice precondition gate" section of `phases/new.md`.
- Existing-article guard: compute the article's slug, and if `articles/<slug>.md` already exists, stop and point the author to `/academic-writer:write edit articles/<slug>.md` (or `edit-section`). The check is in the "existing-article guard" section of `phases/new.md`.
- Preflight: if the author has not run `/academic-writer:setup`, ask them to run it first.
