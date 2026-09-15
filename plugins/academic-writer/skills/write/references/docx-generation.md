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

Write the article data to a JSON file, then run the standalone DOCX generator script:

1. **Write the article JSON** using the Write tool to `/tmp/aw-article-data.json`. Use this exact schema — do NOT write inline Python to construct it:

```json
{
  "title": "ARTICLE_TITLE from synthesizer",
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
    "aiUseDeclaration": "string or null -- if omitted, a default disclosure sentence is used"
  },
  "abstract": {
    "primary": "Abstract text in targetLanguage (from Step 8.5)",
    "secondary": "Optional abstract in second language, or null"
  },
  "sections": [
    {
      "title": "Section title",
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
    "bodySize": 11,
    "titleSize": 16,
    "headingSize": 13,
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
- Populate `sections` from the synthesizer output — each section's title and paragraph list
- Paragraphs use the structured form `{text, footnotes[]}`. Strip the parenthetical citations out of `text` and move each citation into `footnotes[]` with `after` set to a unique substring in `text` where the marker should appear. The DOCX generator renders them as native Word footnotes (superscript in body, text at page bottom). Plain strings are still accepted for backward compatibility (no footnotes)
- Dependency: requires `lxml` (`pip install lxml`) in addition to `python-docx`
- Read `outputFormatPreferences` from the profile and fill in the `format` object
- Set `totalWords` to the actual word count (controls section title visibility — hidden when under 1500 words)
- Set `isRtl` based on `targetLanguage` (true for Hebrew, false for English)
- `pageSize` is `"A4"` (default) or `"Letter"`; python-docx's bundled template defaults to US Letter, which is wrong for the Israeli academic documents this plugin targets, so leave `pageSize` unset unless the researcher specifically wants Letter
- `margins` is a plain number interpreted per `marginsUnit` (`"in"` default, or `"cm"`) — passing a centimetre value with the unit left at the "in" default produces oversized margins on a narrowed text column; set `marginsUnit: "cm"` explicitly whenever `margins` is a centimetre value

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
