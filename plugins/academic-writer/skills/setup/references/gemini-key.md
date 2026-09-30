# Gemini key: get it, store it, check it

> Shared by `setup` Step 5 and `init` Phase 3.5. Read it when the researcher wants Gemini.

## How the key reaches the plugin (what the code does)

- The plugin's `aw` command reads the key from an environment variable named `GOOGLE_API_KEY`
  (a named value that programs on your computer can read). It reads nothing else: a
  `.academic-helper/secrets.json` file is **not** a key source.
- There are two ways to give it that value:
  1. **Plugin setting `google_api_key` (recommended).** Claude Code keeps it in the operating
     system's keychain (the password store built into macOS and Windows; on Linux a protected
     credentials file). At the start of every Claude Code session, the plugin's start-up hook
     copies it into `GOOGLE_API_KEY` for that session.
  2. **An `export GOOGLE_API_KEY=...` line in your shell profile** (or, on Windows, a user
     environment variable). This works for every tool on the computer, not just this plugin.
- The start-up hook only runs in a project that already has `.academic-helper/profile.md`. That is
  why setup saves the profile **before** asking the researcher to restart.
- Changes take effect only in a **new** Claude Code session.

## What to tell the researcher (plain words)

> "Gemini is Google's AI model. Academic Writer can use it to draft and proofread, while Claude
> keeps checking every citation. To let the plugin talk to Gemini, you need an **API key** — a
> long password, tied to your own Google account, that lets a program use Gemini on your behalf.
>
> - **Cost:** Google's free tier is enough for normal use, and creating a key normally needs no
>   credit card.
> - **Privacy:** when Gemini is on, the text of your article and the source passages it uses are
>   sent to Google to be processed. If a text must not leave your computer, don't run the drafting, proofreading or scan-reading commands on it.
> - **Safety:** please don't paste the key into this chat. Everything typed in the chat is saved in
>   the conversation history, so a key there could be read later. I'll show you a safe place to put
>   it instead."

## Getting a key (the researcher does this)

1. Open https://aistudio.google.com/apikey in your browser.
2. Sign in with your Google account (a personal Gmail account works).
3. If asked, accept the Google AI Studio terms.
4. Click **Create API key**. If it asks for a project, choose the default one it offers.
5. Click the copy icon next to the new key. It is a long code that starts with `AIza`.
6. Keep that browser tab open until the key is stored.

## Storing the key

Ask with `AskUserQuestion`:

```python
AskUserQuestion(questions=[{
  "question": "Where would you like to keep your Gemini key?",
  "header": "Key storage",
  "options": [
    {"label": "Plugin settings (recommended)", "description": "Claude Code keeps it in your computer's keychain. Nothing to edit by hand."},
    {"label": "My shell profile", "description": "A line in a settings file on your computer. Use this if you run other tools that also need the key."}
  ],
  "multiSelect": false
}])
```

### Option A — Plugin settings (kept in the keychain)

1. In Claude Code, type `/plugin` and press Enter.
2. Open the **Installed** tab and select **academic-writer**.
3. Choose **Configure** (the plugin's options).
4. In the **google_api_key** ("Gemini API key") field, paste the key and confirm.
5. Quit Claude Code completely and open it again in this project folder.

Claude Code may also ask for this value when the plugin is first installed or enabled; entering it
there is the same thing.

### Option B — Shell profile / environment variable

**macOS**
1. Open the Terminal app (Cmd+Space, type "Terminal", Enter).
2. Type `touch ~/.zshrc && open -e ~/.zshrc` and press Enter. A TextEdit window opens.
3. On a new line at the end, type `export GOOGLE_API_KEY="` then paste the key, then type `"`.
4. Save (Cmd+S) and close TextEdit, then quit Terminal.
5. Quit Claude Code completely and open it again.

**Windows**
1. Press the Windows key, type "environment variables", and open **Edit environment variables
   for your account**.
2. Under "User variables", click **New…**.
3. Variable name: `GOOGLE_API_KEY`. Variable value: paste the key. Click OK, then OK again.
4. Close Claude Code completely and open it again.

**Linux**: add `export GOOGLE_API_KEY="..."` to the end of `~/.bashrc` (or `~/.zshrc`), then open
a new terminal and restart Claude Code.

A shell-profile key is only seen by Claude Code when Claude Code is started from a terminal or
login shell. If the check below says the key is missing, use Option A.

## Checking the key (after the restart)

Never print the key. First confirm the plugin's command is available:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" models check
```

It lists the Gemini steps the plugin uses; it does not contact Google. Then run one tiny live
check. It asks Google for its model list, so no article text is sent, and the key travels in a
header rather than on the command line:

```bash
if [ -z "${GOOGLE_API_KEY:-}" ]; then
  echo "NO_KEY"
else
  code=$(curl -s -o /dev/null -w '%{http_code}' -H "x-goog-api-key: ${GOOGLE_API_KEY}" \
    https://generativelanguage.googleapis.com/v1beta/models)
  echo "HTTP ${code}"
fi
```

| Result | Tell the researcher |
|---|---|
| `HTTP 200` | "Your Gemini key works." |
| `NO_KEY` | "Claude Code didn't pick up the key yet. Make sure you restarted Claude Code in this project folder, and that `.academic-helper/profile.md` exists. If you used the shell profile, try the plugin settings instead." |
| `HTTP 400`, `401` or `403` | "Google didn't accept the key. Copy it again from https://aistudio.google.com/apikey (the whole code, starting with `AIza`) and store it again." |
| `HTTP 429` | "The key works but has hit Google's free-tier limit for now. Try again later." |
| `HTTP 000` | "I couldn't reach Google — check your internet connection." |

## Saving the choice

Record the result in the `## Gemini` block of `profile.md` (field-by-field format:
`${CLAUDE_PLUGIN_ROOT}/skills/init/references/profile-schema.md`): `enabled: true` with
`approvedLanguages: ["<targetLanguage>"]` when the researcher wants Gemini, otherwise
`enabled: false` and `approvedLanguages: []`. A key that failed the check still leaves
`enabled: true` if they want to fix it later; mention it in the summary.
