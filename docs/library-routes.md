# Library routes: where your books are read from

Every article project reads its books from a library. This page explains the choices, what the plugin writes down about each lookup, how to read the comparison report, and how to connect an optional second library.

You do not need to do anything for this to work. A project with no choice made behaves exactly as before: it reads from Trove.

---

## The three choices

Setup (`/academic-writer:init`) and `/academic-writer:update-tools` ask which library this article project should use. The answer is saved for that project only, in `.academic-helper/library.json`.

| Choice | What it means |
|---|---|
| **Trove** | Your books are read from Trove, as the plugin has always done. Nothing else runs. This is the default. |
| **PageIndex** | Your books are read from a PageIndex library instead. PageIndex is optional: it is a library you (or someone you work with) run yourself. The plugin does not install it. |
| **Both** | One library answers, and the other is tested quietly in the background on the same request. You choose which one answers; Trove is the usual choice. |

You can change the choice later with `/academic-writer:update-tools`.

### What "tested quietly in the background" does

With **Both**, every time the plugin looks something up (a list of books, a table of contents, some pages), it also asks the second library the same question, in a separate background step, and keeps the result for comparison.

What it does:

- Your answer always comes from the library you chose to answer. The background test cannot change it.
- It never makes a lookup slower, and it never makes one fail. If the second library is slow, broken or switched off, the background step is stopped after a time limit and the plugin notes that in its log. You see no difference while you work.
- It records whether the two libraries returned the same page text, how long each took, and, when the citation checker passes or fails a citation, whether the second library's page would also have supported the claim.

What it does not do:

- It does not take over when the answering library fails. If Trove answers and Trove is down, the lookup fails and you are told. The second library is never used as a fallback.
- It does not change your drafts, your sources, your citations or your Word file.
- It does not send anything to Anthropic or Google. It uses no model at all.

The point is to find out, on your real articles, whether the second library is as good as the first before you rely on it.

---

## Where the log lives, and what it records

Every lookup and every citation check is written to one file in your research folder:

```
.academic-helper/retrieval.jsonl
```

This is the **ledger**. It is a plain text file with one line per event. It is written for every project, also when you use Trove only, so there is always something to compare against later.

It records, for each lookup:

- which library answered, and what was asked (the book, the pages, the kind of lookup);
- how long it took, how large the answer was, and any short error message;
- the result of the quiet second lookup: whether it worked, how long it took, whether it timed out, and whether the page text matched.

And for each citation the checker looked at:

- passed or failed, the corrected page when it found one, and whether the second library's page also supported the claim.

The ledger holds figures and short messages, not your text. For the comparison, the plugin briefly keeps a copy of the second library's pages in `.academic-helper/retrieval/`. Those copies are deleted after about three days.

**Nothing leaves your computer because of the ledger.** It is not uploaded or shared, and the plugin has no step that sends it anywhere. (A PageIndex command you set up yourself may contact your own server to fetch pages; that is part of your setup, not of the ledger.) Deleting `retrieval.jsonl` and the `retrieval/` folder is always safe; the report simply starts again from zero.

---

## Reading `aw library report`

Ask Claude to run `aw library report` in your research folder, or to "show me the library report". It reads the ledger and prints a summary in plain words. Add `--run <name>` to look at one article run only.

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
```

How to read it:

- **Answered ... failed.** How often the library you chose answered, how many lookups failed, and how fast (half within X means the typical lookup; nine in ten within Y means the slow ones).
- **Ran quietly alongside.** How the background library behaved: how many times it failed or timed out (a timeout counts as a failure too, so one timeout reads "1 failed, 1 timed out"). A few of these are normal. A high number means that library is not ready to rely on.
- **Returned the same page text.** Of the pages both libraries returned, how many matched. Close to 100% means they hold the same books in the same page numbering.
- **Auditor.** How many citations the citation checker passed, and for those, whether the second library's page would also have supported the claim. If the second library supports nearly everything the first one does, it is a safe replacement for citation checking.
- **Passed / Failed: the other library supports.** The same comparison split by the checker's verdict. A good second library supports what passed and does not support what failed.
- **Gaps.** What is missing from the comparison (for example, a verdict recorded before the background lookup finished). Run `aw library report --settle` to finish those.
- A note at the bottom tells you when there are too few lookups for the percentages to mean much; about five per library is a rough minimum, and more is better.

---

## Pointing the plugin at a PageIndex command

PageIndex is reached through a command that you provide. The plugin ships no server, address or account.

1. In Claude Code, type `/plugin`, open **Installed**, choose **academic-writer**, then **Configure**.
2. In **pageindex_command**, type the command that starts your PageIndex library. Two kinds of value are typical:
   - a program on your computer's path, for example `pilib`;
   - the full path to a small script that reaches your library for you, for example `/path/to/pilib-wrapper`.
3. Start a new Claude Code session (the setting is picked up at the start of a session).
4. Run `/academic-writer:update-tools` in your research folder and choose **PageIndex** or **Both**.

Notes:

- The setting is not a password. Do not put a key, password or account name in it. If your wrapper needs one, keep it inside the wrapper.
- Avoid quotation marks in the setting.
- A project can also name its own command in `.academic-helper/library.json`. A minimal file for the **Both** choice, with Trove answering, looks like this:

```json
{
  "route": "both",
  "primary": "trove",
  "pageindex": { "command": "/path/to/pilib-wrapper", "shelf": "pageindex-shelf.json" }
}
```

  `shelf` is optional. It is a small file in your research folder that lists which PageIndex books correspond to which Trove books, so a book is looked up under the right name. Set `"route": "trove"` to go back to Trove only, or add `"shadow": { "enabled": false }` to keep **Both** but stop the background test.
- If `aw library status` says PageIndex is not reachable, `/academic-writer:health` and the troubleshooting list in `/academic-writer:setup` have the matching steps.

---

## Known limits

These are known and accepted for now. None of them changes your sources, drafts or citations.

- **The comparison is only as good as its sample.** The report is a guide, not a verdict. Fewer than about five lookups per library is too little to read anything from. The cut-offs for "same page" and "also supports the claim" are rough starting values and have not yet been tuned on real Hebrew and English pairs.
- **No automatic fallback.** If the library you chose to answer is unavailable, the lookup fails. The plugin does not quietly switch.
- **Some lookups are not tested in the background.** Reading a whole book of more than about 40 pages, a book PageIndex has no page mapping for, and a moment when three background tests are already running are skipped. The report counts these under "skipped" so you can see them.
- **The limit of three background tests is approximate.** In a rare race, a fourth can start briefly. It affects only how busy the computer is, never an answer or the ledger.
- **A shortcut swapped into the ledger folder is not caught.** The plugin refuses to write the ledger through a shortcut (symbolic link) that is already there, but not one swapped in during the fraction of a second between its check and its write. This needs someone deliberately tampering on your own computer, so it is accepted for a single-researcher setup.
- **Unusual characters in a source id.** The citation checker reads `sources.json` directly. A source id with characters other than letters, digits and `. _ # : -` (for example, from editing `sources.json` by hand) is treated as unverifiable and fails its check instead of being looked up.
- **Run names are plain.** A run name used in the ledger must be made of Latin letters, digits and hyphens. The write and edit skills build such a name for you.
