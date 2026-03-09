# Academic Writer — Claude Code Plugin

AI-first academic writing assistant for Humanities researchers. Produces rigorously cited, style-matched academic articles as `.docx` files.

## Features

- **Style-matched writing** — analyzes your past articles to extract your writing style, then applies it to new work
- **Collaborative workflow** — subject → sources → thesis proposal → outline → write → audit → publish
- **Parallel processing** — sections written simultaneously, each audited independently for speed
- **Full workflow tracking** — every pipeline step logged to Cognetivy for transparency and auditability

## Installation

### 1. Prerequisites

You need **at least one** of these integrations:

| Tool | What it does | Setup |
|------|-------------|-------|
| **Candlekeep** | Cloud document library for source PDFs | [https://github.com/CandleKeepAgents/candlekeep-cli](https://github.com/CandleKeepAgents/candlekeep-cli) |
| **Cognetivy** | Workflow audit trail (optional) | Built-in — no setup needed |

Choose which tools you want to use during `/academic-writer-init`.

### 2. Install the Plugin

Navigate to the folder where you do your research work, then run:

```bash
cd your-research-folder
claude plugin install academic-writer --scope project
```

The `--scope project` flag activates the plugin only in this folder, not globally.

> **Note:** The plugin marketplace must already be registered. If you get "marketplace not found", add it first:
> ```bash
> claude plugin marketplace add ~/.claude/plugins/marketplaces/academic-writer
> ```

### 3. Initialize Your Profile

```bash
/academic-writer-init
```

This is a one-time setup. You'll be asked to provide:
- Your field of study
- Citation style (Inline Parenthetical / Chicago / MLA / APA)
- 5–10 past articles for style analysis (placed in `past-articles/` folder)
- Which integrations to enable (Candlekeep, RAG, MongoDB, Cognetivy)
- Your research sources (if using Candlekeep)

Your profile is saved to `.academic-writer/profile.json` and automatically loaded each time you use the plugin.

## Usage

### Write an Article

```bash
/academic-writer
```

**Workflow:**
1. Describe your article topic
2. Select relevant sources (from Candlekeep or provide manually)
3. Deep read your sources to understand coverage
4. Propose thesis statements (2–3 options to choose from)
5. Outline the article together (back-and-forth refinement)
6. Approve the outline
7. **Automated:** Sections written in parallel, each audited for citations
8. **Automated:** Final synthesis for coherence and style
9. Export as `.docx` with Chicago footnotes

### Quick Commands

| Command | What it does |
|---------|-------------|
| `/academic-writer` | Write a new article |
| `/academic-writer-init` | First-time setup |
| `/academic-writer-update-field` | Change your field of study |
| `/academic-writer-update-tools` | Add/remove integrations (Candlekeep, RAG, etc.) |
| `/academic-writer-research` | Research a topic using your sources |
| `/academic-writer-edit` | Edit a previously written article |
| `/academic-writer-edit-section` | Quick edit of a single section |
| `/academic-writer-health` | Check all integrations & profile status |
| `/academic-writer-help` | Show plugin info |

## File Structure

```
your-project/
├── past-articles/              ← Drop your published papers here (5–10 PDFs/DOCXs)
├── .academic-writer/
│   └── profile.json           ← Your profile (auto-created, never edit manually)
├── .cognetivy/                ← Workflow audit trail (auto-managed)
├── articles/                  ← Output .docx files go here
└── .claude-plugin/            ← Claude Code plugin cache (auto-managed)
```

## Profile Structure

Your profile (`.academic-writer/profile.json`) contains:

```json
{
  "fieldOfStudy": "Your field",
  "citationStyle": "chicago",
  "styleFingerprint": {
    "sentenceLevel": { ... },
    "vocabularyAndRegister": { ... },
    "paragraphStructure": { ... },
    "toneAndVoice": { ... },
    "transitions": { ... },
    "citations": { ... },
    "rhetoricalPatterns": { ... },
    "representativeExcerpts": [ ... ]
  },
  "tools": {
    "candlekeep": { "enabled": true },
    "mongodb-agent-skills": { "enabled": false },
    "cognetivy": { "enabled": true }
  },
  "sources": [
    { "id": "...", "title": "...", "type": "pdf" }
  ]
}
```

Update tools with `/academic-writer-update-tools`. Update your field with `/academic-writer-update-field`.

## Configuration

### Environment Variables (Optional)

```bash
export CANDLEKEEP_CLI=ck                       # Candlekeep CLI path
export COGNETIVY_CLI=cognetivy                 # Cognetivy CLI path
```

### MCP Servers (Optional)

If you enable **MongoDB Agent Skills**, add to `.mcp.json`:

```json
{
  "mcpServers": {
    "mongodb-agent-skills": {
      "command": "node",
      "args": ["/path/to/mongodb-agent-skills/dist/index.js"],
      "env": {
        "MONGODB_URI": "your-connection-string"
      }
    }
  }
}
```

## Troubleshooting

### "No profile found" error

Run `/academic-writer-init` first to set up your profile.

### "Candlekeep not detected" error

Install Candlekeep CLI: https://github.com/romiluz13/candlekeep

```bash
brew tap CandleKeepAgents/candlekeep
brew install candlekeep-cli
# or
cargo install candlekeep-cli
```

Then authenticate:
```bash
ck auth login
```

### Citation verification fails

Ensure:
1. Your sources are indexed (the init process does this automatically)
2. The cited passage actually exists in your source materials

### Articles won't export to .docx

Ensure `python-docx` is installed:

```bash
pip install python-docx
```

## Architecture

### Agents

Each agent is a specialized prompt that runs as a subagent:

- **Deep Reader** — Explores source material before writing to understand coverage
- **Architect** — Proposes thesis statements and generates article outline
- **Section Writer** — Writes one complete section with citations (runs in parallel)
- **Auditor** — Hard gate: verifies every citation against source material
- **Synthesizer** — Final review for coherence, transitions, and style consistency

### RAG Query Modes

The plugin uses different RAG query modes for different tasks:

| Mode | Use case |
|------|----------|
| `mix` | General search (default) |
| `bypass` | Citation verification — exact quotes and page numbers |
| `local` | Deep dive on a specific entity |
| `global` | Thematic overview across all sources |

## Updating / Reinstalling

After pulling changes from GitHub, rebuild and reinstall the plugin from the **marketplace directory**:

```bash
cd ~/.claude/plugins/marketplaces/academic-writer
npm run build
claude plugin install academic-writer --scope project
```

Then **restart Claude Code** to apply the changes.

### Full reinstall (clears cache)

If you see stale behaviour or install errors, delete the cache first:

```bash
rm -rf ~/.claude/plugins/cache/academic-writer
cd ~/.claude/plugins/marketplaces/academic-writer
npm run build
claude plugin install academic-writer --scope project
```

### Install in a specific project

The install command must be run from the project folder you want the plugin active in:

```bash
cd ~/your-research-folder
claude plugin install academic-writer --scope project
```

## Contributing

This is a Claude Code plugin. Source files live in `src/` — never edit `plugins/` directly (it is generated).

1. Edit source files in `src/skills/`, `src/agents/`, `src/hooks/`
2. Build: `npm run build`
3. Test locally: `claude plugin install academic-writer --scope project` (from your research folder)
4. Commit and push to GitHub

## License

MIT

## Support

- **Plugin issues:** Open an issue on [yodem/academic-writer](https://github.com/yodem/academic-writer)
- **Candlekeep help:** https://github.com/CandleKeepAgents/candlekeep-cli
- **RAG help:** https://github.com/romiluz13/Agentic-Search-Vectorless
