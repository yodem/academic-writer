# Academic Writer — First-Time User Flow

A step-by-step guide for a professor using Academic Writer for the first time.

---

## Overview

The first session has two phases:

1. **Setup** (`/academic-writer-init`) — one-time profile creation (~15 minutes)
2. **Write** (`/academic-writer`) — write your first article (30–60 minutes depending on length)

You only run `/academic-writer-init` once. After that, just use `/academic-writer` whenever you want to write.

---

## Phase 1: Setup

Setup has two parts:
1. **`npx academic-writer-setup`** — interactive CLI in your terminal (2 minutes)
2. **`/academic-writer-init`** — Claude analyzes your writing style (10 minutes)

### Before you start

Gather these:
- **5–10 of your published papers** (PDF or DOCX) — the system analyzes these to learn your writing style
- **Your research source PDFs** — the books and articles you cite in your work

### Part A: Interactive CLI (`npx academic-writer-setup`)

Run this in the Academic Helper folder:

```bash
npx academic-writer-setup
```

An interactive terminal wizard walks you through with arrow-key prompts:

#### 1. Field of study

Example: "Early Modern Jewish Philosophy" or "Ottoman Palestine History". Be specific.

#### 2. Article language

Hebrew, English, or another language. This is enforced throughout — the system flags any foreign-language text that sneaks into your prose.

#### 3. Citation style

| Option | Format | Best for |
|--------|--------|----------|
| Inline Parenthetical | (Author, Title, p. N) in text | Hebrew articles |
| Chicago/Turabian | Footnotes | English Humanities |
| MLA | In-text citations | Literature |
| APA | Author-date | Social sciences |

#### 4. Data services

The CLI auto-detects which tools you have installed and lets you toggle them:

| Tool | What it does | Required? |
|------|-------------|-----------|
| **Candlekeep** | Cloud library for your source PDFs | Recommended |
| **Agentic-Search-Vectorless** | Smart search across your sources | Recommended |
| **Cognetivy** | Tracks every step (audit trail) | Recommended |

You can change these later with `/academic-writer-update-tools`.

The CLI creates your folders (`past-articles/`, `.academic-writer/`) and saves a starter profile.

### Part B: Style Analysis (`/academic-writer-init`)

Now open Claude Code in this folder. Drop 5–10 of your published papers into `past-articles/`, then run:

```
/academic-writer-init
```

Claude reads your papers and builds a **Style Fingerprint** — a detailed profile of how you write:

- Sentence length and structure patterns
- Vocabulary and academic register
- How you build paragraphs (topic sentence, evidence, analysis)
- Your tone and authorial stance
- Transition phrases you prefer
- Citation density and integration style
- How you open and close articles
- 5 representative excerpts as style targets

**You review the fingerprint** and can correct anything before it's saved.

If you enabled Candlekeep, Claude also helps you index your research sources:
- Upload your source PDFs: `ck items add your-source.pdf`
- The system enriches each document (extracts title, author, table of contents)

If you enabled Agentic-Search-Vectorless, there's nothing to do now — when you run `/academic-writer`, the system automatically pulls your selected sources from Candlekeep and ingests them into the search engine before writing begins. This happens transparently at the start of each article.

When done, your profile is complete. Run `/academic-writer` whenever you're ready to write.

---

## Phase 2: Writing Your First Article (`/academic-writer`)

### The conversational phase (you + AI together)

#### Step 1: Describe your topic

Tell the system what you want to write about. Be as detailed or as vague as you like — it will ask follow-up questions.

#### Step 2: Select sources

The system shows your indexed sources. Pick which ones are relevant for this article (by name, number, or "all").

#### Step 3: Deep read

An AI agent reads through your selected sources, mapping:
- Key arguments and claims
- Available evidence
- Gaps in the material
- Connections between sources

This happens automatically. You wait for results.

#### Step 4: Thesis proposals

Based on what the deep reader found, the system proposes 2–3 possible thesis statements. You:
- Pick one
- Modify one
- Or state your own

#### Step 5: Outline

The system generates a structured outline with section titles, roles, and suggested sources per section. You can:
- Reorder sections
- Add or remove sections
- Adjust the scope

When you're satisfied, say "go" or "looks good."

### The autonomous phase (AI writes, you wait)

#### Step 6: Source ingestion

Selected sources are synced to the search engine for fast retrieval during writing.

#### Step 7: Parallel section writing

One AI agent writes each section **simultaneously**. Every single paragraph goes through a 7-step quality pipeline:

| # | Check | What happens |
|---|-------|-------------|
| 1 | **Draft** | Searches your sources, writes using ONLY retrieved evidence |
| 2 | **Style compliance** | Scores against your fingerprint on 10 dimensions, fixes deviations |
| 3 | **Hebrew grammar** | Checks grammar, spelling, academic register |
| 4 | **Academic language** | Upgrades vocabulary, checks linking word usage |
| 5 | **Language purity** | Removes any embedded foreign-language text |
| 6 | **Repetition check** | Catches repeated words, phrases, and arguments |
| 7 | **Citation audit** | Verifies every citation against your actual sources (hard gate — fails if unverified) |

If a citation can't be verified, the paragraph is rewritten (up to 3 attempts). Nothing fabricated makes it through.

#### Step 8: Synthesis

A final editor reviews the complete article for:
- Argument coherence across sections
- Logical flow and transitions
- Full-article style compliance
- Cross-section repetition
- Introduction and conclusion conventions

#### Step 9: Output

The finished article is saved as a `.docx` file on your Desktop with your preferred formatting (font, size, spacing, margins, RTL).

You receive a quality report showing every check that was applied.

---

## After your first article

| Command | When to use |
|---------|------------|
| `/academic-writer` | Write another article |
| `/academic-writer-edit` | Revise a previously written article |
| `/academic-writer-edit-section` | Quick fix for a single section |
| `/academic-writer-research` | Ask questions about your sources |
| `/academic-writer-health` | Check if everything is working |
| `/academic-writer-update-tools` | Add or remove integrations |
| `/academic-writer-update-field` | Change your field of study |

---

## What you can trust

1. **No fabricated citations** — every claim is verified against your actual sources
2. **No invented page numbers** — confirmed via search + direct document reads
3. **Your voice** — every paragraph checked against your style fingerprint
4. **Full transparency** — every step logged to Cognetivy audit trail
5. **Your data stays local** — past articles are never uploaded anywhere
