---
name: academic-writer-help
description: "Learn what the Academic Writer plugin does and how to use it."
user-invocable: true
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
/academic-writer-init
```

This walks you through:
- Setting your **field of study** (e.g., History, Literature, Philosophy)
- Choosing your **citation style** (Chicago, MLA, APA)
- Analyzing your **writing style** from past articles (place 5–10 PDFs or DOCX files in `past-articles/`)
- Connecting your **data tools** (all optional):

| Tool | What it does |
|------|-------------|
| **Candlekeep** | Cloud document library — your source PDFs and research materials |
| **Hybrid-Search-RAG** | Semantic + keyword search across all your sources |
| **MongoDB Agent Skills** | Database-backed research operations |
| **Cognetivy** | Workflow tracking and audit trail |

---

## Slash Commands

| Command | What it does |
|---------|-------------|
| `/academic-writer` | **Write a new article** — the full pipeline from subject to .docx |
| `/academic-writer-research` | **Research a topic** — query your sources, get answers with citations |
| `/academic-writer-init` | **First-time setup** — profile, style analysis, source indexing |
| `/academic-writer-health` | **System check** — verify all integrations are working |
| `/academic-writer-update-field` | **Change your field** without re-running full init |
| `/academic-writer-update-tools` | **Add/remove integrations** |
| `/academic-writer-help` | **This help page** |

---

## How Article Writing Works

When you run `/academic-writer`, you go through a conversational pipeline:

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

## How Research Works

When you run `/academic-writer-research`, you can:
- Ask questions about your sources ("What does X say about Y?")
- Explore topics across all your documents
- Compare how different authors treat a concept
- Find exact quotes with page numbers
- Browse your Candlekeep library

This is independent of the article pipeline — use it anytime you want to query your research materials.

---

## Your Style Fingerprint

The fingerprint is extracted from your past articles during `/academic-writer-init`. It captures 25 dimensions of your writing across 8 categories:

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

## Files & Folders

| Path | Purpose |
|------|---------|
| `.academic-writer/profile.json` | Your researcher profile (field, style, tools, sources) |
| `past-articles/` | Your published papers for style analysis (never uploaded) |
| `agents/` | AI agent prompts (deep-reader, architect, section-writer, auditor, synthesizer) |
| `.cognetivy/` | Workflow tracking data |
| `references/` | API documentation for integrations |

---

## Troubleshooting

- **Something not working?** → Run `/academic-writer-health` to check all components
- **Want to change your field?** → `/academic-writer-update-field`
- **Want to add/remove tools?** → `/academic-writer-update-tools`
- **Style not matching?** → Add more past articles to `past-articles/` and re-run `/academic-writer-init`
- **RAG server down?** → `cd ~/dev/Hybrid-Search-RAG && uvicorn hybridrag.api.main:app --port 8000`

---

## Critical Guarantees

1. **No fabricated citations** — Every claim verified against your sources
2. **No invented page numbers** — Exact quotes confirmed via RAG bypass + Candlekeep
3. **Your voice** — Every paragraph checked against your style fingerprint
4. **Full transparency** — Every step logged to Cognetivy audit trail
5. **Your data stays local** — Past articles are never uploaded anywhere
