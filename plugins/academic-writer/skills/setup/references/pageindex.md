# PageIndex: offer, install, or connect your own

> Used by `setup` Step 4g, `init` Phase 3, `update-tools` and `health`. Trove stays the default library; PageIndex is optional and chosen per article (`.academic-helper/library.json`, see `${CLAUDE_PLUGIN_ROOT}/skills/init/references/integration-setup.md`). Nothing here installs or sends anything without a yes.

## What to tell the researcher (plain words)

> "PageIndex is a second way for Claude to find the right page in your books. It keeps a short outline of every book, with a few lines on each section, so Claude can go straight to the likely page. Trove stays your main library either way, and you choose per article which one to use.
>
> To prepare a book, its text is sent once to Google (Gemini), with your own Gemini key, to write those few lines. On Google's free tier Google may use what you send to improve its products. There is a free option without Gemini summaries (the outline then uses the notes already written for Trove)."

## Ask (AskUserQuestion)

Offer all three, with "Not now" as the safe choice:

```python
AskUserQuestion(questions=[{
  "question": "Do you want PageIndex as a second library for your books?",
  "header": "PageIndex",
  "options": [
    {"label": "Set it up on this computer", "description": "Installs a small helper in the plugin's own folder. It takes a few minutes, needs some disk space, and you can remove it later. Books are sent to Google (Gemini) once when you prepare them."},
    {"label": "I run my own PageIndex on a server", "description": "You give the plugin the command that reaches your server. Nothing is installed here."},
    {"label": "Not now", "description": "(recommended if unsure) Trove only, as before. You can set this up later."}
  ],
  "multiSelect": false
}])
```

## "Set it up on this computer"

1. **Show the plan, change nothing** (no yes needed for this):

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library install --dry-run
```

The JSON names the `tier` it would install, the Python it found (`python.version`), the rough size (`approx_size_mb`) and, for the larger tier, a system library to add first (`system_library`). Say it in plain words:

- **Basic helper** (`core`, the smaller one, any Python 3.9 or newer): prepares books that have a table of contents, which is every book uploaded with `/academic-writer:ingest-book`.
- **Full helper** (`structure`, much larger, needs Python 3.10 or newer): also prepares a book that has no table of contents, by letting Gemini find its structure. On a Mac it needs the `pango` system library first (`brew install pango`); ask before installing it, as for any other tool.
- If only an older Python exists, the basic helper is chosen and the output says so. Do not install Python for the researcher: point at the Python steps of this setup, then offer to run the install again.

2. **Ask for the yes** with the figures from step 1 (the size in `approx_size_mb`, where it goes: the plugin's own data folder, how long: a few minutes, with a time limit after which the plugin stops). The command refuses to run without `--yes`; add it only after a yes.

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library install --yes [--tier core|structure]
```

3. **Check it** and report the result in plain words:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library status --check
```

`installed.installed` should be `true`, `pilib.ok` and `pilib.index_trove` should be `true`, and `installed.matches_pinned` should be `true`. If the full helper could not start, the install ends as the basic helper and says why (usually the missing system library): report that, it still works for books with a table of contents.

4. **Gemini key.** Summaries use the plugin's Gemini key (Step 5). If Gemini is not set up, say that books can still be prepared without summaries (`--summaries hints`) and that Step 5 sets the key up. Never ask for the key in chat.

To remove it later: `"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" library uninstall --yes` (the prepared books are kept unless `--purge-library` is added; ask before using that).

## "I run my own PageIndex on a server"

Nothing is installed. Tell the researcher: open `/plugin`, choose academic-writer, then Configure, and fill in `pageindex_command` with the command that reaches the server (for example `pilib`, or the full path of a helper script such as `/path/to/pilib-wrapper` that reaches it for them). Then start a new Claude Code session and run `/academic-writer:update-tools`. Never ask for a host, address, key or password in chat, and never put one in a file.

Two things to say honestly:

- To prepare books through a command like this, the server needs the plugin's PageIndex helper (the same one the built-in install uses), a signed-in Trove, and its own Gemini key. The plugin does not send your Gemini key to a server. `library status --check` reports `index_trove: false` and a plain warning when the server's helper is too old; reading books that are already prepared still works.
- A command the researcher sets always wins over the built-in helper, so a computer-local install is never used by surprise.

## "Not now"

Say in one line that Trove is used as before and that `/academic-writer:update-tools` or `/academic-writer:setup` offers this again.

## Many existing books (backfill)

After either setup, offer once to prepare existing Trove books too, only when the author wants PageIndex for old books. It reads Trove and never changes it. Show the plan first, with the estimate of Gemini calls, then ask:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library backfill --shelf-current --skip-existing --dry-run
```

Choose the books with `--shelf-current` (the active Trove shelf), `--ids a,b,c` or `--all`; add `--summaries hints` for the free option. After the author agrees, run the same command without `--dry-run`, adding `--yes` when the plan said it needs one (a large estimate, or a book with no table of contents). It can be run again safely: books already prepared are skipped.
