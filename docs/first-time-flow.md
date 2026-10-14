# Academic Writer: your first session

A step-by-step walkthrough for a researcher using Academic Writer for the first time, from install to a first Word draft. The same steps, with more detail on each, are in the offline guide: type `/academic-writer:intro` in Claude Code.

---

## Before you start

- **Claude Code** installed ([claude.com/claude-code](https://claude.com/claude-code)).
- **A Google account**, for a free Gemini API key. Setup shows you how to get it.
- **Microsoft Word** or a compatible program.
- Optional but recommended: **5 to 10 of your published papers** (PDF or Word), so the plugin can learn your style, and **your source texts** as PDFs.

Plan on about ten minutes for setup, a little more for init, and 30 to 60 minutes for a first article, depending on length.

---

## 1. Install (once)

In Claude Code, type each line and press Enter:

```text
/plugin marketplace add yodem/academic-writer
/plugin install academic-writer@yodem
```

Quit Claude Code and open it again **inside your research folder**. The plugin keeps one profile per folder, so always start Claude Code from the same folder for the same project.

---

## 2. Setup: `/academic-writer:setup`

A short conversation, one question at a time.

1. **Your field, article language and citation style.** Styles offered: Inline Parenthetical (common for Hebrew), Chicago / Turabian, MLA and APA. Setup saves a starter profile to `.academic-helper/profile.md` right away.
2. **A check of the tools the plugin needs.** You see a table of what is found and what is missing: Python 3, its add-ons, the Hebrew spelling checker hspell (Hebrew writers only), and the optional Trove and NotebookLM. For each missing piece, setup says what it is for and **asks before installing it**. Python itself and Homebrew you install yourself; setup gives numbered steps for your system. Skipping something never blocks setup.
3. **Gemini.** Setup explains what Gemini is, that your article text is sent to Google when it is on, and why the key must not be pasted into the chat. If you say yes, it walks you through getting a free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and storing it, either in the plugin settings (`/plugin` → **Installed** → **academic-writer** → **Configure** → **google_api_key**, kept in your keychain) or as an environment variable.
4. **Restart.** Quit Claude Code, open it again in the same folder, run `/academic-writer:setup` again and choose **Check my Gemini key**. Setup tests the key without sending any article text.
5. **A sample paragraph**, so you can see the tone, and a summary table of what is ready.

Gemini is technically optional, but in this version drafting, evidence extraction, proofreading and OCR all run on Gemini. Without a key, those steps stop with a "missing Google API key" message.

---

## 3. Your style and sources: `/academic-writer:init`

Put your published papers into the `past-articles` folder that setup created, then run `/academic-writer:init`.

- It asks your full name (used as the key for your voice profile), confirms field, language and citation style, and which languages you want abstracts in.
- It reads your papers and builds a **style fingerprint**: sentence length and structure, vocabulary and register, how you build paragraphs, your tone and stance, preferred transitions, citation density, and how you open and close. **You review it and correct anything** before it is saved.
- It sets up your **voice profile** (a set of 12 to 20 paragraphs from your papers that you pick as examples of your writing), or reuses the one you already have. The voice profile is shared by all your projects.
- If you use Trove, it helps you add and list your sources.

`/academic-writer:init --quick` does a faster version: no computed style analysis, no voice setup, no sources.

Before your first article, `/academic-writer:write` checks that your voice profile exists. If it does not, it asks you to run `/academic-writer:voice`.

---

## 4. Your first article: `/academic-writer:write`

**The conversation (you decide):**

1. Describe the topic and choose the language.
2. Pick the sources for this article.
3. State your thesis in your own words. If you used `/academic-writer:ideate` first, its research brief is the starting point.
4. The plugin extracts **verified evidence**: passages whose quotations match the source word for word. You can mark passages that must appear.
5. Shape the outline together. You approve each section's claim; drafting does not start until every claim is approved.

**The drafting (the plugin works, you wait):**

6. Gemini drafts each section in dependency order, in your style, with the introduction and conclusion last. Automatic checks reject any draft that cites a source not on your list, quotes text not in the verified evidence, or breaks your style rules or length limits.
7. Claude checks every paragraph's citations. Failed paragraphs are rewritten; any that still fail after the allowed attempts are marked `[NEEDS REVIEW]` and named in the final report.
8. A synthesis pass adds transitions between paragraphs. It never rewrites a paragraph and never changes a citation.
9. You get a `.docx` with Word footnotes. Claude tells you where it is.

**Then:**

10. Open it in Word, add comments or tracked changes, save, and run `/academic-writer:revise`. It groups your comments, asks you to confirm each group, updates the article and makes a new Word file.

---

## After your first article

| Command | When to use it |
|---|---|
| `/academic-writer:write` | Start another article. |
| `/academic-writer:revise` | Fold your Word comments back into the article. |
| `/academic-writer:edit` | Larger revisions: several passages, tone, structure, evidence. |
| `/academic-writer:edit-section` | A quick fix to one section. |
| `/academic-writer:proofread` | A final typo, language and editorial pass before submission. |
| `/academic-writer:review` | A six-dimension scorecard of the finished article. |
| `/academic-writer:research` | Check a claim or explore a topic in your sources. |
| `/academic-writer:health` | Check that everything still works, with a fix for anything missing. |
| `/academic-writer:help` | The short command list. |

To change your field or turn Trove or NotebookLM on or off, ask in plain words ("change my field to ...", "turn on Trove"); Claude updates the profile.

---

## What you can rely on

1. **Citations come from your sources.** Drafts may quote only verified passages, code checks reject unknown sources and unverified quotes, and Claude audits every paragraph. Anything still unresolved is marked for you, never passed silently.
2. **Your thesis is yours.** The plugin records it exactly as you wrote it and does not draft until you approve the outline.
3. **Your original files are not overwritten.** Proofreading writes a separate corrected copy; revise makes a new Word file.
4. **You know what leaves your computer.** Conversation and the text Claude reads go to Anthropic; with Gemini on, drafted text and the source passages it uses go to Google. Details: the Privacy section of the [README](../README.md#privacy).
