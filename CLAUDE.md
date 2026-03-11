# Academic Writer Plugin

AI-first academic writing assistant for Humanities researchers. Writes rigorously cited, style-matched academic articles as `.docx` files.

---

## Source Layout

```
src/              ← EDIT HERE (never edit plugins/)
  agents/         ← 6 agent definitions
  skills/         ← 15 skills (one SKILL.md each)
  hooks/          ← TypeScript hooks (esbuild → dist/)
  settings/       ← Plugin settings JSON
  workflows/      ← Cognetivy workflow definitions
  words.md        ← Hebrew linking words reference

plugins/          ← GENERATED — committed to git, rebuilt by CI
  academic-writer/

scripts/
  build-plugins.sh

manifests/
  academic-writer.json     ← Plugin manifest

.claude-plugin/
  marketplace.json         ← Marketplace registration
```

**Build commands:**
```bash
npm run build        # Full build (hooks + plugin assembly)
npm run build:hooks  # Hooks only
npm run typecheck    # TypeScript check
npm run clean        # Remove build artifacts
```

---

## After Any Source Change

```bash
npm run build
cd ~/path/to/research-project
claude plugin install academic-writer --scope project
# Restart Claude Code
```

**If install fails or behaves strangely:**
```bash
rm -rf ~/.claude/plugins/cache/academic-writer
npm run build
claude plugin install academic-writer --scope project
```

---

## Versioning

Version lives in four places — they must always match:
- `package.json`
- `manifests/academic-writer.json`
- `.claude-plugin/marketplace.json` (top-level `version`)
- `.claude-plugin/marketplace.json` (`plugins[0].version`)

**Never bump manually.** On every push to `main`, CI automatically bumps the patch version, rebuilds (including `plugins/`), commits, tags, and creates a GitHub Release.

`plugin.json` validation: no unknown keys (e.g. `stats` is rejected), no trailing commas.

---

## Critical Rules (Always Enforce)

- **No fabricated citations.** Every claim must be verified against Candlekeep or Vectorless results. If a source cannot be retrieved, remove the claim or flag it.
- **No invented page numbers.** Confirm via `ck items read` or exact vectorless `bypass` query.
- **Search is mandatory.** Section-writers must query Vectorless or Candlekeep before writing each paragraph. No paragraph may cite a source not found in search context.
- **Language purity.** All body prose must be in `targetLanguage`. Foreign terms must be transliterated or footnoted — never inline.
- **Citations format.** Default for Hebrew: `(Author, Hebrew Title, עמ' N)` inline. No footnote-only citations.
- **DOCX output.** Font: David, 11pt body, 1.5 line spacing, justified, 1" margins, page numbers.
- **Anti-AI check.** Every paragraph scored on 5 dimensions (Directness, Rhythm, Trust, Authenticity, Density). Threshold: 35/50. Rewrite if below.
- **Abstract.** Every article includes a תקציר. Dual-language abstracts supported via `profile.abstractLanguages`.
- **Self-review gate.** Articles scored on 6 dimensions (60-point scale) before DOCX export. Score < 40 → researcher review required.
- **Cognetivy logging.** Every pipeline step must be logged. Run starts at Phase 1, closes after .docx is saved.

---

## Integrations

All integrations are optional. Enabled tools are stored in `profile.tools`. Configure during `/academic-writer:setup` or via `/academic-writer:update-tools`.

| Tool | Type | Purpose |
|------|------|---------|
| `candlekeep` | `ck` CLI | Cloud document library for source PDFs |
| `agentic-search-vectorless` | Local service (`localhost:8000`) | Vectorless semantic search — mandatory for every paragraph |
| `cognetivy` | `cognetivy` CLI | Workflow tracking and audit trail |
| `notebooklm` | MCP server | AI-powered Q&A, audio overviews, study guides |
| `mongodb-agent-skills` | MCP server | Database-backed research operations |

Past articles go in `./past-articles/` (local only, gitignored).

If a tool is disabled in `profile.tools`, its steps are skipped gracefully.

---

## Commands

| Command | What it does |
|---------|-------------|
| `/academic-writer:setup` | Quick first-time setup: profile + tool detection |
| `/academic-writer:init` | Full init: field, citation style, style fingerprint, source indexing |
| `/academic-writer:write` | Write a new article end-to-end |
| `/academic-writer:edit` | Edit a previously written article |
| `/academic-writer:edit-section` | Quick edit of a single section |
| `/academic-writer:research` | Research a topic using indexed sources |
| `/academic-writer:ideate` | Brainstorm research questions (5W1H + gap analysis) |
| `/academic-writer:learn` | Scan new past-articles and update style fingerprint |
| `/academic-writer:review` | Score a completed article on 6 quality dimensions |
| `/academic-writer:present` | Generate conference outlines, journal abstracts, proposals |
| `/academic-writer:health` | Check all integrations and profile |
| `/academic-writer:help` | Show plugin info |
| `/academic-writer:update-field` | Change field of study |
| `/academic-writer:update-tools` | Add or remove integrations |

---

## Article Pipeline

**Phase 1 (conversational):** subject → source selection → deep read → thesis options → outline → researcher approval

**Phase 2 (autonomous, parallel sections):**
Each paragraph goes through 8 skills:
1. Draft (mandatory vectorless search first)
2. Style fingerprint compliance
3. Hebrew grammar check
4. Academic language & linking words
5. Language purity
6. Anti-AI check (5 dimensions, threshold 35/50)
7. Repetition check
8. Citation audit (hard gate via Auditor subagent)

Then: synthesis → abstract → self-review → `.docx` export

**Parallelism:** All sections spawn simultaneously (one subagent per section). Deep read queries also run in parallel.

---

## Agents

Defined in `src/agents/`, built to `plugins/academic-writer/agents/`. Each is spawned via the Agent tool — skills must use explicit "Use the Agent tool to spawn X" language.

| Agent | Source | Purpose |
|-------|--------|---------|
| Deep Reader | `deep-reader.md` | Parallel source exploration before thesis |
| Architect | `architect.md` | Thesis proposals + outline |
| Section Writer | `section-writer.md` | One section, full 8-skill pipeline |
| Auditor | `auditor.md` | Hard citation verification gate |
| Synthesizer | `synthesizer.md` | Coherence + style final pass |
| Style Miner | `style-miner.md` | Extracts patterns from past articles |

---

## Search Query Modes (Vectorless)

| Mode | When to use |
|------|------------|
| `mix` | Default — general search |
| `bypass` | Citation verification — exact quotes and page numbers |
| `local` | Deep dive on a specific concept or entity |
| `global` | Thematic overview across all documents |

---

## Cognetivy Workflows

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

---

## Profile

Location: `.academic-writer/profile.json` — load at the start of every `/academic-writer:write`.
