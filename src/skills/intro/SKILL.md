---
name: intro
description: "Opens the full illustrated Academic Writer guide (a page bundled with the plugin) in the user's web browser, then gives a five-line summary. Use when the user asks how the plugin works, wants an overview, a tutorial or the full guide, or is new and unsure where to begin."
user-invocable: true
disable-model-invocation: false
allowed-tools: [Bash]
metadata: {author: "Yotam Fromm", version: "0.16.0", summary: "Open the full guide in your web browser: what the plugin does, setup, your first article, privacy and troubleshooting."}
---

# Academic Writer — Open the guide

The guide is a single page that ships inside the plugin and works offline:
`${CLAUDE_PLUGIN_ROOT}/guide/index.html`. It is regenerated at every build, so its command list always
matches the installed version.

## Step 1 — Open it

Run this once. It picks the right way to open a file for the user's operating system and never
fails loudly.

```bash
GUIDE="${CLAUDE_PLUGIN_ROOT}/guide/index.html"
if [ ! -f "$GUIDE" ]; then echo "MISSING $GUIDE"; exit 0; fi
opened=""
case "$(uname -s 2>/dev/null)" in
  Darwin)
    open "$GUIDE" && opened=yes ;;
  Linux)
    if grep -qi microsoft /proc/version 2>/dev/null && command -v wslview >/dev/null 2>&1; then
      wslview "$GUIDE" && opened=yes
    elif command -v xdg-open >/dev/null 2>&1; then
      xdg-open "$GUIDE" >/dev/null 2>&1 && opened=yes
    fi ;;
  MINGW*|MSYS*|CYGWIN*|Windows_NT)
    WIN_GUIDE="$GUIDE"
    command -v cygpath >/dev/null 2>&1 && WIN_GUIDE="$(cygpath -w "$GUIDE")"
    cmd //c start "" "$WIN_GUIDE" 2>/dev/null && opened=yes
    [ -z "$opened" ] && powershell.exe -NoProfile -Command "Start-Process -FilePath '$WIN_GUIDE'" && opened=yes ;;
esac
[ -n "$opened" ] && echo "OPENED $GUIDE" || echo "NOT_OPENED $GUIDE"
```

- `OPENED`: tell the user the guide is now open in their browser (it may be behind the terminal
  window).
- `NOT_OPENED`: give them the full file path on its own line and say: "Open your file manager
  (Finder on a Mac, File Explorer on Windows), go to this location, and double-click `index.html`.
  It opens in your web browser and needs no internet connection." On Windows you can also paste the
  path into the browser's address bar.
- `MISSING`: the plugin install is incomplete. Suggest `/academic-writer:health`, then reinstalling
  the plugin, and give the five-line summary below anyway.

## Step 2 — Five-line summary in chat

Whatever happened above, finish with exactly these five lines (translate to Hebrew if the user wrote
in Hebrew):

1. Academic Writer drafts a scholarly article in your voice, using only the sources you choose.
2. First run `/academic-writer:setup`: it gets you a free Gemini key and checks the tools it needs.
3. Then `/academic-writer:write`: you agree on topic, sources, thesis and outline, and get a Word file.
4. Mark up the Word file with comments, then `/academic-writer:revise` folds them back in.
5. Stuck? `/academic-writer:health` checks everything, and `/academic-writer:help` lists every command.
