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
