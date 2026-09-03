---
name: ocr
description: "OCR a scanned PDF or image (or a directory of them) into clean plain-text markdown via the bundled Gemini vision tool. Skips Gemini entirely for born-digital pages (extracted directly). Use when you have a scanned source — an old article, a photographed archival page, a screenshot of a source — and want its text extracted before using it in research or writing. Takes a path to a file or directory as its argument."
user-invocable: true
allowedTools: [Bash, Read, Write, Glob, mcp__plugin_academic-writer_gemini-api__gemini_ocr]
metadata: {author: "Yotam Fromm", version: "0.1.0"}
---

# Academic Writer — OCR

Extracts clean, reading-order plain text from a scanned PDF or image using the bundled Gemini
vision OCR tool (`gemini_ocr`). Born-digital pages (real text layer, e.g. a normal exported PDF)
never touch Gemini — they're extracted directly by a PyMuPDF pre-pass. Only pages that are actually
scanned images go through vision OCR.

**This is OCR only.** It transcribes faithfully; it does not correct, paraphrase, or clean up the
underlying text. A garbled scan stays garbled in the output — it is flagged via `confidence`/`notes`
instead of silently "fixed". Hebrew OCR correction (or any correction) is a separate, Sonnet-only
concern outside this skill's scope — if you want a correction pass afterward, that's a job for a
human editor or `/academic-writer:proofread` on the resulting text, never Haiku or Gemini.

**Preflight**: If you haven't run `/academic-writer:setup` yet, running it first gets your Gemini key
working with a live test. This skill checks for a key below and points you there if it's missing.

---

## Step 1 — Resolve the input

The user passes a path as an argument. If none was given, ask:

> "What should I OCR? Give me a path to a PDF or image file, or a directory containing several."

Resolve what it is:

```bash
INPUT_PATH="THE_PATH_HERE"
if [ -d "$INPUT_PATH" ]; then
  echo "DIRECTORY"
  find "$INPUT_PATH" -maxdepth 1 -type f \( -iname "*.pdf" -o -iname "*.png" -o -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.tif" -o -iname "*.tiff" \) | sort
elif [ -f "$INPUT_PATH" ]; then
  echo "FILE"
else
  echo "NOT_FOUND"
fi
```

- **NOT_FOUND** → tell the user the path doesn't exist and stop.
- **FILE** with an unsupported extension (not pdf/png/jpg/jpeg/tif/tiff) → tell the user OCR
  supports PDF and common image formats, and stop.
- **DIRECTORY** with zero matching files → tell the user and stop; otherwise the matched file list
  becomes the batch (all files, processed one at a time — see Step 4).

## Step 2 — Check the Gemini credential

Reuse the same check `/academic-writer:setup` and `/academic-writer:init` use — do not invent a new
key path:

```bash
if [ -n "$GOOGLE_API_KEY" ]; then
  echo "Found GOOGLE_API_KEY in environment."
elif [ -f .academic-helper/secrets.json ] && python3 -c "import json,sys; sys.exit(0 if json.load(open('.academic-helper/secrets.json')).get('GOOGLE_API_KEY') else 1)" 2>/dev/null; then
  echo "Found GOOGLE_API_KEY in .academic-helper/secrets.json."
else
  echo "NO_KEY"
fi
```

**If `NO_KEY`**: don't hard-block yet — a document that's entirely born-digital never calls Gemini
and will still work. Warn once: "No Gemini API key configured yet. Born-digital pages will still
extract fine, but any scanned page will fail until you run `/academic-writer:setup` (Step 3 — Gemini
API key) to configure one." Continue to Step 3.

If a scanned page is later hit with no key, `gemini_ocr` itself returns a `no_credentials` structured
error (`"Set GOOGLE_API_KEY in your environment or run /academic-writer:setup..."`) — surface that
message verbatim when it happens (Step 5).

## Step 3 — Output location

Create the output directory:

```bash
mkdir -p ocr-output
```

Each source document gets one output file: `ocr-output/<basename>.ocr.md` (basename = the source
filename without its extension). Never overwrite the source; never write inside `.academic-helper/`
— OCR output is a deliverable, not internal plugin state.

## Step 4 — OCR each document, one at a time

**Process files strictly one at a time, in order — never in parallel, and never batch multiple
files into concurrent tool calls.** This applies both across files (in a directory batch) and across
pages within one file (Step 4b) — a prior parallel run of this same tool corrupted output, so
sequencing is a hard requirement, not an optimization.

For each document (single file, or each match from a directory listing, in listed order):

### Step 4a — Determine target language

If the researcher's profile exists, use its `targetLanguage` (Hebrew → `he`, mixed Hebrew/English
sources → `mixed`, otherwise → `en`):

```bash
cat .academic-helper/profile.md 2>/dev/null | grep -A1 "^targetLanguage:" || echo "no profile"
```

If no profile, ask the user once (`he` / `en` / `mixed`) unless it's obvious from the filename/context;
default to `en` if truly unclear and note the assumption in the output file.

