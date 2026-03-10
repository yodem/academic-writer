# Academic Writer Plugin

AI-first academic writing assistant for Humanities researchers. Produces rigorously cited, style-matched academic articles as .docx files.

## Build System

**Source of truth lives in `src/`.** Run `npm run build` to assemble the plugin into `plugins/academic-writer/`.

```
src/                    <- EDIT HERE
  agents/               <- 6 agent definitions (.md with YAML frontmatter)
  skills/               <- 15 skill directories (SKILL.md each)
  hooks/                <- TypeScript hooks (esbuild → dist/)
  settings/             <- Plugin settings JSON
  workflows/            <- Cognetivy workflow definitions
  words.md              <- Hebrew linking words reference

plugins/                <- GENERATED (never edit!)
  academic-writer/      <- Built plugin output

scripts/
  build-plugins.sh      <- Build script

manifests/
  academic-writer.json  <- Plugin manifest

.claude-plugin/
  marketplace.json      <- Plugin marketplace registration
```

**Commands:**
- `npm run build` — Full build (hooks + plugin assembly)
- `npm run build:hooks` — Build TypeScript hooks only
- `npm run typecheck` — TypeScript type checking
- `npm run clean` — Remove built artifacts

## Versioning

Version is stored in **four places** (must always match):
- `package.json` → `"version"`
- `manifests/academic-writer.json` → `"version"`
- `.claude-plugin/marketplace.json` → `"version"` (top-level)
- `.claude-plugin/marketplace.json` → `"plugins[0].version"`

**Automatic on every push to `main`:** `.github/workflows/release.yml` bumps the patch version, rebuilds, commits (`chore: bump version to vX.Y.Z [skip ci]`), pushes a tag, and creates a GitHub Release. Never bump versions manually in PRs — the CI handles it.

**Critical:** Always edit `src/`, never `plugins/`. After editing `src/`, run `npm run build`.

## Build → Install Sequence

After any source change, always follow this exact sequence:

```bash
# 1. From the marketplace repo root:
npm run build

# 2. Install into a project (run from that project's directory, or pass --scope user for global):
cd ~/path/to/research-project
claude plugin install academic-writer --scope project

# 3. Restart Claude Code
```

### Reinstall with cache clear

If install fails or plugin behaves strangely:

```bash
rm -rf ~/.claude/plugins/cache/academic-writer
npm run build   # from marketplace root
claude plugin install academic-writer --scope project
```

### plugin.json validation rules

Claude Code validates `plugins/academic-writer/.claude-plugin/plugin.json` strictly:
- No unknown keys (e.g. `stats` is **not** allowed)
- No trailing commas
- The `build-plugins.sh` script has been fixed to not emit these — do not re-add them

## Critical Enforcement Rules

- **Language purity**: Every article section is checked for embedded foreign-language text. ALL body prose must be in the article's `targetLanguage`. Foreign terms must be transliterated or footnoted — never inline.
- **Citations**: Default format is `inline-parenthetical` for Hebrew articles: `(Author, Hebrew Title, עמ' N)` in running text. No footnote-only citations.
- **DOCX output**: Every article is saved as a properly formatted `.docx` file with the researcher's font (default: David), 11pt body, 1.5 line spacing, justified, 1" margins, page numbers.
- **Cognetivy**: All pipeline steps are logged. Cognetivy run starts at the beginning of Phase 1 (before conversational steps) and completes only after the .docx is saved.
- **Search is mandatory**: Section-writers MUST query Agentic-Search-Vectorless or Candlekeep before writing any paragraph. No paragraph may cite a source that was not retrieved from search context.
- **Anti-AI check**: Every paragraph is scored on 5 dimensions (Directness, Rhythm, Trust, Authenticity, Density) to detect and fix AI writing patterns. Threshold: 35/50.
- **Abstract generation**: Every article includes a structured abstract (תקציר). Dual-language abstracts supported via `profile.abstractLanguages`.
- **Self-review gate**: Before DOCX output, articles are scored on 6 dimensions (60-point scale). Score < 40 triggers researcher review.

## Integrations (Tool Registry)

All integrations are **optional**. During `/academic-writer:setup` or `/academic-writer:init`, the researcher selects which tools to enable. Enabled tools are stored in `profile.tools`. Use `/academic-writer:update-tools` to change them later.

| Tool ID | CLI / Type | What it does | Setup |
|---------|-----------|-------------|-------|
| `candlekeep` | `ck` CLI | Cloud document library — source PDFs and research materials | https://github.com/romiluz13/candlekeep |
| `agentic-search-vectorless` | Local service | Vectorless semantic search for citation retrieval | `../Agentic-Search-Vectorless/` |
| `mongodb-agent-skills` | MCP server | Database-backed research operations | https://github.com/romiluz13/mongodb-agent-skills |
| `cognetivy` | `cognetivy` CLI | Workflow tracking and audit trail | Built-in (`.cognetivy/`) |
| `notebooklm` | MCP server | AI-powered source Q&A, audio overviews, study guides, research discovery | https://github.com/jacob-bd/notebooklm-mcp-cli |

- **Past articles**: `./past-articles/` folder — researcher's past work for style analysis (local only, never uploaded)

