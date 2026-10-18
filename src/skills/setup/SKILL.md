---
name: setup
description: "Friendly first-run setup for researchers with no technical background: checks each tool Academic Writer needs, explains it in one sentence, asks before installing anything, walks you through getting and safely storing a free Gemini key, and ends with a sample paragraph. Use when you have just installed the plugin, when something seems missing, or when you want to add Gemini later."
user-invocable: true
disable-model-invocation: true
allowed-tools: [Bash, Read, Write, Glob, Grep, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.2.0"}
---

# Academic Writer — Setup Wizard

You are guiding a humanities researcher, often with no programming background, through first-run
setup. Speak plainly and warmly, one question at a time. Every technical word gets a one-line
explanation the first time it appears. Match the researcher's language: if they write in Hebrew,
answer in Hebrew.

Four rules hold for the whole wizard:

1. **Ask before you install.** Run an install command only after the researcher chose "Install" in
   an `AskUserQuestion` for that specific tool. Report the result in one plain sentence.
2. **Never ask for the Gemini key in the chat.** Chat messages are saved in the conversation
   history, so a key typed there could be read later. The key goes into Claude Code's plugin
   settings (the keychain) or the researcher's own shell profile — never into a message or a file
   you write.
3. **A question's text is the only text the researcher is sure to see.** Anything you print in the
   same turn right before an `AskUserQuestion` may not be shown to them (a researcher once reported "I saw no paragraph").
   So either put everything they need in order to answer inside the question text itself, or, when it is
   long (a paragraph, a numbered list of steps, a table), print it, **end your turn** with a line such as
   "Tell me when you're done", and ask in the next turn. Never print-then-ask in one turn.
4. **When the researcher must type a command themselves** (the lines that start with `!`), use the
   recipe in `references/dependencies.md § Typing a command yourself`: say where to click, exactly what to
   type, what will open, and how they will know it worked. Then end your turn and wait.

Questions appear as a short list: the researcher moves with the up and down arrow keys and presses
Enter (or clicks an option). The last choice, **Other**, lets them type their own answer. Say this once, in the
first question.

Reference files (read when the step says so): `references/dependencies.md` (tools, per-OS steps, typing a command,
restarting), `python-deps.md`, `gemini-key.md`, `finish.md` (Steps 6 and 8), `pageindex.md`, `troubleshooting.md`.

---

## Step 0 — Preflight

Run silently before saying anything. First check that Claude Code was opened in a folder made for this work,
not in the home folder itself (setup creates `past-articles` and `.academic-helper` in the current folder):

```bash
[ "$PWD" = "$HOME" ] && echo "IN_HOME_FOLDER" || echo "FOLDER_OK"
```

On `IN_HOME_FOLDER`, create nothing. Say, in plain words: "Claude Code is open in your main home folder. Make a new folder
for your research (for example `Academic` inside Documents), quit Claude Code, reopen it in that folder and run
`/academic-writer:setup` again," with the steps from `references/dependencies.md § Restarting Claude Code`. Then stop.

Otherwise create the folders:

```bash
mkdir -p past-articles .academic-helper .academic-helper/logs && cp -n "${CLAUDE_PLUGIN_ROOT}/thresholds.json" .academic-helper/ 2>/dev/null || true
cat .academic-helper/profile.md 2>/dev/null && echo "EXISTS" || echo "NOT_FOUND"
```

If a profile exists, ask:

```python
AskUserQuestion(questions=[{
  "question": "You've run setup here before. Where should we start?",
  "header": "Welcome back",
  "options": [
    {"label": "Check my Gemini key", "description": "Pick up after a restart — jump straight to testing the key."},
    {"label": "Check everything again", "description": "Re-run the whole check. Your saved answers are kept, not wiped."}
  ],
  "multiSelect": false
}])
```

"Check my Gemini key" → jump to Step 5f. Otherwise continue.

### Python first

Every script in this plugin, including the one that saves your home folder, needs Python 3.9 or newer. Check it
before any step that runs `home.py`:

```bash
python3 --version
```

If that prints 3.9 or higher, carry on. If the command is not found or the version is older, say in plain words:
"Python is not installed (or is too old). It is the free engine that saves your settings and builds your Word
files, and I can't install it for you." Give the numbered steps for their system from
`references/dependencies.md § Python 3` (print them, end your turn), and tell them to restart Claude Code and run
`/academic-writer:setup` again. On a Mac that has never had developer tools, `python3 --version` may instead open an
Apple window asking to install "command line developer tools": that is safe, and the same file has the plain
words for it. Then stop. Do not run `home.py`, `home_migrate.py` or `setup_checks.py` without Python.

---

## Step 1 — Welcome

The welcome is **part of the first question's text** (Step 2), because text printed just before a question may
not be shown: "I'll ask one short question at a time, explain anything technical, and won't install anything
without asking you first. It takes about ten minutes."

---

## Step 2 — The basics

Just enough to write a sample paragraph; `/academic-writer:init` builds the full profile later.

AskUserQuestion needs 2 to 4 options, and always adds an **Other** choice that lets the researcher type their own
answer. So offer broad examples; most people will choose Other and type their exact field.

```python
AskUserQuestion(questions=[{
  "question": "Hi! I'll get Academic Writer ready for you. It takes about ten minutes. I'll ask one short question at a time, explain anything technical, and won't install anything without asking you first. (Use the arrow keys and Enter to choose; pick \"Other\" to type your own answer.) First: what is your field of study?",
  "header": "Field of study",
  "options": [
    {"label": "Jewish studies", "description": "Talmud, Bible, Jewish history or thought."},
    {"label": "History", "description": "Medieval or early modern history."},
    {"label": "Literature or language", "description": "Hebrew poetry, linguistics."},
    {"label": "Philosophy or religion", "description": "Philosophy, theology, religious studies."}
  ],
  "multiSelect": false
}])
```

If they choose one of these broad examples, ask in plain chat for the specific field in a few words (for example "Medieval
Hebrew Poetry") and wait for the reply. Store the specific answer as `fieldOfStudy`.

```python
AskUserQuestion(questions=[{
  "question": "Which language will you write your articles in?",
  "header": "Article language",
  "options": [
    {"label": "Hebrew", "description": "Right-to-left; I'll also offer a Hebrew spelling checker."},
    {"label": "English", "description": "Left-to-right. For another language, choose Other and type its name."}
  ],
  "multiSelect": false
}])
```

Store as `targetLanguage`.

```python
AskUserQuestion(questions=[{
  "question": "Which citation style do you use? (A citation style is the format of your footnotes and references.)",
  "header": "Citation style",
  "options": [
    {"label": "Inline Parenthetical", "description": "(Author, Title, Page) in running text — common for Hebrew."},
    {"label": "Chicago / Turabian", "description": "Footnotes with a bibliography — common in English Humanities."},
    {"label": "MLA", "description": "Parenthetical with a Works Cited page."},
    {"label": "APA", "description": "(Author, Year) — common in social sciences."}
  ],
  "multiSelect": false
}])
```

Map: Inline → `inline-parenthetical`, Chicago → `chicago`, MLA → `mla`, APA → `apa`. Store as
`citationStyle`.

### 2b. Your role

```python
AskUserQuestion(questions=[{
  "question": "Which describes you best? This only decides which next steps I suggest at the end.",
  "header": "Your role",
  "options": [
    {"label": "Student", "description": "Courses, readings, lessons and your own papers."},
    {"label": "Researcher", "description": "Articles, sources and your own writing style."},
    {"label": "Lecturer", "description": "You teach courses, and you do your own research."}
  ],
  "multiSelect": false
}])
```

Store as `role` (`student`, `lecturer` or `researcher`). These are the only three values.
A course you teach is a kind of folder, which `/academic-writer:init` registers later.

### 2c. Your home folder

The home folder is one visible folder that holds your identity and defaults (`home.md`), your
course registry and the list of your workspaces (every project or course folder you work in). First
see whether one is already chosen:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/home.py" --data-dir "${CLAUDE_PLUGIN_DATA}" show
```

If it names a home that exists, say so in one sentence and keep it. Otherwise choose one:

- **macOS:** open the system folder picker. Tell them first, in the same message that precedes it, what will
  happen: "A Finder window will open. Pick (or make, with **New Folder**) the folder where you keep your academic
  work, then click **Choose**. If you don't see the window, look for a new icon in the Dock; it can hide behind Claude Code."

  ```bash
  osascript -e 'POSIX path of (choose folder with prompt "Choose the folder where Academic Writer keeps your work")'
  ```

- **Any other system, or if the picker fails or is cancelled:** ask with `AskUserQuestion`; offer
  `~/Documents/Academic`, the current folder, and "Other" (the researcher types a path). Say that
  the folder is created if it does not exist. A "home folder" here is just one ordinary folder on your computer, not your
  computer's main home directory.

Then save the pointer and your answers in one call. `home.py set` writes the pointer file, the home's
`.academic-helper/` folder and `home.md` (your identity and defaults); it keeps anything `home.md` already held and
only fills in the answers you pass. Pass every answer you collected in Step 2 (`--name` only if you asked for it):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/home.py" --data-dir "${CLAUDE_PLUGIN_DATA}" set --path "CHOSEN_FOLDER" --role "ROLE" --field "FIELD_OF_STUDY" --target-language "TARGET_LANGUAGE" --citation-style "CITATION_STYLE"
```

Other flags: `--name`, `--institution`, `--degree`. A non-zero exit prints a plain `error`; read it to the
researcher and do not go on (the dashboard and setup's home check read `home.md`).

If the researcher has courses in the older (legacy) registry `~/.academic-writer/courses`, say a one-time
migration can move them and run it as a preview first: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/home_migrate.py" --home "CHOSEN_FOLDER" --data-dir "${CLAUDE_PLUGIN_DATA}"`.
It deletes nothing; only on a yes in `AskUserQuestion` add `--apply`. After updating the plugin, restart
Claude Code (quit it fully and open it again in the same folder): a running session keeps the old skills until then.

**Save the folder profile now**, before anything else: write `.academic-helper/profile.md` with
`workspace: project` and nothing else yet (format: `${CLAUDE_PLUGIN_ROOT}/skills/init/references/profile-schema.md`),
keeping every field an earlier profile already had. Your identity and defaults live in `home.md`; a folder profile
holds only what overrides them for that folder, so do not copy the Step 2 answers into it. The plugin's start-up hook
only passes the Gemini key on in a project that has this file, so it must exist before the restart in Step 5.

---

## Step 3 — What I'll check

Run the one checks script (it changes nothing and never prints a key):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_checks.py" --data-dir "${CLAUDE_PLUGIN_DATA}" --json
```

Each row has an `id`, `ok`, `optional` and a plain-language reason; Steps 4 and 8 read them (the per-OS lines in
`references/dependencies.md` are the fallback if the script cannot run). Show a short table — the tool, what it is for in
one phrase, ✓ found / ✗ missing / optional — for: Python 3 (`python`), the Python packages (`python-addons`), hspell
(`hspell`, Hebrew writers only), Trove (`trove`), NotebookLM (`notebooklm`) and the Gemini key (`gemini-key`).

> "Here's what I'll go through. Anything already ✓ we skip. For each missing piece I'll tell you
> what it's for and ask before installing. Say 'go' when you're ready."

Then **end your turn** (rule 3: the next step is a question, and the table would not be shown if you asked in
the same turn). If every row is ok, skip this pause and go to Step 5.

---

## Step 4 — One tool at a time

Handle each missing item in this order. For each: say what it is for in one sentence (the
sentences are in `references/dependencies.md`), ask, act, then re-run its detection line and report
in plain words. A skipped or failed item never blocks setup; note it for the summary.

### 4a. Python 3 (the researcher installs it)

If the `python` row is not ok, Claude cannot install it. Give the numbered steps for their system from
`references/dependencies.md § Python 3`, then stop here: the rest of setup needs Python, and the
researcher must restart Claude Code after installing. Tell them: "Your answers so far are saved. Quit Claude Code
completely, open it again in this same folder, and type `/academic-writer:setup`; I'll skip what is already done."


### 4b. Python packages (Claude installs after asking)

Skip if the `python-addons` row is ok. Otherwise (the missing names are in its reason):

```python
AskUserQuestion(questions=[{
  "question": "Academic Writer needs a few free Python add-ons to open Word and PDF files and build your finished document (missing: MISSING_LIST). May I install them now?",
  "header": "Python add-ons",
  "options": [
    {"label": "Install", "description": "One command, usually under a minute. Installs for your user account only."},
    {"label": "Skip for now", "description": "Reading PDFs and building the .docx won't work until they're installed."}
  ],
  "multiSelect": false
}])
```

Only on "Install":

```bash
python3 -m pip install --user python-docx lxml pdfplumber pymupdf jsonschema
```

Re-run `setup_checks.py --json` and read the `python-addons` row. On failure, read `references/troubleshooting.md § pip install failures`
and explain the fix before offering a retry (any retry with a different command is asked again).

### 4c. Homebrew (macOS, only if hspell is wanted)

Homebrew is a free installer for Mac tools. It needs the Mac password, so the researcher installs it in the
Terminal app: give the numbered steps from `references/dependencies.md § Homebrew` (print them, end your turn,
verify with `brew --version` in the next turn). Offer this only for a Hebrew writer who wants hspell while `BREW_MISSING`
(Trove and NotebookLM do not need Homebrew). If they decline, hspell is skipped; proofreading still works.

### 4d. hspell — Hebrew spelling checker (Hebrew writers only)

Skip unless `targetLanguage` is Hebrew and hspell is missing. On Windows it does not exist; proofreading skips that check. On Linux, give the researcher the
steps from the reference (it needs their password, so they run it in a regular terminal window). On macOS with
Homebrew:

```python
AskUserQuestion(questions=[{
  "question": "hspell is a free Hebrew spelling dictionary. The proofreader uses it to catch typos that are easy to miss. Install it?",
  "header": "Hebrew spelling",
  "options": [
    {"label": "Install", "description": "Uses Homebrew; takes about a minute."},
    {"label": "Skip", "description": "Proofreading still works, with one fewer safety net."}
  ],
  "multiSelect": false
}])
```

Only on "Install":

```bash
brew install hspell
```

### 4e. Trove — your research library (optional)

Skip if found. Explain it in one sentence (reference), then:

```python
AskUserQuestion(questions=[{
  "question": "Trove is an online library for your source PDFs, so I can search and quote them with exact pages. Set it up?",
  "header": "Trove (optional)",
  "options": [
    {"label": "Install", "description": "I download and run Trove's own installer (one command); then you create a Trove account or sign in once, in your browser."},
    {"label": "Skip", "description": "You can add it later by running setup again."}
  ],
  "multiSelect": false
}])
```

Only on "Install", on macOS or Linux:

```bash
curl -fsSL https://heytrove.ai/install.sh | sh
```

On Windows, point to https://heytrove.ai/install instead. If `command -v trove` still finds nothing, the new
tool is not visible to this session yet: the researcher quits Claude Code fully and opens it again in the same folder
(answers saved), then setup picks up at Trove.

Then the researcher signs in themselves: give the numbered steps from `references/dependencies.md § Trove`
(sign-up, `! trove login`, how they know it worked), end your turn, and verify next turn with
`trove auth whoami --no-session`.

### 4f. NotebookLM — source Q&A (optional)

Skip if found, or if `npm` is missing (say it's optional and can be added later; `references/dependencies.md § NotebookLM` explains how to add Node.js if they want it now). Otherwise:

```python
AskUserQuestion(questions=[{
  "question": "NotebookLM is Google's tool for asking questions about a set of sources; I can use it as a second research assistant. Install its connector?",
  "header": "NotebookLM (optional)",
  "options": [
    {"label": "Install", "description": "One command; you then sign in with Google once."},
    {"label": "Skip", "description": "Nothing else depends on it."}
  ],
  "multiSelect": false
}])
```

Only on "Install":

```bash
npm install -g notebooklm-mcp-cli
```

Then the researcher signs in themselves: give the numbered steps from `references/dependencies.md § NotebookLM`
(`! nlm login`, a Google sign-in page, how they know it worked), end your turn, and verify next turn with
`nlm login --check`.

### 4g. PageIndex library (optional; Trove stays the default)

PageIndex is a second way to find pages in the researcher's books. Offer it once, in plain words, only after the
Trove step. `references/pageindex.md` is the source for the question, the install plan and the "I run my own
server" path: set it up here (dry-run plan first), connect their own server (the `pageindex_command` setting; never a
host or password in chat), or not now (Trove only). Never install without a yes; failures are in `references/troubleshooting.md`.

---

## Step 5 — Gemini

Read `references/gemini-key.md` now; it is the source for every sentence and command below.

### 5a. Explain and ask

Use the "What to tell the researcher" facts from the reference (what Gemini and an API key are, the free tier, that
article text is sent to Google when Gemini is on, and why the key must not go in the chat), shortened into the
question text itself, because the question must carry them:

```python
AskUserQuestion(questions=[{
  "question": "Gemini is Google's AI model; Academic Writer uses it to draft, proofread and read scans, while Claude still checks every citation. It needs an \"API key\": a long password from your own Google account (Google's free tier is normally enough). When Gemini is on, your article text is sent to Google. Never paste the key into this chat. Set up your free key now?",
  "header": "Gemini key",
  "options": [
    {"label": "Yes, set it up", "description": "About five minutes: get a free key, store it safely, restart once."},
    {"label": "Not now", "description": "Nothing is sent to Google. Planning, research and review still work, but writing drafts, proofreading and reading scans need the key. Run setup again any time to add it."}
  ],
  "multiSelect": false
}])
```

"Not now" → record `gemini.enabled: false`, tell the researcher in one sentence which commands will ask for the key later (`write`, `edit`, `proofread`, `ocr`), and go to Step 6.

### 5b. Already set?

```bash
[ -n "${GOOGLE_API_KEY:-}" ] && echo "KEY_PRESENT" || echo "NO_KEY"
```

`KEY_PRESENT` → go to 5f.

### 5c. Get a key (the researcher does this)

Print the numbered steps from `references/gemini-key.md § Getting a key`, starting at
https://aistudio.google.com/apikey, and end your turn with "Tell me when you have copied the key. Don't paste it here."
Wait for them to say they have copied it.

### 5d. Store the key (the researcher does this)

Ask where to keep it with the `AskUserQuestion` in `references/gemini-key.md § Storing the key`,
then print the numbered steps for their choice (end your turn; they say "done" when stored):

- **Plugin settings (recommended):** `/plugin` → **Installed** → **academic-writer** →
  **Configure** → paste into **google_api_key**. Claude Code keeps it in the operating system's
  keychain (the built-in password store), never in a plain settings file.
- **Shell profile:** the macOS, Windows or Linux steps from the reference.

### 5e. Restart

Give the restart steps from `references/dependencies.md § Restarting Claude Code` in full (quit completely, reopen in the
same folder, type `/academic-writer:setup`, choose **Check my Gemini key**) and say: "Your answers so far are saved."

Stop the wizard here until they come back.

### 5f. Check the key

Run the two checks in `references/gemini-key.md § Checking the key` (`aw models check`, then the
live check, which never prints the key and sends no article text). Tell the researcher the
matching plain-language line from the result table. Record `gemini.enabled: true` and
`approvedLanguages: [targetLanguage]` in the profile if they want Gemini, even when the check
failed — note the failure in the summary.

---

## Step 6 — Sample paragraph

A quick proof that the conversation works, not a full article. Read `references/finish.md § Step 6`: it takes
**two turns** (ask a topic; then ask "Does this look right?" with the 2-4 sentence paragraph **inside the question
text**), because a paragraph printed just before a question may not be shown. Either answer completes setup.

---

## Step 7 — Save and summarize

Update `.academic-helper/profile.md` with the `## Gemini` block and anything else gathered, keeping
every existing field. Show:

> | Item | Status |
> |------|--------|
> | Field / language / citation style | [values] |
> | Home folder | ✓ [path] / ⚠ not chosen |
> | Python and its add-ons | ✓ Ready / ⚠ [what's missing and the one-line fix] |
> | Hebrew spelling (hspell) | ✓ / skipped / not available on Windows / not needed |
> | Trove / NotebookLM | ✓ / skipped (optional) |
> | PageIndex library | — Not now (Trove only) / ✓ Built-in helper installed [tier] / ✓ Your own server set in `pageindex_command` / ⚠ [problem in plain words] |
> | Gemini | ✓ Key works / ⚠ [problem in plain words] / — Not set up yet (needed to write, proofread, read scans) |
> | Sample paragraph | ✓ Looked good / noted: [feedback] |

---

## Step 8 — What you can do now

Re-run `setup_checks.py --json` once more, then print the short block in `references/finish.md § Step 8` for the
researcher's `role` (at most 8 lines, plain words, in `targetLanguage`). Researchers get three concrete next steps: put
5 to 10 past articles in the `past-articles` folder and run `/academic-writer:init`; `/academic-writer:write`; and
`/academic-writer:research`. List only commands whose prerequisites passed, and always end with
`/academic-writer:intro`. End your turn after the block and ask Step 9 in the next turn.

## Step 9 — What next

```python
AskUserQuestion(questions=[{
  "question": "You're set up. What would you like to do next?",
  "header": "Next step",
  "options": [
    {"label": "Show me the guide", "description": "Opens the illustrated guide in your browser: /academic-writer:intro"},
    {"label": "Start an article", "description": "Begin writing now: /academic-writer:write"},
    {"label": "Teach it my style", "description": "Fuller onboarding from your past articles: /academic-writer:init"},
    {"label": "I'm done for now", "description": "Everything is saved. Run /academic-writer:help any time for the command list."}
  ],
  "multiSelect": false
}])
```

Tell them which command to type for their choice. Re-running `setup` or `init` is always safe: they never wipe the profile.
