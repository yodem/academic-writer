# Academic Writer

Academic Writer is a plugin (an add-on) for Claude Code that helps humanities researchers write scholarly articles in Hebrew or English. You talk with Claude in plain language. The plugin takes you from a rough topic to a footnoted Word file: it reads the sources you choose, helps you settle a thesis and an outline, drafts in your own style, checks every citation against your sources, and then folds your Word comments back into the text.

A fuller, step-by-step version of this page ships with the plugin as an offline guide. After installing, type `/academic-writer:intro` to open it in your browser (it works offline).

---

## What you need

| What | Why | Cost |
|---|---|---|
| **Claude Code** | The program the plugin runs inside. Download it from [claude.com/claude-code](https://claude.com/claude-code). | Included in a Claude plan that has Claude Code |
| **A Gemini API key** | An API key is a long password that lets the plugin use Google's Gemini AI. Setup walks you through getting one from your own Google account. See [Your Gemini key](#your-gemini-key). | Free tier available |
| **Microsoft Word** (or a compatible program) | To read the finished `.docx` and mark it up with comments and tracked changes. LibreOffice opens the file too, but Word handles comments and tracked changes best. | Your existing copy |

Also useful:

- **Python 3**, a free program the plugin uses to read PDFs and build Word files. Macs and most Linux computers already have it. Setup checks for it and asks before installing the small add-ons it needs.
- **5 to 10 of your published articles** (PDF or Word), so the plugin can learn how you write.
- **Your source texts** as PDFs or Word files. The optional CandleKeep library (an online bookshelf for your sources) lets the plugin search and quote them page by page.

---

## Install

You install once. Open Claude Code and type these two lines, pressing Enter after each:

```text
/plugin marketplace add yodem/academic-writer
/plugin install academic-writer@yodem
```

The first line tells Claude Code where to find the plugin (a *marketplace* is a list of plugins; this one is called `yodem`). The second installs it. Then quit Claude Code and open it again so the new commands appear.

If you prefer a regular terminal window, the same two steps are:

```bash
claude plugin marketplace add yodem/academic-writer
claude plugin install academic-writer@yodem
```

**How to open a terminal:** on a Mac, press Cmd+Space, type `Terminal`, press Enter. On Windows, open the Start menu and type `Terminal` or `PowerShell`. On most Linux systems, press Ctrl+Alt+T. Then move to your research folder (type `cd `, drag the folder into the window, press Enter) and type `claude`. Everything the plugin creates for a project stays in that folder.

---

## First steps

Run these inside Claude Code, started in your research folder.

1. **`/academic-writer:intro`** opens the full guide in your web browser.
2. **`/academic-writer:setup`** is a short guided conversation, one question at a time, about ten minutes. It asks your field, article language and citation style; checks the tools the plugin needs and **asks your permission before installing anything**; walks you through getting and safely storing a free Gemini key, then tests it; and writes one short sample paragraph. After you store the key, setup asks you to restart Claude Code once and choose **Check my Gemini key**.
3. **`/academic-writer:init`** (recommended) builds your full profile. Put 5 to 10 of your published articles in the `past-articles` folder that setup created first. Init reads them, shows you what it learned about your style so you can correct it, and helps you connect your source library.
4. **`/academic-writer:write`** starts your first article.

Running setup or init again later is safe: they update your profile and never erase it.

---

## How writing an article works

`/academic-writer:write` has a conversation part, where you make every decision about the argument, and a drafting part the plugin runs on its own.

1. **Your voice.** Before anything else, write checks that your voice profile (the examples and writing habits drafts should follow) exists. If it does not, it stops and asks you to run `/academic-writer:voice`.
2. **Topic and language.** Say what you want to write about and in which language.
3. **Sources.** You pick the sources for this article from the ones you made available.
4. **Your thesis.** You state the thesis in your own words; the plugin records it exactly as you wrote it.
5. **Verified evidence.** The plugin reads the chosen sources and keeps only passages whose quotations match the source word for word. These are the only passages the draft may quote or cite.
6. **Outline.** Together you shape the sections. You approve each section's claim; nothing is drafted until every claim is approved.
7. **Drafting.** Gemini drafts the article from the approved outline, section by section, in your style, with the introduction and conclusion written last. Automatic checks reject any draft that cites a source not on your list, quotes text that is not in the verified passages, or breaks your style rules.
8. **Citation check.** Claude then checks every paragraph's citations against your sources. A paragraph that fails is rewritten. If it still fails after the allowed number of attempts, it is marked `[NEEDS REVIEW]` and named in the final report so you know exactly what to check.
9. **Word file.** You get a `.docx` with real Word footnotes. Claude tells you where it saved it.
10. **Your comments.** Open it in Word, add comments or tracked changes wherever you want something changed, save and close.
11. **Revise.** Run `/academic-writer:revise`. It reads your comments and tracked changes, groups them, asks you to confirm each group, updates the text and makes a new Word file. With your agreement, it also learns from your rewrites so later drafts sound more like you. Repeat steps 10 and 11 as often as you like.

Before you submit, run `/academic-writer:proofread` for a typo, language and editorial pass (the original is never changed; you get a corrected copy, a report and an editorial memo), and `/academic-writer:review` for a scorecard of the article's structure, argument and citations.

---

## Commands

Type any of these in Claude Code. You can also describe what you want in your own words ("proofread my article"), and Claude picks the right command for most requests. Setup, init and voice run only when you type them, because they change your settings.

| Command | What it does |
|---|---|
| `/academic-writer:intro` | Open the full guide in your web browser. |
| `/academic-writer:setup` | First-run setup: tools, Gemini key, a sample paragraph. Asks before installing anything. |
| `/academic-writer:init` | Full onboarding: your profile, your writing style from past articles, your source library. |
| `/academic-writer:write` | Write a new article, step by step, ending with a Word file. |
| `/academic-writer:revise` | Read your Word comments and tracked changes and update the article. |
| `/academic-writer:edit` | Revise an article you already drafted: several passages, tone, structure, argument order or evidence. |
| `/academic-writer:edit-section` | Quick revision of one section: rewrite, expand, shorten, fix citations or style. |
| `/academic-writer:proofread` | Proofread a finished article (Markdown or Word): a corrected copy, a report and an editorial memo. |
| `/academic-writer:review` | Score a finished article on six dimensions and show concrete findings. |
| `/academic-writer:research` | Investigate a topic or check a claim against your sources; only word-for-word verified quotations come back. |
| `/academic-writer:ideate` | Turn a vague topic into a sharp research question; saves a research brief that write reads. |
| `/academic-writer:ocr` | Turn a scanned PDF or photographed page (or a folder of them) into plain text. |
| `/academic-writer:voice` | Build or update your voice profile: exemplar paragraphs you choose and your writing habits. |
| `/academic-writer:health` | Check that everything is ready, with a plain-language fix for anything missing. |
| `/academic-writer:help` | A short list of every command and the three steps to get started. |

A few more things the plugin can do have no command of their own. Ask for them in plain words:

- **Learn from new papers or your corrections**: "I added new papers to past-articles, update my voice."
- **Follow-on materials**: "Make a conference talk outline (or a journal abstract, or a chapter proposal) from this article."
- **Change your field of study**: "Change my field in my profile to ..."
- **Connect or disconnect CandleKeep or NotebookLM**: "Turn on CandleKeep in my profile."

---

## Your Gemini key

**What it is.** Gemini is Google's AI model. In this version, the plugin's own drafting tool (`aw`) sends every drafting, evidence-extraction (used by write and research), synthesis, editing, proofreading, OCR and voice-analysis step to Gemini, while Claude runs the conversation and checks every citation.

**Is it optional?** Setup lets you answer "No, Claude only", and nothing is then sent to Google. But the steps listed above stop with a "missing Google API key" error without a key, so in practice you need one to write, research, proofread or OCR.

**Cost.** Google's free tier is enough for normal use, and creating a key normally needs no credit card. Get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey); it starts with `AIza`.

**Where to keep it.** Never paste the key into the Claude chat: the conversation is saved, so a key there could be read later. Use one of these:

1. **Plugin settings (recommended).** In Claude Code, type `/plugin`, open **Installed**, choose **academic-writer**, then **Configure**, and paste the key into **google_api_key**. Claude Code keeps it in your computer's keychain (on Linux, a protected credentials file), not in a plain settings file. At the start of each session the plugin passes it on to its tools, but only in a research folder that already has a profile (`.academic-helper/profile.md`), which setup creates.
2. **An environment variable.** Set `GOOGLE_API_KEY` in your shell profile (macOS/Linux) or as a user environment variable (Windows). This also works for other tools on your computer. `/academic-writer:setup` shows the exact steps for your system.

Either way, the key is picked up only when a **new** Claude Code session starts. The plugin reads nothing else: a `.academic-helper/secrets.json` file is not used.

---

## Privacy

- **Anthropic (Claude).** Your conversation with Claude, and the text Claude reads to help you (your drafts, the source passages it checks), go to Anthropic, as with any use of Claude Code.
- **Google (Gemini).** With a Gemini key, the text being drafted, edited, proofread or summarised, the source passages it relies on, and any scanned pages you ask it to read are sent to Google. On Google's free tier, Google may use what you send to improve its products. Check Google's current terms, and consider a paid key for unpublished work you consider sensitive.
- **CandleKeep (optional).** Only the sources you choose to upload are stored there. If you use CandleKeep, your voice profile is also synced there so it follows you between computers.
- **Jev (advanced, off by default).** Only if you enter the optional `jev_api_key` setting, the question and context at a few decision points are also sent to the Jev service. In this version its answers are only logged and never change your results. Most users should leave it empty.
- **Your keys.** Saved through the plugin settings, the key is kept in your keychain. The plugin never prints it or writes it into your research folder.

**What stays on your computer, and where:**

| Where | What |
|---|---|
| `.academic-helper/` in your research folder | This project's working files: your profile (`profile.md`), the source list, the outline, drafts, verified evidence and a log of each run. |
| `past-articles/`, `ocr-output/` and your `.docx` files, in your research folder | Your published articles, text from scanned pages, and the finished articles. |
| The plugin's data folder, `~/.claude/plugins/data/` (the folder whose name starts with `academic-writer`) | Your voice data, shared by all your projects, and a small log of plugin mistakes you flagged during revise. |

Folders whose names start with a dot are hidden by default. On a Mac, press Cmd+Shift+. in Finder; on Windows, choose View, then Show, then Hidden items in File Explorer.

**Uninstalling deletes the plugin's data folder, including your voice data**, unless you keep it:

```bash
claude plugin uninstall academic-writer@yodem --keep-data
```

Your research folders, drafts and Word files are never touched by uninstalling.

---

## Troubleshooting

Start with **`/academic-writer:health`**. It checks your profile, key, tools and sources, and tells you in plain words what to fix. Its report contains no keys, so you can share it when asking for help.

- **The `/academic-writer:` commands do not appear.** Quit Claude Code completely and open it again. Then type `/plugin` and check that academic-writer is listed and enabled. If not, repeat the two install lines.
- **"missing Google API key" or "API key not valid".** Run `/academic-writer:setup` again and choose to check the Gemini key. After saving a key, start a new Claude Code session in your research folder.
- **"No profile found".** Make sure you started Claude Code inside your research folder. In a new folder, run `/academic-writer:setup` first.
- **Write stops and asks for your voice profile.** Run `/academic-writer:voice`, then run write again.
- **The Word file is not created, or a "missing Python package" message.** Run `/academic-writer:setup`; it offers to install the add-ons. To do it yourself: `python3 -m pip install --user python-docx lxml pdfplumber pymupdf jsonschema`.
- **Proofreading a Word file fails.** The proofread command converts `.docx` files with `pandoc`, a free document converter, which setup does not install. Install it from [pandoc.org/installing.html](https://pandoc.org/installing.html), or proofread a Markdown copy.
- **Hebrew looks reversed in the Claude Code window.** That is only the display; the Word file is laid out right to left.

Still stuck? Open an issue at [github.com/yodem/academic-writer/issues](https://github.com/yodem/academic-writer/issues) and include the output of `/academic-writer:health`.

---

## Updating

In a terminal (or through `/plugin` in Claude Code), then restart Claude Code:

```bash
claude plugin marketplace update yodem
claude plugin update academic-writer@yodem
```

Refreshing the marketplace alone does not update an installed plugin; run both lines. Updating keeps your profile, drafts and voice data. See [CHANGELOG.md](CHANGELOG.md) for what changed.

---

## For contributors

Source lives in `src/`. Never edit `plugins/` directly: `npm run build` generates it from `src/` and `manifests/`, and the output is committed.

```bash
npm run build                           # assemble plugins/academic-writer/ from src/
npm run build:hooks                     # rebuild only the TypeScript hooks
npm run typecheck                       # strict TypeScript check on src/hooks/
python3 -m pytest -q tests              # full test suite
python3 tests/test_plugin_structure.py  # structural integrity tests
bash scripts/check-no-private-refs.sh   # privacy gate
python3 scripts/version-sync.py --check # version agrees in every registered location
npm run clean                           # wipe plugins/ and src/hooks/dist/
```

- **Privacy gate.** The repository is public. `scripts/check-no-private-refs.sh` fails if a tracked file carries a personal identifier (home paths, private emails, internal host names) or if internal dev-state paths are tracked. It runs in CI and in pytest.
- **Generated guide blocks.** The command table and version stamp in `src/guide/index.html` and the command list in `src/skills/help/SKILL.md` are generated from skill frontmatter by `scripts/gen-guide.py`, which the build runs. Edit the text around the `guide:` markers, never inside them; `python3 scripts/gen-guide.py --check` reports drift.
- **Thresholds.** Numeric limits live only in `src/thresholds.json`.
- **Versions and releases.** Bump with `python3 scripts/version-sync.py --bump patch|minor|major` in the same commit that writes the CHANGELOG section. The Release workflow is started by hand; it verifies and tags what is committed and does not bump anything.

Project conventions for Claude Code sessions are in [CLAUDE.md](CLAUDE.md).

---

## License

MIT. Source and issues: [github.com/yodem/academic-writer](https://github.com/yodem/academic-writer).
