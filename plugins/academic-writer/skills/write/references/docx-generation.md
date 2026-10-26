# DOCX Generation Detail (Step 9)

> Read this when you reach Step 9 (DOCX Output) in SKILL.md — it has the exact markdown structure,
> the DOCX JSON schema, and the closing report template.

## Step 9a: Markdown Output

Use the `Write` tool to write the article as markdown to `$MD_PATH`. Structure:

```markdown
# ARTICLE_TITLE

*ARTICLE_THESIS*

## תקציר

[Abstract text from Step 8.5]

[If dual-language: second abstract under its own heading]

## Section Title (only if totalWords > 1500)

Paragraph 1 text with inline citations...

Paragraph 2 text...

## Next Section Title

...
```

**Rules:**
- Title as `# H1`, thesis as italic line below it
- Section headings as `## H2` — but only include them if `totalWords > 1500` (same rule as DOCX)
- Paragraphs separated by blank lines
- Keep all inline citations exactly as they appear (e.g., `(Author, Title, p. N)`)
- No extra formatting beyond what the article text already contains

## Step 9b: DOCX Output — article JSON schema

`aw docx` (W6 in SKILL.md) builds this JSON from the synthesized drafts in code, writes it to `.academic-helper/runs/<id>/article.json` and runs `scripts/generate-docx.py` for you. The schema below is what it writes; use it only to read or check that file, or when you must regenerate a Word file by hand with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/generate-docx.py" --input <article.json> --output <file.docx>`. Keep any hand-written JSON inside the project (never `/tmp`), so the run's files stay together.

1. **Article JSON schema**:

```json
{
  "title": "ARTICLE_TITLE",
  "thesis": "ARTICLE_THESIS or null",
  "coverPage": {
    "university": "string or null",
    "faculty": "string or null",
    "department": "string or null",
    "title": "string or null -- falls back to the top-level article title if omitted",
    "author": "string or null",
    "studentId": "string or null",
    "supervisor": "string or null",
    "course": "string or null",
    "date": "string or null -- caller supplies a formatted date; this script does not compute one",
    "aiUseDeclaration": "string or null -- if omitted, a default disclosure sentence is used",
    "layout": "compact (default) or labeled -- optional, see the cover rules below",
    "labels": {"author": "caller-supplied label line", "supervisor": "...", "course": "..."},
    "titleSize": 18,
    "detailSize": 14
  },
  "abstract": {
    "primary": "Abstract text in targetLanguage (from Step 8.5)",
    "secondary": "Optional abstract in second language, or null"
  },
  "sections": [
    {
      "title": "Section title",
      "level": 1,
      "kind": "bibliography (optional; a section titled ביבליוגרפיה / Bibliography / References is detected anyway)",
      "subsections": [{ "title": "Sub-section title (Heading 2)", "paragraphs": ["..."] }],
      "paragraphs": [
        {
          "text": "Paragraph body with NO inline parenthetical citations.",
          "footnotes": [
            { "after": "substring in text to anchor the superscript marker", "text": "Author, Title (Pub, 2024), p. 42." }
          ]
        }
      ]
    }
  ],
  "format": {
    "font": "from profile.outputFormatPreferences.font or David",
    "latinFont": "Times New Roman",
    "bodySize": 11,
    "titleSize": 16,
    "headingSize": 13,
    "heading1Size": 14,
    "heading2Size": 12,
    "headingStyles": true,
    "sectionStartsNewPage": true,
    "toc": "auto",
    "noteDirection": "auto",
    "coverUnnumbered": true,
    "lineSpacing": 1.5,
    "pageSize": "A4",
    "margins": 1.0,
    "marginsUnit": "in",
    "isRtl": true
  },
  "totalWords": 0
}
```

**Rules:**
- Use the `Write` tool to write this file — never use Python heredoc or `python3 -c` to construct JSON (Hebrew text causes UTF-8 encoding errors in heredocs)
- `coverPage` is entirely optional — omit the key (or leave it `null`) for no cover page at all; when present, only its populated fields render, each skipped field renders nothing (no stray "None" or empty line). When present, a page break always separates the cover page from the article title, which starts fresh on the next page
- Populate `sections` from the synthesized `drafts/<unitId>.md` files (W5 in SKILL.md) — each section's title and paragraph list
- Paragraphs use the structured form `{text, footnotes[]}`. Strip the parenthetical citations out of `text` and move each citation into `footnotes[]` with `after` set to a unique substring in `text` where the marker should appear. The DOCX generator renders them as native Word footnotes (superscript in body, text at page bottom). Plain strings are still accepted for backward compatibility (no footnotes)
- Dependency: requires `lxml` (`pip install lxml`) in addition to `python-docx`
- Read `outputFormatPreferences` from the profile and fill in the `format` object
- Set `totalWords` to the actual word count (controls section title visibility — hidden when under 1500 words)
- Set `isRtl` based on `targetLanguage` (true for Hebrew, false for English)
- `pageSize` is `"A4"` (default) or `"Letter"`; python-docx's bundled template defaults to US Letter, which is wrong for the Israeli academic documents this plugin targets, so leave `pageSize` unset unless the researcher specifically wants Letter
- The layout conventions in the next section (fonts, note direction, heading styles, TOC, cover numbering, one page per section) are generator defaults; each has a `format` option so an old caller can opt out
- `margins` is a plain number interpreted per `marginsUnit` (`"in"` default, or `"cm"`) — passing a centimetre value with the unit left at the "in" default produces oversized margins on a narrowed text column; set `marginsUnit: "cm"` explicitly whenever `margins` is a centimetre value

