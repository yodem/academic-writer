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
- **Authentication error**: check that the complete key is active at
  https://aistudio.google.com/apikey.
- **Quota or network error**: wait for quota to reset or check the network/proxy, then retry.
- **CAP_REACHED (exit 4)**: inspect `aw ledger show <run>` to see the calls and budget state. Start
  a new run only after addressing the budget or input size that exhausted the cap.

## pip install failures

- **`pip3: command not found`**: try `python3 -m pip install python-docx lxml pdfplumber pymupdf`.
- **Permission denied**: retry with `pip3 install --user python-docx lxml pdfplumber pymupdf`, or
  use a virtual environment if the researcher's workflow supports one.
- **Build errors on `lxml` or `pymupdf`**: upgrade pip and retry; a source build can indicate an
  unusual Python version or architecture.

See `python-deps.md` in this folder for the dependency check script.
