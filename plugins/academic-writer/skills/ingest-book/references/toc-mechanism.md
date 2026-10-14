# How Trove's table of contents actually works

Read this if the ToC isn't rendering the way you expect, or before you try to
"fix" navigation by editing page content.

## Two different things are both called "ToC"

1. **Page content** — the markdown you upload. Each `# ` (H1) line starts a new
   Trove page. Headings *inside* a page (`##`, `###`) render as that page's
   internal outline, but they all belong to — and link to — that one page.

2. **ToC metadata** — a separate structured outline attached to the book via
   `trove items enrich <id> --toc '[{"title","page","level"}]'`. This is what draws
   the navigable sidebar tree. Each entry has its own target `page` (a Trove
   page number) and a `level` (1 = top, deeper = more indented).

The sidebar you see is **#2**. It is independent of page headers.

## The trap

A natural first instinct is to write a big, beautiful nested ToC as `##`/`###`
headings on page 1. It looks right in the page, but every entry resolves to
page 1 — because those headings live on page 1. Readers click "Chapter 7" and
land back on the reading guide. Meanwhile pages 2..N each show only their generic
`# original page N` header in the sidebar: a flat, useless list.

**Proof it's metadata, not headers:** inspect any well-formed enriched book
(`trove items toc <id>`). Its content pages can have plain headers like `# עמוד PDF 7`,
yet its sidebar shows Part I → p.6, Chapter 1 → p.8, each jumping to a *different
real page*. That tree comes entirely from the enrich `--toc` metadata.

## The fix

Build a `[{title, page, level}]` array where `page` is the real Trove page
for each unit/section/subsection, and apply it with `trove items enrich`. That is
exactly what `scripts/build_toc_enrich.py` produces and applies.

- `level: 1` — volume / part (and the page-1 reading guide)
- `level: 2` — unit / chapter
- `level: 3` — section, appendix, front/end matter
- `level: 4` — subsection
- `level: 5` — sub-subsection

Levels are presentation only; they don't have to be contiguous, but keeping them
consistent makes the tree readable.

## Mapping printed pages → Trove pages

ToC rows speak in the book's *printed* page numbers. You need Trove page
numbers. Three numbering systems are in play:

- **printed page** — what's printed in the book and listed in the ToC.
- **stored number** — the number you wrote into each `# <label> N` header during
  extraction (usually the PDF page index).
- **Trove page** — Trove's sequential 1..N, which also *skips* any source page
  that cleaned to nothing.

`build_crosswalk.py` derives stored → Trove exactly from the uploaded file.
`build_toc_enrich.py` converts printed → stored via a per-volume `offset` you
discover from anchors, then stored → Trove (interpolating skipped pages).

**Finding the offset:** take a ToC entry with a memorable title and known printed
page (e.g. the first chapter at printed p.15). Read Trove pages until you find that
content (`trove items read <id>:<ck>`); say it's Trove 13 and that page's stored header
is 17. Then `offset = stored - printed = 2`. Verify 2-3 more anchors spread
across the volume (a famous mid-book section, the index) before trusting it. A
confidently-wrong ToC that points everywhere except the right page is worse than
no ToC.

## Applying and verifying

```bash
trove items enrich <id> --toc "$(cat /tmp/toc_enrich.json)" --no-session
trove items toc <id> --no-session      # confirm the nested tree + page targets
```

Known harmless quirk: with non-ASCII descriptions the CLI prints `✓ Enriched`
and then panics on a UTF-8 char-boundary while truncating the description for
display. The metadata is already saved — ignore the panic and trust
`trove items toc`.
