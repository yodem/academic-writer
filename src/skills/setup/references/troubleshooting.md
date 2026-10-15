# Setup Troubleshooting

> Loaded on demand by setup when an `aw` CLI operation fails or Python tools are missing.

## Gemini key and `aw` CLI failures

The `aw` CLI at `plugins/academic-writer/bin/aw` reads `GOOGLE_API_KEY` from its environment. At
session start, the plugin's SessionStart hook exports the `google_api_key` option from the OS
keychain. You can also export `GOOGLE_API_KEY` in your shell. If you change either setting during
an active session, start a new session before retrying.

The CLI prints failures as `ERROR <step>: ...`. Exit status `3` means a required precondition is
missing; status `4` means the configured CAP_REACHED budget was reached. Inspect the run's ledger
with `aw ledger show <run>` (use the run ID shown by the command that failed).

- **Missing key / precondition**: confirm `GOOGLE_API_KEY` is available to the session, then start
  a fresh session. The plugin option is named `google_api_key`; a shell export is also supported.
  The start-up hook only exports the plugin option in a project that has
  `.academic-helper/profile.md`, so run `/academic-writer:setup` in the project first.
- **Authentication error**: check that the complete key is active at
  https://aistudio.google.com/apikey.
- **Quota or network error**: wait for quota to reset or check the network/proxy, then retry.
- **CAP_REACHED (exit 4)**: inspect `aw ledger show <run>` to see the calls and budget state. Start
  a new run only after addressing the budget or input size that exhausted the cap.

## PageIndex library (optional second library)

These apply only to projects whose `.academic-helper/library.json` has `"route": "pageindex"` or
`"route": "both"`. With `"route": "trove"`, or no `library.json`, none of this is used. The setting
`pageindex_command` (`/plugin` → Installed → academic-writer → Configure) reaches the session as
`AW_PAGEINDEX_COMMAND`; the start-up hook exports it only in a project that has
`.academic-helper/profile.md`, and only a new session picks up a changed value.

- **PageIndex not reachable**: run `"${CLAUDE_PLUGIN_ROOT}/bin/aw" library status --check` in the
  project. If the `pageindex` entry under `check` shows `"ok": false`, its `error` says why. Check, in this order: the setting
  `pageindex_command` is filled in (no quotation marks) or `pilib` works in your terminal; the
  computer or server that hosts the library is on and you can reach it; then start a new Claude
  Code session. `AW_PAGEINDEX_COMMAND`, when set, wins over the command in `library.json`. If you
  cannot fix it now, run `/academic-writer:update-tools` and choose Trove, or write
  `{ "route": "trove" }` in `.academic-helper/library.json`; your articles read from Trove as before.
- **Wrong book list**: with PageIndex answering, the list shows the PageIndex library's books,
  narrowed to the shelf file named by `pageindex.shelf` in `library.json` when there is one
  (a bare list of book ids, or `{"books": [...]}`; a missing or unreadable shelf file means no
  narrowing). A book from Trove appears under its Trove id only when the shelf file's `map` links
  it to the PageIndex book. Add or fix the entry, or check the active shelf in Trove
  (`trove shelf current`) when Trove answers. An error "cannot tell how PageIndex pages map to
  Trove pages" means the `map` entry needs `"pages": "identity"` or a page map; the message names
  the book.
- **Shadow errors in the report**: with `"route": "both"`, the library that does not answer is
  tried quietly on the same request. Errors from that quiet lookup are recorded in
  `.academic-helper/retrieval.jsonl` and summarised by `aw library report`. They never change or
  delay your answers; they mean the second library did not respond or returned something the
  plugin could not read. Fix it as in "PageIndex not reachable", or stop the quiet test with
  `"shadow": { "enabled": false }` in `library.json` (or choose a single library).

## pip install failures

- **`No module named pip`**: Python was installed without its package installer. On macOS and
  Windows, reinstall Python from https://www.python.org/downloads/ (the official installer
  includes it); on Linux install `python3-pip` with the system package manager.
- **`externally-managed-environment`** (common with Homebrew Python or recent Linux): ask the
  researcher before retrying with `python3 -m pip install --user --break-system-packages ...`;
  explain that this flag only means "install for my user account even though the system manages
  Python", and that it does not touch other users.
- **Permission denied**: the command already uses `--user`; check the researcher is not in a
  folder or account without write access, then retry.
- **Build errors on `lxml` or `pymupdf`**: upgrade pip and retry; a source build can indicate an
  unusual Python version or architecture.

See `python-deps.md` for the package check and `dependencies.md` for every other tool.
