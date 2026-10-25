# Changelog

All notable changes to the academic-writer plugin are documented here.

## [Unreleased]

## [0.20.3] — 2026-10-25

### Fixed
- **`drive-reorg` moves keep the Drive file.** rclone treated a destination under `--drive-root-folder-id` as another remote and copied the file, then deleted the original (it went to the Drive trash, and the copy got a new file id). Moves now pass `--drive-server-side-across-configs`, so they are server-side and the file keeps its id. The post-move id check caught the first such move and stopped the run.

## [0.20.2] — 2026-10-25

### Fixed
- **A lesson transcript is named a transcript.** A `.txt` transcript registered as a recording was named "הקלטת שיעור …"; it is now "תמלול שיעור …".

## [0.20.1] — 2026-10-25

### Fixed
- **Lesson transcripts and recordings get names you can read.** A transcript or recording whose own name is machine-made (`wispr-2026-10-23-1201-24673bab.txt`, `zoom-…`, `20261012 120422.m4a`) is now named by its lesson and date, for example `תמלול שיעור 02 · 23.10.2026.txt` or `הקלטת שיעור 01 · 12.10.2026.m4a`, and filed in its lesson folder; a transcript with no lesson goes to `שיעורים/תמלולים`. A recording with a real title keeps it.
- **A generic title no longer hides what a file is.** When a source is titled only "שיעור 1", "סילבוס", "מבוא" or "פתיחה", its Drive name keeps the fuller original file name ("תפיסות יסוד בספרות הנבואה שיעור 1 תשפז"), not just the generic word.

## [0.20.0] — 2026-10-25

### Added
- **Drive files get Chicago-citation names in kind folders.** Course sources are filed by kind: `00 כללי`, `שיעורים/שיעור NN`, `מטלות/מטלה N`, `קריאות/<citation>`, and `לא ממוין` for anything unclassified. Uploads go to their kind folder under a Chicago-style display name, and the NotebookLM source takes the same name. Media keep their lesson titles.
- **`courses.py drive-reorg`.** `--course SLUG` or `--all` prints the move manifest; `--apply` moves the Drive files and renames the matching NotebookLM sources. Every file left at a course's root, and the files inside old `שיעור N` / `מטלה N` folders, go into their kind folder. Safety:
  - Files move by Drive file id, never by name, and never over another file: the destination is checked first, the move skips an existing file, and the file id is checked at the destination afterwards.
  - Nothing is deleted. Emptied old folders stay; remove them by hand.
  - Every step is written to a journal (`logs/drive-reorg-<time>-<course>.jsonl`) before it runs. After a crash, `drive-reorg --resume <journal> --apply` finishes it, and a new `--apply` refuses while a journal is unfinished.
  - The reorg holds the course lock for the whole run, and refuses to start while the nightly job runs (`--force` overrides).
- **Lesson folders keep their numbers.** A lesson that already has a folder keeps it; a lesson imported later takes the next number. A recording is uploaded after its lesson key is fixed, so two recordings from the same minute get two folders.
- **Uploads are confirmed.** An upload never replaces a file at its path, and is checked by MD5 on Drive. A retried upload reuses the copy already there instead of adding a second one.
- **The nightly run fails when the Lemida watch leaves a gap** (`courses.py lemida-coverage-check`). The watch writes `logs/lemida-coverage-<date>.json` for its run. The check fails the run when the report is missing or from another run, when an active course has no Lemida id (a chore is added) or was not visited, when a new assignment was not handled, or when a notification on `notifications.php` was not opened. `COURSES_ONLY` limits the check to the named courses.
- **Writer runs show on the dashboard Writing tab without `workspaces.json`.** The dashboard finds workspace folders up to two levels under the home folder that hold a `profile.md` or `runs/`, and merges them with the registry. `aw activity start|step|end` record each run; the five writing skills (write, edit, edit-section, proofread, revise) call them.

### Changed
- **Finished terms and courses are skipped by the course loops.** A term or course with `status: "finished"` is left out of the default term lookup and of every loop over all courses (map, validate, wispr scan, Lemida `--all`, drive-reorg `--all`, toc_audit `--all`). Naming one course still works. `toc_audit --include-finished --course SLUG` audits one finished course.

## [0.19.2] — 2026-10-20

### Fixed
- **Readings show on the overview.** A reading due before a lesson now appears in the "מבחנים ודדליינים" column, marked "קריאה:", in date order with the deadlines. Before, it was only mentioned in the opening sentence, and there without its course; the sentence now names the course too.

## [0.19.1] — 2026-10-20

### Fixed
- **Task links on the dashboard open the right Lemida page.** They pointed at `mod/view.php?id=…`, a page Moodle does not have; they now name the activity type (`mod/assign/view.php?id=…` for an assignment, `mod/forum/…` for a forum). The same fix applies to the course bookmarks. When the type is not known, no link is shown instead of a broken one.
- **A task follows its Lemida deadline.** When a lecturer moves a deadline, the next watch updates the task on the dashboard; before, the task kept the first deadline it was given.

### Added
- **Readings the lecturer announces become reading tasks.** The nightly Lemida watch now reads your Lemida notifications first, so it sees every announcement and forum post, including posts in threads it had already seen. A post that says what to read for the next lesson becomes a reading task, due when that lesson starts, with a link to the post. You close it with "I read".

## [0.19.0] — 2026-10-20

### Changed
- **Scanned pages go to the reader that measured best, page by page.** In a test on 67 scanned pages (Hebrew and English, clean to 75 dpi, one and two columns, the vowel-marked Bible), Claude Opus read as accurately as the best Gemini at every scan quality from 100 dpi up. So `aw ocr` now has Claude read the pages. Gemini, when you have set a Google key, reads only the pages Claude refuses (the vowel-marked Bible), the pages where Claude writes a summary instead of the text, and scans under 100 dpi. Every page reports which reader read it, and so does the saved text.
- **A course's required readings get the most accurate reader.** The primary and secondary sources of a course, and anything you will quote, are read by Claude, with Gemini covering the pages Claude cannot. For a source you added on your own (`--source additional`), the free readers on your computer go first: if Surya (it needs an NVIDIA graphics card and a running Surya server) and Tesseract agree on 98% of the letters, their text is kept. That saves your Claude plan, at a cost of a few more wrong letters per page (0.3% against Opus's 0.0% in the test).
- Without a Google key, a page Claude refuses comes back blank and marked "blocked", as before; it is never filled in from a weaker reader.
- The Gemini reader is now `gemini-3.8-flash`, one page per call. The old `gemini-2.5-flash`, six pages per call, dropped passages.
- `aw ocr --engine gemini|claude|local` still sends every page to one reader.


## [0.18.4] — 2026-10-19

### Changed
- **Nothing is OCR'd or text-extracted on its own any more.** New course files, fetched readings and Lemida routing only download to the right place (the course's sources folder, Drive and NotebookLM). On the dashboard's course page you tick the files you want as text and press "חילוץ טקסט", choosing how: automatic, Claude, Gemini or Tesseract. The next nightly run does only what you chose.
- **Extraction without a model where possible.** Word files are read with Python; PDFs that already contain text are read page by page with PyMuPDF, keeping the printed page numbers and reading two-column Hebrew pages right column first. A page that comes out garbled, and every scan, goes to Claude. Gemini and Tesseract run only when you pick them. Claude is now the default reader in the ocr and ingest skills.
- The nightly's own Claude sessions and their helpers run on Sonnet (`CLAUDE_CODE_SUBAGENT_MODEL`).

### Fixed
- When Anna's Archive asks for a browser check, the reading is marked "blocked" with a plain note and a reminder, instead of an error about missing JSON.

## [0.18.3] — 2026-10-18

### Changed
- **Setup is step by step for researchers who are new to Claude Code.** The install guide (README, site, illustrated guide) now starts from getting Claude Code and signing in, and says what you should see after each step. Setup explains each tool in one sentence and gives numbered, Mac-first steps for anything you install yourself: Python, Homebrew, Hebrew spelling, Trove (sign-up and sign-in), NotebookLM, and the free Gemini key. It explains what typing a line that starts with `!` means, how to open Terminal, and how to restart Claude Code without losing your answers. It ends with concrete next steps for your role.

### Fixed
- The field-of-study question in setup and init had no choices to pick from; it now offers examples and a free answer.
- The sample paragraph at the end of setup did not show before its question; it is now part of the question.
- The Trove step said it installs with Homebrew; it uses Trove's own installer, and now says so.

## [0.18.2] — 2026-10-18

### Fixed
- **The live activity pane opens again.** Its command was registered as `/watch`, a name the `/academic-writer:watch` skill already owns; Claude Code refused it and the refusal stopped the whole start-up step, so the pane never opened. The pane command is now `/activity`, and a refused name no longer stops the pane from opening.

## [0.18.1] — 2026-10-18

### Added
- **Choose when the nightly run happens, or turn it off.** `courses.py nightly set --time HH:MM` schedules it (on macOS it updates your existing LaunchAgent in place, with a backup); `nightly off` keeps it on demand only; `nightly run-now` runs it now; `nightly status` shows the time and the last run. Elsewhere `set` prints a cron line.
- **Trove links on the dashboard.** Each course page links to its Trove book next to NotebookLM (`https://heytrove.ai/library/<book>?page=<n>`); the per-course Chrome bookmark folders include Trove pages too.
- The site says up front that this is a Claude Code plugin and lists the recent changes, generated from this changelog.

### Fixed
- **The home-folder migration finishes the move.** `home_migrate.py --data-dir` records the home folder (before, `home.py show` reported none); it rewrites old registry paths inside the copied course files, lesson notes and notes files, in the helper scripts beside the nightly script (sync, lock) and in the LaunchAgent's log paths (text and binary plists), with a backup of each file; a path after a shell default (`${VAR:-$HOME/...}`) is matched too. Logs and finished queue records are left as they were. Running it again changes nothing.
- Setup and health say to restart Claude Code after updating the plugin: a running session keeps the old skills until then.
- Follow-up: course files still store absolute paths, so a later move needs the migration again.

