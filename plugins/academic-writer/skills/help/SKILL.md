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
<<<<<<< HEAD
=======
|---------|-------------|
| `/academic-writer:write` | **Write a new article** — the full pipeline from subject to .docx |
| `/academic-writer:edit` | **Edit an article** — revise sections, fix citations, adjust tone, restructure |
| `/academic-writer:edit-section` | **Edit one section** — fast, focused single-section edit |
| `/academic-writer:proofread` | **Proofread** — three-stage pipeline (editorial venue-fit memo → language editing → mechanical הגהה) with a tracked-changes .docx and a change report; `--venue <slug>` scopes the editorial memo to a venue profile, `--only editorial\|language\|mechanical` runs a single stage |
| `/academic-writer:ocr` | **OCR a scanned PDF or image** — clean extracted text via Gemini vision, born-digital pages skipped automatically |
| `/academic-writer:courses` | **Manage courses** — set up a term from a schedule, validate Drive/NotebookLM/Trove resources, sync LMS readings, and run the daily scan |
| `/academic-writer:lesson-notes` | **Process lesson recordings** — use NotebookLM transcripts to create structured Hebrew lesson pages in the course manuscript; `--pending` resumes queued jobs |
| `/academic-writer:research` | **Research a topic** — query your sources, get answers with citations |
| `/academic-writer:init` | **First-time setup** — profile, style analysis, source indexing |
| `/academic-writer:health` | **System check** — verify all integrations are working |
| `/academic-writer:review` | **Self-review** — score a completed article on 6 quality dimensions |
| `/academic-writer:ideate` | **Brainstorm ideas** — 5W1H framework, gap analysis, research question formulation |
| `/academic-writer:setup` | **Quick setup** — creates profile, detects integrations |
| `/academic-writer:voice` | **Deep voice profile** — Stage 2 adversarial interview (7 sessions) |
| `/academic-writer:help` | **This help page** |

### Internal skills (invoked from other skills)

These don't have their own slash command; they run as sub-workflows:

- `learn` — run after dropping new files in `past-articles/` (auto-invoked by the dashboard hint)
- `update-tools` / `update-field` — invoked from within `init` or `setup`
- `present` — invoked from `edit` or `write` after a final article ships
- `feedback` — invoked from `edit` after researcher review

---

## How Article Writing Works

When you run `/academic-writer:write`, you go through a conversational pipeline:

### Phase 1: Planning (you + AI together)
1. **Subject** — Tell me what you want to write about
2. **Sources** — Select which of your indexed sources to use
3. **Deep Read** — AI explores your sources to map what's available
4. **Thesis** — AI proposes 2–3 thesis statements; you pick or modify
5. **Outline** — AI generates a structured outline; you refine it

### Phase 2: Writing (AI, with guardrails)
6. **Section Writing** — One AI agent per section, all writing in parallel
7. **Per-paragraph quality pipeline:**
   - **Draft** — Written using your sources, applying your style fingerprint
   - **Style Compliance** — Scored against your fingerprint on 10 dimensions
   - **Hebrew Grammar** — Academic Hebrew quality check (when applicable)
   - **Repetition Check** — No repeated words, phrases, or arguments
   - **Citation Audit** — Every footnote verified against sources (hard gate)
8. **Synthesis** — Final coherence review + full-article style compliance
9. **Output** — Clean .docx with footnotes and bibliography

---

## How Editing Works

When you run `/academic-writer:edit`, you can:
- **Revise sections** — rewrite or restructure any section (full skill pipeline: draft → style → grammar → repetition → audit)
- **Fix citations** — re-audit all footnotes, correct page numbers, add missing citations
- **Adjust tone** — make sections more/less formal, assertive, cautious — checked against your fingerprint
- **Restructure** — reorder, split, merge, add, or remove sections
- **Strengthen arguments** — find additional evidence, address counterarguments
- **Cut or expand** — shorten or lengthen specific sections
- **Full review** — run the complete synthesis + style compliance pass

For quick, single-section work, use `/academic-writer:edit-section` instead — it's faster because it only processes one section.

Both edit skills spawn **parallel subagents** for speed — multiple sections are edited simultaneously, and research queries (for finding new evidence) run in parallel across RAG and Trove.

---

## How Research Works

When you run `/academic-writer:research`, you can:
- Ask questions about your sources ("What does X say about Y?")
- Explore topics across all your documents
- Compare how different authors treat a concept
- Find exact quotes with page numbers
- Browse your Trove library

This is independent of the article pipeline — use it anytime you want to query your research materials.

---

## Your Style Fingerprint

The fingerprint is extracted from your past articles during `/academic-writer:init`. It captures 25 dimensions of your writing across 8 categories:

| Category | What it tracks |
|----------|---------------|
| **Sentence-level** | Length, structure variety, openers, passive voice |
| **Vocabulary** | Complexity, register, field jargon, Hebrew conventions |
| **Paragraph structure** | Pattern, length, argument progression, evidence handling |
| **Tone & voice** | Descriptors, authorial stance, hedging/asserting, engagement |
| **Transitions** | Preferred phrases by function, section bridging |
| **Citations** | Density, integration style, quote length |
| **Rhetorical patterns** | Common moves, opening/closing strategies |
| **Representative excerpts** | 5 real passages as style targets |

Every paragraph is scored against this fingerprint. The synthesizer also runs a full-article compliance check at the end.

---

## Speed & Parallelism

The plugin is designed for speed. Wherever possible, work is parallelized:

| Operation | What happens |
|-----------|-------------|
| **Deep read** | 3 RAG queries run simultaneously, then entity queries in parallel |
| **Section writing** | One subagent per section, all writing at the same time |
| **Research** | RAG + Trove queried by separate subagents in parallel |
| **Editing multiple sections** | One section-writer subagent per section, all in parallel |
| **Citation audit (edit)** | One auditor per section, all in parallel |

---

## Files & Folders

| Path | Purpose |
|------|---------|
| `.academic-helper/` | Plugin working data for this project — see below |
| `past-articles/` | Your published papers for style analysis (never uploaded) |
| `ocr-output/` | Extracted text from `/academic-writer:ocr`, one `<name>.ocr.md` per scanned source |
| `.claude/agents/` | AI agent prompts (deep-reader, architect, section-writer, auditor, synthesizer) |
| `references/` | API documentation for integrations |

### What's in `.academic-helper/`?

This directory is created by `/academic-writer:init` and holds everything the plugin needs to
remember about *this* project between sessions. It is **gitignored** — it can contain your
personal profile, provider API keys, and drafts of unpublished sources, none of which belong in
version control.

| File / subfolder | What it is |
>>>>>>> 43cca5b (ale: T5 WIP (fetch-back))
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
| `/academic-writer:ocr` | Turn a scanned PDF or photographed page (or a folder of them) into plain text with the bundled Gemini reading tool; pages that already contain text are extracted directly. |
| `/academic-writer:ingest` | Upload one article or chapter to the source library with printed page numbers, hinted contents and a citation guide. |
| `/academic-writer:ingest-book` | Upload a whole book (multi-volume, scanned or EPUB) to the source library with a navigable hinted table of contents and a citation guide. |
| `/academic-writer:voice` | Build or update the author's voice profile: import older voice files, choose exemplar paragraphs from past papers, derive writing rules and sync them to CandleKeep. |
| `/academic-writer:health` | Check that Academic Writer is ready to use — your profile, the tools it needs (Python and its add-ons, Hebrew spelling, CandleKeep, NotebookLM), the Gemini key and past articles — with a plain-language fix for anything missing. |
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
