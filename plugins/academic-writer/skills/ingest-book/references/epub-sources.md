# EPUB sources skip half of this skill

The bundled scripts are **PDF-only**. When the source is an EPUB — especially a
calibre-produced one — the expensive, error-prone half of the workflow
disappears:

- **`toc.ncx` *is* the ToC tree.** Labels, nesting and anchor targets, already
  faithful. Parse it instead of OCRing ToC pages; the text is born-digital, and
  OCR would only degrade it.
- **Printed pagination is usually absent** — check, don't assume:
  `grep -c 'id="page\|epub:type="pagebreak"' OEBPS/*.html`. When it is absent
  there is no printed→Trove crosswalk and no per-volume offset to discover;
  `build_crosswalk.py` has nothing to do, you choose the page unit yourself,
  and the mapping is exact by construction. When pagebreak anchors *are*
  present (more likely in a publisher-produced EPUB than a calibre one), prefer
  one Trove page per printed page — you get a real crosswalk and citable
  locators for free.

Unzip the EPUB, read `content.opf` for metadata and spine order, then walk
`toc.ncx` in document order. Slice at **anchor ids**, not at heading tags:
chapter navLabels are often bare numbers (`1`, `2`) with no reliable `<h*>` at
that position.

**The spine is the authority on what content exists; the ncx is the authority
on what it is called and how it nests.** Never enumerate pages from the nav
tree alone. Reconcile the two before writing an extractor — one command:

```bash
# every non-footnote spine file, minus every file toc.ncx references.
# NB strip the #fragment — many navPoints target file.html#anchor, and a pattern
# that excludes '#' silently matches none of them and reports false orphans.
comm -23 <(ls OEBPS/*.html | grep -v footnote | xargs -n1 basename | sort) \
         <(grep -o 'src="[^"]*"' OEBPS/toc.ncx | sed 's/src="//; s/"$//; s/#.*//' \
           | xargs -n1 basename | sort -u)
```

Files in that set are usually harmless (half-title, ad card, the EPUB's own
ToC), but any that sits **between** two referenced files in spine order is
producer continuation text with no navPoint of its own, and slicing from the
nav tree will silently drop it.

**A section can span file boundaries.** Producers split XHTML at arbitrary byte
offsets, so a unit runs from its anchor to the *next anchor*, continuing across
into following spine files — it does not end where its file ends. Slicing
anchor→end-of-file keeps only each unit's head. When anchors and file boundaries
disagree, concatenate the whole work's files into one stream in spine order and
split that stream at the anchors. Cheap tell, before you trust either layout:

```bash
# an anchor at 85% of its file means most of that file belongs to the PREVIOUS unit
python3 - <<'EOF'
import re, glob
for p in sorted(glob.glob("OEBPS/*.html")):
    b = open(p, encoding='utf-8', errors='replace').read()
    for m in re.finditer(r'id="(cha\\w+)"', b):
        print("%-40s %5.1f%%  %s" % (p, 100*m.start()/len(b), m.group(1)))
EOF
```

Before uploading, **cross-check the unit count two independent ways** — e.g.
the `toc.ncx` navPoint count minus its non-chapter entries, against the sum of
the book's own front-matter ToC. Two routes agreeing means the nav tree is
complete; a disagreement is worth resolving before you build anything on it.

**Assert conservation of content, with a number.** Structural checks —
page-marker count, no stray `#`, ToC nests correctly — all pass happily on a
truncated book. Strip tags from every spine content file *and* every footnote
file, sum the normalized characters, sum them again over the emitted markdown,
and fail below 99%. This is the single check that catches a wrong slicing
model, and it names the lossy file instead of leaving you to notice a jump
months later. Expect slightly over 100% when you emit footnote markers and
per-page Notes headers.

**Sanitize body lines that begin with `#`** (escape them). Trove splits pages on
top-level `# `, so one stray line silently shifts every later ToC target. Then
assert that the emitted `# ` count equals the page count you expect.

**Point parent ToC entries at their first child page** rather than creating
divider pages — no fabricated filler, and nothing for Trove's blank-page
skipping to desynchronize.

## Take structure from the file, and check the nav tree both ways

An EPUB's `dc:description` is marketing copy and may describe a different
edition than the one in your hands: a description can list the whole corpus of
an author while its own `toc.ncx` and front matter hold a smaller set. Importing
the blurb's structure would assert a completeness the file did not have and
produce empty parts. Take the structure from the nav tree, retitle the book
honestly, and record the discrepancy on page 1.

The nav tree can fail in the opposite direction too, so it is not the last word
on *coverage*. A `toc.ncx` can reference fewer content files than the spine
holds — with orphans sitting inside major works holding the tails of chapters —
and works can run from their anchor across into following files, so
anchor→end-of-file slicing keeps only each part's head. Both faults are
invisible structurally — the build emits every expected page marker with
correct nesting — and together can lose over ten percent of the text. The
character-conservation gate catches it and names the files.

So: **blurb under-claims or over-claims, and the nav tree can under-cover the
spine.** Reconcile spine against ncx, then assert coverage with a number.
