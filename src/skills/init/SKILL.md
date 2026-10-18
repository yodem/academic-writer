---
name: init
description: "Full onboarding for Academic Writer: builds your researcher profile, learns your writing style from past articles, connects your research library, and offers Gemini. Asks before installing anything. Use when you want the plugin to learn your voice and sources, when redoing onboarding from scratch, or for a fast pass with --quick."
user-invocable: true
disable-model-invocation: true
allowed-tools: [Bash, Read, Write, Glob, Grep, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.4.0"}
---

# Academic Writer — Initialization Wizard

Personalized onboarding that creates your researcher profile, detects available integrations, analyzes your writing style, indexes your research sources, and optionally wires up Gemini as a prose writer.

You are talking to a humanities researcher who may have no technical background. Use plain words,
explain any technical term in one line, and match their language (Hebrew or English). **Never run
an install command until the researcher has said yes in an `AskUserQuestion` for that tool**, and
never ask for an API key in the chat (chat history is saved, so a key there could be read later).

**Preflight**: If you haven't run `/academic-writer:setup` yet, run that first — it checks every
tool, sets up your Gemini key, and shows a sample paragraph. For a guided tour of all commands, run
`/academic-writer:intro`.

## Quick Mode

Invoke as `/academic-writer:init --quick` for a fast onboarding path. Quick mode:

- **Runs**: Phase 0 (Preflight), Phase 1 (Integration Detection), Phase 2 (Researcher Profile,
  including the `author_key` step), Phase 3.5 (Gemini Onboarding).
- **Downgrades**: Style Analysis (Phase 2 Step 4) becomes narrative-only — no computational
  extraction, no Hebrew baseline fetch, no `extract-style-metrics.py`, and no Stage 1 voice
  fingerprint chain (voice store migration and author-picked exemplars). The researcher can still describe
  their style in free text if they wish, but nothing is computed.
- **Skips entirely**: Phase 3 (Research Sources) — `sources` is saved as `[]` and no `library.json` is written (Trove only).

Everywhere below, a phase or step marked "(skipped in --quick mode)" does not run when `--quick` is
passed; everything else runs identically. `setup` and `init` are both safe to re-run: `setup` is
the short guided check, `init` (full or `--quick`) builds the deeper profile and style analysis.

## The Phases

| Phase | What | Output | Quick mode |
|-------|------|--------|------------|
| 0. Preflight | Create folders, detect existing profile | Workspace ready | Runs |
| 1. Integrations | Auto-detect tools, let you choose | `tools` config | Runs |
| 2. Profile | Field, language, citation style, author_key | Core profile | Runs |
| 3.5. Gemini Onboarding | Optionally enable Gemini as prose writer | `gemini` config | Runs |
| 3. Style Analysis | Read past articles, build fingerprint | `styleFingerprint` + `articleStructure` | Narrative-only, no computation (skipped in --quick mode: computational chain + voice fingerprint chain) |
| 4. Sources | Index Trove library; choose the library route | `sources` array, `library.json` | Skipped entirely in --quick mode |

---

## Phase 0: Preflight

Run silently before saying anything:

```bash
mkdir -p past-articles .academic-helper .academic-helper/logs && cp -n "${CLAUDE_PLUGIN_ROOT}/thresholds.json" .academic-helper/ 2>/dev/null || true
```

Profile schema, file format, and legacy migration script: see `references/profile-schema.md`.

### Home and workspace type

Run `home.py show`, then `references/home-workspace.md`: inside home, ask "which course is this?" or "separate project", then `home.py register`; outside home or no home, a plain project.

### Python add-ons check

Style analysis needs a few Python add-ons. Check with `setup_checks.py --json` (the `python-addons` row) or `${CLAUDE_PLUGIN_ROOT}/skills/setup/references/python-deps.md`. If Python itself is missing, give the numbered steps from `${CLAUDE_PLUGIN_ROOT}/skills/setup/references/dependencies.md § Python 3` and note that style
analysis will be skipped until it is installed. If only add-ons are missing:

```python
AskUserQuestion(questions=[{
  "question": "To read your past articles I need a few free Python add-ons (missing: MISSING_LIST). May I install them now?",
  "header": "Python add-ons",
  "options": [
    {"label": "Install", "description": "One command, usually under a minute. Installs for your user account only."},
    {"label": "Skip for now", "description": "Style analysis from PDF/Word files will be skipped."}
  ],
  "multiSelect": false
}])
```

Only on "Install":

```bash
python3 -m pip install --user python-docx lxml pdfplumber pymupdf jsonschema
```

Re-run the check and report the result in one plain sentence. Failures: see
`${CLAUDE_PLUGIN_ROOT}/skills/setup/references/troubleshooting.md`.

Check for existing profile:

```bash
cat .academic-helper/profile.md 2>/dev/null && echo "EXISTS" || echo "NOT_FOUND"
```

**If EXISTS**: Use `AskUserQuestion`:

```python
AskUserQuestion(questions=[{
  "question": "You already have an Academic Writer profile. What would you like to do?",
  "header": "Existing profile detected",
  "options": [
    {
      "label": "Update my profile",
      "description": "Keep existing data, modify selected fields only.",
      "markdown": "```\nUpdate Mode\n───────────\n✓ Field of study preserved\n✓ Style fingerprint preserved\n✓ Sources preserved\n→ Re-run only the steps you choose\n```"
    },
    {
      "label": "Start fresh",
      "description": "Delete the current profile and rebuild from scratch.",
      "markdown": "```\nFresh Start\n───────────\n⚠ Existing profile will be replaced\n⚠ Style fingerprint will be cleared\n⚠ Sources will be cleared\n→ Walk through all 4 phases again\n```"
    }
  ],
  "multiSelect": false
}])
```

If **Update**, ask which phases to re-run (multiSelect: true) with options: "Integrations", "Profile (field/language/citation)", "Style Analysis", "Sources". Run only selected phases, then save.

Then greet the user:
> "Welcome to Academic Writer! I'll walk you through setup in a few steps.
>
> Your workspace folders are ready:
> - **`past-articles/`** — drop 5–10 of your published papers here (PDF or DOCX) so I can learn your writing style
> - `.academic-helper/` — your profile (auto-managed)
>
> Let's start."

---

## Phase 1: Integration Detection

Per-tool detection commands, AskUserQuestion blocks, and port-fallback logic: see `references/integration-setup.md`.

After running detection (parallel batch), store the tool selection as the `tools` object for Phase 4.

If the researcher selects a tool that was not found, explain what it is for in one sentence (from
`${CLAUDE_PLUGIN_ROOT}/skills/setup/references/dependencies.md`) and ask before installing:

```python
AskUserQuestion(questions=[{
  "question": "TOOL_NAME isn't installed yet. May I install it now?",
  "header": "Install TOOL_NAME?",
  "options": [
    {"label": "Install", "description": "I'll run one install command, then you sign in once in your browser."},
    {"label": "Skip", "description": "I'll leave it off; you can add it later by asking me to add or remove integrations."}
  ],
  "multiSelect": false
}])
```

Only on "Install", run the matching command: Trove on macOS or Linux,

```bash
curl -fsSL https://heytrove.ai/install.sh | sh
```

or NotebookLM when `npm` is available,

```bash
npm install -g notebooklm-mcp-cli
```

On Windows, or when npm is missing, give the researcher the numbered steps from
`dependencies.md` instead. Then ask them to sign in themselves by typing `! trove login` or
`! nlm login` (it opens their browser), re-run detection, and report the result plainly. A tool
that could not be installed is saved as disabled.

---

## Phase 2: Researcher Profile

### Step 1 of 5 — Full Name & Author Key

Check first whether a `name` field is already present in an existing profile (Phase 0). If not,
ask:

A name is free text, and `AskUserQuestion` needs 2 to 4 options, so ask in plain chat and end your turn:
"What is your full name, as you'd like it to appear on articles?" Take the next message as the answer.

Derive `author_key` as a kebab-case slug of the name: lowercase, trim, replace runs of
whitespace/punctuation with a single hyphen, strip leading/trailing hyphens. Example:
"Dana Levi" → `dana-levi`.

```bash
python3 -c "
import re, sys
name = sys.argv[1]
slug = re.sub(r'[^a-z0-9]+', '-', name.strip().lower()).strip('-')
print(slug)
" "FULL_NAME_HERE"
```

Confirm the derived slug with the user before saving — this key is stable across projects and used
to key cross-project Trove voice-profile lookups (see `${CLAUDE_PLUGIN_ROOT}/skills/voice/voice-sync.sh`), so it
should not change casually later:

```python
AskUserQuestion(questions=[{
  "question": "Your author key will be `DERIVED_SLUG`. This stays stable across all your projects and links your voice profile to your name. Use it, or provide a custom slug?",
  "header": "Confirm author key",
  "options": [
    {"label": "Use `DERIVED_SLUG`", "description": "Recommended — derived automatically from your name."},
    {"label": "I'll provide a custom slug", "description": "You'll type a kebab-case slug of your choice."}
  ],
  "multiSelect": false
}])
```

Store the final value as `author_key`. Store the full name as `name`.

---

### Step 2 of 5 — Field of Study

`AskUserQuestion` needs 2 to 4 options and always adds an **Other** choice for typing. Offer broad examples, then ask for
the specific field in plain chat if they pick one:

```python
AskUserQuestion(questions=[{
  "question": "What is your field of study and area of specialization? Choose the closest, or choose Other and type your own.",
  "header": "Step 2 of 5 — Field of Study",
  "options": [
    {"label": "Jewish studies", "description": "For example Talmud, Bible, Jewish history or thought."},
    {"label": "History", "description": "For example medieval or early modern history."},
    {"label": "Literature or language", "description": "For example Hebrew poetry, linguistics."},
    {"label": "Philosophy or religion", "description": "For example philosophy, theology, religious studies."}
  ],
  "multiSelect": false
}])
```

The more specific, the better; when they pick a broad choice, ask for the specific area in plain chat (for example
*Early Modern Jewish Philosophy*, *Talmudic Literature and Rabbinic Thought*, *Medieval Hebrew Poetry*).

Record the free-text answer as `fieldOfStudy`.

---

### Step 3 of 5 — Article Language

```python
AskUserQuestion(questions=[{
  "question": "What language will you write your articles in?",
  "header": "Step 3 of 5 — Article Language",
  "options": [
    {
      "label": "Hebrew",
      "description": "Right-to-left, David font, inline-parenthetical citations recommended.",
      "markdown": "```\nHebrew Mode\n───────────\nDirection:  RTL\nFont:       David 11pt\nCitations:  (מחבר, כותרת, עמ' N) in running text\nPurity:     Foreign terms must be transliterated\n```"
    },
    {
      "label": "English",
      "description": "Left-to-right, Times New Roman, Chicago/MLA/APA supported.",
      "markdown": "```\nEnglish Mode\n────────────\nDirection:  LTR\nFont:       Times New Roman 12pt\nCitations:  Chicago, MLA, or APA\n```"
    },
    {
      "label": "Other",
      "description": "You'll specify the language name.",
      "markdown": "```\nOther Language\n──────────────\n→ You'll type the language name\n→ RTL/LTR detected from language\n→ Citation style: your choice\n```"
    }
  ],
  "multiSelect": false
}])
```

Store as `targetLanguage`. If "Other", ask for the language name with a follow-up `AskUserQuestion`.

---

### Step 4 of 5 — Citation Style

```python
AskUserQuestion(questions=[{
  "question": "Which citation style do you use in your academic work?",
  "header": "Step 4 of 5 — Citation Style",
  "options": [
    {
      "label": "Inline Parenthetical (Recommended for Hebrew)",
      "description": "(Author, Title, Page) in running text — no footnotes required.",
      "markdown": "```\nInline Parenthetical\n────────────────────\nExample:\n  כפי שטוען לוי (לוי, משנת הנפש, עמ' 42), הרעיון\n  המרכזי הוא...\n\nWhen to use:\n  ✓ Hebrew articles\n  ✓ Short citation format\n  ✓ Dense citation density\n```"
    },
    {
      "label": "Chicago / Turabian",
      "description": "Footnotes with full bibliography — most common in English Humanities.",
      "markdown": "```\nChicago / Turabian\n──────────────────\nExample footnote:\n  ¹ Levy, The Soul's Teaching, 42.\n\nWhen to use:\n  ✓ English Humanities articles\n  ✓ History, Philosophy, Literature\n  ✓ Requires bibliography section\n```"
    },
    {
      "label": "MLA",
      "description": "Parenthetical with Works Cited page.",
      "markdown": "```\nMLA\n───\nExample: (Levy 42)\n\nWhen to use:\n  ✓ Literature and language studies\n  ✓ Humanities with Works Cited\n```"
    },
    {
      "label": "APA",
      "description": "(Author, Year) style — more common in social sciences.",
      "markdown": "```\nAPA\n───\nExample: (Levy, 2019, p. 42)\n\nWhen to use:\n  ✓ Social sciences\n  ✓ Psychology, Education, Linguistics\n```"
    }
  ],
  "multiSelect": false
}])
```

Map selection: Inline → `inline-parenthetical`, Chicago → `chicago`, MLA → `mla`, APA → `apa`.

---

### Step 4b of 5 — Abstract Languages

```python
AskUserQuestion(questions=[{
  "question": "Do your articles need abstracts? Some journals require dual-language abstracts.",
  "header": "Abstract Languages",
  "options": [
    {
      "label": "Primary language only",
      "description": "Abstract in the article's language only.",
      "markdown": "```\nSingle Abstract\n───────────────\nAbstract in: [targetLanguage]\nCommon for: Most journals\n```"
    },
    {
      "label": "Hebrew + English",
      "description": "Dual-language abstracts — common for Israeli journals.",
      "markdown": "```\nDual Abstract\n─────────────\nAbstracts in: Hebrew + English\nCommon for: Israeli journals,\n            academic theses\n```"
    },
    {
      "label": "No abstract needed",
      "description": "Skip abstract generation.",
      "markdown": "```\nNo Abstract\n───────────\nAbstracts will not be generated.\nYou can enable later with\n/academic-writer:init (Update)\n```"
    }
  ],
  "multiSelect": false
}])
```

Store as `abstractLanguages` array:
- Primary only → `["Hebrew"]` (or whatever `targetLanguage` is)
- Hebrew + English → `["Hebrew", "English"]`
- No abstract → `[]`

---

### Step 5 of 5 — Writing Style

(In `--quick` mode this step still runs, but only the narrative confirm/skip choice — the
computational extraction and Stage 1 voice fingerprint chain below are skipped in --quick mode.)

Ask (via AskUserQuestion) whether the researcher has added papers to `past-articles/` yet. If yes,
run the style analysis: **Step 1** computational extraction (`extract-style-metrics.py`, with an
optional Hebrew contrastive baseline from Trove), **Step 2** mechanical text extraction from
each PDF/DOCX for the qualitative pass, **Step 3** qualitative analysis across the dimensions the
script can't compute, then confirm the combined fingerprint with the researcher before saving. If
they skip, the profile saves without a style fingerprint. Full question text, extraction commands,
and the 25-dimension rubric: see `references/style-analysis.md`.

Then, unless in `--quick` mode, reuse `${CLAUDE_PLUGIN_DATA}/voice/` when its `author_key` matches
the current profile. If it does not match or no store exists, run `/academic-writer:voice` to migrate
`AUTHOR_VOICE.md` and fingerprint material, scan `past-articles/`, and let the author select 12–20
representative paragraphs. The store is shared across projects in the plugin data directory; the
project records only the key and voice version.

---

## Phase 3.5: Gemini Onboarding

Runs in both full and `--quick` modes. Ask the researcher whether to enable Gemini as the prose
writer for `/write`, `/edit`, and `/edit-section`. Claude remains the orchestrator and citation
auditor either way.

If they decline, skip the rest of this phase and note Gemini disabled in the summary. If they
accept: check whether `GOOGLE_API_KEY` is already set (never print it); if not, walk them through
getting a key at https://aistudio.google.com/apikey and storing it in the plugin settings
(`/plugin` → Installed → academic-writer → Configure → `google_api_key`, kept in the keychain) or a
shell profile, then restart and run the live check. Explain that article text is sent to Google
when Gemini is on. Store the result in the `## Gemini` block of `profile.md` (Phase 4). Steps and
wording: `references/gemini-onboarding.md`, which uses
`${CLAUDE_PLUGIN_ROOT}/skills/setup/references/gemini-key.md`.

