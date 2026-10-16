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

> Used by `init` Phase 3 and `update-tools`. Decides which library this article project reads its books from, and stores the answer in `.academic-helper/library.json` (schema: `src/schemas/library-config.schema.json`). Trove is the default. PageIndex is optional: either the built-in helper (a separate, asked-first install, see `${CLAUDE_PLUGIN_ROOT}/skills/setup/references/pageindex.md`) or a library the researcher hosts themselves. Choosing a route installs nothing.

### Detect (changes nothing, never prints the command itself)

Read what the project already says and how the command resolves, the same order `aw library` uses
(`AW_PAGEINDEX_COMMAND`, then `pageindex.command` in `.academic-helper/library.json`, then the built-in helper if it is installed, then `pilib`):

```bash
python3 - <<'PY'
import json, os, shlex, shutil
try:
    cfg = json.load(open('.academic-helper/library.json', encoding='utf-8'))
except Exception:
    cfg = {}
env_cmd = os.environ.get('AW_PAGEINDEX_COMMAND', '').strip()
file_cmd = (cfg.get('pageindex') or {}).get('command')
cmd = env_cmd or file_cmd or 'pilib'
words = cmd if isinstance(cmd, list) else shlex.split(cmd)
home = os.environ.get('AW_PAGEINDEX_HOME') or os.path.join('${CLAUDE_PLUGIN_DATA}', 'pageindex')
builtin = os.path.exists(os.path.join(home, 'installed.json'))
found = bool(env_cmd or file_cmd or builtin or (words and shutil.which(words[0])))
print('PAGEINDEX_CONFIGURED' if found else 'PAGEINDEX_NOT_CONFIGURED')
print('CURRENT_ROUTE=' + str(cfg.get('route', 'none')) + ' CURRENT_PRIMARY=' + str(cfg.get('primary', 'trove')))
PY
```

`AW_PAGEINDEX_COMMAND` comes from the plugin setting `pageindex_command` (`/plugin` → Installed → academic-writer → Configure), exported at session start in projects that have `.academic-helper/profile.md`. A project that already names its own command in `library.json` counts as configured.

### Ask

**An existing `library.json` is never overwritten without asking.** When `CURRENT_ROUTE` is not `none`, tell the researcher the current choice in plain words and ask whether to change it; the current choice comes first in the options and its description starts with "(current)". Write only after they pick a different route. If they keep it, write nothing. If the current route includes PageIndex but detection says it is not configured, say in plain words that PageIndex is not reachable right now and ask:

```python
AskUserQuestion(questions=[{
  "question": "Your article is set to read from PageIndex, but I can't reach it right now. Switch this article to Trove for now?",
  "header": "Library",
  "options": [
    {"label": "Keep it as it is", "description": "(current) Nothing changes. See the PageIndex entries in the troubleshooting list to get it working again."},
    {"label": "Switch to Trove", "description": "Your books are read from Trove, as before. You can pick PageIndex again later."}
  ],
  "multiSelect": false
}])
```

"Keep it as it is" is the default: leave the file unchanged unless the researcher explicitly picks "Switch to Trove" (then write `{ "route": "trove" }`, keeping the other keys). Either way, point to the "PageIndex" entries in `${CLAUDE_PLUGIN_ROOT}/skills/setup/references/troubleshooting.md`.

**PageIndex not configured** (and no existing route to keep): do not offer it as a route yet. Say, in one sentence: "Your books will be read from Trove. PageIndex is an optional second library; I can set it up for you now, or you can do it later with `/academic-writer:update-tools`." If the researcher wants it, follow `${CLAUDE_PLUGIN_ROOT}/skills/setup/references/pageindex.md` (its own question, plan and yes; "Not now" is the default), then run the detection again. If it is still not configured, use route `trove`, and write it only when there is no `library.json` yet.

**PageIndex configured**:

```python
AskUserQuestion(questions=[{
  "question": "Which library should this article read its books from?",
  "header": "Library",
  "options": [
    {"label": "Trove (your current library)", "description": "What you use today. Nothing changes."},
    {"label": "PageIndex (a second library: on this computer or your own server)", "description": "Books are read from your PageIndex library instead of Trove."},
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
