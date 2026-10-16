# pilib index commands: the stdout JSON contract

Read by `aw library index` (and `backfill`). Pinned by `tests/test_pageindex_index.py`: a field or an error code
added to the code must be added here, or that test fails.

## Commands

```
pilib index-trove <trove-id> [--book-id ID] [--title T] [--author A] [--summaries gemini|hints|none]
                  [--no-fallback] [--max-calls N] [--model M] [--concurrency N] [--dry-run]
pilib index-md    --pages pages.md --toc toc.json --book-id ID --title T [--author A] [--page-marker REGEX]
                  [--summaries ...] [--max-calls N] [--model M] [--concurrency N] [--dry-run]
pilib health [--require core|structure]
```

- `index-trove` reads Trove (read-only: `trove items toc <id> --json` and `trove items read <id>:all --json`, both with
  `--no-session`) on the machine it runs on, so it needs `trove` logged in there. The library book id defaults to the
  Trove id, which is what `aw library` looks up first.
- `--summaries` defaults to `gemini` (one model call per node, key from `GEMINI_API_KEY`, or `GOOGLE_API_KEY`);
  `hints` copies the hint of "Title - hint" into the node (free); `none` writes the bare tree.
- `--dry-run` reads Trove and plans: nothing is written, no model is called.
- The model defaults and the call cap come from `library.index` in `thresholds.json`.

## Output rules

- **stdout is exactly one JSON object on one line**, success or failure. Anything a library prints is sent to stderr.
- Exit code `0` on success, `1` on any failure (usage errors from argument parsing exit `2` with no JSON).
- On failure stderr also carries one plain line: `ERROR library index: <message>`.
- A book is written as a complete new version folder and published by one atomic rename of `books/<id>/CURRENT`, so a reader sees the old book or the new one, never a mixture, and concurrent indexers of the same book each leave a whole book (the last pointer rename wins). Nothing a reader can see changes when a run fails; a book that was indexed before stays exactly as it was.
  Summaries already paid for are kept in `books/<id>/summaries.json` and reused by the next run.
- The key never appears in stdout, stderr, or the JSON.

## Success object

| field | type | meaning |
|---|---|---|
| `ok` | true | |
| `command` | string | `index-trove` or `index-md` |
| `dry_run` | boolean | true: nothing was written |
| `book_id` | string | the library id (the Trove id unless `--book-id`) |
| `trove_id` | string or null | the Trove item (null for `index-md`) |
| `title` | string | |
| `source` | string | where the tree came from: `trove-toc` (the hinted table of contents), `markdown-toc` (`index-md`), `flash-structure` (PageIndex structure detection) |
| `fallback` | boolean | true when there was no hinted table of contents and PageIndex detected the structure |
| `summaries` | string | the mode that ran: `gemini`, `hints` or `none` (a fallback run with `hints` reports `none`) |
| `model` | string or null | the model of the summaries (null unless `gemini`) |
| `n_pages` | integer | pages in the library book (Trove pages, 1..N) |
| `toc_entries` | integer | entries in the table of contents as stored |
| `hinted_entries` | integer | entries whose title carries a hint (`Title - hint`) |
| `nodes` | integer | nodes in the tree. For `trove-toc` it equals `toc_entries` unless a warning says entries were ignored |
| `nodes_with_summary` | integer | nodes that carry a summary or prefix_summary |
| `summaries_reused` | integer | summaries taken from the previous run (no model call) |
| `summaries_generated` | integer | summaries written this run (`hints`: copied; `gemini`: model calls that succeeded) |
| `summary_failures` | integer | nodes left without a summary because the model failed twice; the run still succeeds, run it again to fill them |
| `expected_calls` | integer or null | model calls this run needs (dry run: the plan; null for a fallback dry run) |
| `input_chars` | integer | characters still to be sent to the model (dry run: the estimate) |
| `calls` | integer | model calls made, failed ones included (the cap counts these) |
| `failures` | integer | model calls that raised an error |
| `prompt_tokens` | integer | |
| `completion_tokens` | integer | |
| `reasoning_tokens` | integer | thinking tokens, when the model reports them |
| `cost_usd` | number | LiteLLM's price for the calls it can price; `cost_unknown_calls` of them could not be priced |
| `cost_unknown_calls` | integer | calls with no known price |
| `call_cap` | integer | the cap in force (`--max-calls`) |
| `seconds` | number | wall time of the run |
| `library` | string | the library root (`AW_LIBRARY`) |
| `indexed_at` | string or null | UTC time written to `meta.json` (null on a dry run) |
| `warnings` | array of strings | plain-language notes: entries ignored, page gaps, a low render check |

