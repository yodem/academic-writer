# Setup Troubleshooting

> Loaded on demand by `setup` Steps 3d, 4, and the "Known gap" note.

## Gemini key / `gemini_raw` ping failures

**`{ error: { code: "no_credentials" } }`**
The `aw` CLI (`plugins/academic-writer/bin/aw`) reads the Gemini key from its environment only: `GOOGLE_API_KEY`, which a SessionStart hook exports from the plugin's `google_api_key` setting (stored in the OS keychain), or which you export in your shell. `.academic-helper/secrets.json` is no longer read. Common causes:
- You just set the plugin option or the environment variable in a session that had already started. The SessionStart hook only runs at session start. **Fix**: start a new Claude Code session, then re-run `/academic-writer:setup`.
- You configured the plugin option (`claude plugin install --config google_api_key=...` /
  `claude plugin config`) at a different scope (`user` vs `project`) than the one active for this
  session. **Fix**: re-run the config command at the scope you're actually using, or check current
  values via `/plugin`.
- You saved the key to a *different* project's `.academic-helper/secrets.json` — the server reads
  from the current working directory. **Fix**: confirm you're in the right project folder.
- Typo in the key file — the server reads the key `GOOGLE_API_KEY` (accepts lowercase
  `google_api_key` as a fallback, but always write the uppercase form). **Fix**: `cat
  .academic-helper/secrets.json` and check the key name matches exactly.

**Any other error from the ping** (auth failure, quota, network):
- Double-check the key was copied in full from https://aistudio.google.com/apikey — a truncated
  paste is the most common cause.
- A brand-new key can take a minute to activate on Google's side. Wait a moment and re-run setup.
- If you're behind a restrictive network/proxy, the MCP server call itself may be blocked — this
  is outside Academic Writer's control.

## Key storage troubleshooting

- **Plugin configuration not resolving**: this is the preferred, most secure path (OS keychain, or a
  protected credentials file on platforms without one) — but it requires an action outside this
  conversation (`claude plugin install --config google_api_key=...`, `claude plugin config`, or the
  `/plugin` manager's configuration dialog) followed by a Claude Code restart so the MCP server
  process picks up the new value. It coexists with the two paths below; setting it doesn't require
  removing an existing `GOOGLE_API_KEY` env var or `secrets.json` — the server just prefers whichever
  is set first, in that order.
- **Environment variable not sticking**: confirm you added the `export GOOGLE_API_KEY=...` line to
  the shell profile file your shell actually loads (`~/.zshrc` for zsh, `~/.bashrc` or
  `~/.bash_profile` for bash), not just typed it into the current terminal session. Open a new
  terminal/session and run `echo $GOOGLE_API_KEY` to confirm it's set before restarting Claude Code.
- **Secrets file not being picked up**: confirm you're running Claude Code from the same project
  directory where `.academic-helper/secrets.json` lives — it's a project-local file, not global.
- **Permissions**: the setup wizard chmods the secrets file to `0600` (owner read/write only) after
  writing it. If you edit it by hand afterward with a tool that resets permissions, re-run:
  `chmod 600 .academic-helper/secrets.json`.

## pip install failures

- **`pip3: command not found`**: try `python3 -m pip install python-docx lxml pdfplumber pymupdf`
  instead — some Python installs don't put `pip3` on `PATH` directly.
- **Permission denied**: on some systems the global site-packages directory isn't user-writable.
  Retry with `pip3 install --user python-docx lxml pdfplumber pymupdf`, or use a virtual
  environment (`python3 -m venv .venv && source .venv/bin/activate && pip install ...`) if the
  researcher's workflow supports one.
- **Build errors on `lxml` or `pymupdf`**: these ship prebuilt wheels for all common platforms: a
  build-from-source attempt usually means pip is falling back due to an unusual Python
  version/architecture combination. Recommend upgrading pip first (`pip3 install --upgrade pip`)
  and retrying.
- See `python-deps.md` in this same folder for the check script and the note that there's no
  `requirements.txt` in this repo to fall back to.

## SessionStart hook nudge — known gap

There is no editable SessionStart hook source in this repo that checks for a missing
`.academic-helper/` and nudges the researcher toward `/academic-writer:setup`. The hooks that do
exist ship as built `.mjs` files under `plugins/academic-writer/hooks/dist/`, sourced from
`src/hooks/src/` (see `src/hooks/hooks.json` for the wired SessionStart entries: `session-dashboard`,
`voice-pull`, and a `voice-migrate.sh` script — none of them check for or create
`.academic-helper/`, none of them point a new user at `setup`). Until that's built, the
text-based nudges in this SKILL.md, `write/SKILL.md`, and `init/SKILL.md` are the only onboarding
signal a first-time user gets.
