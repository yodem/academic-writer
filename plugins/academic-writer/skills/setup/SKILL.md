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

Two rules hold for the whole wizard:

1. **Ask before you install.** Run an install command only after the researcher chose "Install" in
   an `AskUserQuestion` for that specific tool. Report the result in one plain sentence.
2. **Never ask for the Gemini key in the chat.** Chat messages are saved in the conversation
   history, so a key typed there could be read later. The key goes into Claude Code's plugin
   settings (the keychain) or the researcher's own shell profile — never into a message or a file
   you write.

Reference files (read when the step says so):
- `references/dependencies.md` — what each tool is for, detection commands, per-OS steps.
- `references/python-deps.md` — the Python package check (the same check `setup_checks.py` runs).
- `references/gemini-key.md` — getting, storing and checking the Gemini key.
- `references/troubleshooting.md` — what to do when something fails.

---

## Step 0 — Preflight

Run silently before saying anything:

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
`references/dependencies.md § Python 3`, tell them to restart Claude Code and run `/academic-writer:setup` again,
and stop. Do not run `home.py`, `home_migrate.py` or `setup_checks.py` without Python.

---

## Step 1 — Welcome

> "Hi! I'll get Academic Writer ready for you. It takes about ten minutes. I'll ask one short
> question at a time, explain anything technical, and I won't install anything without asking you
> first."

---

## Step 2 — The basics

Just enough to write a sample paragraph; `/academic-writer:init` builds the full profile later.

```python
AskUserQuestion(questions=[{
  "question": "What's your field of study? (For example: Medieval Hebrew Poetry, Early Modern History)",
  "header": "Field of study",
  "options": []
}])
```

Store as `fieldOfStudy`.

```python
AskUserQuestion(questions=[{
  "question": "Which language will you write your articles in?",
  "header": "Article language",
  "options": [
    {"label": "Hebrew", "description": "Right-to-left; I'll also offer a Hebrew spelling checker."},
    {"label": "English", "description": "Left-to-right."},
    {"label": "Other", "description": "You'll type the language name."}
  ],
  "multiSelect": false
}])
```

Store as `targetLanguage`.

```python
AskUserQuestion(questions=[{
  "question": "Which citation style do you use?",
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

- **macOS:** open the system folder picker:

  ```bash
  osascript -e 'POSIX path of (choose folder with prompt "Choose the folder where Academic Writer keeps your work")'
  ```

- **Any other system, or if the picker fails or is cancelled:** ask with `AskUserQuestion`; offer
  `~/Documents/Academic`, the current folder, and "Other" (the researcher types a path). Say that
  the folder is created if it does not exist.

Then save the pointer and your answers in one call. `home.py set` writes the pointer file, the home's
`.academic-helper/` folder and `home.md` (your identity and defaults); it keeps anything `home.md` already held and
only fills in the answers you pass. Pass every answer you collected in Step 2 (`--name` only if you asked for it):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/home.py" --data-dir "${CLAUDE_PLUGIN_DATA}" set --path "CHOSEN_FOLDER" --role "ROLE" --field "FIELD_OF_STUDY" --target-language "TARGET_LANGUAGE" --citation-style "CITATION_STYLE"
```

Other flags: `--name`, `--institution`, `--degree`. A non-zero exit prints a plain `error`; read it to the
researcher and do not go on. Setup's "home folder" check and the dashboard read `home.md`, so skipping this call
leaves both stuck on "not set up".

If the researcher already has courses in the older registry under `~/.academic-writer/courses`
(the legacy location), tell them in one sentence that a one-time migration can move them, and
run it as a preview first: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/home_migrate.py" --home "CHOSEN_FOLDER" --data-dir "${CLAUDE_PLUGIN_DATA}"`.
It deletes nothing; only on a yes in `AskUserQuestion` add `--apply`. After updating the plugin, restart
Claude Code: a running session keeps the old skills until then.

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

Each row has an `id`, `ok`, `optional` and a plain-language reason. Keep the result: Steps 4 and 8
read it, and the dashboard's setup page shows the same rows. Show a short table built from the rows
— the tool, what it is for in one phrase, and ✓ found / ✗ missing / optional — for: Python 3
(`python`), the Python packages (`python-addons`), hspell (`hspell`, Hebrew writers only), Trove
(`trove`), NotebookLM (`notebooklm`), and the Gemini key (`gemini-key`). The per-OS detection
lines in `references/dependencies.md` stay the fallback when the script itself cannot run
(for example, no Python at all).

> "Here's what I'll go through. Anything already ✓ we skip. For each missing piece I'll tell you
> what it's for and ask before installing."

---

## Step 4 — One tool at a time

Handle each missing item in this order. For each: say what it is for in one sentence (the
sentences are in `references/dependencies.md`), ask, act, then re-run its detection line and report
in plain words. A skipped or failed item never blocks setup; note it for the summary.

### 4a. Python 3 (the researcher installs it)

If the `python` row is not ok, Claude cannot install it. Give the numbered steps for their system from
`references/dependencies.md § Python 3`, then stop here: the rest of setup needs Python, and the
researcher must restart Claude Code after installing. Tell them to run `/academic-writer:setup`
again afterwards.

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

### 4c. Homebrew (macOS, only if hspell or Trove is wanted)

Homebrew needs the Mac password, so the researcher installs it: give the numbered steps from
`references/dependencies.md § Homebrew`. Offer this only when the researcher wants hspell or
Trove and `BREW_MISSING`.

### 4d. hspell — Hebrew spelling checker (Hebrew writers only)

