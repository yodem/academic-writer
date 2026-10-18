---
name: watch
description: "Show what Academic Writer is doing right now: the current step of the article run, how far it has got, and anything the checker rejected. Use when the researcher asks what is happening, how far along the article is, whether it is stuck, or to open the live activity pane."
user-invocable: true
allowed-tools: [Bash]
metadata: {author: "Academic Writer", version: "0.1.0"}
---

# Academic Writer — Watch a run

Show the status of the newest run. This works in every Claude Code version and in Cowork; it needs no add-on.

1. Run the status command and print its one line for the researcher:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/aw" --project-dir "${CLAUDE_PROJECT_DIR:-$PWD}" activity show --latest
   ```

   If the output says there is no activity yet, say so in plain words and suggest `/academic-writer:write` to start an article.

2. Tell them, in one sentence, that in a Claude Code version that supports plugin panes, `/activity` opens a live
   pane beside the conversation (it needs a terminal about 144 columns wide), and that the dashboard's Writing page
   shows the same record.

The pane and the status line only read the run's record. They never change the article or call a model.
