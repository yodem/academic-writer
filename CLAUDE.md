# Academic Writer Plugin

AI-first academic writing assistant for Humanities researchers. Produces rigorously cited, style-matched academic articles as .docx files.

## Integrations

- **Candlekeep** (`ck` CLI): Cloud document library — source PDFs and research materials
- **Hybrid-Search-RAG** (`curl http://localhost:8000`): Deep semantic + keyword retrieval. Full API reference in `references/hybridrag-api.md`
- **Cognetivy** (`cognetivy` CLI): Workflow tracking and audit trail
- **Past articles**: `./past-articles/` folder — researcher's past work for style analysis (local only, never uploaded)

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/academic-writer-init` | First-time setup: field of study, citation style, style fingerprint from past articles, source indexing |
| `/academic-writer` | Write a new article: conversational subject → sources → thesis → outline → write → audit → .docx |

## RAG Query Modes (use the right one for each task)

| Mode | When to use |
|------|------------|
| `mix` | Default — general search combining all methods |
| `bypass` | **Citation verification** — exact quotes and page numbers |
| `local` | Deep dive on a specific entity or concept |
| `global` | Thematic overview across all documents |
| `hybrid` | Fast relevance scoring (BM25 + vector) |

## Agent Architecture

Agents are spawned as subagents. Each reads its own prompt from `agents/`:

| Agent | File | Spawned by | Purpose |
|-------|------|-----------|---------|
| Deep Reader | `agents/deep-reader.md` | write-article skill | Explores source material before thesis |
| Architect | `agents/architect.md` | write-article skill | Proposes thesis + generates outline |
| Section Writer | `agents/section-writer.md` | write-article skill | Writes one section (parallel) |
| Auditor | `agents/auditor.md` | section-writer | Verifies citations (hard gate) |
| Synthesizer | `agents/synthesizer.md` | write-article skill | Final coherence + style review |

## Profile Location

Researcher profile: `.academic-writer/profile.json`
Always load at the start of `/academic-writer`.

## Critical Rules

- NEVER fabricate citations. Every claim must be verified against RAG results.
- NEVER invent page numbers. Use `bypass` mode to get exact quotes, confirm via `ck items read`.
- If a claim cannot be cited, remove it or flag it for the researcher.
- Log every pipeline step to Cognetivy for auditability.
- When verifying citations, always use `include_context: true` to get source passages.
