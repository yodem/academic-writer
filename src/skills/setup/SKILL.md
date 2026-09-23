---
name: setup
description: "Friendly, guided first-run setup wizard for a non-engineer: one question at a time, gets your Gemini API key working with a live test, checks your Python tools, and shows you a sample paragraph before you're done. Use on first install, or anytime you want a fast guided re-check of your setup. Use when this skill's command or workflow is needed."
user-invocable: true
disable-model-invocation: true
allowed-tools: [Bash, Read, Write, Glob, Grep, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.1.0"}
---

# Academic Writer — Setup Wizard

A short, guided conversation that gets you ready to write. One question at a time — no forms, no jargon left unexplained. By the end you'll have a working Gemini connection (tested live, not just saved), your Python tools checked, and one sample paragraph to look at before we call it done.

Want the deeper onboarding instead — analyzing your past articles for your writing voice, indexing your research library? See "Cross-reference" at the end; both commands are safe to run any time, including again later.

## Known gap

Hooks in this repo ship as built output only (`plugins/academic-writer/hooks/dist/*.mjs`) — there is no editable hook source for an automatic "nudge me when `.academic-helper/` is missing" SessionStart check. (There IS a SessionStart hook already wired — `session-dashboard` — but it shows a dashboard, it does not detect/create `.academic-helper/` or point new users at setup.) So today, onboarding relies on this SKILL.md's own text, plus the preflight lines added to `write` and `init`, rather than an automatic hook nudge. See `references/troubleshooting.md` for more.

---

## Step 0 — Preflight

Run silently before saying anything:

```bash
mkdir -p past-articles .academic-helper .academic-helper/logs && cp -n "${CLAUDE_PLUGIN_ROOT}/thresholds.json" .academic-helper/ 2>/dev/null || true
```

```bash
cat .academic-helper/profile.md 2>/dev/null && echo "EXISTS" || echo "NOT_FOUND"
```

If a profile already exists, say so briefly and note it's safe to re-run setup — it'll update, not wipe, existing fields. Continue either way.

---

## Step 1 — Warm welcome

> "Hi! I'm going to help you get Academic Writer ready to use. This will take a few minutes — I'll ask you one short question at a time, nothing to configure by hand. No technical background needed."

---

## Step 2 — The basics (1-2 questions only)

Keep this minimal — this is not the full profile from `/academic-writer:init`, just enough to write a sample paragraph later.

```python
AskUserQuestion(questions=[{
  "question": "What's your field of study?",
  "header": "Field of study",
  "options": []
}])
```

Store as `fieldOfStudy`.

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

Map: Inline → `inline-parenthetical`, Chicago → `chicago`, MLA → `mla`, APA → `apa`. Store as `citationStyle`.

---

## Step 3 — Gemini API key

### 3a. Explain in plain language

> "Academic Writer can use Google's Gemini AI to help draft your paragraphs, with Claude always checking the citations and quality. To use Gemini, you need an **API key** — think of it as a password that lets this tool talk to Gemini on your behalf, tied to your own free Google account. This is optional: you can skip it and just use Claude."

```python
AskUserQuestion(questions=[{
  "question": "Would you like to set up Gemini now?",
  "header": "Optional — Gemini",
  "options": [
    {"label": "Yes, set it up", "description": "I'll walk you through getting a free key and test it live."},
    {"label": "No, Claude only", "description": "Skip this — you can add it later by running setup again."}
  ],
  "multiSelect": false
}])
```

If "No, Claude only": skip to Step 4, note Gemini disabled in the closing summary.

### 3b. Check for an existing key

The `aw` CLI (`plugins/academic-writer/bin/aw`) reads `GOOGLE_API_KEY` from its environment. A
SessionStart hook exports the plugin's `google_api_key` option from the OS keychain, or the user can
export the key in their shell. Check the current environment:

```bash
if [ -n "$GOOGLE_API_KEY" ]; then echo "Found GOOGLE_API_KEY in environment."; else echo "NO_KEY in environment; configure the plugin option or export it in your shell, then start a new session."; fi
```

If a key was found, continue to 3d. Otherwise configure the plugin option or shell variable and
start a new session so the SessionStart hook can export the value.

### 3c. Get and store a key

> "Here's how to get a free key:
> 1. Open https://aistudio.google.com/apikey in your browser
> 2. Sign in with a Google account
> 3. Click 'Create API key' and copy it (it starts with `AIza...`)"

```python
AskUserQuestion(questions=[{
  "question": "Where should I keep your key?",
  "header": "Key storage",
  "options": [
    {
      "label": "Plugin configuration (recommended)",
      "description": "Stored securely by Claude Code itself (OS keychain, or a protected credentials file) — never plaintext in a settings file.",
      "markdown": "```\nclaude plugin install academic-writer --scope project \\\n  --config google_api_key=\"AIza...\"\n\n# Already installed? Reconfigure any time via the\n# /plugin manager (Manage plugins -> academic-writer)\n# or:\nclaude plugin config academic-writer \\\n  --config google_api_key=\"AIza...\"\n```"
    },
    {
      "label": "Environment variable",
      "description": "Set GOOGLE_API_KEY in your shell profile — works across all your projects, but is not stored as securely as the plugin option above.",
      "markdown": "```\nexport GOOGLE_API_KEY=\"AIza...\"\n# add this line to ~/.zshrc or ~/.bashrc\n```"
    },
  ],
  "multiSelect": false
}])
```

- **Plugin configuration (recommended)**: print the `claude plugin install`/`claude plugin config`
  command above for the user to run in their own terminal (or point them at the `/plugin` manager's
  configuration dialog), then ask them to confirm they've done it. Claude Code cannot open its own
  plugin-configuration dialog or run its own CLI from inside this conversation — same reason the
  environment-variable path below needs the user to act outside the chat. Once set this way, the key
  is exported as `GOOGLE_API_KEY` by the plugin's SessionStart hook at the start of a new session.
- **Environment variable**: print the export line above for the user to run in their own terminal, then ask them to confirm they've done it and reopened their session — Claude Code cannot set their shell environment from inside this conversation.
The key is never written to a project file. The plugin option is stored in the OS keychain; the
SessionStart hook exports it for `aw`. A shell-level `GOOGLE_API_KEY` also works.

### 3d. Confirm the CLI is available

The `aw` CLI needs the key only when it makes a Gemini request. Confirm the current configuration:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" models check
```

