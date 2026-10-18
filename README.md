# Academic Writer

Academic Writer is a plugin (an add-on) for Claude Code that helps humanities researchers write scholarly articles in Hebrew or English. You talk with Claude in plain language. The plugin takes you from a rough topic to a footnoted Word file: it reads the sources you choose, helps you settle a thesis and an outline, drafts in your own style, checks every citation against your sources, and then folds your Word comments back into the text.

See it in action on the **[Academic Writer site](https://yodem.github.io/academic-writer/)** (English and Hebrew). A fuller, step-by-step version of this page is the **[Academic Writer guide](https://yodem.github.io/academic-writer/guide/)**, which you can read online with no install. It also ships with the plugin as an offline guide: after installing, type `/academic-writer:intro` to open it in your browser.

---

## What you need

| What | Why | Cost |
|---|---|---|
| **Claude Code** | The program the plugin runs inside. Install steps are below. | A Claude plan that includes Claude Code (Pro, Max, Team or Enterprise; the free plan does not) |
| **A Gemini API key** | An API key is a long password that lets the plugin use Google's Gemini AI. Setup walks you through getting one from your own Google account. See [Your Gemini key](#your-gemini-key). | Free tier available |
| **Microsoft Word** (or a compatible program) | To read the finished `.docx` and mark it up with comments and tracked changes. LibreOffice opens the file too, but Word handles comments and tracked changes best. | Your existing copy |

Also useful:

- **Python 3**, a free program the plugin uses to read PDFs and build Word files. Some Macs and most Linux computers already have it; if yours does not, setup shows you, click by click, how to install it from python.org. Setup also asks before installing the small add-ons it needs.
- **5 to 10 of your published articles** (PDF or Word), so the plugin can learn how you write.
- **Your source texts** as PDFs or Word files. The optional [Trove](https://heytrove.ai) library (an online bookshelf for your sources; [install Trove](https://heytrove.ai/install), [docs](https://docs.heytrove.ai/)) lets the plugin search and quote them page by page.

---

## Install

You install once. About 15 minutes if you have never used Claude Code. Each step says what you should see.

**Step A. Get Claude Code and sign in** (skip if you already use it).

1. You need a Claude plan that includes Claude Code (Pro, Max, Team or Enterprise). Subscribe or sign in at [claude.ai](https://claude.ai).
2. Open the **Terminal** app (a window where you type commands instead of clicking). Mac: press Cmd+Space, type `Terminal`, press Enter. Windows: Start menu, type `PowerShell`, press Enter. Linux: Ctrl+Alt+T on most systems.
3. Paste this line and press Enter (Windows PowerShell: `irm https://claude.ai/install.ps1 | iex`). It shows no progress for a minute; that is normal.

   ```bash
   curl -fsSL https://claude.ai/install.sh | bash
   ```

4. Make a folder for your research (for example `Academic` inside Documents). In Terminal type `cd ` (with a space), drag that folder into the window, press Enter, type `claude` and press Enter.
5. The first time, your web browser opens so you can sign in. Sign in, then return to the Terminal window. You now see Claude Code's prompt box (where you type to Claude).

If Terminal says `command not found: claude`, close it and open a new Terminal window, then try step 4 again. Prefer an app? Anthropic also offers a Claude desktop app with Claude Code; the website steps for it are at [yodem.github.io/academic-writer](https://yodem.github.io/academic-writer/#install).

**Step B. Add the plugin.** In the prompt box, type these two lines, one at a time, pressing Enter after each:

```text
/plugin marketplace add yodem/academic-writer
/plugin install academic-writer@yodem
```

The first line tells Claude Code where to find the plugin (a *marketplace* is a list of plugins; this one is called `yodem`). The second installs it. Each prints a short confirmation. If the first one says it cannot find the marketplace, check the line is typed exactly as above and try again; if it still fails, copy the message and paste it to Claude. (A line starting with `/` is typed in Claude Code's prompt box, not in Terminal.)

**Step C. Restart.** Type `/exit` and press Enter, then type `claude` again in the same folder, so the new commands appear.

**Step D. Check it.** Type `/plugin`, open the **Installed** tab with the arrow keys, and look for **academic-writer**. If it is missing, repeat Step B. Then go to *First steps* below.

If you prefer to add the plugin from Terminal instead of the prompt box, the same two steps are:

```bash
claude plugin marketplace add yodem/academic-writer
claude plugin install academic-writer@yodem
```

---

## First steps

Run these inside Claude Code, started in your research folder (not your main home folder).

1. **`/academic-writer:intro`** opens the full guide in your web browser.
2. **`/academic-writer:setup`** is a short guided conversation, one question at a time, about ten minutes. It asks your field, article language and citation style; checks the tools the plugin needs and **asks your permission before installing anything**; walks you through getting and safely storing a free Gemini key, then tests it; and writes one short sample paragraph. After you store the key, setup asks you to quit Claude Code completely, open it again in the same folder, type `/academic-writer:setup` and choose **Check my Gemini key**; your answers are saved.
3. **`/academic-writer:init`** (recommended) builds your full profile. First copy 5 to 10 of your published articles (PDF or Word) into the `past-articles` folder inside your research folder (setup created it). Init reads them, shows you what it learned about your style so you can correct it, and helps you connect your source library.
4. **`/academic-writer:write`** starts your first article.

Running setup or init again later is safe: they update your profile and never erase it.

---

## How writing an article works

`/academic-writer:write` has a conversation part, where you make every decision about the argument, and a drafting part the plugin runs on its own.

1. **Your voice.** Before anything else, write checks that your voice profile (the examples and writing habits drafts should follow) exists. If it does not, it asks whether to build it first with `/academic-writer:voice` (about 10 minutes, using 3 or more of your past articles) or to write in a neutral scholarly voice for now.
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
| `/academic-writer:ingest` | Upload a single article or chapter to your source library, keeping its printed page numbers and adding a citation guide. |
| `/academic-writer:ingest-book` | Upload a whole book (multi-volume, scanned or EPUB) with a clickable table of contents that jumps to the right page. |
| `/academic-writer:ideate` | Turn a vague topic into a sharp research question; saves a research brief that write reads. |
| `/academic-writer:ocr` | Turn a scanned PDF or photographed page (or a folder of them) into plain text, with Gemini, Claude, Codex or local Tesseract, your choice. |
| `/academic-writer:library-eval` | Compare Trove and PageIndex on your own article: you judge anonymous A and B answers, then see which library was which. |
| `/academic-writer:voice` | Build or update your voice profile: exemplar paragraphs you choose and your writing habits. |
| `/academic-writer:health` | Check that everything is ready, with a plain-language fix for anything missing. |
| `/academic-writer:help` | A short list of every command and the three steps to get started. |

A few more things the plugin can do have no command of their own. Ask for them in plain words:

- **Learn from new papers or your corrections**: "I added new papers to past-articles, update my voice."
- **Follow-on materials**: "Make a conference talk outline (or a journal abstract, or a chapter proposal) from this article."
- **Change your field of study**: "Change my field in my profile to ..."
- **Connect or disconnect Trove or NotebookLM**: "Turn on Trove in my profile."

---

## Choosing a library (optional)

Your books are read from **Trove** unless you choose otherwise. Nothing here changes how the plugin works for you today, and you can skip this whole section.

**What the choices are.** Each article project can read its books from Trove (the default), from **PageIndex**, or from both, where one library answers and the other is tested quietly in the background without ever changing, slowing or failing your result. PageIndex is a second library that keeps a short outline of every book, with a few lines on each section, so Claude can go straight to the likely page. You choose per article, and you can change your mind with `/academic-writer:update-tools`.

**Two ways to get PageIndex.** Setup, init and update-tools offer both, in plain words, and ask before doing anything:

1. **The plugin's own helper.** The plugin sets up a small helper in its own data folder (not in your system). The basic helper is about 100 MB and needs Python 3.9 or newer; a larger one (about 500 MB, Python 3.10 or newer and, on a Mac, the `pango` library) can also prepare a book that has no table of contents. You can remove it again. The steps are below.
2. **Your own PageIndex.** If you already run PageIndex yourself, for example on a server, you type its command into the plugin's `pageindex_command` setting (`/plugin`, then **Installed**, then **academic-writer**, then **Configure**). A command you set yourself always wins over the built-in helper.

**Preparing your books.** A book must be prepared once before PageIndex can read it. When you add a book with `/academic-writer:ingest` or `/academic-writer:ingest-book`, the plugin writes it to Trove first, checks it, and then offers to prepare it for PageIndex too, with the same table of contents and the same page numbers, so a citation means the same page in both. You can also add a reading to a book you already have, and prepare the books already in Trove (a "backfill") in one go. For each preparation the plugin tells you in advance how much text would be sent to Google and asks you; the free choice sends nothing (see Privacy).

**What is measured.** Every lookup and every citation check is logged on your computer in `.academic-helper/retrieval.jsonl`, with the time it took, an estimate of how many tokens of text it returned, and the citation checker's verdict. `aw library report` turns that into a comparison on your real articles: speed, failures, how often the two libraries return the same page, the citation checker's pass rate, tokens, and the cost of any preparation and evaluation runs. Token figures from the log are estimates, not a bill.

**Judge it yourself: a blind evaluation.** `/academic-writer:library-eval` picks claims from one of your drafts, has a separate Claude (or Codex) look up the supporting pages in each library, and shows you the two answers side by side as "A" and "B" in random order on a private page that works offline, in Hebrew and English. You mark each pair better A, better B, same or neither, with a note. Only after you finish does the plugin reveal which library was which, with win rates, a confidence range, time, cost and how often each found the page the citation checker had confirmed. With too few pairs it tells you it is only a first look.

**Install steps for the built-in helper.** Run these in Claude Code, started in your research folder, and answer the questions it asks:

1. Type `/academic-writer:update-tools` (or `/academic-writer:setup`, the first time) and say you want PageIndex. Among the choices it offers, pick **Set it up on this computer**.
2. Read the plan it shows (which size, how much disk space, where it goes) and say yes if you want it. Nothing is installed before that.
3. If it says your Python is too old or `pango` is missing for the larger helper, you can accept the basic helper or follow the short steps it gives for your system. It never installs Python for you.
4. Type `/academic-writer:health` to confirm it is ready. It shows which helper is in use.

Full details, commands, the report explained line by line and the known limits are in [docs/library-routes.md](docs/library-routes.md).

---

## Your Gemini key

**What it is.** Gemini is Google's AI model. In this version, the plugin's own drafting tool (`aw`) sends every drafting, evidence-extraction (used by write and research), synthesis, editing, proofreading, OCR and voice-analysis step to Gemini, while Claude runs the conversation and checks every citation.

**Is it optional?** Setup lets you answer "Not now", and nothing is then sent to Google. Planning and review still work, but the steps listed above need the key, so in practice you need one to write, research, proofread or OCR. Setup tells you this when you choose.

**Cost.** Google's free tier is enough for normal use, and creating a key normally needs no credit card. Get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey); it starts with `AIza`.

**Where to keep it.** Never paste the key into the Claude chat: the conversation is saved, so a key there could be read later. Use one of these:

1. **Plugin settings (recommended).** In Claude Code, type `/plugin`, open **Installed**, choose **academic-writer**, then **Configure**, and paste the key into **google_api_key**. Claude Code keeps it in your computer's keychain (on Linux, a protected credentials file), not in a plain settings file. At the start of each session the plugin passes it on to its tools, but only in a research folder that already has a profile (`.academic-helper/profile.md`), which setup creates.
2. **An environment variable.** Set `GOOGLE_API_KEY` in your shell profile (macOS/Linux) or as a user environment variable (Windows). This also works for other tools on your computer. `/academic-writer:setup` shows the exact steps for your system.

Either way, the key is picked up only when a **new** Claude Code session starts. The plugin reads nothing else: a `.academic-helper/secrets.json` file is not used.

---

## Privacy

- **Anthropic (Claude).** Your conversation with Claude, and the text Claude reads to help you (your drafts, the source passages it checks), go to Anthropic, as with any use of Claude Code.
- **Google (Gemini).** With a Gemini key, the text being drafted, edited, proofread or summarised, the source passages it relies on, and any scanned pages you ask it to read are sent to Google. On Google's free tier, Google may use what you send to improve its products. Check Google's current terms, and consider a paid key for unpublished work you consider sensitive.
- **Google (Gemini) and PageIndex.** If you prepare books for PageIndex and choose **Gemini summaries**, the text of each section of the book is sent to Google, with your Gemini key, so Gemini can write the short outline. The plugin tells you how much text, and asks first, every time. The free option (`--summaries hints`, offered alongside) sends nothing: it reuses the hints already written for Trove. The same Google terms as above apply. Nothing is ever sent to PageIndex Cloud: the plugin has no code for it and needs no PageIndex account.
- **Anthropic (or OpenAI) and the blind evaluation.** `/academic-writer:library-eval` runs a separate Claude Code (or Codex, if you choose it) to find supporting pages. The claims from your draft and the page text it reads go to Anthropic (or OpenAI), on your own plan, after you have seen an estimate and said yes. The quiet background test of a second library uses no AI model at all.
- **Trove (optional).** Only the sources you choose to upload are stored there. If you use Trove, your voice profile is also synced there so it follows you between computers.
- **Jev (advanced, off by default).** Only if you enter the optional `jev_api_key` setting, the question and context at a few decision points are also sent to the Jev service. In this version its answers are only logged and never change your results. Most users should leave it empty.
- **Your keys.** Saved through the plugin settings, the key is kept in your keychain. The plugin never prints it or writes it into your research folder.

**What stays on your computer, and where:**

| Where | What |
|---|---|
| `.academic-helper/` in your research folder | This project's working files: your profile (`profile.md`), the source list, the outline, drafts, verified evidence, a log of each run, a log of library lookups (`retrieval.jsonl`) and, if you run an evaluation, its files (`library-eval/`), including the sealed key that says which side was which. |
| `past-articles/`, `ocr-output/` and your `.docx` files, in your research folder | Your published articles, text from scanned pages, and the finished articles. |
| The plugin's data folder, `~/.claude/plugins/data/` (the folder whose name starts with `academic-writer`) | Your voice data, shared by all your projects, a small log of plugin mistakes you flagged during revise, and, only if you installed it, the built-in PageIndex helper and the books prepared for it (the `pageindex` folder). |

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
- **Write asks about your voice profile.** Choose "Build my voice first" and run `/academic-writer:voice`, or continue without it and build it later.
- **The Word file is not created, or a "missing Python package" message.** Run `/academic-writer:setup`; it offers to install the add-ons. To do it yourself: `python3 -m pip install --user python-docx lxml pdfplumber pymupdf jsonschema`.
- **Proofreading a Word file fails.** The proofread command converts `.docx` files with `pandoc`, a free document converter, which setup does not install. Install it from [pandoc.org/installing.html](https://pandoc.org/installing.html), or proofread a Markdown copy.
- **The PageIndex helper will not install, or `aw library status` says PageIndex is not reachable.** Run `/academic-writer:health`; it names the cause (Python older than 3.10 for the larger helper, a missing `pango` library on a Mac, no network, or an old command in `pageindex_command`). The basic helper works with Python 3.9. Trove keeps working either way.
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
(cd src/cli && npm ci)                  # once: dependencies of the aw tool (CLI tests and the end-to-end test need them)
npm run test:cli                        # tests of the aw command-line tool
npm run typecheck:cli                   # strict TypeScript check on src/cli/
python3 -m pytest -q tests              # full test suite
python3 tests/test_plugin_structure.py  # structural integrity tests
bash scripts/check-no-private-refs.sh   # privacy gate
python3 scripts/version-sync.py --check # version agrees in every registered location
npm run clean                           # wipe plugins/ and src/hooks/dist/
npm run hooks:install                   # once: pre-commit version check and a pre-push guard (set ALE_ALLOW_RUNS=<run-id> to push an ALE run's merge; git push --no-verify skips it)
```

- **Privacy gate.** The repository is public. `scripts/check-no-private-refs.sh` fails if a tracked file carries a personal identifier (home paths, private emails, internal host names) or if internal dev-state paths are tracked. It runs in CI and in pytest.
- **Generated guide blocks.** The command table and version stamp in `src/guide/index.html` and the command list in `src/skills/help/SKILL.md` are generated from skill frontmatter by `scripts/gen-guide.py`, which the build runs. Edit the text around the `guide:` markers, never inside them; `python3 scripts/gen-guide.py --check` reports drift.
- **CI.** The CI and release workflows install the dependencies of `src/hooks` and `src/cli`, then run the version, privacy and test gates, `npm run test:cli` and both typechecks. They do not install the larger PageIndex helper, so the tests use fakes for it.
- **PageIndex helper.** `src/scripts/pageindex/` holds `pilib`, the helper the plugin installs on request (pinned version and hashes in `PINNED.json`; third-party licences in `THIRD_PARTY_NOTICES.md`). Its tests run on Python 3.9 or newer.
- **Thresholds.** Numeric limits live only in `src/thresholds.json`.
- **Versions and releases.** Bump with `python3 scripts/version-sync.py --bump patch|minor|major` in the same commit that writes the CHANGELOG section. The Release workflow is started by hand; it verifies and tags what is committed and does not bump anything.

Project conventions for Claude Code sessions are in [CLAUDE.md](CLAUDE.md).

---

## License

MIT. Source and issues: [github.com/yodem/academic-writer](https://github.com/yodem/academic-writer).