---

## Phase 3: Research Sources

**(skipped entirely in --quick mode — `sources` is saved as `[]`)**

**If Trove is enabled:**

```python
AskUserQuestion(questions=[{
  "question": "Let's index your research library. Have you added sources to Trove yet?",
  "header": "Research sources",
  "options": [
    {
      "label": "Yes, index my sources now",
      "description": "I'll enrich and index everything in your Trove library.",
      "markdown": "```\nSource Indexing\n───────────────\n→ Lists items in your library\n   (scoped to the active shelf,\n    if you have set one)\n→ Saves minimal metadata to profile\n   (id, title, type only)\n```"
    },
    {
      "label": "Skip — I'll add sources later",
      "description": "Run /academic-writer:init again (choose Update → Sources) after adding items.",
      "markdown": "```\nSkip Sources\n────────────\n⚠ Articles won't have source metadata yet\n→ Add sources with: trove items add file.pdf\n→ Then re-run this step\n```"
    }
  ],
  "multiSelect": false
}])
```

If **"Yes"**: list the items, scoped to the active shelf when one is set:

```bash
# `trove shelf current` names this project's active shelf (set with `trove shelf use`) or says there is none.
# Scope the listing to it so a Jewish Studies write run doesn't present the
# researcher's entire library (engineering books included) as source options.
trove shelf current
trove items list --shelf "<the shelf named above>" --json   # when a shelf is active
trove items list --json                                       # when none is
```

Do **not** run `trove items enrich` over the library. It is a manual metadata *setter*
(`--title`, `--author`, `--toc`, ...), not an auto-extractor: a bare
`trove items enrich <ID>` exits with "At least one of --title, --author, --description,
--toc, --add-prompt, or --sample-question is required", and running it across every
item would overwrite metadata the researcher curated by hand.

If an item is missing a title or author, tell the researcher which items are thin and
offer to set the fields explicitly, one item at a time:

```bash
trove items enrich ITEM_ID --title "..." --author "..."
```

Build the sources array from the listing (id + title + type only — never raw JSON).

**If Trove is NOT enabled**: set sources to `[]`.

### Library route

Then ask which library this article reads its books from, with `AskUserQuestion` in plain words
(Trove, PageIndex or both; with both, which one answers), and save `.academic-helper/library.json`.
Trove is the default. Offer PageIndex as a route when a PageIndex command is configured or the
built-in helper is installed. Otherwise say in one sentence that PageIndex is an optional second
library and, only if the researcher wants it, make the separate offer in
`${CLAUDE_PLUGIN_ROOT}/skills/setup/references/pageindex.md` (what it installs, how big, what is
sent to Google; "Not now" is the default). Questions, detection and file format:
`references/integration-setup.md` (section "Library route"). Never install anything for this step.

---

## Phase 4: Save Profile + Register Workflows

Use the Write tool to save `.academic-helper/profile.md`, populating YAML frontmatter
(`name`, `author_key`, `fieldOfStudy`, `citationStyle`, `targetLanguage`, `abstractLanguages`,
`analyzedArticles`, `createdAt`, `updatedAt`) plus the `## Tools`, `## Output Format Preferences`,
`## Style Fingerprint`, `## Article Structure`, `## Sources`, and `## Gemini` JSON sections with the
values gathered in Phases 1–3.5. Exact file format and field-by-field template: see
`references/profile-schema.md#profile-file-format`.

