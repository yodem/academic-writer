---
name: help
description: "Short, plain-language overview of Academic Writer and its commands, with the three first steps for a new user. Use when the user asks what the plugin can do, which command to run, or where to start."
user-invocable: true
allowed-tools: [Read]
model: haiku
metadata: {author: "Yotam Fromm", version: "0.16.0", summary: "A short list of every command and the three steps to get started."}
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
| `/academic-writer:setup` | Friendly first-run setup for researchers with no technical background: checks each tool Academic Writer needs, explains it in one sentence, asks before installing anything, walks you through getting and safely storing a free Gemini key, and ends with a sample paragraph. |
| `/academic-writer:init` | Full onboarding for Academic Writer: builds your researcher profile, learns your writing style from past articles, connects your research library, and offers Gemini. |
| `/academic-writer:write` | Write a new academic article with the author, step by step: topic, sources, verified evidence, the author's thesis, an approved outline, drafting, a citation audit and a Word file. |
| `/academic-writer:revise` | Read the Word comments and tracked changes the author left on a generated draft, group them, confirm each group, then update the article and the voice and feedback stores. |
| `/academic-writer:edit` | Revise an article you already drafted: several passages at once, tone, structure, argument order or evidence. |
| `/academic-writer:edit-section` | Quick revision of one section of an existing article: rewrite, expand, shorten, fix its citations or adjust its style. |
| `/academic-writer:proofread` | Proofread a finished article (Markdown or Word) for typos, wrong words, grammar and editorial issues, producing a corrected copy, a report and an editorial memo without touching the original. |
| `/academic-writer:review` | Score a completed article on six dimensions (structure, argument logic, citation completeness, source coverage, writing quality, academic conventions) and show a scorecard with concrete findings. |
| `/academic-writer:research` | Investigate a topic or check a claim against the author's indexed sources, returning only passages whose quotations were verified word for word. |
| `/academic-writer:ideate` | Guided brainstorming that turns a vague topic into a sharp research question, using who/what/when/where/why/how, a gap check against the author's sources and a choice of approach; saves a research brief that /academic-writer:write reads. |
| `/academic-writer:ocr` | Turn a scan or photo into plain text with Gemini, Claude, Codex or Tesseract, your choice. |
| `/academic-writer:ingest` | Upload one article or chapter to the source library with printed page numbers, hinted contents and a citation guide. |
| `/academic-writer:ingest-book` | Upload a whole book (multi-volume, scanned or EPUB) to the source library with a navigable hinted table of contents and a citation guide. |
| `/academic-writer:library-eval` | Compare Trove and PageIndex on your own article: anonymised pairs you judge yourself, then the unblinded results. |
| `/academic-writer:voice` | Build or update the author's voice profile: import older voice files, choose exemplar paragraphs from past papers, derive writing rules and sync them to Trove. |
| `/academic-writer:health` | Check that Academic Writer is ready to use — your profile, the tools it needs (Python and its add-ons, Hebrew spelling, Trove, NotebookLM), the Gemini key and past articles — with a plain-language fix for anything missing. |
| `/academic-writer:help` | A short list of every command and the three steps to get started. |
| `/academic-writer:courses` | Use when setting up an academic term from a schedule, validating course resources, syncing your LMS (Moodle) materials, or running the daily course scan. |
| `/academic-writer:kotar-fetch` | Download the cited pages of a book on Kotar (CET, through the Bar-Ilan OpenAthens proxy) as one PDF in printed-page order, for the author's own study. |
| `/academic-writer:lesson-notes` | Use when processing a course recording into a structured Hebrew lesson note, or when resuming queued NotebookLM lesson transcripts with --pending. |
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