Skip unless `targetLanguage` is Hebrew and hspell is missing. On Windows, say it has no Windows
version and that proofreading simply skips that check; move on. On Linux, give the researcher the
`! sudo apt install hspell` line from the reference (it needs their password). On macOS with
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
    {"label": "Install", "description": "On a Mac I install it with Homebrew; you then sign in once in your browser."},
    {"label": "Skip", "description": "You can add it later by running setup again."}
  ],
  "multiSelect": false
}])
```

Only on "Install", on macOS or Linux:

```bash
curl -fsSL https://heytrove.ai/install.sh | sh
```

On Windows, point to https://heytrove.ai/install instead. Then ask the researcher to
sign in themselves by typing `! trove login` (it opens their browser).

### 4f. NotebookLM — source Q&A (optional)

Skip if found, or if `npm` is missing (say it's optional and can be added later). Otherwise:

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

Then ask the researcher to type `! nlm login` to sign in (it opens their browser).

### 4g. PageIndex library (optional; Trove stays the default)

PageIndex is a second way to find pages in the researcher's books. Offer it once, in plain words,
and only after the Trove step: read `references/pageindex.md` now; it is the source for the
question, the install plan (what it installs, how big, how long, what is sent to Google) and the
"I run my own server" path. Three choices through `AskUserQuestion`: set it up on this computer
(asked, with a dry-run plan first), connect the researcher's own server (the `pageindex_command`
setting; never a host, address or password in chat), or not now (Trove only). Never install without
a yes. Failures: "PageIndex" in `references/troubleshooting.md`.

---

## Step 5 — Gemini

Read `references/gemini-key.md` now; it is the source for every sentence and command below.

### 5a. Explain and ask

Say the "What to tell the researcher" text from the reference: what Gemini and an API key are, the
free tier, that article text is sent to Google when Gemini is on, and why the key must not go in
the chat. Then:

```python
AskUserQuestion(questions=[{
  "question": "Set up your free Gemini key now? Drafting, proofreading and reading scans run on Gemini.",
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

Give the numbered steps from `references/gemini-key.md § Getting a key`, starting at
https://aistudio.google.com/apikey. Wait for them to say they have copied it.

### 5d. Store the key (the researcher does this)

Ask where to keep it with the `AskUserQuestion` in `references/gemini-key.md § Storing the key`,
then give the numbered steps for their choice:

- **Plugin settings (recommended):** `/plugin` → **Installed** → **academic-writer** →
  **Configure** → paste into **google_api_key**. Claude Code keeps it in the operating system's
  keychain (the built-in password store), never in a plain settings file.
- **Shell profile:** the macOS, Windows or Linux steps from the reference.

### 5e. Restart

> "Now quit Claude Code completely and open it again in this same folder, then type
> `/academic-writer:setup` and choose **Check my Gemini key**. Your answers so far are saved."

Stop the wizard here until they come back.

### 5f. Check the key

Run the two checks in `references/gemini-key.md § Checking the key` (`aw models check`, then the
live check, which never prints the key and sends no article text). Tell the researcher the
matching plain-language line from the result table. Record `gemini.enabled: true` and
`approvedLanguages: [targetLanguage]` in the profile if they want Gemini, even when the check
failed — note the failure in the summary.

---

## Step 6 — Sample paragraph

A quick proof that the conversation works, not a full article.

```python
AskUserQuestion(questions=[{
  "question": "Let's write one short sample paragraph. Give me a small topic, or I'll pick one.",
  "header": "Sample paragraph",
  "options": [
    {"label": "I'll give a topic", "description": "Type a short topic, e.g. \"the printing press\"."},
    {"label": "Pick one for me", "description": "I'll choose a general topic in your field."}
  ],
  "multiSelect": false
}])
```

Write 2–4 sentences yourself on that topic, in the register of `fieldOfStudy` and in
`targetLanguage`. Say that real articles cite sources and follow their own voice, which
`/academic-writer:init` learns from past articles. Then:

```python
AskUserQuestion(questions=[{
  "question": "Does this look like the tone you'd expect?",
  "header": "Does this look right?",
  "options": [
    {"label": "Yes, looks good", "description": "Setup is complete."},
    {"label": "Not quite", "description": "Tell me what's off — I'll note it; it doesn't block anything."}
  ],
  "multiSelect": false
}])
```

Either answer completes setup.

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

Re-run `setup_checks.py --json` once more, then print a short block (at most 6 lines, plain words, in
`targetLanguage`) for the researcher's `role`. List only commands whose prerequisites passed in
that run, and leave out the rest instead of apologising for them. Always end with
`/academic-writer:intro`.

| Role | Candidate commands | Needs |
|---|---|---|
| Student | `/academic-writer:courses` (set up a term), `/academic-writer:lesson-notes`, `/academic-writer:dashboard`, `/academic-writer:write` | `courses` and `dashboard`: home folder; `lesson-notes`: `trove`; `write`: `gemini-key` |
| Researcher | `/academic-writer:init` (learn your style), `/academic-writer:research`, `/academic-writer:write`, `/academic-writer:proofread` | `write`, `proofread`: `gemini-key`; `research`: `trove` |
| Lecturer | `/academic-writer:courses`, `/academic-writer:dashboard`, then the researcher list | as above |

If nothing but `/academic-writer:intro` qualifies, say that and name the one missing step that
would unlock the most.

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

Tell them which command to type for their choice. Re-running `setup` or `init` later is always
safe: they update the profile, they never wipe it.