**Home identity:** if `home.md` lacks `name` or `role`, run `home.py profile --name ...` (see `references/home-workspace.md`).

---

## Completion

```python
AskUserQuestion(questions=[{
  "question": "Setup is complete. What would you like to do next?",
  "header": "You're all set!",
  "options": [
    {
      "label": "Write my first article",
      "description": "Launch /academic-writer:write to start writing.",
      "markdown": "```\nWrite Article\n─────────────\n→ /academic-writer:write\n→ Conversational pipeline:\n   subject → sources → thesis\n   → outline → write → .docx\n```"
    },
    {
      "label": "Read the guide",
      "description": "Open the illustrated guide in your browser: /academic-writer:intro"
    },
    {
      "label": "Check system health",
      "description": "Run /academic-writer:health to verify everything is working."
    },
    {
      "label": "I'm done for now",
      "description": "Profile saved. Run /academic-writer:write anytime to start writing.",
      "markdown": "```\nProfile saved to:\n  .academic-helper/profile.md\n\nKey commands:\n  /academic-writer:write         ← write an article\n  /academic-writer:health       ← check everything\n  /academic-writer:intro        ← open the guide\n  "add Trove" ← just ask to change integrations\n```"
    }
  ],
  "multiSelect": false
}])
```

Show a summary table:

> | Setting | Value |
> |---------|-------|
> | Field | [field] |
> | Language | [language] |
> | Citation style | [style] |
> | Style fingerprint | ✓ Analyzed / — Skipped |
> | Sources indexed | [N] documents |
> | Tools enabled | [list] |
