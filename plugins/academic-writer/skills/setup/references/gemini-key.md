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

Print these as a list, then end your turn with "Tell me when you have copied the key. Don't paste it here."

1. Open https://aistudio.google.com/apikey in your web browser (Safari or Chrome).
2. Sign in with your Google account (a personal Gmail account works). The page is Google's "AI Studio".
3. If asked, tick the box to accept the Google AI Studio terms and click **Continue**.
4. Click the **Create API key** button. If it asks for a project, choose the default one it offers (or **Create API key in new project**).
5. The new key appears in a list. Click the copy icon (two overlapping squares) next to it. It is a long code that starts with `AIza`.
   Nothing visible happens when you copy; that is normal.
6. Keep that browser tab open until the key is stored. Do not paste the key into this conversation.

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

Print these steps, then end your turn ("Tell me when it is saved"). The `/plugin` screen is a text menu inside Claude Code:
move with the up and down arrow keys, press Enter to choose, Esc to go back. (Clicking with the mouse may not work there.)

1. Click in the prompt box at the bottom of Claude Code, type `/plugin` and press Enter. A menu opens.
2. Use the arrow keys to open the **Installed** tab (left and right arrows switch tabs) and press Enter on **academic-writer**.
3. Choose **Configure** and press Enter. A list of the plugin's settings appears.
4. In the **google_api_key** ("Gemini API key") field, paste the key (Cmd+V on a Mac, Ctrl+V on Windows and Linux) and press Enter to save.
   The pasted key may show as dots or stars: that is the keychain protecting it.
5. Press Esc until the menu closes. Then restart Claude Code (see `dependencies.md § Restarting Claude Code`).

Claude Code may also ask for this value when the plugin is first installed or enabled; entering it
there is the same thing.

### Option B — Shell profile / environment variable

**macOS**
1. Open the Terminal app (Cmd+Space, type `Terminal`, press Enter).
2. Type `touch ~/.zshrc && open -e ~/.zshrc` and press Enter. A TextEdit window opens with a text file (it may be empty: that is fine).
3. Click at the very end of the text, press Enter for a new line, then type `export GOOGLE_API_KEY="`, paste the key (Cmd+V), and type `"`.
   The line should look like: `export GOOGLE_API_KEY="AIza..."` with no spaces around the `=`.
4. Save (Cmd+S) and close TextEdit, then quit Terminal (Cmd+Q).
5. Quit Claude Code completely and open it again in the same folder. It must be started from a Terminal window (type `claude`) to see
   this line; if it was started from the desktop app and the check below says `NO_KEY`, use Option A instead.

**Windows**
1. Press the Windows key, type "environment variables", and open **Edit environment variables
   for your account**.
2. Under "User variables", click **New…**.
3. Variable name: `GOOGLE_API_KEY`. Variable value: paste the key. Click OK, then OK again.
4. Close Claude Code completely and open it again.

**Linux**: add `export GOOGLE_API_KEY="..."` to the end of `~/.bashrc` (or `~/.zshrc`), then open
a new terminal and restart Claude Code.

A shell-profile key is only seen by Claude Code when Claude Code is started from a terminal or
login shell. If the check below says the key is missing, use Option A (it works the same everywhere).

## Checking the key (after the restart)

Tell the researcher first, in one plain sentence, what is about to happen ("I'll test the key; this sends no article text and shows
nothing secret"). If setup asks to run the commands below and the permission prompt appears, they should choose **Yes**.

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