All pipeline steps (write-article, agents) check `profile.tools` before calling any integration. If a tool is disabled, its steps are skipped gracefully.

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/academic-writer:setup` | First-time setup: creates profile, detects integrations, optional style fingerprinting |
| `/academic-writer:init` | Full initialization: field of study, citation style, detailed style fingerprint from past articles, source indexing |
| `/academic-writer:write` | Write a new article: conversational subject → sources → thesis → outline → write → audit → .docx |
| `/academic-writer:research` | Research a subject or answer questions using indexed sources (Candlekeep, Vectorless, MongoDB) — spawns parallel subagents for speed |
| `/academic-writer:edit` | Edit a previously written article — revise sections, fix citations, adjust tone, restructure, strengthen arguments |
| `/academic-writer:edit-section` | Quick edit of a single section — faster than full article edit |
| `/academic-writer:health` | Run a comprehensive health check on all integrations, profile, agents, and source index |
| `/academic-writer:help` | Explain what this plugin is and how to use it |
| `/academic-writer:update-field` | Update your field of study without re-running full initialization |
| `/academic-writer:update-tools` | Add, remove, or reconfigure integrations (Candlekeep, Vectorless, MongoDB, Cognetivy) |
| `/academic-writer:review` | Self-review quality gate — scores a completed article on 6 dimensions and presents a scorecard |
| `/academic-writer:ideate` | Guided research ideation — brainstorm research questions using 5W1H, gap analysis, and structured framing |
| `/academic-writer:learn` | Style learning — scans past-articles/ for new files and updates the style fingerprint |
| `/academic-writer:present` | Post-article deliverables — conference presentations, journal abstracts, book chapter proposals |

## Cognetivy Workflows

Workflow definitions are in `src/workflows/`. Each major pipeline has its own workflow:

| Workflow | File | Triggered by |
|----------|------|-------------|
| `wf_setup` | `src/workflows/wf_setup.json` | `/academic-writer:setup` |
| `wf_write_article` | `src/workflows/wf_write_article.json` | `/academic-writer:write` |
| `wf_edit_article` | `src/workflows/wf_edit_article.json` | `/academic-writer:edit` |
| `wf_edit_section` | `src/workflows/wf_edit_section.json` | `/academic-writer:edit-section` |
| `wf_research` | `src/workflows/wf_research.json` | `/academic-writer:research` |
| `wf_ideate` | `src/workflows/wf_ideate.json` | `/academic-writer:ideate` |
| `wf_learn` | `src/workflows/wf_learn.json` | `/academic-writer:learn` |

Collection schemas: `src/workflows/collection-schemas.json`

## Search Query Modes (Agentic-Search-Vectorless)

| Mode | When to use |
|------|------------|
| `mix` | Default — general search combining all methods |
| `bypass` | **Citation verification** — exact quotes and page numbers |
| `local` | Deep dive on a specific entity or concept |
| `global` | Thematic overview across all documents |

## Agent Architecture

Agents are defined in `src/agents/` (source) and built to `plugins/academic-writer/agents/`. Each has YAML frontmatter (name, description, tools, model). They are spawned as subagents using the **Agent tool**. Skills must explicitly invoke the Agent tool to spawn subagents — use "Use the Agent tool to spawn the X subagent" language in skill instructions.

**Agents are spawned in parallel whenever possible** for speed — e.g., all section-writers run simultaneously via multiple Agent tool calls in a single response.

| Agent | Source File | Spawned by | Purpose |
|-------|------------|-----------|---------|
| Deep Reader | `src/agents/deep-reader.md` | write-article | Explores source material before thesis (parallel search queries) |
| Architect | `src/agents/architect.md` | write-article | Proposes thesis + generates outline |
| Section Writer | `src/agents/section-writer.md` | write-article, edit, edit-section | Writes one section with full skill pipeline (parallel per section) |
| Auditor | `src/agents/auditor.md` | section-writer, edit | Verifies citations (hard gate, with optional external verification) |
| Synthesizer | `src/agents/synthesizer.md` | write-article, edit | Final coherence + style review |
| Style Miner | `src/agents/style-miner.md` | academic-writer-learn | Analyzes new articles to update style fingerprint |

### Parallelism Strategy

| Operation | Parallelism |
|-----------|------------|
| Deep read queries | All in parallel |
| Section writing | All sections spawn simultaneously (multiple Agent tool calls in one response) |
| Research skill (Vectorless + Candlekeep) | Separate subagent per tool, all in parallel |
| Edit (multiple sections) | One section-writer subagent per section, all in parallel |
| Citation audit (edit mode) | One auditor per section, all in parallel |
| Style learning (new articles) | One style-miner subagent for all new files |

## Profile Location

Researcher profile: `.academic-writer/profile.json`
Always load at the start of `/academic-writer:write`.

## Critical Rules

- NEVER fabricate citations. Every claim must be verified against Agentic-Search-Vectorless or Candlekeep results.
- NEVER invent page numbers. Confirm via `ck items read` or exact vectorless search query.
- If a claim cannot be cited, remove it or flag it for the researcher.
- Log every pipeline step to Cognetivy for auditability.
- When verifying citations, always retrieve the source passage before confirming.