## Layout conventions (generator defaults)

These come from a professional editor's review of a Hebrew seminar paper (author decisions of 2026-10-26). Each is on by default and has a `format` option that turns it off.

| Convention | Default behaviour | Opt out / tune |
|---|---|---|
| Dashes and quotes | The renderer never converts them. The spaced em dash is the Hebrew dash for an aside; Hebrew quotations keep the straight `"`; typed gershayim (e.g. תנ״ך) stays. Typography is fixed upstream, not here. | none (nothing to switch) |
| Fonts | `font` (David) is the document default in every font slot, the Heading and TOC styles, and every RTL run. A Latin-dominant paragraph that is LTR (an English bibliography entry, an English footnote, a URL line) uses `latinFont` for its Latin text; Hebrew words inside it are split into their own RTL runs and stay David. An RTL paragraph, including a Hebrew-leading note with a long English title, is David throughout, so a Latin word or number inside a Hebrew sentence never switches font mid-line. Word chooses the font slot from the run's `w:rtl` flag, not from the character, so document-level slots (`ascii` = Times New Roman, `cs` = David) alone do not give this result; that was rendered and rejected. | `latinFont`: another font, or `null`/`""` for David everywhere |
| Direction of notes and bibliography | Follows the FIRST strong character, not the majority script. A footnote or bibliography paragraph that starts with Latin is LTR (`w:bidi val=0`, left aligned, runs without `w:rtl`); a Hebrew-leading one stays RTL even if it holds a long English title. Body paragraphs are never flipped. | `noteDirection: "document"` |
| Headings | Real Heading 1 (14 pt, bold, black, document font) and Heading 2 (12 pt, bold) styles on every heading, including מבוא, so Word can collect them. Heading 2 comes from `subsections` (or a flat entry with `"level": 2`). Abstract headings stay plain bold paragraphs. | `headingStyles: false` (plain bold `headingSize` paragraphs), `heading1Size`, `heading2Size` |
| Section titles | Hidden at or under 1500 words, as before. Consecutive entries with the same title (the intro, body and conclusion units `aw docx` emits) are merged into one section with one heading. An empty title renders no heading. | `showSectionTitles: true/false` |
| New page per section | `pageBreakBefore` is part of the Heading 1 style. No blank paragraphs. The first Heading 1 breaks only when real front matter (an abstract or the TOC) precedes it; with only the title block before it, the section starts on the title page so no page is empty. | `sectionStartsNewPage: false` |
| Table of contents | A real Word `TOC \o "1-2" \h \z \u` field under a bold 14 pt heading (`tocTitle`, default תוכן העניינים), with `w:updateFields` in settings.xml so Word refreshes it on open. | `toc`: `"auto"` (default), `true`, `false` |
| Cover page numbering | With a cover page: `pgNumType start=0`, `titlePg`, and an empty first-page footer with no PAGE field, so the cover is unnumbered and the next page is 1. No cover: normal numbering from 1. | `coverUnnumbered: false` |
| Cover layout | `coverPage.layout: "labeled"`: bold title at `titleSize` (18), then a label line followed by a value line for author, supervisor and course at `detailSize` (14); the student ID joins the author line in parentheses. Labels are supplied by the caller in `coverPage.labels`; the plugin hard-codes none. The default `"compact"` layout is the previous one. | `layout` |

**TOC page numbers are not computed.** python-docx cannot paginate, so the TOC field is written with the heading titles as its cached result and no page numbers. The `updateFields` setting makes Word ask to update fields when the file is opened; accepting fills in the page numbers and links. Until then (or in a viewer that does not update fields) the contents list shows titles only. Never tell the researcher the page numbers are already filled in.

**`toc: "auto"` rule.** A TOC is built when the section headings are shown (see the 1500-word rule above, or `showSectionTitles`) AND the article has a cover page OR more than 3 top-level sections (`TOC_SECTION_THRESHOLD` in generate-docx.py). With a cover, the TOC gets its own page right after it and the article title starts the next page; without a cover, it follows the title and abstract, before the first section. `headingStyles: false` disables the TOC, because the field collects Heading styles.

The section-break and TOC layout is checked in `tests/test_docx_editor_conventions.py`.

## Closing report template

Report to researcher:
> "Done! Your article has been saved to:
> - `articles/FILEBASE.docx` (formatted document)
> - `articles/FILEBASE.md` (markdown)
>
> Word count: [N] words
> Citations: [N] ([citationStyle] format)
> Sections: [N]
> Language: [targetLanguage]
>
> Quality checks applied per paragraph:
> - Style fingerprint compliance: avg [N]/5 score, [N] adjustments
> - Hebrew grammar: [N] issues fixed
> - Language purity: [N] foreign-term violations fixed
> - Repetition: [N] instances fixed
> - Citation audits: [N] claims verified, [N] rejections resolved
>