### Step 4b — Call `gemini_ocr`, following truncation until done

Call the tool with no `page_range` first (full document). The tool caps a single call at 40 pages and
reports `truncated`/`truncation_message` if the document is longer — loop, feeding the next
`page_range` from the message, until `truncated` is `false`. Each call is a single sequential
invocation; wait for each result before making the next one:

```
mcp__plugin_academic-writer_gemini-api__gemini_ocr({
  document_path: "ABS_PATH_TO_DOCUMENT",
  target_language: "he" | "en" | "mixed",
  response_format: "concise"
})
```

- If the result has `truncated: true`, read `truncation_message` for the next starting page (it says
  "...call again with page_range starting at page N") and the document's last page (from the first
  call's page count, or just keep going with `"N-<lastKnownPage>"` — if you don't know the last page,
  use `"N-"`-style open range is NOT supported; instead re-derive the total by noting how many pages
  came back so far plus what the message implies, and pass `"N-<total>"`). Repeat until
  `truncated: false`.
- Accumulate all `pages` arrays across calls into one ordered list (sort by `page_number` if calls
  ever returned out of order — they shouldn't, but don't assume).

**Large pages (`>20MB`) now route through the Gemini Files API automatically** — the bundled MCP
server uploads each oversized page's rasterized image, polls until the upload reaches `ACTIVE`, runs
OCR against the uploaded file, then deletes it, all inside a single `gemini_ocr` call. This is
transparent to the skill: no special handling needed on the happy path.

**On an `ocr_failed` error whose message mentions "Files API"** (the upload failed, the uploaded file
was rejected/`FAILED`, or the upload didn't reach `ACTIVE` within the poll timeout): the Files API path
itself failed for this batch. Retry **once** with the same `page_range` narrowed to a single page at a
time (call `gemini_ocr` per individual page instead of the default 6-page-per-call batch) — this fixes
the common case where a *batch* of pages together crossed 20MB even though no single page does, and
gives a single problematic page's upload a clean retry in isolation. If a **single page alone** still
fails the same way, do not keep retrying: report to the user plainly that this page's Files API upload
did not succeed (include the error message) — skip that page, note it in the output file's Notes
section, and continue with the rest of the document.

**On any other structured error** (`no_credentials`, `api_error`, `transient`, `validation`,
`ocr_failed` for other reasons): stop processing *this* document, report the error's `message` field
verbatim to the user (it's already written to be actionable), and move on to the next document in the
batch rather than aborting the whole run. For `no_credentials` specifically, point at
`/academic-writer:setup` (Step 3 — Gemini API key) as the fix, exactly as the tool's own message says.

### Step 4c — Write the output file

Write `ocr-output/<basename>.ocr.md`:

```markdown
# OCR — <basename>

- Source: `<INPUT_PATH_TO_THIS_DOCUMENT>`
- Language: <target_language>
- Pages: <N> total, <M> born-digital (skipped Gemini), <K> OCR'd via Gemini vision
- Date: <YYYY-MM-DD>
- Truncated calls: <how many gemini_ocr invocations this took, if more than one>

## Page 1

<page 1 text>

## Page 2

<page 2 text>

...

## Notes

- <any page with confidence: "low" or a non-empty `notes` field — page number + note, verbatim>
- <any skipped page from a persistent Files API failure above, with the reason>
```

Every page's `notes` and `confidence` fields carry over into this Notes section when non-trivial —
don't drop them. Pages with `is_born_digital: true` need no confidence caveat (extracted, not OCR'd).

## Step 5 — Report to the researcher

After the batch (single file or whole directory) finishes:

> "OCR complete.
> | Document | Pages | Born-digital | OCR'd | Issues |
> |---|---|---|---|---|
> | <file> | <N> | <M> | <K> | <count of notes/skips, or —> |
>
> Output: `ocr-output/<basename>.ocr.md` (one per document).
> <If any document hit a fatal error>: `<file>` failed — <error message>. <If it was a missing key>: run `/academic-writer:setup` to configure your Gemini key, then re-run `/academic-writer:ocr <path>`."

## Hard rules

- **Sequential only.** One `gemini_ocr` call at a time, one document at a time — never parallel,
  never batched concurrently. This mirrors the MCP tool's own internal sequencing (C1) at the skill
  level.
- **OCR only, never correction.** Do not rewrite, "clean up", or paraphrase any transcribed text
  before writing it to the output file, even if it looks garbled. Confidence/notes flags are how
  uncertainty is surfaced — not silent fixes. Any correction pass belongs to a Sonnet-only downstream
  step, never this skill, never Haiku, never Gemini.
- **Honest failure.** A missing credential, an oversized page, or any other tool error is reported
  with the tool's own actionable message — never swallowed, never retried indefinitely.
- **Output never overwrites the source.** Everything lands in `ocr-output/`, never over the original
  file, never inside `.academic-helper/`.
