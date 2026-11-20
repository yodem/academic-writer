# Academic Writer — Help

Show the user the text below, lightly formatted for the chat. Do not run any commands, do not read
their files, and do not add technical detail they did not ask for. The reader is a humanities
researcher, not a programmer. If they ask a follow-up question, answer it in the same plain style,
and point to `/academic-writer:setup intro` for the full illustrated guide.

---

## What Academic Writer does

Academic Writer helps you write a scholarly article in your own voice, grounded only in sources you
choose. You talk it through with Claude: the topic, the sources, the thesis and the outline. Then the
plugin drafts the article, checks every footnote against your sources, and gives you a Word file
(`.docx`). You mark it up in Word, and it folds your comments back in.

It works in Hebrew and in English.

## Start here: three steps

1. **Read the guide (optional, 5 minutes):** `/academic-writer:setup intro` opens a full guide in your
   web browser that explains each step.
2. **Set up (about 10 minutes, once):** open Claude Code in your research folder, then type
   `/academic-writer:setup`. It asks a few short questions, checks the small tools it needs and asks
   before installing anything, and walks you through getting a free Gemini key (a kind of password
   that lets the plugin use Google's AI). After you store the key it asks you to quit Claude Code and
   open it again in the same folder; your answers are saved.
3. **Write:** `/academic-writer:write` starts your first article. Claude asks you one question at a
   time.

Want the plugin to learn your personal writing style from your past articles first? Copy 5 to 10 of
your published articles (PDF or Word) into the `past-articles` folder inside your research folder,
then run `/academic-writer:setup init` after setup.

## All commands

This table is generated from the plugin itself, so it is always complete.

<!-- help:commands:start -->
| Command | What it does |
|---|---|
| `/academic-writer:setup intro` | Open the full illustrated guide in the browser, then a five-line summary |
| `/academic-writer:setup` | First-run setup for researchers with no technical background: checks each tool, asks before installing, walks through a free Gemini key, ends with a sample paragraph (the default; by name only) |
| `/academic-writer:setup init` | Full onboarding: researcher profile, writing style from past articles, research library, Gemini; --quick for a fast pass (by name only) |
| `/academic-writer:write new` | Write a new article from scratch: topic, sources, evidence, thesis, outline, drafting, citation audit, Word file |
| `/academic-writer:write revise` | Read Word comments and tracked changes on a generated draft and update the article: <file.docx> [--editor [original.docx]] |
| `/academic-writer:write edit` | Revise a drafted article across several passages: tone, structure, argument order or evidence |
| `/academic-writer:write edit-section` | Quick revision of one section or passage of an existing article |
| `/academic-writer:write proofread` | Proofread a finished article for typos, wrong words and grammar, with a corrected copy and a report |
| `/academic-writer:write review` | Score a completed article on six dimensions before submission |
| `/academic-writer:write research` | Check a claim or ask what the author's sources say, with verified quotations only |
| `/academic-writer:write ideate` | Brainstorm: turn a vague topic into a sharp research question and save a research brief |
| `/academic-writer:write present` | Turn a finished article into a talk outline, abstract with keywords, chapter proposal or study materials |
| `/academic-writer:write watch` | Show what Academic Writer is doing right now: current step, progress and anything rejected |
| `/academic-writer:setup voice` | Build or update the voice profile: import old voice files, choose exemplar paragraphs, derive writing rules, sync to Trove (by name only) |
| `/academic-writer:setup health` | Check that Academic Writer is ready: profile, tools, connections, Gemini key and past articles, with a plain fix for anything missing |
| `/academic-writer:setup help` | Short overview of Academic Writer and its commands, with the three first steps for a new user |
| `/academic-writer:courses dashboard` | Open the local course dashboard: what is due next, whether readings are ready, what is new, a week agenda and a page per course |
| `/academic-writer:courses lesson-notes` | Turn a course recording's NotebookLM transcript into a structured Hebrew Trove lesson note; --pending resumes queued transcripts |
| `/academic-writer:courses term` | Set up a term from a schedule, validate course resources, sync the LMS (Moodle), run the daily scan and its steps such as extract-handoff, trove-notes and calendar-sync (the default) |
| `/academic-writer:library ingest` | Upload one article, paper or chapter to Trove with printed page numbers, a hinted table of contents and a citation guide |
| `/academic-writer:library ingest-book` | Upload a whole book (100+ pages, multi-volume, EPUB or scanned PDF) with a nested navigable table of contents, or repair a flat one |
| `/academic-writer:library kotar-fetch` | Download the cited pages of a Kotar book as one PDF in printed-page order, for the author's own study |
| `/academic-writer:library library-eval` | Compare Trove and PageIndex on the author's own article, judging anonymised A/B pairs |
| `/academic-writer:library ocr` | Turn a scanned PDF, photo or screenshot (or a folder of them) into plain text: <file or folder> |
| `/academic-writer:setup learn` | Refresh the voice store from newly added past articles and from the author's own rewrites of drafts |
| `/academic-writer:setup update-field` | Change the research field in the profile, keeping every other setting |
| `/academic-writer:setup update-tools` | Turn Trove or NotebookLM on or off, change the library route (Trove, PageIndex or both), set up PageIndex, without redoing the full setup |
<!-- help:commands:end -->

## The usual cycle

1. `/academic-writer:write` gives you a Word file.
2. You open it in Word and add comments or tracked changes wherever you want something changed.
3. `/academic-writer:write revise` reads your comments, asks you to confirm, and updates the article.
4. `/academic-writer:write proofread` does a final typo and language pass before you submit.

## If something goes wrong

- Run `/academic-writer:setup health`. It checks everything and says, in plain words, what to fix.
- Your Gemini key stopped working? Run `/academic-writer:setup` again. It is safe to repeat and
  never erases your profile.
- The "Troubleshooting" section of `/academic-writer:setup intro` covers the most common problems.

## Your files and privacy, in one paragraph

Your drafts and settings stay in your research folder (in a hidden folder named `.academic-helper`).
Your writing-style data lives in the plugin's own data folder on your computer. The text you work on
is sent to Anthropic (Claude) and, if you set up a Gemini key, to Google, only to do the writing
and checking you asked for. When you save your key through the plugin's settings (setup does this),
it is stored in your computer's secure keychain, not in a plain file.