## [0.18.0] — 2026-10-18

### Added
- **One home folder with typed workspaces.** `home.md` holds the profile and semester once; a project, course or teaching folder keeps only what differs, and the two are merged on read (Python and the hooks agree). The course registry moves under the home folder; a user who has not migrated keeps working from the old `~/.academic-writer/courses` location. `home_migrate.py` previews first, backs up, never overwrites and deletes nothing, and can be run again safely. A workspace whose folder was moved shows as "not found" and stays in the list.
- **Agent activity record.** `aw` and a SubagentStop hook append one line per step to `runs/<id>/activity.jsonl` (no model call); a torn last line is skipped. `aw activity show --latest` prints the current step in one line, and `/academic-writer:watch` plus an optional Claude Code pane show it live. New `thresholds.json` key `activity.activeRunMaxAgeMinutes`.
- **"The Margin" brand file** (`src/brand/DESIGN.md`) with a generator for the dashboard and site tokens and a check that fails the build on any colour, font, size or radius that is not in the file.
- **Redesigned dashboard** with seven pages (overview, timeline, courses, course, writing, setup, about), light and dark, Hebrew right to left, no horizontal page scroll at 360 px; exams and course colours; a Setup page driven by `setup_checks.py`; an About page generated from `features.json` (new `tested` field). A Playwright suite covers it in Chromium and Firefox.
- Setup checks (`setup_checks.py --json`) used by health, setup, init and the dashboard; a dashboard and activity section on the site.
- **Setup asks for the home folder and who you are** (student, lecturer or researcher) and writes them to `home.md`; it checks Python first and explains in plain words what it is for. It ends with a short "what you can do now" list. Hebrew spelling is required only for writing in Hebrew; Trove, Gemini, NotebookLM and PageIndex are optional.
- The Writing page opens the finished Word file (only a file recorded for that run, inside a registered workspace) and shows each section as passed or rejected with the reason.

### Fixed
- The activity record holds steps and verdicts only: no article text, quotes or reviewer feedback text.
- Skills pass the plugin data folder to `home.py`, `setup_checks.py` and the dashboard (`--data-dir`), because the Bash tool does not receive it.
- A malformed row in `workspaces.json` no longer stops the dashboard's live updates, and a corrupt `workspaces.json` is never overwritten.
- The auditor context hook read only `subagent_type`; Claude Code sends `agent_type`, so the injection never fired. It reads both now.

## [0.17.1] — 2026-10-18

### Fixed
- **Wispr Flow lecture import (`courses.py wispr-scan`) is now private by construction.** It opens Wispr's database read-only in place and never copies it; if the database cannot be opened it imports nothing and leaves nothing behind (the old fallback copied the whole database, work meetings included, to a temporary folder). For a recording that matches no course it reads only the id and times; a test watches every column the importer reads.
- **No phantom or misattributed lessons.** A failed import no longer makes the next same-day recording an "alternate" of a lesson that does not exist, and a pending lesson is resumed only by the recording that owns it (recorded when the lesson is created), never by a matching file hash.
- **Times across the daylight-saving change** are compared in UTC, so a lecture that spans the switch still matches its class slot. `--since` keeps an explicit time offset.

## [0.17.0] — 2026-10-16

### Added
- **Course dashboard** (`/academic-writer:dashboard`, `courses.py dashboard`): one local page (127.0.0.1 only, a random key per run, cookie after the first load, Host and Origin checked on every write) that replaces a stack of course tabs. An overview of every course reads like a table of contents (next task, due date, and marks drawn on the text: a red circle for a missing source, a green tick for ready, a highlighter for a reading, a caret for a new lesson) under one sentence saying what needs you; a week agenda from the class slots (semester-aware); and a page per course with its tasks, the sources of each task (downloaded / Trove / NotebookLM) and its lessons. Light and dark themes, Hebrew right to left, keyboard navigation and a command palette (⌘K). Live updates over Server-Sent Events from a registry file watch. "I submitted" goes through `tasks.py` with a 5-second undo (new `courses.py task unsubmit`); "fetch selected" queues a job in `queue/fetch/`, which the nightly run processes.
- **Sources per task.** Each course now keeps its tasks (`tasks[]` in the course file, id = the Lemida chore id), and references and sources can be linked to a task. New `courses.py`/`refs.py task list|show|link|submit|unsubmit`; `task show` gives each source's status (downloaded, in Trove, in NotebookLM, Anna's Archive). `courses.py migrate-tasks [--dry-run]` links existing course specs to their tasks (backing up every file it changes) and folds a spec task into the Lemida task it duplicates. All additions to the files are additive.
- **One fetch chain for a reading:** `refs.py fetch --course X --ref KEY` runs Anna's Archive (skipped and recorded as not checked when no key is set), the BIU library lookup, then the download, Kotar or print-only step, logging each step on the reference. `refs.py fetch-queue` runs the jobs the dashboard queues; the nightly script calls it.
- **Lectures from Wispr Flow.** `courses.py wispr-scan` reads Wispr Flow's local database (read-only), matches each finished recording to a course by its class slot and the semester, and hands the transcript and summary to the lesson pipeline. A lesson that already exists is never replaced (the new transcript is kept beside it); a recording that matches no course is never opened (only its id and time are listed for you). The nightly script runs it before `lesson-notes --pending`.
- **Course-book runbook decisions** in `courses`: a book lock (one writer per Trove course book, held through writes, ToC repair and audit; a lock older than 3 hours goes to the user); ToC repair per book (snapshot, write, `enrich`, `assignment_toc.py` without `--base-toc`, `toc_audit --keep-from`), never a plan re-apply or `toc_rebuild` on books with assignment blocks; Anna's Archive as step 0 before OCR, with an `annas` result per ref and never for Kotar items; Kotar fetching left to `/academic-writer:kotar-fetch`; in-copyright library readings ingested as full text in Trove and NotebookLM with exact printed page numbers, the original PDF in the course Drive folder, then `check-source`.
- **Course references** in `courses`: `refs.py` finds the works a course cites, looks them up in the BIU library and renders the `מקורות נזכרים` index. The runbook is `references/library-refs.md`. `courses.py bookmarks` can still rebuild Chrome bookmark folders by hand, but it is no longer part of the nightly run (creating folders through AppleScript crashed Chrome); the dashboard replaces it.
- **A pre-push guard** for maintainers (`.githooks/pre-push`): lists the commits being pushed and stops a push that carries another run's `ale/` merges unless that run is listed in `ALE_ALLOW_RUNS`.


- **Nightly Lemida watcher (Chrome)** in `/academic-writer:courses`, with the full procedure in `skills/courses/references/lemida-watch.md`. Moodle's REST API is blocked by a captcha, so the watch drives your signed-in Chrome: it walks every section of each course, continues from the last section with content, always reads the announcements forum, downloads files from their `pluginfile.php` links, handles Zoom recordings (download, else transcript reduced to the lecturer's main ideas with meaningful asides kept), Perusall items (OCR of the pdf twin, else a `perusall-capture` chore), assignments (time left, task, core texts; `assignment` and `kotar-source` chores) and forums you must post in (`forum-post` chore). Seen state advances only after routing succeeded (`courses.py watch-diff --apply --ok`).
- **Table of contents rule** in `courses`, `lesson-notes` and `ingest-book`: every page has its own `Title - hint` entry, nested (course, lessons, readings with sections) and in page order, with `tools/toc_rebuild.py` and `tools/toc_audit.py` named as the repo-local check.
- **Choose where an article project reads its books from.** Setup and `/academic-writer:update-tools` now ask whether to use Trove (the default and the previous behaviour), a PageIndex library you run yourself, or both, where one answers and the other is tested quietly in the background without ever changing, slowing or failing your result. The choice is saved per project in `.academic-helper/library.json`; a project without it behaves exactly as before. PageIndex stays optional: you supply the command through the new `pageindex_command` plugin setting, and nothing private ships in the plugin.
- **A local log of every library lookup and every citation check**, in `.academic-helper/retrieval.jsonl` (figures and short messages, never uploaded), and **`aw library report`**, which compares the libraries on your real articles: agreement on page text, speed, failures and timeouts, the citation checker's pass rate, and whether the second library's page also supported each claim. See [docs/library-routes.md](docs/library-routes.md).
- **A built-in PageIndex helper, installed only if you ask for it.** `/academic-writer:setup`, `/academic-writer:init` and `/academic-writer:update-tools` can now set up PageIndex inside the plugin's own data folder (a pinned version, checked against recorded hashes), or you can keep pointing at your own command. Trove stays the default. Two sizes: a basic helper (about 100 MB, Python 3.9 or newer) for books that have a table of contents, and a full helper (about 500 MB, Python 3.10 or newer and, on a Mac, the `pango` system library) that can also find the structure of a book with no table of contents. `aw library install` shows a plan first and refuses to run without `--yes`; `aw library uninstall` removes it. A command you set yourself always wins over the built-in helper. Nothing is sent to PageIndex Cloud; there is no cloud code in the plugin.
- **Ingest writes to PageIndex as well as Trove.** After the Trove read-back, `/academic-writer:ingest` and `/academic-writer:ingest-book` offer to prepare the same text for PageIndex (`aw library index --trove-id`): an outline built from the same table of contents and the same page numbers as Trove, with a short summary per entry. Summaries are written by Gemini, so **the book's text is sent to Google when you choose them** (you are asked first, with the number of calls and characters); the free option (`--summaries hints`) sends nothing and reuses the hints already written for Trove. A book with no table of contents falls back to the full helper. Re-indexing reuses summaries already paid for. Each run is read back against Trove and recorded in the usage ledger.
- **Add a reading to a book you already have.** A written procedure for appending to an existing Trove item that keeps every old page, hint and level, re-applies a merged table of contents last, and reads everything back. `ingest-book` also fixes an ordering bug: replacing page 1 resets the table of contents, so the table is now re-applied after it.
- **Prepare your existing books: `aw library backfill`.** Copies books already in Trove into PageIndex (`--shelf-current`, `--ids` or `--all`), shows an estimate first, skips books already done and can be run again safely.
- **OCR engines.** `/academic-writer:ocr` now offers the plugin's own Gemini OCR, Claude or Codex reading the page images, or local Tesseract; the engine used is recorded.
- **`/academic-writer:library-eval`: compare Trove and PageIndex on your own article, blind.** It picks claims from a draft, asks a separate Claude (or Codex) helper to find the supporting pages in each library, shows you the two answers as anonymous "A" and "B" in random order on a private judging page (a single local file that works offline, Hebrew and English), stores your verdicts (better A, better B, same, neither, with a note) and only then reveals which library was which, with win rates, a confidence range, an exact sign test, time, tokens, cost and agreement with the citation checker. The key linking A and B to the libraries is sealed with a checksum, and the judging text never names a library. The claims and page excerpts go to Anthropic (or OpenAI, if you choose Codex), on your own plan; you are asked and given an estimate first.
- **Tokens, cost and time per library in `aw library report`.** New sections for the size of returned text (estimated tokens), the locating agents' own token and cost figures, indexing runs, latency percentiles and page-level figures, alongside the existing pass rate, page agreement and second-library support; `--eval <id>` reports one evaluation. Old ledgers still read. `AW_LIBRARY_ROUTE=trove|pageindex` forces a single route for one run.

