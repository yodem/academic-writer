---
name: help
description: "Learn what the Academic Writer plugin does and how to use it. Use when you don't know which command to run."
user-invocable: true
allowedTools: [Read]
metadata: {author: "Yotam Fromm", version: "0.2.18"}
---

# Academic Writer — Help

Display a friendly, comprehensive guide to the Academic Writer plugin. No profile or tools required — this is pure documentation.

---

Print the following (adapt formatting for readability):

---

## What is Academic Writer?

Academic Writer is an AI-powered writing assistant built for **Humanities researchers**. It helps you produce rigorously cited, style-matched academic articles as .docx files.

What makes it different:
- **Your voice, not AI voice** — It analyzes your past publications to learn your writing style (sentence patterns, vocabulary, tone, transitions, rhetorical moves) and checks every paragraph against that fingerprint.
- **Citation integrity** — Every claim is grounded in your indexed sources. An auditor agent verifies every footnote before it's included. Nothing is fabricated.
- **Full audit trail** — Every step of the writing process is logged, so you can see exactly how each paragraph was drafted, checked, and approved.

---

## Getting Started

### 1. Initialize your profile

```
/academic-writer:init
```

This walks you through:
- Setting your **field of study** (e.g., History, Literature, Philosophy)
- Choosing your **citation style** (Chicago, MLA, APA)
- Analyzing your **writing style** from past articles (place 5–10 PDFs or DOCX files in `past-articles/`)
- Connecting your **data tools** (all optional):

| Tool | What it does |
|------|-------------|
| **Candlekeep** | Cloud document library — your source PDFs and research materials |
| **Agentic-Search-Vectorless** | Vectorless semantic search across all your sources |

---

## Slash Commands

| Command | What it does |
|---------|-------------|
| `/academic-writer:write` | **Write a new article** — the full pipeline from subject to .docx |
| `/academic-writer:edit` | **Edit an article** — revise sections, fix citations, adjust tone, restructure |
| `/academic-writer:edit-section` | **Edit one section** — fast, focused single-section edit |
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

Both edit skills spawn **parallel subagents** for speed — multiple sections are edited simultaneously, and research queries (for finding new evidence) run in parallel across RAG and Candlekeep.

---

## How Research Works

When you run `/academic-writer:research`, you can:
- Ask questions about your sources ("What does X say about Y?")
- Explore topics across all your documents
- Compare how different authors treat a concept
- Find exact quotes with page numbers
- Browse your Candlekeep library

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
| **Research** | RAG + Candlekeep queried by separate subagents in parallel |
| **Editing multiple sections** | One section-writer subagent per section, all in parallel |
| **Citation audit (edit)** | One auditor per section, all in parallel |

---

## Files & Folders

| Path | Purpose |
|------|---------|
| `.academic-helper/profile.md` | Your researcher profile (field, style, tools, sources) |
| `past-articles/` | Your published papers for style analysis (never uploaded) |
| `.claude/agents/` | AI agent prompts (deep-reader, architect, section-writer, auditor, synthesizer) |
| `references/` | API documentation for integrations |

---

## Troubleshooting

- **Something not working?** → Run `/academic-writer:health` to check all components
- **Want to change your field?** → `/academic-writer:update-field`
- **Want to add/remove tools?** → `/academic-writer:update-tools`
- **Style not matching?** → Add more past articles to `past-articles/` and re-run `/academic-writer:init`
- **Vectorless search not working?** → Ensure `../Agentic-Search-Vectorless/` repo exists and the service is running

---

## Critical Guarantees

1. **No fabricated citations** — Every claim verified against your sources
2. **No invented page numbers** — Exact quotes confirmed via RAG bypass + Candlekeep
3. **Your voice** — Every paragraph checked against your style fingerprint
5. **Your data stays local** — Past articles are never uploaded anywhere
