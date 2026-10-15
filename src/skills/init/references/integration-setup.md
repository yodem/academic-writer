# Integration Setup (Trove, NotebookLM, library route)

> Loaded on demand by `init` Phase 1 (tools) and Phase 3 (library route), and by `update-tools`. Each tool has detection command, configuration block, and registration steps.

## Detection Commands

Run ALL in parallel:

```python
# PARALLEL — launch all at once
Bash(command="command -v trove >/dev/null 2>&1 && echo 'DETECTED' || echo 'NOT_DETECTED'")
Bash(command="command -v nlm >/dev/null 2>&1 && nlm login --check 2>/dev/null && echo 'DETECTED' || echo 'NOT_DETECTED'")
```

## Present Results

```python
AskUserQuestion(questions=[{
  "question": "Here are the tools I found. Which would you like to enable?",
  "header": "Integration setup",
  "options": [
    {
      "label": "Trove",
      "description": "✓ Detected  (or ✗ Not found — I can install it after asking)",
      "markdown": "```\nTrove\n─────\nType:    CLI (trove)\nWhat:    Cloud document library\nBest for: Storing and searching your source PDFs\nStatus:  ✓ Detected\n```"
    },
    {
      "label": "NotebookLM",
      "description": "✓ Detected  (or ✗ Not found — I can install it after asking)",
      "markdown": "```\nNotebookLM\n──────────\nType:    MCP server (nlm CLI)\nWhat:    AI-powered source Q&A, audio overviews,\n         study guides, research discovery\nStatus:  ✓ Detected\n```"
    }
  ],
  "multiSelect": true
}])
```

**Rules:**
- Pre-check options that were detected.
- If a tool is not detected and the researcher selects it, follow the ask-before-install step in `SKILL.md` Phase 1. Re-run detection before proceeding.
- Store final selection as the `tools` object (used in Phase 4).

## Library route

> Used by `init` Phase 3 and `update-tools`. Decides which library this article project reads its books from, and stores the answer in `.academic-helper/library.json` (schema: `src/schemas/library-config.schema.json`). PageIndex is optional: it is a library the researcher hosts themselves, so nothing here installs it.

### Detect (changes nothing, never prints the command itself)

```bash
{ [ -n "${AW_PAGEINDEX_COMMAND:-}" ] || command -v pilib >/dev/null 2>&1; } && echo "PAGEINDEX_CONFIGURED" || echo "PAGEINDEX_NOT_CONFIGURED"
```

`AW_PAGEINDEX_COMMAND` comes from the plugin setting `pageindex_command` (`/plugin` → Installed → academic-writer → Configure), exported at session start in projects that have `.academic-helper/profile.md`.

### Ask

**PageIndex not configured**: do not offer it. Say, in one sentence: "Your books will be read from Trove; if you keep a PageIndex library on your own server you can add it later in `/plugin` → academic-writer → Configure (the `pageindex_command` setting), then run `/academic-writer:update-tools`." Use route `trove`.

**PageIndex configured**:

```python
AskUserQuestion(questions=[{
  "question": "Which library should this article read its books from?",
  "header": "Library",
  "options": [
    {"label": "Trove (your current library)", "description": "What you use today. Nothing changes."},
    {"label": "PageIndex (a library on your own server)", "description": "Books are read from your PageIndex library instead of Trove."},
    {"label": "Both: one answers and the other is tested quietly in the background", "description": "Your writing only ever waits for the one that answers. The other is tried on the same request and its timing and result are noted in a private log in this project, so you can compare them later."}
  ],
  "multiSelect": false
}])
```

Only when the researcher picked **Both**:

```python
AskUserQuestion(questions=[{
  "question": "Which library should give the answers while the other is tested in the background?",
  "header": "Which answers",
  "options": [
    {"label": "Trove (recommended)", "description": "Your current library answers; PageIndex is tested quietly."},
    {"label": "PageIndex", "description": "PageIndex answers; Trove is tested quietly."}
  ],
  "multiSelect": false
}])
```

Never ask for a host, address, key or password in chat.

### Write

Use the Write tool to save `.academic-helper/library.json`, one of:

```json
{ "route": "trove" }
```

```json
{ "route": "pageindex" }
```

```json
{ "route": "both", "primary": "trove" }
```

(`primary` is `"pageindex"` when the researcher chose PageIndex as the answering library.) When the file already exists, read it first and keep its other keys (`pageindex`, `shadow`) unchanged; change only `route` and `primary` (drop `primary` for a single route). Then confirm in one plain sentence what was chosen. When the route includes PageIndex, also run `"${CLAUDE_PLUGIN_ROOT}/bin/aw" library status --check` and report the result in plain words; if PageIndex did not answer, say so and point to the "PageIndex" entries in `${CLAUDE_PLUGIN_ROOT}/skills/setup/references/troubleshooting.md` (the route is still saved).