- If the hook or shell provides `GOOGLE_API_KEY`, note that Gemini is configured; otherwise ask the user to configure one or continue without Gemini. See `references/troubleshooting.md` for errors from actual CLI runs.

---

## Step 4 — Python tools check

Academic Writer uses four Python packages for reading Word docs and PDFs: `python-docx`, `lxml`, `pdfplumber`, and `pymupdf`. Full check script, install commands, and the "no requirements.txt" note: see `references/python-deps.md`.

Run the check from that reference file, then:

```python
AskUserQuestion(questions=[{
  "question": "Some Python tools Academic Writer needs aren't installed yet. Install them now?",
  "header": "Python tools",
  "options": [
    {"label": "Yes, install them", "description": "Runs one pip3 install command — takes a few seconds."},
    {"label": "Skip for now", "description": "You'll be prompted again the first time a feature needs them."}
  ],
  "multiSelect": false
}])
```

(Only ask this if something was actually missing — if the check reports everything present, skip straight to Step 5 with a one-line confirmation.)

---

## Step 5 — Optional: CandleKeep + NotebookLM

Reuses the same detection approach as `/academic-writer:init` Phase 1 (see `${CLAUDE_PLUGIN_ROOT}/skills/init/references/integration-setup.md`):

```python
# PARALLEL — launch both at once
Bash(command="command -v ck >/dev/null 2>&1 && echo 'DETECTED' || echo 'NOT_DETECTED'")
Bash(command="command -v nlm >/dev/null 2>&1 && nlm login --check 2>/dev/null && echo 'DETECTED' || echo 'NOT_DETECTED'")
```

If either is detected, briefly offer to enable it (mirroring init's Phase 1 options). **If neither is available or configured, do not block or error** — just print:

> "CandleKeep (research library) and NotebookLM (source Q&A) aren't set up yet — that's fine, they're optional. You can add them anytime by running `/academic-writer:setup` or `/academic-writer:init` again."

---

## Step 6 — Sample paragraph checkpoint

This is a lightweight proof-of-life, not a full pipeline run.

Ask for (or pick, if they'd rather skip) a trivial micro-topic:

```python
AskUserQuestion(questions=[{
  "question": "Let's generate one short sample paragraph to make sure everything's working. Give me a small topic (or I'll pick a generic one).",
  "header": "Sample paragraph",
  "options": [
    {"label": "I'll give a topic", "description": "Type a short topic, e.g. \"the printing press\"."},
    {"label": "Pick one for me", "description": "I'll use a generic placeholder topic."}
  ],
  "multiSelect": false
}])
```

Generate a 2-4 sentence paragraph on that topic, in `fieldOfStudy`'s general register, using whichever writer is configured:
Write a 2-4 sentence paragraph yourself (Claude) directly in the conversation. The proof-of-life here checks the conversation workflow; Gemini is exercised when an `aw` command runs.

Show the paragraph, then:

```python
AskUserQuestion(questions=[{
  "question": "Does this look right — the kind of tone and quality you'd expect?",
  "header": "Does this look right?",
  "options": [
    {"label": "Yes, looks good", "description": "Setup is complete."},
    {"label": "Not quite", "description": "Tell me what's off — this won't block setup, just noting it for later."}
  ],
  "multiSelect": false
}])
```

Either answer completes setup — this is a checkpoint, not a gate. If "Not quite," note their feedback in the closing summary as something to revisit (e.g. via `/academic-writer:init`'s fuller style analysis).

---

## Step 7 — Save profile + closing summary

Write or update `.academic-helper/profile.md` with the fields gathered above (`fieldOfStudy`, `citationStyle`, `gemini` block), preserving any existing fields from a prior profile (name, targetLanguage, style fingerprint, sources, etc. — do not clear them). Use the same schema as `/academic-writer:init` (see `${CLAUDE_PLUGIN_ROOT}/skills/init/references/profile-schema.md`) so both commands stay interoperable.

Show a short summary:

> | Setting | Value |
> |---------|-------|
> | Field | [fieldOfStudy] |
> | Citation style | [citationStyle] |
> | Gemini | ✓ Enabled & tested / — Not enabled |
> | Python tools | ✓ Ready / ⚠ Some missing (see references/python-deps.md) |
> | CandleKeep / NotebookLM | [enabled tools, or "not set up — optional"] |
> | Sample paragraph | ✓ Looked good / noted feedback |

> "You're set up. Run `/academic-writer:write` to start your first real article.
>
> **Cross-reference**: Want the fuller onboarding — style analysis from your past articles, indexing your research sources? Run `/academic-writer:init` any time. Re-running either `setup` or `init` later is always safe — they update your profile, they don't wipe it."