### Changed
- **Course OCR: Gemini reads the page, Tesseract only checks it.** For scanned readings Gemini produces the page text; Tesseract runs silently and its reading is used only to flag a page whose Gemini text drifts (the flagged page is shown to you, never replaced). A page Gemini returns empty is marked blocked and reported, never filled in by another engine. Library and Kotar readings use Gemini by default; other sources ask first.
- The citation check, the evidence build and the source listing in write, ideate, research and health now go through one `aw library` command instead of calling Trove directly.
- **Privacy wording corrected.** `docs/library-routes.md` said the library routes send nothing to Anthropic or Google, and the README did not mention indexing. That is true of the quiet background test (no model at all) but not of PageIndex indexing: choosing Gemini summaries sends the book's text to Google. The docs now say so, and also that a Claude or Codex locating run sends claims and page text to Anthropic or OpenAI.
- **CI and the release workflow now run the `aw` tool's tests and type check** (`npm run test:cli`, `npm run typecheck:cli`) after installing its dependencies, before the Python test suite.

### Fixed
- **Model keys stay out of helper processes.** Every child process the plugin starts (Trove, PageIndex, the Python helpers, the voice and Pi helpers) now receives an allow-listed environment, so your Gemini, Anthropic or other keys reach only the one call that needs them.
- A Word-document test that failed about once in fifty runs (two builds stamped different seconds) now uses a fixed clock.
- **The session start hook works again on current Claude Code.** Claude Code 2.1.300 refuses to run a hook command that contains a `${user_config.*}` setting, so on that version the start-up step silently never ran: your Gemini key (and the optional Jev key and PageIndex command) were not passed to the session and the built-in PageIndex helper was not found. The hook now reads each plugin setting from the environment Claude Code gives it (`CLAUDE_PLUGIN_OPTION_*`, with the older `USER_CONFIG_*` names as a fallback), never prints a key, and always tells `aw library` where the built-in helper is once it is installed. Start a new Claude Code session after updating.
- **Library comparison: locating helpers that piped the page text through `head` or `grep` no longer ruin runs unnoticed.** The prompt now says plainly that each command is run exactly as given (no pipes, redirects, `;`, `&&` or subshells), and `eval run` and `eval status` list the invalid runs, with the reason, first.
- **Library comparison: footnotes that cite by author and title** ("Pedersén, South Palace Archives, 14.", "Ibid.", "שם") are matched to your sources (accents, capital letters and Hebrew vowel signs do not matter); notes that match no source, or two equally, are listed with the reason instead of being guessed.
- The usage figures of a comparison run no longer add up lookups of an earlier run that had the same run id.

## [0.16.1] — 2026-10-14

