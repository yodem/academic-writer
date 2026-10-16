# Add a reading to an existing Trove item

Used by `/academic-writer:ingest` and `/academic-writer:ingest-book` when the author says "add this to the book I already have" (a course book of readings, a collected volume, a book that gained a chapter). The new text is **appended** to the item; nothing that is already there is changed.

Why this has its own flow: replacing a page with `trove items put <id>:<page>` resets the whole table of contents and loses every hint and every level. So new content is never written with `put`, and the table of contents is always re-applied last.

## 1. Pick the item and take a snapshot

1. Ask which item (AskUserQuestion with titles from `trove items list --json`; match the id and title exactly, never guess from a partial title).
2. Record the page count N and the version, and save the current table of contents:

```bash
trove items get <ITEM_ID> --no-session
trove items toc <ITEM_ID> --json --no-session > /tmp/toc-before.json
```

The saved file holds the entries under `items[0].toc` (each `{"title","page","level"}`, the title in the form `Title - hint`). Also read two old pages with `trove items read <ITEM_ID>:1 --no-session` and `trove items read <ITEM_ID>:2 --no-session` and keep their text for the comparison in step 4.

If the item already has a table of contents but without hints, say so; the new entries still carry hints and the old ones stay as they are (offer `/academic-writer:ingest-book` repair separately).

## 2. Build only the new pages

Build the new reading exactly as for a new item: printed-page markers, footnotes under each page, one `# ` line per page. Do not include the reading guide again unless the author asks for the item's page 1 to be updated (that is a separate edit, step 3).

The new pages become Trove pages N+1, N+2, and so on, in the order they appear in the new file. Write the new file to `/tmp/new-pages.md`.

## 3. Append, then re-apply a merged table of contents last

```bash
trove items append <ITEM_ID> --file /tmp/new-pages.md --no-session
```

`append` adds to the end; do not use `--prepend`, which would shift every existing page number and so every old table-of-contents entry.

If the author also wants page 1 (the reading guide) updated, do it now with `trove items put <ITEM_ID>:1 --file /tmp/reading-guide.md --no-session`, **before** the next command, because `put` resets the table of contents.

Build the merged table of contents: every entry of `/tmp/toc-before.json` unchanged, then one entry per new page or section with its Trove page (N + position), a level that matches how the item already nests (for a course book of readings: the reading's own title one level under its source, its sections one level deeper; read the old entries and copy their pattern), and the `Title - hint` form with a hint of up to 3 sentences in the document's language. Save it as `/tmp/toc-merged.json` and apply it:

```bash
trove items enrich <ITEM_ID> --toc "$(cat /tmp/toc-merged.json)" --no-session
```

Do not assume `append` kept the old table of contents; apply the merged one every time, as the last write to the item.

## 4. Read-back (mandatory)

```bash
trove items get <ITEM_ID> --no-session
trove items toc <ITEM_ID> --no-session
trove items read <ITEM_ID>:<first-new-page> --no-session
```

Check all five, and report any failure plainly. Checks 3 and 5 (the appended pages and the merged table of contents) apply in every case:

1. **Page count** is N plus the number of pages you added.
2. **Old entries** are all still in the table of contents, with their hints and levels.
3. **New entries** are present, each pointing at its real new page.
4. **Existing pages** read back as intended: every old page you did not mean to change (page 2 as saved in step 1, and page 1 when step 3 did not update it) is byte-equal to the text saved in step 1. When step 3 did rewrite page 1, compare page 1 with the **approved replacement** (`/tmp/reading-guide.md`) instead, never with the old text.
5. **Printed-page markers** are on the new pages and match the source's sequence.

## 5. Index it for PageIndex (only if the author uses it)

When PageIndex is set up, run the index step of the calling skill again for this item: `aw library index --trove-id <ITEM_ID>`. It indexes the whole item again and reuses the summaries it already paid for, so only the new or changed entries cost Gemini calls. Ask first, with the estimate, exactly as for a new item.

## Rules

- Never delete or overwrite an existing page or item without the author's explicit confirmation.
- A failed read-back is a failed append: fix it and re-verify before telling the author the reading is in.
- Always pass `--no-session` on every `trove` command.
