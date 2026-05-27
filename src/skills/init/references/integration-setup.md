# Integration Setup (Candlekeep, NotebookLM)

> Loaded on demand by `init` Phase 1. Each tool has detection command, configuration block, and registration steps.

## Detection Commands

Run ALL in parallel:

```python
# PARALLEL — launch all at once
Bash(command="command -v ck >/dev/null 2>&1 && echo 'DETECTED' || echo 'NOT_DETECTED'")
Bash(command="command -v nlm >/dev/null 2>&1 && nlm login --check 2>/dev/null && echo 'DETECTED' || echo 'NOT_DETECTED'")
```

## Present Results

```python
AskUserQuestion(questions=[{
  "question": "Here are the tools I found. Which would you like to enable?",
  "header": "Integration setup",
  "options": [
    {
      "label": "Candlekeep",
      "description": "✓ Detected  (or ✗ Not found — install from github.com/romiluz13/candlekeep)",
      "markdown": "```\nCandlekeep\n──────────\nType:    CLI (ck)\nWhat:    Cloud document library\nBest for: Storing and searching your source PDFs\nStatus:  ✓ Detected\n```"
    },
    {
      "label": "NotebookLM",
      "description": "✓ Detected  (or ✗ Not found — run: npm install -g notebooklm-mcp-cli)",
      "markdown": "```\nNotebookLM\n──────────\nType:    MCP server (nlm CLI)\nWhat:    AI-powered source Q&A, audio overviews,\n         study guides, research discovery\nStatus:  ✓ Detected\n\nSetup (if not installed):\n  npm install -g notebooklm-mcp-cli\n  nlm login\n```"
    }
  ],
  "multiSelect": true
}])
```

**Rules:**
- Pre-check options that were detected.
- If a tool is not detected and the researcher selects it, show the setup URL and walk them through installation. Re-run detection after they confirm, before proceeding.
- Store final selection as the `tools` object (used in Phase 4).
