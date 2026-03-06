# Academic Writer Plugin

AI-first academic writing assistant for Humanities researchers. Produces rigorously cited, style-matched academic articles as .docx files.

## Critical Enforcement Rules

- **Language purity**: Every article section is checked for embedded foreign-language text. ALL body prose must be in the article's `targetLanguage`. Foreign terms must be transliterated or footnoted — never inline.
- **Citations**: Default format is `inline-parenthetical` for Hebrew articles: `(Author, Hebrew Title, עמ' N)` in running text. No footnote-only citations.
- **DOCX output**: Every article is saved as a properly formatted `.docx` file with the researcher's font (default: David), 11pt body, 1.5 line spacing, justified, 1" margins, page numbers.
- **Cognetivy**: All pipeline steps are logged. Cognetivy run starts at the beginning of Phase 1 (before conversational steps) and completes only after the .docx is saved.
- **RAG is mandatory**: Section-writers MUST query RAG before writing any paragraph. No paragraph may cite a source that was not retrieved from RAG context.

## Integrations (Tool Registry)

All integrations are **optional**. During `/academic-writer-init`, the researcher selects which tools to enable. Enabled tools are stored in `profile.tools`. Use `/academic-writer-update-tools` to change them later.

| Tool ID | CLI / Type | What it does | Setup |
|---------|-----------|-------------|-------|
| `candlekeep` | `ck` CLI | Cloud document library — source PDFs and research materials | https://github.com/romiluz13/candlekeep |
| `hybrid-search-rag` | HTTP service (`:8000`) | Deep semantic + keyword retrieval (Agentic-Search-Vectorless). Full API reference in `references/hybridrag-api.md` | https://github.com/romiluz13/Agentic-Search-Vectorless |
| `mongodb-agent-skills` | MCP server | Database-backed research operations | https://github.com/romiluz13/mongodb-agent-skills |
| `cognetivy` | `cognetivy` CLI | Workflow tracking and audit trail | Built-in (`.cognetivy/`) |

- **Past articles**: `./past-articles/` folder — researcher's past work for style analysis (local only, never uploaded)

All pipeline steps (write-article, agents) check `profile.tools` before calling any integration. If a tool is disabled, its steps are skipped gracefully.

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/academic-writer-init` | First-time setup: field of study, citation style, style fingerprint from past articles, source indexing |
| `/academic-writer` | Write a new article: conversational subject → sources → thesis → outline → write → audit → .docx |
| `/academic-writer-research` | Research a subject or answer questions using indexed sources (Candlekeep, RAG, MongoDB) — spawns parallel subagents for speed |
| `/academic-writer-edit` | Edit a previously written article — revise sections, fix citations, adjust tone, restructure, strengthen arguments |
| `/academic-writer-edit-section` | Quick edit of a single section — faster than full article edit |
| `/academic-writer-health` | Run a comprehensive health check on all integrations, profile, agents, and source index |
| `/academic-writer-help` | Explain what this plugin is and how to use it |
| `/academic-writer-update-field` | Update your field of study without re-running full initialization |
| `/academic-writer-update-tools` | Add, remove, or reconfigure integrations (Candlekeep, RAG, MongoDB, Cognetivy) |

## RAG Query Modes (use the right one for each task)

| Mode | When to use |
|------|------------|
| `mix` | Default — general search combining all methods |
| `bypass` | **Citation verification** — exact quotes and page numbers |
| `local` | Deep dive on a specific entity or concept |
| `global` | Thematic overview across all documents |
| `hybrid` | Fast relevance scoring (BM25 + vector) |

## Agent Architecture

Agents are spawned as subagents. Each reads its own prompt from `agents/`. **Agents are spawned in parallel whenever possible** for speed — e.g., all section-writers run simultaneously, research queries across RAG + Candlekeep run in parallel.

| Agent | File | Spawned by | Purpose |
|-------|------|-----------|---------|
| Deep Reader | `agents/deep-reader.md` | write-article | Explores source material before thesis (parallel RAG queries) |
| Architect | `agents/architect.md` | write-article | Proposes thesis + generates outline |
| Section Writer | `agents/section-writer.md` | write-article, edit, edit-section | Writes one section with full skill pipeline (parallel per section) |
| Auditor | `agents/auditor.md` | section-writer, edit | Verifies citations (hard gate) |
| Synthesizer | `agents/synthesizer.md` | write-article, edit | Final coherence + style review |

### Parallelism Strategy

| Operation | Parallelism |
|-----------|------------|
| Deep read queries (mix, global, counterargs) | All 3 in parallel, then entity queries in parallel |
| Section writing | All sections spawn simultaneously |
| Research skill (RAG + Candlekeep) | Separate subagent per tool, all in parallel |
| Edit (multiple sections) | One section-writer subagent per section, all in parallel |
| Citation audit (edit mode) | One auditor per section, all in parallel |

## Profile Location

Researcher profile: `.academic-writer/profile.json`
Always load at the start of `/academic-writer`.

## Critical Rules

- NEVER fabricate citations. Every claim must be verified against RAG results.
- NEVER invent page numbers. Use `bypass` mode to get exact quotes, confirm via `ck items read`.
- If a claim cannot be cited, remove it or flag it for the researcher.
- Log every pipeline step to Cognetivy for auditability.
- When verifying citations, always use `include_context: true` to get source passages.