On disk (`$AW_LIBRARY`):

```
books/<book_id>/CURRENT                 one line: the name of the current version folder
books/<book_id>/v/<version>/pages.json  Trove text, page i at index i-1
books/<book_id>/v/<version>/tree.json
books/<book_id>/v/<version>/meta.json   written last; origin.trove = trove_id, title, trove_pages, toc_entries,
                                        hinted_entries, toc_sha, pages_sha; indexer carries the llm_* usage
books/<book_id>/summaries.json          the summary cache, beside the versions
```

A version folder is never changed after it is published; the current one and the newest complete one before it are
kept, older and abandoned ones are removed once they are old. A book from before versions has `tree.json`, `pages.json`
and `meta.json` flat in `books/<book_id>/`; it is read from there until it is indexed again (its flat files, and any
`pagemap.json`, are then removed). There is no catalog file: `catalog` and `list` scan the books on every call.
`pilib meta` reports `pagemap: null` for a versioned book: library pages are Trove pages.

## Failure object

`{"ok": false, "command": ..., "code": ..., "error": ...}` plus, when model calls were made, the usage fields
`calls`, `failures`, `prompt_tokens`, `completion_tokens`, `reasoning_tokens`, `cost_usd`, `cost_unknown_calls`, `call_cap`.

| `code` | meaning | what `aw` should do |
|---|---|---|
| `trove_failed` | `trove` is missing, not logged in, the item is unknown, or the answer was not JSON | show `error`; Trove upload is unaffected |
| `trove_truncated` | Trove cut the whole-book read | tell the researcher the book is too large to index in one go |
| `no_hinted_toc` | the book has no hinted table of contents and `--no-fallback` was given | offer the structure fallback or `--summaries`-free tree |
| `structure_helper_missing` | no hinted table of contents and the structure tier is not installed (`error` is `this book has no hinted table of contents and the structure helper is not installed`); `detail` may name what failed to load | offer to install the structure tier, or the own-server route |
| `core_helper_missing` | `--summaries gemini` but LiteLLM is not installed | offer the core tier, or `--summaries hints` or `none` |
| `missing_key` | `--summaries gemini` with a Gemini model and no key in the environment | ask for the key, or offer `--summaries hints` or `none` |
| `call_cap` | the call cap was reached | summaries so far are kept; raise `--max-calls` and run again |
| `model_failed` | five calls in a row failed with none succeeding (wrong key, wrong model name, no network) | show `error` (key text removed) |
| `bad_input` | unreadable pages or table of contents file, a wrong `--summaries` value, or a book id that is not allowed (letters, digits, `. _ # : -`; no `..`; the book folder may not be a symbolic link out of the library) | fix the input |
| `empty_book` | the book has no pages (or no page starts with the marker) | |
| `no_toc` | no usable table of contents entry (a title and a page inside the book) | |
| `render_failed` | (fallback) the book could not be rendered to a PDF or the render did not match the Trove text; `error` says what | show `error`; the Trove upload is unaffected |
| `structure_failed` | (fallback) PageIndex stopped with a message | show `error` |
| `empty_tree` | PageIndex found no structure (fallback) | |
| `internal` | an unexpected error or a helper that exited with a message; `error` is the exception name and a short message | report it |

## health

`pilib health` prints `{"ok", "pilib_version", "python", "tier", "pageindex_commit", "litellm", "pageindex",
"weasyprint", "library", "books"}`. `tier` is `read` (stdlib only), `core` (LiteLLM present) or `structure`
(LiteLLM, PageIndex and WeasyPrint all import). `--require core|structure` exits 1 with `ok: false` and `error` when
the machine cannot run that tier.

## Read side (unchanged shapes)

`list`, `catalog`, `tree [--depth N] [--node ID]`, `read <book> <pages> [--json]`, `meta <book>` and `verify-library`
print exactly what the original pilib printed, so an older pilib on a server keeps working with this `aw`, and the
other way round. `index-trove` and `index-md` exist only in this version: they are needed on the machine that indexes.
