---
name: help
description: "Short, plain-language overview of Academic Writer and its commands, with the three first steps for a new user. Use when the user asks what the plugin can do, which command to run, or where to start."
user-invocable: true
allowed-tools: [Read]
model: haiku
metadata: {author: "Yotam Fromm", version: "0.15.0", summary: "A short list of every command and the three steps to get started."}
---

# Academic Writer — Help

Show the user the text below, lightly formatted for the chat. Do not run any commands, do not read
their files, and do not add technical detail they did not ask for. The reader is a humanities
researcher, not a programmer. If they ask a follow-up question, answer it in the same plain style,
and point to `/academic-writer:intro` for the full illustrated guide.

---

## What Academic Writer does

Academic Writer helps you write a scholarly article in your own voice, grounded only in sources you
choose. You talk it through with Claude: the topic, the sources, the thesis and the outline. Then the
plugin drafts the article, checks every footnote against your sources, and gives you a Word file
(`.docx`). You mark it up in Word, and it folds your comments back in.

It works in Hebrew and in English.

## Start here: three steps

1. **Read the guide (optional, 5 minutes):** `/academic-writer:intro` opens a full guide in your
   web browser that explains each step.
2. **Set up (about 10 minutes, once):** `/academic-writer:setup` walks you through getting a free
   Gemini key (a kind of password that lets the plugin use Google's AI), checks the small tools it
   needs, and asks before installing anything.
3. **Write:** `/academic-writer:write` starts your first article. Claude asks you one question at a
   time.

Want the plugin to learn your personal writing style from your past articles first? Run
`/academic-writer:init` after setup.

## All commands

This table is generated from the plugin itself, so it is always complete.

<!-- help:commands:start -->
| Command | What it does |
|---|---|
| `/academic-writer:intro` | Open the full guide in your web browser: what the plugin does, setup, your first article, privacy and troubleshooting. |
| `/academic-writer:setup` | Friendly, guided first-run setup wizard for a non-engineer: one question at a time, gets your Gemini API key working with a live test, checks your Python tools, and shows you a sample paragraph before you're done. |
| `/academic-writer:init` | First-time setup for the Academic Writer. |
| `/academic-writer:write` | Write a new academic article. |
| `/academic-writer:revise` | Read Word comments and tracked changes, confirm grouped revisions, and update article and feedback stores. |
| `/academic-writer:edit` | Edit a previously written article — revise sections, fix citations, adjust tone, restructure arguments, or rewrite passages. |
| `/academic-writer:edit-section` | Quick edit of a single section — rewrite, expand, cut, fix citations, or adjust style. |
| `/academic-writer:proofread` | Use when a finished article needs deterministic typo, language, and editorial proofreading with a visible corrected copy and report. |
| `/academic-writer:review` | Self-review quality gate — scores a completed article on 6 dimensions (structure, argument logic, citation completeness, source coverage, writing quality, academic conventions) and presents a scorecard before final output. |
| `/academic-writer:research` | Use when investigating a topic or checking claims against indexed sources. |
| `/academic-writer:ideate` | Guided research ideation — brainstorm research questions using 5W1H, gap analysis, and structured framing. |
| `/academic-writer:ocr` | OCR a scanned PDF or image (or a directory of them) into clean plain-text markdown via the bundled Gemini vision tool. |
| `/academic-writer:voice` | Manage the shared author voice store: migrate, choose exemplars, derive writing moves, and sync it. |
| `/academic-writer:health` | Check the health of all Academic Writer integrations — profile, Candlekeep, RAG, past articles, and source index. |
| `/academic-writer:help` | A short list of every command and the three steps to get started. |
<!-- help:commands:end -->

## The usual cycle

1. `/academic-writer:write` gives you a Word file.
2. You open it in Word and add comments or tracked changes wherever you want something changed.
3. `/academic-writer:revise` reads your comments, asks you to confirm, and updates the article.
4. `/academic-writer:proofread` does a final typo and language pass before you submit.

## If something goes wrong

- Run `/academic-writer:health`. It checks everything and says, in plain words, what to fix.
- Your Gemini key stopped working? Run `/academic-writer:setup` again. It is safe to repeat and
  never erases your profile.
- The "Troubleshooting" section of `/academic-writer:intro` covers the most common problems.

## Your files and privacy, in one paragraph

Your drafts and settings stay in your research folder (in a hidden folder named `.academic-helper`).
Your writing-style data lives in the plugin's own data folder on your computer. The text you work on
is sent to Anthropic (Claude) and, if you set up a Gemini key, to Google, only to do the writing
and checking you asked for. When you save your key through the plugin's settings (setup does this),
it is stored in your computer's secure keychain, not in a plain file.
