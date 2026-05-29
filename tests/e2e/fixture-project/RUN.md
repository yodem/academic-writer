# Dual-Path E2E Run Brief

Both runs use the SAME pinned inputs below so the only variable is the engine. Outputs go to
`tests/e2e/fixture-project/out/gemini/` and `.../out/fallback/`.

## Pinned inputs (identical for both runs)

- **Subject:** תפיסת הזמן אצל אוגוסטינוס וההד שלה אצל ריקר
- **Target language:** Hebrew
- **Citation style:** inline-parenthetical
- **Sources:** pre-seeded in `.academic-helper/sources.json` (skip deep-reader — sources already mapped)
- **Thesis:** see `evidence-ownership.json > thesisAnchor`
- **Outline (3 sections):**
  1. מבוא — הצגת אפוריית הזמן והתזה (owner of `aug-confessions-bk11`)
  2. הזמן כחוויה נפשית אצל אוגוסטינוס (develops `aug-confessions-bk11`)
  3. סיכום — ההד אצל ריקר והרחבת ההשלכות (owner of `ricoeur-time-narrative`)

## Path A — WITH Gemini

Prereq: `/reload-plugins` so `mcp__gemini-api__*` is connected. Run `/write` with `geminiFallback=false`.
The `section-writer` routes Skills 1–7 through `gemini_write_section`; the auditor (Claude) gates each
paragraph; `synthesizer` routes prose through `gemini_synthesize`.

## Path B — WITHOUT Gemini (fallback)

Run `/write` with `geminiFallback=true` (or with the Gemini tool unavailable). The `section-writer`
runs the in-context Skills 1–7 pipeline; the auditor gate is identical.

## Pass criteria

- Both produce a 3-section Hebrew article, all paragraphs auditor-PASS.
- Citations resolve only to `sources.json` entries; metadata never invented.
- Diff the two: confirm both are valid Hebrew; note stylistic differences (expected) but equivalent
  structure and citation integrity (required).
