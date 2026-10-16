# Index a new text for PageIndex (after the Trove read-back)

Used by `/academic-writer:ingest` and `/academic-writer:ingest-book`, and by the existing-item flow (`existing-item.md`). Trove stays the default library and is always written first. PageIndex is a second, optional index of the same text: a short outline of every book that lets Claude find the right page. It is built **from the same table of contents and the same pages that are now in Trove**, so the two always agree.

The Trove upload is already finished and verified when you get here. Nothing in this step can undo it; a failure here is reported and retried, never hidden, and never turns the upload into a failed one.

## 1. Is PageIndex ready?

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library status --check
```

Read `pilib.index_trove` in the JSON. If it is `true`, a PageIndex helper (the built-in one, or the author's own command) can index a book: go on. If it is not, skip this step without comment (the author uses Trove only); mention PageIndex only if the author asked about it, and point at `/academic-writer:setup`.

## 2. Show the plan and ask (nothing is sent anywhere yet)

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library index \
  --trove-id <BOOK_ID> --dry-run
```

A dry run reads Trove and plans; it calls no model and writes nothing. In the JSON, `expected_calls` is the number of Gemini calls (one short summary per table-of-contents entry), `input_chars` the amount of text that would be sent, `hinted_entries` and `toc_entries` how many entries have hints, and `fallback` says whether the book has no usable hinted table of contents.

Tell the author in plain words, then ask with `AskUserQuestion`:

> "To keep a short outline of this book for PageIndex, its text is sent to Google (Gemini), with your Gemini key: about [expected_calls] short calls, [input_chars] characters. I can't promise the price ahead of time (it depends on Google's current Gemini prices; on Google's free tier Google may use what you send to improve its products), so I'll tell you the exact amount afterwards. The Trove copy is already safe either way."

Options: **Index with Gemini summaries**, **Index without summaries (free, nothing is sent to Google)** (`--summaries hints`: each outline entry carries the hint already written for Trove), **Not now** (Trove only; it can be done later with `aw library index`, or for many books with `/academic-writer:update-tools`). Never ask for or show a key here; the plugin passes its Gemini key to the helper itself.

- A large book (`expected_calls` above the limit `library.index.askAboveCalls` in `src/thresholds.json`) is stopped by the command unless `--yes` is given: that is why the author is asked first. Add `--yes` only after the author said yes.
- If `fallback` is true (no hinted table of contents), say so: the helper has to find the structure itself with Gemini, the number of calls cannot be counted ahead, and it needs the full helper (the "structure" level). Offer to repair the table of contents first with `/academic-writer:ingest-book`, which is cheaper and gives the same outline as Trove.
- If the key is missing, offer `--summaries hints`, or point at `/academic-writer:health`.

## 3. Index and read back

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library index \
  --trove-id <BOOK_ID> --run <run-id> [--summaries gemini|hints|none] [--yes]
```

`<run-id>` is built from Latin letters, digits and hyphens only (for example `ingest-20261016-1030`; transliterate Hebrew titles). The book is stored under the Trove id, with the same page numbers, so no page map is needed. The command checks its own work (outline ranges, summaries, the first pages compared with Trove) and prints one JSON line: report `ok`, `nodes`, `nodes_with_summary`, `calls`, `cost_usd`, and in plain words what it means ("62 outline entries, each with a short summary; the Gemini calls cost about $0.0X").

Do not claim PageIndex has the book unless `ok` is `true` and `read_back` passed.

## When it fails

Each failure prints a plain sentence; show it, do not hide it. The Trove upload is complete.

- **"needs --yes"**: ask again with the figures above, then run once more with `--yes`.
- **No Gemini key** or a Google error: use `--summaries hints`, or fix the key with `/academic-writer:health` and run the same command again.
- **No hinted table of contents and the full helper is not installed**: repair the table of contents (`/academic-writer:ingest-book`), or install the full helper through `/academic-writer:setup`.
- **Anything else**: run the same command again. Indexing is repeatable: the same book id replaces the old index, and summaries already paid for are reused.