### Changed
- **CandleKeep is now Trove** ([heytrove.ai](https://heytrove.ai)) everywhere the plugin talks to you, and every command it runs now uses the `trove` program instead of `ck`. New profiles store the setting as `tools.trove`; profiles that still say `candlekeep` keep working. The install steps use Trove's own installer, and the shelf listing asks `trove shelf current` instead of reading a file in your project.
- The README links to the online guide (published with GitHub Pages) and to Trove.

### Fixed
- **Hebrew and other right-to-left headings and footnotes in the Word file** are now aligned to the right margin. Word was drawing them at the left edge because of an explicit "right" setting inside right-to-left paragraphs.

## [0.16.0] — 2026-10-06

### Added
- **`/academic-writer:ingest`** uploads a single article or chapter into your Trove (CandleKeep) source library with its **printed page numbers preserved**, so citations name the printed page and never the library's sequential page. Every upload gets a hinted table of contents (up to 3 sentences per page) and a **page-1 "How to read and cite this book" guide** with the bibliographic record, the page-marker rule, and ready-made footnote templates in three citation styles (Chicago notes-bibliography, the Hebrew academic convention, and MLA or APA chosen from your profile's citation style). Scans and photos go through `/academic-writer:ocr`, with checks for upside-down scans, one page per call, and silently truncated "high-confidence" pages. A mandatory read-back (page count, hints, guide page, printed markers) must pass before the upload is called done, and an existing book is never deleted or overwritten without your explicit confirmation.
- **`/academic-writer:ingest-book`** uploads a whole book — a large or scanned PDF, a multi-volume set, or an EPUB — as one library book with a **nested, clickable table of contents** where every entry jumps to its real page and carries a content hint, plus the same page-1 citation guide and read-back. Multi-volume sets are merged with a printed→library page crosswalk verified against live content, and a book whose sidebar is an unusable flat list of "page N" entries can be repaired with the same enrich step.
- `write` and `research` now point at the two ingest skills when a source you want is not yet in the library.

## [0.15.0] — 2026-10-01

### Added
- An opt-in Jev shadow scorer for proofread `meaningRisk` labels that writes only to `.academic-helper/jev-shadow.jsonl`.
- **`/academic-writer:intro`** opens a bundled, offline HTML guide in your browser: what the plugin does, install, first run, your first article, where files live, privacy, troubleshooting, updating and uninstalling. Its command table and version stamp are generated from skill frontmatter at build time (`scripts/gen-guide.py`), so the guide always matches the installed version.

### Changed
- **Setup and init ask before installing anything.** Each missing tool (Python add-ons, hspell, CandleKeep, NotebookLM) is explained in one sentence and installed only after you say yes; tools only you can install (Python, Homebrew) get numbered steps for your system. Setup now also checks `jsonschema`.
- **Gemini key walkthrough per operating system.** Setup and init explain what the key is and what is sent to Google, never ask for the key in the chat, show how to store it in the plugin settings (keychain) or as an environment variable on macOS, Windows or Linux, and check it with a live call after the restart. Setup saves your profile before the restart and offers "Check my Gemini key" when you come back. The `.academic-helper/secrets.json` option is gone, because the code never read it.
- **Shorter `/academic-writer:help`** with a command list generated from the skills themselves.
- **Skills, agents and Gemini prompts rewritten to current best practice**: plain descriptions with "Use when" triggers, no references to removed agents, `AskUserQuestion` calls within the four-option limit, and the auditor reading citation details from `evidence.json` when there is no `sources.json`.
- `/academic-writer:ideate` no longer creates `.academic-helper/`; only setup and init do.
- `/academic-writer:health` gives update commands for the `yodem` marketplace (`claude plugin marketplace update yodem`, then `claude plugin update academic-writer@yodem`) and a plain fix line for each tool.
- README rewritten for researchers: what you need, install, first steps, how writing works now, the commands you can type, the Gemini key, privacy, troubleshooting and updating.

### Fixed (first-time authors)
- **A new author could not get past `/write`'s voice check.** The check looked for `AUTHOR_VOICE.md` in the project, but `/academic-writer:voice` saves to the plugin data folder, and `aw voice migrate` crashed when no `AUTHOR_VOICE.md` existed. The gate now checks the real voice store, imports an older `AUTHOR_VOICE.md` if one is there, and otherwise asks whether to build the voice first or write in a neutral voice for now. `voice migrate` starts an empty store when there is nothing to import.
- `/write` and `/voice` sync with CandleKeep only when CandleKeep is enabled, so authors without it no longer see a sync error on every run.
- `voice-sync.sh` falls back to the public marketplace's data folder (`academic-writer-yodem`).
- Setup's "Claude only" choice promised more than the code does: drafting, proofreading and OCR need the Gemini key. The choice is now "Not now" and says which commands will ask for the key later.
- `/proofread` checks for pandoc (needed to read Word files) and asks before installing it.

### Removed
- Two prompt files the code never loaded, and personal identifiers and internal development files from the public repository. The privacy gate (`scripts/check-no-private-refs.sh`) now also blocks usernames, personal email addresses, internal host names and internal dev-state paths.

## [0.14.0] — 2026-09-23
### Changed: the architecture
- **`aw` CLI replaces the Gemini MCP server and the dynamic workflows.** Every model call and deterministic step runs through `plugins/academic-writer/bin/aw`, invoked from Bash (the MCP client's ~60 s timeout and 25k-token cap no longer apply). Every call is logged to `.academic-helper/runs/<id>/usage.jsonl`; `aw ledger show <run>` summarizes it. Budgets and model ids live only in `thresholds.json`.
- **Proofread** (`aw proofread`): a deterministic must-catch pass (your names/terms canon, banned and capped style words, hspell), a Gemini-flash finder on line-numbered chunks with text anchoring, a batched cross-family verify, and application in code. Measured on the adversarial Hebrew fixture: names/terms 1.00, style words 1.00, no edits inside quotations, typos 0.77, and **0 Claude tokens** (about 13k Gemini tokens for 1,244 words). Before, a single article's proofread cost 98M tokens.
- **Write** (`aw draft` / `aw synthesize`): your intent and thesis are captured first; evidence passages are extracted with verbatim-checked quotes (`aw evidence build`); the outline is a schema with paragraph moves and bridges, and you approve every section claim. Units are drafted in dependency order and see their predecessors' text; the intro and conclusion come last. Code gates check citations, verbatim quotes, style words and length. The Claude auditor stays the hard gate, one batched call per unit.
- **One voice** in the plugin data dir, shared by all projects: exemplars you pick, rewrite pairs, style words and writing moves. It syncs to CandleKeep on change. The 7-session voice interview and the four Haiku voice agents are removed.
- **`/academic-writer:revise`**: reads Word comments and tracked changes, applies text edits, turns your rewrites into voice data (after you confirm), and logs plugin defects to a ledger that the repo-side `aw-improve` skill turns into eval cases.
- **Jev** (optional `jev_api_key`): a `decide()` cascade at 10 decision points, all in shadow mode until 100 labelled examples and the agreement bar are met. It is never the sole gate on the citation audit. An optional Pi/OpenRouter cross-family judge runs in isolation.

### Removed
- The Gemini MCP server (`mcp/gemini-server`), the dynamic workflows (`src/workflows/*`), and the section-writer, synthesizer, deep-reader, proofreader, copyeditor, editor and four voice agents, plus the `feedback` skill (replaced by `revise`).

### Fixed (found by running the built plugin, not the unit tests)
- Every hook command failed with `MODULE_NOT_FOUND` (quoting); the `aw` bundle crashed on launch (ESM `require`); proofread scripts could not find `thresholds.json` inside the built plugin; drafts cited passage ids that the gate rejected. A new `scripts/smoke-built-plugin.sh` runs the shipped artifacts, and `--live` runs the recall eval.

### Known gaps (author decisions)
- Typo recall is 0.77 against a 0.85 target: Gemini flash misses real-word errors (`לארס→להרוס`, `אם→עם`, `הטעון→הטיעון`), and the optional second pass did not help. Options: accept it; use a stronger model for the wrong_word class; relax the apply gate for verified medium-risk wrong_word fixes.
- `/write` has not yet been measured end to end on a full paper (T16 pilot).

## [0.11.0] — 2026-09-23
### Fixed
- **Plugin permissions and agent settings now take effect.** Every skill used `allowedTools`, which Claude Code ignores; skills now use the documented `allowed-tools`. `disallowed_tools` is now `disallowedTools`, and the ignored `agents:` skill key and the plugin `settings.json` permissions block are removed.
- **No more phantom agents.** The build copied the local `src/agents/memory/` folder into the plugin, where every file loaded as an agent without frontmatter; only top-level agent definitions ship now.
- **Subagents no longer load the project CLAUDE.md** (`omitClaudeMd: true`), measured at about 20k tokens saved per spawn.
- The stale-ownership gate compares a content hash instead of file times, so it no longer fails every normal `/write` run. Hook commands quote `${CLAUDE_PLUGIN_ROOT}`, and the auditor rule injected at subagent start no longer demands a year that Hebrew citations omit.

### Added
- `scripts/measure-run.py` (token cost of a real run from its transcript), a run-ledger schema, and an applied-recall proofread eval: a 1,244-word adversarial Hebrew fixture with a context-anchored grader.
- `/academic-writer:health` reports the installed plugin version.

## [0.10.1] — 2026-09-15
### Fixed

- **Hebrew DOCX headings and footnotes now retain right alignment in Word.**
  The generated OOXML now writes RTL paragraph properties in the schema-required
  order, and the footnote template uses the same order. This prevents Word from
  silently falling back to left alignment for short RTL paragraphs.

- **The distributable plugin bundle is synchronized with the current source
  generator and workflow fixes.**

## [0.10.0] — 2026-09-04
### Added

- **`src/scripts/gate.py` — one deterministic gate dispatcher**, with real exit
  codes (`0` pass / `1` gate failed / `2` could not run) and four subcommands:
  `argument-graph` (DFS cycle detection, transitive `thesis_link` reachability,
  empty-evidence, positional dependency ordering), `coverage` (status
  completeness, contiguous chapter range, `evidence_ids` referential integrity),
  `citation-floor`, and `changes-schema`. Each verdict is appended to a per-run
  gate ledger in `.academic-helper/session-state.json`.

- **`gate-enforce`, the plugin's first blocking hook** (`Stop`). Every previous
  hook returned `continue: true` unconditionally. This one reads the ledger and
  refuses to end the turn while a gate in `run.requiredGates` is failing — or
  **missing**, which is the point: skipping a gate is detected as absence rather
  than passing silently. Fails closed on a real gate failure, open on its own
  infrastructure errors, and honours `stop_hook_active` so an unsatisfiable gate
  cannot trap a session.

- **`citationFloor` thresholds.** The per-paragraph auditor is a *presence*
  check — it verifies that claims which are cited are cited correctly, and is
  structurally blind to a paragraph that cites nothing. Counting absence is
  arithmetic, not judgement. Only secondary citations count, because primary
  sources are quoted inline and make a raw count read healthy.

### Changed

- **The proofread refute fan-out is now bounded.** `concurrencyCap` bounded
  parallelism, never volume, and nothing capped the number of findings, so total
  verify calls were `findings × refuteVotes` with no ceiling — a chunk returning
  50 findings cost 150 calls, and measured worst case for one run was ~300 LLM
  invocations. New `proofread.refuteBudgetPerChunk` (cumulative per chunk across
  residual rounds) caps it; surplus changes are carried with
  `skipReason: "refute-budget-exhausted"` — downgraded, never dropped, matching
  the contract the workflow already committed to.

- **Argument-graph validation and the architect's coverage pre-check are now
  scripts.** Both were previously prose instructing a model to re-derive DFS and
  set validation in its head (`write/SKILL.md`: *"it is reasoning directly over
  the outline JSON already in memory"*). The outline is now persisted to
  `.academic-helper/outline.json`, which also makes the argument graph auditable
  after the run.

### Fixed

- **The inline `CHANGES_SCHEMA` in `proofread.js` had drifted** from the
  canonical `changes-schema.json` (missing `stage` in the change-level
  `required`, missing `change_id`/`applied`/`skipReason`/`refutedBy`, no `type`
  enum). Harmonized, with a new drift test; the language and mechanical prompts
  now ask for per-change `stage`, which the harmonized schema requires and only
  the editorial prompt had been requesting.

- **Consecutive footnote definitions with no blank line between them were being
  merged** into the first definition's body, losing footnotes 2–8.

See `docs/audits/2026-09-04-determinism-audit.md` for the full audit, the
measured LLM-call arithmetic, deviations as built, and what was deliberately
deferred.

## [0.9.0] — 2026-09-04
### Removed

- **The anti-AI numeric gate.** It read `selfReviewScores.anti_ai` and compared
  it to `thresholds.json > antiAi.passThreshold` (35/50), but **nothing ever
  computed that score**: `selfReviewScores` appears nowhere in the Gemini server
  source, so the number was whatever the drafting model chose to assign its own
  unrevised draft.

  Measured on a live 13-unit Hebrew article, it came back a **flat 50/50 on
  every dimension of every paragraph** — including paragraphs the auditor then
  returned `FAIL` on and that were rewritten twice. A scorer pinned at maximum
  passes unconditionally, so the gate did no work in any of the 13 units while
  reporting that it had. Hand-scoring the same paragraphs gave 37–44, which is
  what a scorer with range looks like.

  Removed rather than repaired. Tuning the threshold cannot fix a self-assigned
  score, and making it deterministic would have been worse: the mechanical tells
  are already caught by `detect-ai-typography.py`, and the dimensions that
  remain — cadence, hedging, manufactured symmetry — do not reduce to a script.
  A deterministic implementation would have produced a number that *looks*
  rigorous and isn't, trading a visibly broken gate for an invisibly broken one.

  **The auditor is now the single per-paragraph hard gate.** It already produces
  a real adversarial `PASS`/`FAIL`/`PARTIAL` verdict that the pipeline parses and
  acts on, so this consolidates onto the gate that was doing the work.

  Gone: `thresholds.json > antiAi`, the `selfReviewScores` field in the
  draft-unit schema, the score in `section-writer.md`'s output contract, and the
  threshold line the `SubagentStart` hook injected into every auditor spawn.

### Changed

- **Anti-AI patterns are now writing guidance, not a scored rubric.**
  `write/references/anti-ai-patterns-{english,hebrew}.md` and
  `section-writer.md` Step C still list every dimension and banned construction;
  they now say to judge a paragraph by **reading** it and to rewrite what trips a
  dimension, explicitly forbidding assigning it a number. The patterns were never
  the broken part — the self-assigned score was.

### Known gap

- This removes per-paragraph anti-AI *gating*; the auditor gates citations. If
  that granularity is wanted back, the honest form is an adversarial checker
  with a named verdict — a second auditor-shaped subagent, not a config value or
  a self-score.

## [0.8.0] — 2026-09-04
### Changed

- **Every Gemini tool now defaults to `gemini-3.8-flash`** (was `gemini-2.5-pro`
  for `write_section` / `edit` / `raw` and `gemini-2.5-flash` for `synthesize` /
  `calibrate_sample`).

  Verified against the live ListModels API rather than assumed: `gemini-3.8-flash`
  is the newest stable text model and the **only** 3.8 build published — there is
  no `gemini-3.8-pro`. The newest pro-tier model of any generation is
  `gemini-3.1-pro-preview`, still a preview, so a stable flash three generations
  newer is the better default for a pipeline that runs unattended. Smoke-tested
  end to end: the model answers and accepts `thinkingLevel`.

  Per-tool effort ordering is preserved. `buildThinkingConfig` already maps a
  budget onto `thinkingLevel` for the `gemini-3.x` family (`<512` low, `<4096`
  medium, else high; `-1` high) instead of passing an integer through, so the
  existing `thinking_budget` values keep meaning what they meant.

  `gemini_ocr` is unaffected — it stays hard-pinned to `gemini-2.5-flash`,
  because it needs `thinkingBudget: 0` and the Pro models reject it.

### Added

- **Two ways to change the model globally**, joining the per-tool override that
  already existed. Resolution order, most specific first:

  | Where | Scope |
  |---|---|
  | `gemini.models.<tool>.model` in `profile.md` | one tool |
  | `gemini.defaultModel` in `profile.md` | every tool |
  | `GEMINI_DEFAULT_MODEL` env var | every tool, machine-wide |
  | built-in `DEFAULT_MODEL` | fallback |

  The profile outranks the environment: it is durable, reviewed configuration,
  while the env var exists so a machine or a test can set a default before any
  profile exists. A per-tool entry may still set only `thinking_budget` and
  inherit whichever model won. Previously changing generation meant editing five
  separate per-tool entries; it is now one line.

  Documented in `skills/init/references/profile-schema.md`, including the warning
  to check what is actually published before pinning a version.

## [0.7.7] — 2026-09-03
### Fixed

- **`write-sections.js` produced no sections at all on a real outline.** It read
  a flat `outline.units`, but the architect emits `sections[]` with an optional
  nested `units[]`, and a section *without* one is itself the writer unit
  (`architect.md:101`, `write/SKILL.md:387`). So `units` was always `[]`,
  `canRunDraftAndAudit` requires `units.length > 0`, and the whole
  draft-and-audit stage gated off with `"no outline.units supplied"`. The
  failure was loud rather than silent, but the workflow path was unusable — a
  live run had to fall back to the `Agent` path. The script now flattens
  `sections[] → units[]`, deriving `parentSection` and `siblingUnitsSummary` per
  unit, and still accepts a pre-flattened `outline.units`.

- **The per-unit prompt dropped fields the section-writer documents as
  required.** `evidence`, `brief`, `depends_on`, `thesis_link`, `words`,
  paragraph count and suggested sources were never forwarded, and nothing tells
  a writer to read `outline.json` from disk — `references/section-writer-dispatch.md`
  lists four from-disk inputs and the outline is not among them, so `evidence`
  had no route to a writer at all. The code comment cited the migration spec's
  Section 2.1 disclosed gap as cover; that gap covers `articleStructure`,
  `tools`, `outlineOverview`, `parentSection` and `siblingUnitsSummary` — a
  different set. On the reporting run, 30 verified source corrections lived in
  `evidence`/`brief`, including a Maimonides parable-type mislabel that inverts
  an argument.

- **`detect-ai-typography.py` corrupted Hebrew abbreviations.** `fix_quotes`
  pairs any two quote characters, so in `ר' יוסף בעמ' 12` it paired the two
  geresh marks, read ` יוסף בעמ` as a quoted phrase and returned
  `ר" יוסף בעמ" 12` — turning geresh ("Rabbi") into gershayim, a meaning change.
  Three separate units reported 45, 28 and 12 false `quote_normalize` hits and
  four writers rediscovered it independently in one article. ASCII stand-ins for
  geresh and gershayim are now folded to U+05F3 / U+05F4 *before* quote pairing,
  which is the correct typographic fix in its own right and also removes them
  from the pairing character class. It only ever fired on ASCII-typed marks —
  and since the Gemini path and the source extracts both emit ASCII, that is
  every Hebrew article the plugin produces.

- **The same pairing destroyed English contractions.** `don't break the writer's
  text` came back as `don“t break the writer”s text`. Pre-existing and
  unreported; it affects any English article with two contractions on a line. An
  apostrophe with a letter on both sides is now never treated as a span
  delimiter.

- **Two Hebrew transliterations on one line paired into a false span** —
  `ג'ון כתב על אתרח'סיס` tokenized as `ג` / `ון` / `אתרח` / `סיס`. This was a
  regression introduced by 0.7.6's candidate-opener rule; each transliteration
  worked in isolation, which is why both the unit tests and the corpus check
  passed it. The prefix-opener candidacy is now restricted to Hebrew's closed
  set of inseparable prefixes (ו ל ש ב כ מ ה), so a single-letter stem like `ג'`
  or `ד'` is read as a transliteration while `ו'הכתב והקבלה'` still resolves as
  a quoted title.

### Changed

- `agents/section-writer.md` now documents the typography script's suppression
  flags at the point where it mandates the run, and states that
  `--no-directional-marks` should stay off: Step 9a.5's
  `validate-hebrew-punctuation.py` flags *missing* bidi marks around embedded
  Latin, so stripping them sets up a later gate failure.

## [0.7.6] — 2026-09-03
### Fixed

- **The v0.7.5 geresh fix converted closing single-quotes.** It rested on a claim
  made in this changelog — that all 517 Hebrew-preceded apostrophes in the
  measured corpus "are abbreviations or transliterations, none are closing
  quotes". That claim was wrong. It was generalized from a handful of sampled
  long-run cases, and a proper scan finds **119** apostrophes closing a
  single-quoted span: `'הדברים אשר אנכי מגיד לך'`, `'בין אדם לחברו'`,
  `'חכמת ישראל'`. Preceding-run length does not separate the two cases — `פרופ'`
  is four letters, the closing quote in `...מגיד לך'` follows two.

  Two consequences, both fixed. An apostrophe is now treated as geresh only when
  it is *not* the closing half of a paired span, decided by scanning each line
  and matching openers to closers. And a confirmed quote mark is **removed**
  rather than folded: `WORD_RE` accepts `'` for English (`don't`, `writer's`), so
  a quote left in place welds onto the adjacent word — which is why `ישראל`
  reported 122 against a true 128.

- **A one-letter Hebrew prefix glued to an opening quote split the quoted
  title.** `ו'הכתב והקבלה'` ("and 'the Ktav ve-haKabbalah'"), `ל'כתב והקבלה'`,
  `ש'הכתב והקבלה'` — the prefix leaves the apostrophe flanked by Hebrew on both
  sides, exactly the shape of a transliteration (`ג'ון`, `אתרח'סיס`), so it was
  read as an internal geresh and the title's last word split off as its own term.
  `הכתב והקבלה` is a commentary this corpus discusses at length, so this was
  losing real subject vocabulary, not noise. Such an apostrophe is now a
  *candidate* opener, confirmed by finding a closing quote; an unpaired candidate
  falls back to geresh, which keeps transliterations working.

  Measured on the corpus: tokens carrying a spurious geresh or welded quote fall
  from **0.330% to 0.037%** — `ישראל` 122 → 128, `והקבלה` 36 → 42. The remaining
  ~17 are quotes the source itself never closes.

## [0.7.5] — 2026-09-03
### Fixed

- **Word field instructions reached the extracted text.** `<w:instrText>` sits
  beside real `<w:t>` runs, so stripping tags left the raw switches behind —
  `TOC \h \u \z \t "Heading 1,1,Heading 2,2,..."`, plus `HYPERLINK \l` and
  `PAGEREF`. Eight of 857 paragraphs on the measured corpus, 81 tokens. Small in
  itself, but it inflated vocabulary with syntax the author never wrote, and it
  made those table-of-contents paragraphs long enough to fall on the "keep" side
  of the furniture rule — diluting the short-paragraph share of exactly the terms
  that rule hunts. `<w:instrText>` and `<w:delInstrText>` are now dropped with
  their content, the same way `<w:ins>` is. With them gone the furniture signal
  sharpens: the author's name moves from a 0.96 short-paragraph share to 1.00.

- **The gershayim split, one character over: geresh.** Geresh marks an
  abbreviation (`א׳`, `ה׳`, `ע׳`, `פרופ׳`) or a foreign consonant (`ג׳ורג׳`,
  `אתרח׳סיס`). ASCII `'` is already in `WORD_RE` so these tokenized, but they did
  not *merge* with the U+05F3 spelling, and the corpus uses both: `א'`(66)/`א׳`(7),
  `ה'`(37)/`ה׳`(12), `ע'`(42)/`ע׳`(1), `ב'`(30)/`ב׳`(5). Seven abbreviations were
  counted as fourteen separate words. Only one side is required here, unlike
  gershayim, and deliberately: an ASCII double quote genuinely *is* Hebrew's
  quotation mark, so converting it needs a Hebrew letter on both sides; a single
  quote is not, so a trailing `א'` is an abbreviation rather than a closing quote.
  Checked against the corpus — all 517 occurrences following a Hebrew letter are
  abbreviations or transliterations, none are closing quotes. English
  apostrophes are untouched.

- **The furniture rule judged terms too rare to judge.** `ב׳` and `א׳` — the same
  token doing the same job in the same two files — scored 0.80 and 0.50 on five
  and seven observations, so one was dropped and the other kept. That asymmetry
  is not a threshold wanting tuning; at that sample size the share has no
  resolution. (And `ב׳`'s five observations were themselves an artifact of the
  geresh split above: merged with `ב'` it is 35.) Only terms in **contention** for
  the reported list are now judged — the top
  `topFrequentTermsCount * furnitureCandidateMultiplier` by raw count. The filter
  exists to keep furniture out of `frequentTerms`, so a term that could never be
  reported does not need classifying, and classifying it anyway only adds noise.
  On the measured corpus the terms that matter still are judged (the author's
  name at ranks 32 and 33, `מטלה` at 40) while `ב׳` and `א׳` are not (ranks 1487
  and 708 of a 90-term field), and `meta.droppedFurnitureTerms` narrows from
  eight terms to the three that actually reach the list. `furnitureMinCount`
  stays as an absolute floor for corpora small enough that everything is
  nominally in contention.

## [0.7.4] — 2026-09-03
### Fixed

- **Hebrew acronyms were being split in half by the tokenizer.** Acronyms and
  abbreviations carry gershayim before the last letter (`שד"ל`, `הרמב"ם`, `חז"ל`,
  `רש"י`), writers type an ASCII double quote for it, and `"` is not in `WORD_RE`
  — so every one of them was cut into two fragments. Measured on a real corpus:
  654 occurrences across 243 distinct acronyms, leaving the meaningless fragment
  `שד` ranked 8th among content terms while `שד"ל`, the subject of that paper, did
  not appear at all. An ASCII quote flanked by Hebrew letters is now normalized to
  U+05F4 GERSHAYIM, which `WORD_RE` already accepts, before tokenizing. Ordinary
  quotation marks sit next to a space or punctuation and are untouched. This
  affects every token-based metric — `typeTokenRatio`, `avgWordLength`, sentence
  and paragraph lengths — not only `frequentTerms`.

  The corpus **mixes both characters for the same acronym**, so the fix does more
  than recover broken tokens: it merges a split that was halving the frequency of
  every acronym its writer typed inconsistently. 19 acronyms appear both ways —
  `הרמב"ם` at 37 ASCII plus 33 Unicode, `חז"ל` at 33 plus 15, `רש"י` at 23 plus 3
  — which is why `הרמב"ם` reports 70 after the fix where 0.7.3 saw 37. `שד"ל` is
  the pure case at 82 ASCII and none Unicode, so it disappeared entirely rather
  than merely splitting. Pinned by a regression test using both spellings in one
  fixture: a fix that normalized ASCII but left the two forms distinct would pass
  a single-character test and still under-count every acronym in a real corpus.

- **The 0.7.3 title-page filter targeted the wrong structure and never fired.**
  It looked for terms concentrated in the first N paragraphs of each file. On the
  real corpus it dropped nothing: the author's name and the assignment header are
  not front matter, they are table-of-contents lines and section headers that
  repeat once per assignment *throughout* each document — "מטלה 2 - יוליוס
  ולהאוזן - יותם פרום 4". Only about half the files had the name in their opening
  paragraphs at all.

  The real signal is paragraph **length**, not position. Across 857 paragraphs
  with a 38-word median, the paragraphs carrying the author's name have a median
  of 5 words, and 96% of that name's occurrences sit in paragraphs of ten words or
  fewer — against 3% for genuine subject vocabulary like `שד"ל` or `המקרא`. A term
  is now dropped when at least `furnitureShare` of its occurrences fall in
  paragraphs of at most `furnitureMaxWords` words and it occurs at least
  `furnitureMinCount` times. On that corpus it removes exactly eight terms — the
  author's first and last name, `מטלה`, `רפלקציה`, `סמסטר`, `סיכום`,
  `ביבליוגרפיה`, `ב׳` — with no false positives; the highest-scoring term that is
  kept scores 73%, so the 0.8 cutoff has margin on both sides. Reported in
  `meta.droppedFurnitureTerms`.

  The three `frontMatter*` keys under `thresholds.json > typography.styleMetrics`
  are replaced by `furnitureMaxWords` / `furnitureShare` / `furnitureMinCount`
  rather than kept alongside them: two overlapping heuristics with six knobs is
  worse than one with three, and the old keys tuned nothing.

### Added

- `computationalMetrics.transitions.frequencyPer1000Words`, a paragraph-length
  independent transition rate. `frequencyPerParagraph` is only comparable between
  corpora whose paragraphs are the same length: a corpus averaging 53.8 words per
  paragraph measured against a baseline averaging 122.6 reads about 8x low on the
  per-paragraph rate and only ~1.1x low once normalized, so the contrastive layer
  can report `distinctively_low` for what is a paragraphing difference rather than
  a style fact. The new field is deliberately **not** added to
  `CONTRASTIVE_METRIC_PATHS` — the published baseline carries no per-1000-words
  value, so a contrastive entry for it would read `"unavailable"` on every run.
  `style-fingerprint-rubric.md` now tells the writer to check
  `paragraphStructure.length.mean` before reading a transitions verdict as a style
  fact.

## [0.7.3] — 2026-09-03
### Fixed

- **Tracked changes were folded into the author's style fingerprint.** The `.docx`
  reader in `scripts/lib/style_text_extraction.py` kept `<w:ins>` content, so on a
  supervisor-returned paper the reviewer's marginal notes were attributed to the
  author — measured on a real corpus, a graded paper with 73 tracked runs whose
  extracted text contained the supervisor's instruction as if the author wrote it.
  Corpus files are frequently reviewed papers, so this is the common case, not an
  edge one. `<w:ins>`, `<w:del>` and `<w:moveFrom>` are now stripped *with their
  content* before tag removal (after `<[^>]+>` runs there is no `<w:ins>` left to
  find), with a repeat pass for nested containers. Deleted text is excluded too:
  it is text the author removed.

- **Every `.docx` file counted as ONE paragraph.** The reader joined `<w:p>`
  elements with a single newline while `split_paragraphs` splits on a blank line.
  Observed on a 10-file / 48k-word corpus: `paragraphStructure.length.mean` 4776.7
  chars, `sentencesPerParagraph.mean` 218.8, `count` 10 — and the artifact
  propagated, with `transitions.frequencyPerParagraph` at 42.1 against a 3.9
  baseline, which the contrastive layer then reported as `distinctively_high` for
  both. The fix needed two changes, not one: the paragraph break now emits a blank
  line *and* the line filter no longer discards it.

- **`quot` was the top "content term" in Hebrew corpora.** Hebrew gershayim are
  stored HTML-escaped in `word/document.xml` and were never unescaped, so `quot`
  ranked #1 at 1642 hits (4.3%), ahead of every real word — in a field documented
  as steering the write skill's vocabulary. `html.unescape()` now runs *after* tag
  stripping (before it, a literal `&lt;w:p&gt;` would become a tag the stripper
  deletes), with a stoplist for entity remnants in corpora that arrive pre-escaped.

- **Title-page boilerplate ranked as the researcher's vocabulary.** On the same
  corpus the author's own first and last name appeared 80 times each in
  `frequentTerms`, and the assignment header `מטלה` 74 times — furniture from the
  opening of every file, pushing the writer toward the author's own name. A term is
  now dropped when it appears in the first `frontMatterParagraphs` paragraphs of at
  least `frontMatterDocRatio` of the corpus files AND at least `frontMatterShare`
  of its occurrences come from that front matter (new keys under
  `thresholds.json > typography.styleMetrics`). Dropped terms are reported in
  `meta.droppedFrontMatterTerms` rather than vanishing silently.

- **The contrastive baseline matched headings in Latin only.** `extract_baseline_json`
  looked for a `json` fence under a heading containing "baseline" or "08". The
  shipped Hebrew Linguistic Reference has a Hebrew heading, so the match failed and
  it fell back to the *first* fence in the file — comparing against unrelated
  numbers with no warning. Selection is now by content: the first fence that parses
  and resolves at least one `CONTRASTIVE_METRIC_PATHS` leaf. The last-resort
  fallback now emits a warning.

- **The Hebrew passive-voice metric was noise reported as signal.** The heuristic
  flagged any 3+ letter word opening with נ or מ, which matches מחקר, מאמר, מקום,
  נושא and much of the language; it measured 0.7736 against a 0.19 baseline and was
  reported `distinctively_high`. Reliable nif'al/pu'al/huf'al detection needs
  morphological analysis this stdlib-only script cannot do, so the metric is now
  `null` for Hebrew-dominant text with an explanatory
  `passiveVoiceFrequencyNote`; `compute_contrastive` already degrades a missing
  metric to `"unavailable"`. Latin-script corpora still get a number. Documented in
  `style-fingerprint-rubric.md` so the writer reads the null as expected.

- **The `ck items enrich` loop in `write` Step 2 and `init` Phase 3 was dead code.**
  `ck items enrich` is a manual metadata *setter*, not an auto-extractor: a bare
  `ck items enrich <ID>` exits with "At least one of --title, --author,
  --description, --toc, --add-prompt, or --sample-question is required". The loop
  therefore failed on every item, invisibly inside a `while` loop, and it ran over
  the researcher's entire library — 183 items in the reported case, mostly unrelated
  engineering books — where a success would have overwritten hand-curated metadata.
  Removed at all five call sites, including the `AskUserQuestion` option text that
  described the enrichment to the user. Source listing is now scoped to the active
  shelf (`./.candlekeep/active-shelf`, set by `ck shelf use`) when one is set.

- **Cross-project voice sync had never worked, and blamed the user's install.**
  `skills/voice/voice-sync.sh` called `ck books list|read|create|update`; there is
  no `ck books` subcommand. Every call was wrapped in
  `2>/dev/null || echo "… local-only mode"`, so a hard CLI error surfaced as
  "ck unavailable or books subcommand unsupported" on a machine where `ck` was
  installed, authenticated and working in the same shell. That made the whole
  `author_key` mechanism dead machinery: `author_key` resolution failed loudly, as
  designed, while the step that actually persists anything failed silently, so
  `init` derived a key that could never be used for the one thing it exists for.
  Ported to `ck items list|get|import|put`. This also fixed a second, independent
  bug: `ck items list --json` returns `{"items":[…]}`, not a bare array, and the id
  parser checked `isinstance(d, list)` — so it would have matched nothing even if
  `ck books` had existed. Failures now print the real stderr and exit non-zero;
  only an absent `ck`, or one whose own binary exits 127, is local-only mode. Push
  binds to an existing `Voice Profile — <author_key>` book by title instead of
  creating a duplicate.

### Changed

- `voice-distiller` must now run its verification rather than predict it. It had
  reported "~3,650 words" for a profile that was 1,676, and printed an "Expected
  script output" block for `check-voice-populated.py` instead of executing it. The
  gate passed either way that time; an agent that predicts a verification result
  will eventually report a pass that did not happen.

### Added

- `tests/test_style_metrics.py` — 15 regression tests over the metrics pipeline,
  plus four appended to `tests/test_voice_sync.py` pinning the `ck items` contract
  and the "real errors are surfaced, not swallowed" behaviour. Every one of them
  fails against the previous release.

## [0.7.2] — 2026-09-03
### Fixed

- **The Gemini routing added in 0.7.x never ran — every reference used a tool name
  that does not resolve.** Claude Code registers a plugin-provided MCP server as
  `mcp__plugin_<plugin>_<server>__<tool>`, so the bundled server's real tool names
  are `mcp__plugin_academic-writer_gemini-api__*`. All 35 references across 11 source
  files used the bare `mcp__gemini-api__*` form instead. The failure was silent by
  construction: `section-writer`, `synthesizer` and `voice-calibrator` each name the
  tool in their frontmatter `tools:` allowlist, so the allowlist named a tool that
  does not exist and each agent was spawned without it; their prompts then hit the
  documented guard — "if the tool is NOT present in your available tools at all,
  treat that identically to a `no_credentials` error and use the fallback path
  immediately" — and quietly degraded to in-context Claude. Nothing errored, and the
  MCP server itself tested healthy end-to-end the entire time, which is why three
  releases shipped with the feature inert.

  Confirmed that an explicit frontmatter allowlist *does* deliver an MCP tool when the
  name is correct, rather than assuming it: `deep-reader` declares
  `mcp__claude_ai_Sefaria__get_text` and receives it, while its siblings naming the
  bare form receive nothing. The agents differed only in the tool name.

  The rename also covers `src/workflows/proofread.js:373`, a plain string assignment
  (`opts.mcpTool = '...'`) that a frontmatter-only sweep would miss, and the Path A
  prereq in `tests/e2e/fixture-project/RUN.md`, which told an operator to check for a
  tool name that never existed. Bare-form references in `CHANGELOG.md`,
  `features.json` and `docs/{audits,reviews}/` are deliberately left as-is — they are
  dated records of what was true when written. `docs/reviews/2026-05-28-ork-candlekeep-audit.md`
  is one of them: it reported this exact bug ("reference `mcp__gemini-api__*` tools
  that have no registration path") three months before it was fixed.


## [0.7.1] — 2026-09-02
### Changed

- **`release.yml` no longer bumps the version — it publishes what is committed.**
  The workflow used to derive a bump level from the commits since the last release
  tag and write the new version itself, which made the tree's own version
  meaningless between releases: a maintainer who hand-bumped to prepare a release
  got bumped a *second* time by the job, cutting a tag that disagreed with the
  CHANGELOG section written for it. The version is now decided in exactly one
  place — the commit that makes the change (`version-sync.py --bump ...` plus a
  hand-written CHANGELOG section) — and this workflow verifies and tags it. Two
  new guards replace what the bump used to guarantee implicitly: the job fails if
  `v<version>` is already tagged, and fails if `CHANGELOG.md` has no
  `## [<version>]` section. It no longer rebuilds or commits, so its gates now
  check the exact bytes that ship rather than a tree it just regenerated, and its
  only writes are the tag and the GitHub Release — it can't race a maintainer's
  push or leave `main` in a state nobody authored. All eight shared gate `run:`
  lines remain textually identical to `ci.yml`'s.

- **`release.yml` no longer triggers on push — releases are now a deliberate
  `workflow_dispatch` action.** `push: branches: [main]` meant every push auto-cut a
  release, which is exactly what let the `gemini-api` dist/ regression below ship
  silently for three releases with no one deciding "release now". The quality gates
  `release.yml` carried (test suite, `check-mcp-dist.sh`, `check-no-private-refs.sh`,
  version consistency, hooks typecheck) still need to block every push, so they moved
  to a new **`.github/workflows/ci.yml`**, which runs on `push: [main]` and
  `pull_request` and runs every one of those gates against the tree AS PUSHED —
  no bump, rebuild, tag, commit, or publish. The two files intentionally share
  identical `run:` commands for every gate so they can't drift apart in what they
  check.
- **New gate: `scripts/check-mcp-dist-fresh.sh`** (+ `tests/test_mcp_dist_fresh.py`).
  With auto-release gone, CI no longer rebuilds and commits `dist/index.js` on every
  release — the committed bundle is now the only copy that ever ships, and
  `check-mcp-dist.sh` only proves it *starts*, not that it still matches `src/`. This
  rebuilds the server from `src/` in an isolated temp copy (`npm ci` against the
  pinned `gemini-server/package-lock.json`, then the same `esbuild.config.mjs`) and
  fails if the result differs byte-for-byte from what's committed. esbuild's output
  was verified byte-identical across three consecutive rebuilds before relying on a
  direct comparison — the bundle carries no embedded absolute paths, timestamps, or
  version string, and the lockfile pins the exact esbuild version, so a rebuild in CI
  uses the same dependency graph as a rebuild on a maintainer's machine. Wired into
  both `ci.yml` and `release.yml` — in `release.yml` specifically *before* the bump
  and rebuild steps, so it validates what was actually committed rather than a
  rebuild compared against itself.
- **New `.gitattributes`** marks the committed bundle
  (`plugins/academic-writer/mcp/gemini-server/dist/index.js`) `-diff
  linguist-generated=true` so it stops showing full diffs in PR review and doesn't
  count toward GitHub's language statistics, now that it's a permanent, sizeable
  (2.3MB) tracked file rather than a build artifact.

### Fixed

- **Every user-invocable skill appeared three times in the command palette.**
  `build-plugins.sh` generated a `commands/<name>.md` wrapper for each of the 13
  skills marked `user-invocable: true`, whose body was nothing but
  `# Auto-generated from skills/<name>/SKILL.md` followed by a copy of the skill.
  Claude Code registers user-invocable skills in the palette on its own, so every one
  of those names rendered three identical rows (`/academic-writer:ocr`,
  `:init`, `:edit`, `:write`, `:help`, … each ×3). The control that isolated it:
  skills with `user-invocable: false` and therefore no wrapper (`learn`, `present`,
  `feedback`, `update-field`, `update-tools`) rendered exactly one row each — which
  also ruled out the plugin being loaded more than once and ruled out stale cache
  version directories, since a directory scan would have multiplied those too.
  The generator block and all 13 generated files are gone; each skill keeps its
  single `/academic-writer:<name>` palette entry. Verified against Claude Code
  2.1.258 by removing `commands/` from an installed 0.7.0 cache and restarting —
  the triples collapsed to one row per skill.

- **`gemini-api` MCP server `CONNECTION_CLOSED` on every fresh install.** `dist/` for
  `plugins/academic-writer/mcp/gemini-server/` was gitignored, so the published plugin
  shipped `plugin.json`'s `mcpServers.gemini-api` command (`node .../dist/index.js`)
  with no `dist/index.js` on disk — a regression since v0.6.2 (confirmed broken
  through v0.7.0 across every installed copy). `dist/` is now committed (sourcemap
  generation turned off — it shipped no runtime value and is one more file for the
  privacy scan to clear).
  `dist/index.js` is now a **fully self-contained bundle**: `esbuild.config.mjs`
  inlines `@modelcontextprotocol/sdk` and `@google/genai` (`external: []`) instead of
  externalizing them, so no `node_modules` needs to ship alongside `dist/index.js` at
  all. The blocker on the first attempt at this was `google-auth-library` (pulled in
  via `@google/genai`) calling `require('child_process')` etc. internally — esbuild's
  ESM output throws `Dynamic require ... is not supported` for that, and switching to
  CJS output instead broke the `import.meta.url` resolution used elsewhere in the
  server. The fix is the standard one for exactly this case: a
  `createRequire(import.meta.url)` banner shim, so those internal dynamic `require()`
  calls resolve against the bundle's own inlined modules at runtime. Verified directly
  by running the shipped `dist/index.js` alone — no `node_modules` anywhere in its
  ancestry — through the full MCP `initialize`/`tools/list` handshake, a live
  `gemini_raw` API call, and a real `gemini_ocr` call against a two-page PDF slice
  (Python OCR helper scripts under `mcp/gemini-server/scripts/` are not bundled and
  are resolved as a sibling of `dist/` at runtime — unaffected by this change, already
  tracked in git). New gate `scripts/check-mcp-dist.sh`, wired into `release.yml` and
  `tests/test_mcp_dist.py`, copies only `dist/index.js` (plus that sibling `scripts/`
  dir) into an isolated temp dir with no `node_modules` anywhere in its ancestry and
  fails the build if it doesn't start clean — this exact regression class can no
  longer ship silently, and the check now proves self-containment rather than merely
  checking vendored deps were present.
  (A fully self-contained bundle was the first approach tried; it was set aside after
  two failures without testing the `createRequire` shim, and `node_modules` was
  vendored production-only instead — that worked but put ~4,100 files / ~55MB into git
  permanently, churning on every dependency bump. The shim was tested afterward, found
  to work end-to-end, and is what's shipped here instead.)

## [0.6.4] — 2026-09-02
### Added

- **Unified three-stage `/academic-writer:proofread`.** One user-facing skill now runs
  editorial (עורך — venue/genre fit, loaded terms used without definition, insider
  references, anecdote drift, journalistic vs research treatment), language
  (עריכה לשונית — collocations, cross-clause agreement, academic register, tense), and
  mechanical (הגהה — typos, punctuation, typography) as three different lenses in
  book-production order. `--venue <slug>` and `--only editorial|language|mechanical`.
  New agents `editor.md` and `copyeditor.md`; `proofreader.md` reframed as a
  chunk-scoped exhaustive finder.
- **A shared changes contract**, `src/skills/proofread/references/changes-schema.json`,
  emitted by all three agents and consumed by every script. Carries `stage`,
  `meaningRisk`, `applied`, `skipReason` and `refutedBy`, so a guarded, refuted or
  meaning-risky change stays visible in the report instead of disappearing.
- **Six deterministic scripts, each with pytest coverage**: `chunk-article.py`,
  `spellcheck-candidates.py`, `apply-changes.py`, `citation-guard.py`,
  `build-tracked-docx.py`, `write-proof-report.py`.
- **Real Word tracked changes and comments** on the original `.docx`
  (`build-tracked-docx.py`), replacing what was previously documented as a future
  option. Direct lxml on the unzipped XML, per-stage author names, and a real
  `comments.xml` part.
- **`src/workflows/proofread.js`**, a Workflow-tool orchestrator: caps come from
  `thresholds.json > proofread` via `args`, every loop exit is named
  (`converged` / `cap-reached`), and a refute majority DOWNGRADES a candidate rather
  than dropping it — dropping a true positive was the original recall failure.
- **A regression fixture** at `tests/fixtures/proofread/hebrew-recall/` plus a manual eval
  harness at `tests/e2e/proofread-recall.mjs`.
- **Version-drift tooling**: `scripts/version-locations.json` registers every place the
  plugin version lives and `scripts/version-sync.py` reads, checks, fixes, sets and
  bumps them as one operation. Release bump level now comes from conventional commits
  across every commit in the push, with a `workflow_dispatch` override.
- **A privacy/shareability gate**, `scripts/check-no-private-refs.sh`, wired into CI and
  pytest.

### Changed

- **Gemini is default-on for the profile's target language.** `approvedLanguages` is now
  seeded with `targetLanguage` when Gemini is enabled, so a project that only proofreads
  or edits routes to Gemini instead of silently never qualifying.
  `voice-calibrator --compare-models` becomes an optional opt-OUT rather than the only
  thing that could grant approval, and `write` no longer blocks on it.
- **The release now gates on the test suite.** `pytest` and `npm run typecheck` run
  against the bumped tree before it is tagged and published; previously the whole suite
  gated nothing.

### Fixed

- Hebrew inline-parenthetical citations no longer carry a publication year
  (`(מחבר, עמ' N)`), conditioned on the target language.
- `features.json` `pluginVersion` had drifted for two releases; every version location is
  now written by one script and checked by a CI gate.
- Every `status: "partial"` feature entry now states what is missing.
- `present` declared none of the NotebookLM MCP tools its body calls, so both of its
  optional branches could never have run.
- `proofreader.md` no longer cites a source absent from the library, and its remaining
  provenance is stated by title.

### Added

- **Gemini File API upload for OCR inputs over 20MB.** `uploadViaFilesApi()` was a
  named stub with a `TODO`; documents above the inline limit could only be handled
  by splitting them and OCR'ing page by page — more API calls, more wall-clock, and
  no cross-page context. Large files now upload once and are referenced by URI via
  a `fileData` part.

  Uses `@google/genai` 1.52.0's own `files.upload` / `files.get` / `files.delete`
  primitives — no hand-rolled HTTP was needed. Polls `PROCESSING → ACTIVE` at 2s
  intervals with a 2-minute ceiling, and raises on `FAILED` rather than hanging.
  The uploaded file is deleted in a `finally` block so cleanup runs on every error
  branch as well as on success, and a failed delete never masks the real OCR error.

  The per-page split is retained as the error-path fallback rather than removed.
  Sequential-only OCR, `thinking_budget=0` / `temperature=0` / `top_k=1`, and
  image-part-before-text are all preserved.

  Gemini server suite 54 → 64 passing.

## [0.6.1] — 2026-08-09

### Fixed

- **Voice migration silently did nothing for anyone upgrading from the old
  profile layout.** `voice-migrate.sh` checked `.academic-helper/profile.json`
  for the legacy profile it is supposed to migrate *from*, when the pre-rename
  directory is `.academic-writer/profile.json`. A blanket rename in `806c962`
  swept these two path checks along with the rest of the plugin rename. The
  migration then exited 0 — reporting success — while leaving voice fields stuck
  in the old dict shape and never seeding `AUTHOR_VOICE.md`. Broken since
  2026-06-03.

  This was surfaced by `test_voice_e2e_stage1.py::test_stage1_seeds_author_voice`,
  which had been carried as an accepted "pre-existing failure" across several
  sessions and shipped in that state with 0.6.0. It was reporting a real defect
  the whole time.

  Added `test_migrate_recognizes_academic_writer_legacy_path` to isolate
  legacy-path detection so this cannot silently regress again.

- `test_migrate_strips_voice_fields_and_archives` was additionally stale: it never
  created the `.academic-helper/profile.md` guard file that `voice-migrate.sh` has
  required since `bca2417`. Fixture added; no assertion was weakened.

Suite is now 82 passing, 0 failing.

## [0.6.0] — 2026-08-09

Audit-gap closure release. Everything below came out of the 2026-08-05→06 plugin
audit and the follow-up gap sweep.

### Added

- **`/academic-writer:ocr`** — the bundled `gemini_ocr` MCP tool finally has a
  user-facing entry point. Takes a PDF/image or a directory of them, calls the
  tool sequentially (never batched), follows the tool's own 40-page truncation
  loop, and writes to `ocr-output/<basename>.ocr.md`. Degrades honestly on files
  over 20MB, since the Files-API upload path is still a genuine `TODO` in the
  server.
- **Secure credential configuration** — the Gemini key can now be supplied via
  the plugin's `userConfig` (`sensitive: true`), so Claude Code stores it in the
  OS keychain instead of leaving it plaintext in the built `plugin.json`.
  Resolution order is `USER_CONFIG_GOOGLE_API_KEY` → `GOOGLE_API_KEY` env →
  `.academic-helper/secrets.json`. Strictly additive: every pre-existing path
  still resolves, including the lowercase `google_api_key` secrets-file field.
- **Resumable voice interview** — `.academic-helper/voice-checkpoint.json` is
  written after *every answered question*. `/voice` with no arguments resumes by
  default and reports position ("session 3 of 7, 12 of ~40 answered");
  `--restart` archives rather than deletes; `--session N` jumps.
- **`check-voice-populated.py`** — deterministic stub/populated check for
  `AUTHOR_VOICE.md` (exit 0 populated, 1 stub, 2 unreadable), with the rule
  documented in `skills/voice/references/stub-definition.md`.
- **`/write` voice precondition gate** — `/write` now refuses to draft against a
  stub voice file and directs the user to `/voice`. Fails closed on exit 2: an
  unreadable voice file is not treated as populated.
- **`disable-model-invocation: true`** on `init`, `setup`, and `voice` — the
  three skills that write persistent state, spend money, or hijack a session for
  ~70 minutes. They remain runnable by explicit `/name` invocation.

### Fixed

- **Voice distillation ran only after sessions 1 and 7.** This is the root cause
  of the long-standing "AUTHOR_VOICE.md is a stub" complaint: stopping partway
  through froze the session-1 output in place. The distiller now runs after every
  completed session, and partial profiles are stamped with an explicit coverage
  line instead of passing as complete.
- **8 npm vulnerabilities** (1 low, 4 moderate, 3 high) in the Gemini MCP
  server's dependencies → **0**. Six resolved by `npm audit fix`; the last two
  required `@google/genai` `^0.3.0` → `^1.26.0`, the smallest release that drops
  the vulnerable transitive `uuid`. No `--force` was used.
- **`build-plugins.sh` silently dropped manifest fields.** Its jq filter forwarded
  only `mcpServers`, so the new `userConfig` block would have vanished at build
  time; its awk extraction carried only `description`/`allowed-tools`, so
  `disable-model-invocation` would have been bypassable through the generated
  command copy. Both extended.
- **Literal plugin path** in `skills/write/SKILL.md` — the Hebrew punctuation
  validator was invoked as `plugins/academic-writer/scripts/...` instead of
  `${CLAUDE_PLUGIN_ROOT}/scripts/...`.

### Changed

- **Skills brought under the 500-line cap** via progressive disclosure:
  `init` 707 → 405, `write` 619 → 485, `voice` → 198. Detail moved verbatim into
  `references/*.md`; no step was dropped, only delegated.
- **Voice question bank trimmed** — two verbatim cross-session duplicates and one
  near-duplicate removed, two Hazal-transliteration questions merged. Session 3 is
  now declared the minimum-viable-voice milestone, so stopping there is a
  legitimate finish rather than an abandonment.
- The voice interviewer now **confirms** what the voice-miner inferred from
  `past-articles/` instead of asking cold.

### Notes

- `required-mcp-servers` was investigated and **does not exist** in current Claude
  Code. No such field was added anywhere. Every skill touching `mcp__gemini-api__*`
  has a documented Claude-only fallback, so it would not have applied regardless.
- The MCP `channels` pattern was likewise investigated and found to be for servers
  *pushing* messages into a session, not for supplying credentials. `userConfig` is
  the correct mechanism and is what shipped.
- Two pre-existing test failures remain in `test_voice_e2e_stage1.py` and
  `test_voice_migrate.py`, unrelated to this release and untouched by it.

## [0.5.1] and earlier

See git history.
