# Library routes: where your books are read from

Every article project reads its books from a library. This page explains the choices, how to add the optional PageIndex library (built in, or your own), what is sent where, what the plugin writes down about each lookup, how to read the comparison report, and how to compare the two libraries on your own article with a blind evaluation.

You do not need to do anything for this to work. A project with no choice made behaves exactly as before: it reads from Trove.

Contents:

- [The three choices](#the-three-choices)
- [What is sent where](#what-is-sent-where)
- [Adding PageIndex](#adding-pageindex): the [built-in helper](#option-a-the-built-in-helper), [your own command](#option-b-your-own-command), [which command runs](#which-command-runs)
- [Preparing books for PageIndex](#preparing-books-for-pageindex): [at ingest](#when-you-add-a-book-ingest-writes-to-both), [backfill](#books-you-already-have-backfill)
- [Where the log lives, and what it records](#where-the-log-lives-and-what-it-records)
- [Reading `aw library report`](#reading-aw-library-report)
- [Blind evaluation: `/academic-writer:library-eval`](#blind-evaluation-academic-writerlibrary-eval)
- [Known limits and accepted risks](#known-limits-and-accepted-risks)

---

## The three choices

Setup (`/academic-writer:init`) and `/academic-writer:update-tools` ask which library this article project should use. The answer is saved for that project only, in `.academic-helper/library.json`.

| Choice | What it means |
|---|---|
| **Trove** | Your books are read from Trove, as the plugin has always done. Nothing else runs. This is the default. |
| **PageIndex** | Your books are read from a PageIndex library instead. PageIndex is optional: it is a second library with a short outline of every book, which the plugin can install for you or reach through a command of your own. |
| **Both** | One library answers, and the other is tested quietly in the background on the same request. You choose which one answers; Trove is the usual choice. |

You can change the choice later with `/academic-writer:update-tools`. The choice is per article project, so one article can use PageIndex while another stays on Trove.

### What "tested quietly in the background" does

With **Both**, every time the plugin looks something up (a list of books, a table of contents, some pages), it also asks the second library the same question, in a separate background step, and keeps the result for comparison.

What it does:

- Your answer always comes from the library you chose to answer. The background test cannot change it.
- It never makes a lookup slower, and it never makes one fail. If the second library is slow, broken or switched off, the background step is stopped after a time limit and the plugin notes that in its log. You see no difference while you work.
- It records whether the two libraries returned the same page text, how long each took, and, when the citation checker passes or fails a citation, whether the second library's page would also have supported the claim.

What it does not do:

- It does not take over when the answering library fails. If Trove answers and Trove is down, the lookup fails and you are told. The second library is never used as a fallback.
- It does not change your drafts, your sources, your citations or your Word file.
- It uses no AI model. The quiet test only reads pages from the second library and compares text on your computer.

The point is to find out, on your real articles, whether the second library is as good as the first before you rely on it.

For one run you can also force a single route without editing any file: set the environment variable `AW_LIBRARY_ROUTE` to `trove` or `pageindex`. That route answers and the quiet second lookup is off. Any other value is refused. (The blind evaluation uses this so that each helper reads from exactly one library.)

---

## What is sent where

Reading the library, and the quiet background test, send nothing to any AI service. Three things below do, and each asks you first.

| What | Where it goes | When | You can say no |
|---|---|---|---|
| **Gemini section summaries for PageIndex.** To prepare a book, the built-in helper asks Gemini for a short summary of each section. **The book's text (the pages of each section) is sent to Google.** | Google, with your own Gemini key | Only when you prepare a book and choose Gemini summaries. Setup, ingest and backfill show the number of calls and the amount of text and ask first. | Yes. Choose the free option `--summaries hints`: it sends nothing and writes each outline entry from the hint already stored for Trove. |
| **Locating the pages for a blind evaluation.** A separate Claude Code (or Codex) helper reads claims from your draft and the pages it finds in each library. | Anthropic (Claude), or OpenAI if you choose Codex, on your own plan | Only when you run `/academic-writer:library-eval` and say yes to the estimate. | Yes. |
| **OCR of scanned pages with Gemini.** (Unchanged.) | Google | Only when you run `/academic-writer:ocr` with the Gemini engine. | Yes. Choose Claude, Codex or local Tesseract instead. |

On Google's free tier, Google may use what you send to improve its products. Check Google's current terms, and consider a paid key for unpublished or sensitive work.

What is **not** sent anywhere:

- **Nothing goes to PageIndex Cloud.** The plugin contains no code for it and needs no PageIndex account or key. PageIndex is only the pinned open-source helper installed on your computer, or a command you give.
- **Your Gemini key is never printed, never written to a file, and never put in a command line.** The built-in helper receives it only in its own private environment while it writes summaries. A command you supply yourself (for example a wrapper that reaches your own server) keeps its own key on that server; the plugin does not send your key to it, so book text sent for summaries there goes wherever that server is set up to send it.
- **The judging page** is a single local file. It makes no network requests, and the plugin sends it nowhere (unless you choose to publish it as a private page; the skill asks first).
- **The ledger and the evaluation files** stay in your research folder.

---

## Adding PageIndex

PageIndex gives each book a short outline (a "tree") with a summary per section, so Claude can go straight to the likely page. It is optional. You have two ways to get it, and Trove stays your main library either way.

Both ways are offered, in plain words and with a yes/no for each step, by `/academic-writer:setup`, `/academic-writer:init` and `/academic-writer:update-tools`. The commands below are what those skills run for you. In a terminal you can run them yourself from your research folder; `aw` is the plugin's own command-line tool, found at `${CLAUDE_PLUGIN_ROOT}/bin/aw` inside Claude Code sessions.

### Option A: the built-in helper

The plugin installs a small Python program (`pilib`) and its packages into a private folder inside its own data folder (`.../academic-writer.../pageindex/`). It does not touch your system Python or anything outside that folder, and you can remove it again.

| Level | What it gives you | Needs | Size |
|---|---|---|---|
| **Basic** (`core`) | Prepares books that have a table of contents (every book uploaded with `/academic-writer:ingest-book`), with Gemini summaries or the free hints. | Python 3.9 or newer | about 100 MB |
| **Full** (`structure`) | Also prepares a book that has **no** table of contents, by letting PageIndex and Gemini find its structure. | Python 3.10 or newer, and on a Mac the `pango` system library (`brew install pango`) | about 500 MB |

If your Python is 3.9, or the full level cannot start (for example `pango` is missing), the install ends as the basic helper and says why. The plugin never installs Python or `pango` for you; setup shows numbered steps and asks first. The sizes are rough figures quoted before the install, not measurements.

```bash
# 1. Show the plan. Changes nothing, needs no confirmation.
aw library install --dry-run

# 2. Install. Refuses to run without --yes; the skill asks you first.
aw library install --yes [--tier core|structure] [--python /path/to/python3.12]

# 3. Check it.
aw library status --check

# Remove it later. Your prepared books are kept unless you add --purge-library.
aw library uninstall --yes [--purge-library]
```

How the install protects you:

- Packages are installed from a pinned list with recorded hashes (`src/scripts/pageindex/PINNED.json` and the requirements files next to it): pip refuses anything that does not match. PageIndex itself is installed from one exact version of its public code, not "the latest".
- The install has time limits and ends with a health check. `installed.json` in the same folder records what was installed.
- After the install, `aw library status --check` shows `installed.installed`, `installed.matches_pinned` and `pilib.index_trove`; all three should be `true`.

Third-party licences for what is installed are listed in `src/scripts/pageindex/THIRD_PARTY_NOTICES.md`.

### Option B: your own command

If you (or someone you work with) already run a PageIndex library, for example on a server, give the plugin the command that reaches it. The plugin ships no server, address or account.

1. In Claude Code, type `/plugin`, open **Installed**, choose **academic-writer**, then **Configure**.
2. In **pageindex_command**, type the command that starts your PageIndex library. Two kinds of value are typical:
   - a program on your computer's path, for example `pilib`;
   - the full path to a small script that reaches your library for you, for example `/path/to/pilib-wrapper`.
3. Start a new Claude Code session (the setting is picked up at the start of a session).
4. Run `/academic-writer:update-tools` in your research folder and choose **PageIndex** or **Both**.

Notes:

- The setting is not a password. Do not put a key, password or account name in it. If your wrapper needs one, keep it inside the wrapper.
- Avoid quotation marks in the setting.
- To prepare books through such a command, the server needs the same `pilib` helper that the built-in install uses (a recent version), a signed-in Trove, and its own Gemini key. `aw library status --check` says in plain words when the server's helper is too old to prepare books (`index_trove` is `false`); reading books that are already prepared still works.
- A project can also name its own command in `.academic-helper/library.json`. A minimal file for the **Both** choice, with Trove answering, looks like this:

```json
{
  "route": "both",
  "primary": "trove",
  "pageindex": { "command": "/path/to/pilib-wrapper", "shelf": "pageindex-shelf.json" }
}
```

  `shelf` is optional. It is a small file in your research folder that lists which PageIndex books correspond to which Trove books, so a book is looked up under the right name. Books prepared by `aw library index` are stored under the Trove id and need no shelf entry. Set `"route": "trove"` to go back to Trove only, or add `"shadow": { "enabled": false }` to keep **Both** but stop the background test.
- If `aw library status` says PageIndex is not reachable, `/academic-writer:health` and the troubleshooting list in `/academic-writer:setup` have the matching steps.

### Which command runs

When more than one is available, the plugin picks the first of these, so a command you set yourself always wins and a local install is never used by surprise:

1. the `pageindex_command` plugin setting (exported to the session as `AW_PAGEINDEX_COMMAND`);
2. `pageindex.command` in the project's `.academic-helper/library.json`;
3. the built-in helper, if installed;
4. `pilib` on your computer's path (the older default).

`aw library status` shows which one was chosen (`pageindex_source`: `setting`, `library.json`, `installed` or `default`).

---

## Preparing books for PageIndex

Reading from PageIndex needs the book to have been prepared there first. Prepared books live in the helper's `library/books/<trove id>/` folder (inside the plugin's data folder for the built-in helper, wherever your server keeps them for your own command), under the **same id and the same page numbers as in Trove**, so a citation page means the same thing in both libraries.

What preparing a book does: it reads the book from Trove (it never changes Trove), builds the outline from **the same hinted table of contents Trove has**, and, if you chose Gemini summaries, asks Gemini for a short summary of each entry. Without a hinted table of contents it falls back to PageIndex's own structure detection with Gemini, which needs the full helper and cannot count its calls ahead of time. Summaries already paid for are reused when you prepare the same book again.

Each run:

- shows a **dry run first** (`--dry-run`: how many Gemini calls, how much text, how many table-of-contents entries carry hints; it calls no model and writes nothing);
- has a hard cap on Gemini calls, and a larger book needs your explicit yes (`--yes`) before it starts;
- checks its own work by reading the result back: the outline's page ranges, the share of entries with a summary, and the first pages compared with Trove (if Trove cannot be reached for the comparison, it says so rather than failing);
- reports what it cost, and records the run in the usage ledger of the run you name.

### When you add a book: ingest writes to both

`/academic-writer:ingest` and `/academic-writer:ingest-book` always write to Trove first and read it back. If a PageIndex helper is ready (`aw library status --check` shows `pilib.index_trove: true`), they then offer to prepare the same text for PageIndex, show the plan, and ask you to choose: **Gemini summaries**, **free hints (nothing sent to Google)**, or **not now**. A failure here never undoes the Trove upload; it is reported and can be repeated.

The same skills can also **add a reading to a book you already have**: the new pages are appended, every old page, hint and level stays, and a merged table of contents is applied last and read back. Then PageIndex is prepared again for that book, reusing the summaries already paid for.

```bash
aw library index --trove-id <ID> --dry-run
aw library index --trove-id <ID> --run <run-name> [--summaries gemini|hints|none] [--yes] [--no-fallback] [--max-calls N]
```

`--run` names the run in the ledger (Latin letters, digits and hyphens). `--summaries none` writes an outline with no summaries.

### Books you already have: backfill

`aw library backfill` copies books that are already in Trove into PageIndex. It reads Trove only. It can be run again safely: with `--skip-existing`, books already prepared are skipped.

```bash
aw library backfill --shelf-current --skip-existing --dry-run     # the active Trove shelf
aw library backfill --ids <id1>,<id2> --yes                        # chosen books
aw library backfill --all --summaries hints --yes                  # every book, free option
```

It needs `--yes` when the estimated number of Gemini calls is above the limit set in `src/thresholds.json` (`library.index.askAboveCalls`), or when a book has no hinted table of contents.

### Exit codes of `aw library install`, `index` and `backfill`

`0` worked; `2` a usage problem (including a missing `--yes`); `3` a setup problem (no PageIndex command, or a helper too old to prepare books); `4` the work itself failed. Every failure prints a plain sentence; `index` also prints one line of JSON with `ok`, `error`, `needs_yes` and the read-back result.

---

## Where the log lives, and what it records

Every lookup and every citation check is written to one file in your research folder:

```
.academic-helper/retrieval.jsonl
```

This is the **ledger**. It is a plain text file with one line per event. It is written for every project, also when you use Trove only, so there is always something to compare against later.

It records, for each lookup:

- which library answered, and what was asked (the book, the pages, the kind of lookup);
- how long it took, how large the answer was, an **estimate of how many tokens** the returned text is, how many distinct pages came back, and any short error message;
- the result of the quiet second lookup: whether it worked, how long it took, whether it timed out, whether the page text matched, and the same size and token estimate for its answer.

And for each citation the checker looked at:

- passed or failed, the corrected page when it found one, and whether the second library's page also supported the claim.

The token figures in the ledger are **estimates**: the number of characters divided by a fixed ratio (about 2 characters per token for Hebrew, about 4 for other scripts; the ratios are in `src/thresholds.json` under `library.tokens`). They are for comparing libraries with each other, not a bill, and Claude's own counts will differ. The rows are marked `"tokens_basis": "estimate"`. Rows written by older versions have no token fields and are still read and shown.

Two other files record work that is not a lookup. Both are written in the folder of the run you name, `.academic-helper/runs/<run>/usage.jsonl`, and are read by the report:

- `step` `library.index`: one row per PageIndex preparation (model, tokens in and out, cost, how long);
- `step` `library.eval.locate`: one row per locating helper of a blind evaluation, with the helper's own token and cost figures.

The ledger file holds figures and short messages, not your text. The plugin does, however, keep temporary working copies in the folder `.academic-helper/retrieval/` so it can compare the two libraries:

- a copy of the pages each library returned (the answering one and the quiet one), and
- while a citation check is still waiting for the quiet lookup to finish, a small file holding the supporting quote the citation checker gave. It is removed once that check is settled.

These temporary files are not cleaned on a timer. Files older than about three days are removed only when the library is used again (the next background lookup or citation check). A project you stop using keeps its copies until you delete the `retrieval/` folder yourself.

**Nothing leaves your computer because of the ledger or these copies.** They are not uploaded or shared, and the plugin has no step that sends them anywhere. Page requests that go through a PageIndex route are different: they go wherever your PageIndex command points (for example your own server). That is part of your setup, not of the ledger. Deleting `retrieval.jsonl` and the `retrieval/` folder is always safe; the report simply starts again from zero.

---

## Reading `aw library report`

Ask Claude to run `aw library report` in your research folder, or to "show me the library report". It reads the ledger and the usage files and prints a summary in plain words. Add `--run <name>` to look at one article run only, `--eval <id>` for one blind evaluation (the two cannot be combined), or `--json` for the same figures as data.

Here is an example from a project set to **Both**, with Trove answering. The numbers are illustrative.

```
Library report
Lookups 14, second lookups 14, auditor verdicts 9
Setups seen: both, trove answers (14)

Trove
  Answered 14 lookups, 0 failed (0%); half finish within 412 ms, nine in ten within 1180 ms
  When trove answered, the other library returned the same page text for 22 of 24 pages (91.7%)
  Auditor: 8 of 9 citations passed (88.9%), 1 failed with a corrected page; the other library's page also supported the claim for 8 of 9 checked (88.9%)

PageIndex
  Ran quietly alongside 14 times: 1 failed, 1 timed out, 0 had no page mapping; half within 240 ms, nine in ten within 2900 ms

Page agreement overall: 22 of 24 pages (91.7%) over 11 lookups
Lookups with an auditor verdict: 9 of 11 page reads (81.8%); 9 verdicts in all
  Passed: the other library supports 8, does not 0, unknown 0
  Failed: the other library supports 0, does not 1, unknown 0
Gaps: 0 verdicts waiting on the second lookup, 0 with no second-lookup text, 0 without a usable quote, 0 second lookups with no result

Returned text (token figures are estimates: about 2 Hebrew or 4 other characters per token, so Claude's own counts will differ)
  Trove: 14 lookups answered, about 21,000 tokens in all; half return 1,200 or fewer, nine in ten 3,900 or fewer; about 650 per page
  PageIndex: second lookups 14, about 9,500 tokens in all
```

How to read it:

- **Answered ... failed.** How often the library you chose answered, how many lookups failed, and how fast (half within X means the typical lookup; nine in ten within Y means the slow ones).
- **Ran quietly alongside.** How the background library behaved: how many times it failed or timed out (a timeout counts as a failure too, so one timeout reads "1 failed, 1 timed out"). A few of these are normal. A high number means that library is not ready to rely on.
- **Returned the same page text.** Of the pages both libraries returned, how many matched. Close to 100% means they hold the same books in the same page numbering.
- **Auditor.** How many citations the citation checker passed, and for those, whether the second library's page would also have supported the claim. If the second library supports nearly everything the first one does, it is a safe replacement for citation checking.
- **Passed / Failed: the other library supports.** The same comparison split by the checker's verdict. A good second library supports what passed and does not support what failed.
- **Gaps.** What is missing from the comparison (for example, a verdict recorded before the background lookup finished). Run `aw library report --settle` to finish those.
- **Returned text.** How much text each library handed back, as estimated tokens: in all, typical and heavy lookups, and per page. Less is cheaper for the model to read, if the pages are the right ones: judge it together with the pass rate, not alone.
- A note at the bottom tells you when there are too few lookups for the percentages to mean much; about five per library is a rough minimum, and more is better.

Three more sections appear only when there is something to show:

- **Locating agents** (from blind evaluations): per library, how many helper runs, how many failed, how long they took, the tokens in and out and the cost **as the helper's own tool reported them**, and the lookups each run made. These are the real figures, unlike the estimated ones above. The citation checker inside a normal writing session does not report its own tokens, so a project that has never run an evaluation has no agent figures, and the report says so.
- **Indexing**: the PageIndex preparation runs: how many, how many failed, tokens, cost, how long, and the model.
- Latency percentiles per kind of lookup, when more than one kind was seen.

Time is the wall-clock time the plugin measured. Cost is shown only when the tool that ran the work reported it; where it did not, the report says "cost not reported" instead of guessing.

---

## Blind evaluation: `/academic-writer:library-eval`

The report above compares libraries from your day-to-day lookups. The blind evaluation answers a sharper question on your own sources: **for the claims in this article, which library finds the better pages?** You judge real results without knowing which library produced which.

Prerequisites: a draft with footnotes in `.academic-helper/drafts/` (or a list of claims you give with `--claims`); the cited sources in **both** libraries (a source only in Trove is skipped, with a reason; prepare it first, see above); Claude Code on your computer (or Codex); and PageIndex set up, so `aw library status --check` shows both libraries answering.

The steps, each of which the skill runs for you and explains in plain words:

1. **Plan** (`aw library eval plan --article <draft> [--n <claims>] [--seed <text>]`). Picks claims (sentences with a footnote, joined to the source and printed page they cite), up to the limit in `src/thresholds.json` (`library.eval.maxClaims`, at most a few per source). It prints the number of helper runs, an estimate of the cost, and what it skipped and why. Nothing is spent yet.
2. **You are asked.** The skill says what will be sent (the claims and the page text the helpers read go to Anthropic, or to OpenAI with Codex, on your plan), the estimated cost, and that it takes a while. **Not now** keeps the plan and spends nothing.
3. **Run** (`aw library eval run --eval <id> [--engine claude|codex]`). For every claim, in each library separately, a fresh Claude Code (or Codex) helper is asked to find the pages that support it, with a time limit, a turn limit and a budget limit per run (`library.eval`). Each helper is isolated: it starts in an empty temporary folder, may run only the plugin's table-of-contents and page-reading lookups, and is tied to its one library through `AW_LIBRARY_ROUTE`. Re-running continues where it stopped. A few failed runs are normal; the same command retries them. `aw library eval status` shows progress and never names a library.
4. **Pairs** (`aw library eval pairs --eval <id>`). Builds anonymous side-by-side pairs "A" and "B" in a random order for each claim, using the same text and layout on both sides, so only the *choice of pages* differs. Pairs where both libraries chose exactly the same pages are recorded as "same" and not shown to you. The key saying which side is which is written to a **sealed** file with a checksum that also covers the plan and the runs; if any of them is changed afterwards, unblinding is refused.
5. **Judging page** (`aw library eval page --eval <id>`). Writes `judge.html` in `.academic-helper/library-eval/<id>/`. Double-click it. For each pair you see the claim and the two answers side by side, and choose **Better: A**, **Better: B**, **Same** or **Neither**, with an optional note. It works in Hebrew and English, in light and dark, and on a phone-width window, makes no network requests, shows no library names, remembers your answers in the browser so you can stop and come back, and at the end offers **Download judgments** (a file named `judgments-<id>.json`). You may mark a pair **Skip**.
6. **Import** (`aw library eval import --eval <id> --file judgments-<id>.json`). Checks the file and stores your judgments. It refuses a file that leaves pairs unjudged unless you add `--partial` (to save progress and import the rest later).
7. **Unblind** (`aw library eval unblind --eval <id>`). Only now is the key opened, and only if all pairs are judged. It prints and saves `report.md` and `report.json` in the evaluation folder:
   - for each library: pairs won, lost, tied ("same") and "neither", and the **win rate among pairs with a clear winner**, with a 95% range (Wilson interval);
   - an exact **sign test** of whether one library won more often than chance would give;
   - the **time, tokens and cost** of each library's helpers (the helpers' own figures), and how much page text each returned;
   - **agreement with the citation checker**: how often each library found the page the checker had confirmed, and whether your choices agree with that;
   - your own notes, now with the libraries named.

   If fewer than `library.eval.minPairs` pairs were judged, the report says so and does **not** name a better library. A small number of pairs is a first look, not proof.

Everything lives in `.academic-helper/library-eval/<id>/`: `plan.json`, `runs/`, `pairs.json`, `sealed/mapping.json` (the key; do not open it before unblinding), `judge.html`, `judgments.json`, `report.md` and `report.json`.

What the blinding does and does not protect: it protects **you as the judge**. The text you see never names a library, and the plugin's skill is told not to guess aloud. The helpers that find the pages can still notice, by the shape of what they read, whether they are looking at a Trove table of contents or a PageIndex outline; their answers are about this article's sources only.

---

## Known limits and accepted risks

These are known and accepted for now. None of them changes your sources, drafts or citations.

**The comparison**

- **The comparison is only as good as its sample.** The report is a guide, not a verdict. Fewer than about five lookups per library is too little to read anything from, and a blind evaluation needs at least the number of judged pairs in `library.eval.minPairs`. The cut-offs for "same page" and "also supports the claim" are rough starting values and have not yet been tuned on real Hebrew and English pairs.
- **Token figures from the ledger are estimates**, not tokenizer counts. Agent token and cost figures are what the helper's own tool reported, and cost is missing when it did not report one.
- **The citation checker's own tokens are not in the report.** Only locating helpers of a blind evaluation and indexing runs report them.
- **The evaluation does not record how well the checker's quote is supported.** It records page agreement with the checker's confirmed page, not quote-level support.
- **Codex support is less tested than Claude's.** The Codex command-line flags were checked against its help output only; Claude Code is the tested default.

**The background test and the ledger**

- **No automatic fallback.** If the library you chose to answer is unavailable, the lookup fails. The plugin does not quietly switch.
- **Some lookups are not tested in the background.** Reading a whole book of more than about 40 pages, a book PageIndex has no page mapping for, and a moment when three background tests are already running are skipped. The report counts these under "skipped" so you can see them.
- **The limit of three background tests is approximate.** In a rare race, a fourth can start briefly. It affects only how busy the computer is, never an answer or the ledger.
- **A shortcut swapped into the ledger or evaluation folder is not caught.** The plugin refuses to write the ledger or the evaluation files through a shortcut (symbolic link) that is already there, but not one swapped in during the fraction of a second between its check and its write. This needs someone deliberately tampering on your own computer, so it is accepted for a single-researcher setup.
- **Unusual characters in a source id.** The citation checker reads `sources.json` directly. A source id with characters other than letters, digits and `. _ # : -` (for example, from editing `sources.json` by hand) is treated as unverifiable and fails its check instead of being looked up.
- **Run names are plain.** A run name used in the ledger must be made of Latin letters, digits and hyphens. The write and edit skills build such a name for you.

**The built-in helper and indexing**

- **The full level has had less testing.** The basic level was installed and run for real; the full level (PageIndex with WeasyPrint, Python 3.10 or newer, `pango`) is exercised only with fakes in the automated tests and is not installed in continuous integration. If it cannot start, the install ends as the basic helper.
- **One helper version per library.** The prepared books use a versioned folder layout that an older `pilib` cannot read. `aw library status` warns, and `aw library index` refuses (exit 3) until the helper is updated. Prepare one library with one helper version.
- **A book being re-prepared can look "not prepared" for an instant** to a reader that happens to read at that moment, if it was prepared by an older flat layout and is being converted for the first time.
- **Local disks only.** The helper locks each book while preparing it, using a file lock that is only guaranteed on a local disk (not on network drives). A second preparation of the same book at the same time is refused as "busy".
- **Cost is known only afterwards.** The number of Gemini calls is counted ahead for a book with a table of contents, not for one that needs structure detection; the dollar figure comes from what Google reports after the run.
- **The summaries are Gemini's.** They are short machine-written outlines to help locate pages, never quoted as evidence; the citation checker still checks the real page text.

**The blind evaluation**

- **A helper that leaves a background process running** can make `eval run` wait until the helper's time limit.
- **The judging page can be published as a private page only when the session can do that**; the local file always works. Answers saved on the page itself are only as private as the page.
