---
name: The Margin — Academic Writer
version: 1.0
surfaces: [dashboard, site]
register: dashboard = full palette (Operate mode, committed course colour); site = restrained (unchanged)
colors:
  # shared core (derived from site/assets/css/site.css OKLCH values)
  ink: '#151e37'
  ink-2: '#444d61'
  ink-3: '#636975'
  indigo: '#253776'
  indigo-soft: '#dfe8fd'
  verified: '#288463'
  verified-soft: '#d7f3e5'
  rejected: '#c4422c'
  rejected-soft: '#ffe8e2'
  marker: '#f7e59f'
  # dashboard surfaces
  paper: '#f5efe2'
  paper-2: '#ece4d2'
  sheet: '#fffdf8'
  rule: '#d8cfbd'
  sage: '#4f7d68'
  shadow: '#151e37'   # the hard offset shadow colour (dark theme: see dark.shadow)
  # course hues (text-safe: >= 4.5:1 on paper and sheet)
  course-teal: '#167a73'
  course-coral: '#b8492a'
  course-violet: '#6440a0'
  course-blue: '#2d5fb8'
  course-ochre: '#876209'
  course-rose: '#a83a6b'
  course-olive: '#5b6e1f'
  course-slate: '#4a5a78'
dark:
  # dark theme: every text colour >= 5:1 on dark paper; follows prefers-color-scheme, with a nav switch
  # engravings in dark: filter invert(1) hue-rotate(180deg) saturate(.85) brightness(.95); mix-blend-mode screen
  paper: '#14161f'
  paper-2: '#191c27'
  sheet: '#1c1f2b'
  ink: '#e8e4da'
  ink-2: '#a9a69c'
  rule: '#33374a'
  indigo: '#7187d2'
  verified: '#2e9872'
  rejected: '#d86450'
  marker: 'rgba(178,129,12,.45)'
  shadow: '#7187d2'   # the hard offset shadow is drawn in indigo so it stays visible
  course-teal: '#1b9890'
  course-coral: '#d6684a'
  course-violet: '#9678c9'
  course-blue: '#5b87d7'
  course-ochre: '#b2810c'
  course-rose: '#cb6994'
  course-olive: '#799229'
  course-slate: '#778aab'
typography:
  display:   {fontFamily: 'Frank Ruhl Libre', fontSize: 60px, fontWeight: '900', lineHeight: '1.05'}
  h1:        {fontFamily: 'Frank Ruhl Libre', fontSize: 36px, fontWeight: '700', lineHeight: '1.15'}
  h2:        {fontFamily: 'Frank Ruhl Libre', fontSize: 30px, fontWeight: '700', lineHeight: '1.2'}
  h3:        {fontFamily: 'Frank Ruhl Libre', fontSize: 20px, fontWeight: '700', lineHeight: '1.25'}
  lede:      {fontFamily: 'Frank Ruhl Libre', fontSize: 20px, fontWeight: '400', lineHeight: '1.5'}
  body:      {fontFamily: 'IBM Plex Sans Hebrew', fontSize: 16px, fontWeight: '400', lineHeight: '1.6'}
  ui:        {fontFamily: 'IBM Plex Sans Hebrew', fontSize: 14px, fontWeight: '500', lineHeight: '1.4'}
  label:     {fontFamily: 'IBM Plex Sans Hebrew', fontSize: 13px, fontWeight: '600', lineHeight: '1.3'}
  numeral:   {fontFamily: 'Frank Ruhl Libre', fontSize: 72px, fontWeight: '900', lineHeight: '0.9'}
spacing: {s1: 4px, s2: 8px, s3: 12px, s4: 16px, s5: 24px, s6: 32px, s7: 48px, s8: 64px, s9: 96px}
rounded: {none: 0, sm: 2px, md: 4px}
site:
  colors:
    light:
      --paper: 'oklch(0.978 0.004 250)'
      --paper-2: 'oklch(0.955 0.007 255)'
      --ink: 'oklch(0.24 0.05 268)'
      --ink-2: 'oklch(0.42 0.035 265)'
      --rule: 'oklch(0.88 0.012 260)'
      --indigo: 'oklch(0.36 0.11 268)'
      --indigo-soft: 'oklch(0.93 0.03 268)'
      --verified: 'oklch(0.55 0.10 165)'
      --verified-soft: 'oklch(0.94 0.035 165)'
      --rejected: 'oklch(0.56 0.17 32)'
      --rejected-soft: 'oklch(0.95 0.03 32)'
      --on-indigo: 'oklch(0.978 0.004 250)'
      --shadow: '0 1px 2px oklch(0.24 0.05 268 / 0.06), 0 14px 32px -16px oklch(0.24 0.05 268 / 0.22)'
      --plate-filter: 'none'
      color-scheme: 'light'
    dark:
      --paper: 'oklch(0.165 0.02 268)'
      --paper-2: 'oklch(0.205 0.024 268)'
      --ink: 'oklch(0.93 0.01 260)'
      --ink-2: 'oklch(0.74 0.02 262)'
      --rule: 'oklch(0.31 0.025 268)'
      --indigo: 'oklch(0.76 0.09 270)'
      --indigo-soft: 'oklch(0.27 0.05 268)'
      --verified: 'oklch(0.74 0.11 165)'
      --verified-soft: 'oklch(0.27 0.04 165)'
      --rejected: 'oklch(0.72 0.14 35)'
      --rejected-soft: 'oklch(0.28 0.05 32)'
      --on-indigo: 'oklch(0.165 0.02 268)'
      --shadow: '0 1px 2px oklch(0 0 0 / 0.3), 0 14px 32px -16px oklch(0 0 0 / 0.5)'
      --plate-filter: 'brightness(0.92)'
      color-scheme: 'dark'
  fonts:
    --serif: '"Spectral", "Iowan Old Style", Georgia, serif'
    --display: 'var(--serif)'
    --sans: '"IBM Plex Sans", "IBM Plex Sans Hebrew", system-ui, -apple-system, "Segoe UI", sans-serif'
    --mono: '"IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace'
  other:
    --verified-ink: 'color-mix(in oklch, var(--verified) 62%, var(--ink))'
    --rejected-ink: 'color-mix(in oklch, var(--rejected) 62%, var(--ink))'
    --ease: 'cubic-bezier(0.25, 1, 0.5, 1)'
    --bar: '56px'
    --wrap: '1240px'
    --gutter: '16px'
    --term-bg: 'oklch(0.24 0.045 268)'
    --term-fg: 'oklch(0.93 0.01 260)'
    --term-dim: 'oklch(0.72 0.03 262)'
---

# The Margin

Academic Writer's brand. One family, two registers: the **site** (GitHub Pages) stays as it is, restrained and
editorial; the **dashboard** is the same family in a fuller palette for daily work. Hebrew first, right to left.

## 1. Visual theme & atmosphere

A printed academic almanac or a well-made weekly planner: cream paper with grain, newspaper rules and columns,
serif headlines, two-ink engravings of real people studying, and the marks a reader makes in a margin (a red pen
circle, a green tick, a yellow highlighter, a strike). It must never read as a generic SaaS or "AI" dashboard.

Key characteristics: paper not white; rules not boxes; one hard offset shadow per screen at most; colour is ink, not
fill; state is a mark on the text, plus a word.

## 2. Colour palette & roles

| Role | Token | Job |
|---|---|---|
| Text | `ink`, `ink-2`, `ink-3` | body, secondary, tertiary (tertiary only >= 18px or as meta) |
| Interaction | `indigo` | links, the one primary button, focus ring, active nav mark. Nothing else. |
| Verified | `verified` | ready, done, passed citation check (with ✓ and a word) |
| Rejected | `rejected` | missing, overdue, failed check, the countdown numeral (with ✗ or a pen circle and a word) |
| Highlight | `marker` | a highlighter stroke behind one piece of good news per screen |
| Course | `course-*` | identifies a course: its square, its underline, its agenda block, its card spine. Assigned in course order, stable per course. |
| Surfaces | `paper`, `paper-2`, `sheet` | page, recessed band, the one raised card |

Register: dashboard uses **full palette**: course colour may fill agenda blocks and card spines; total coloured fill
stays under 25% of any screen. Course colours never fill page backgrounds or large panels.

## 3. Typography rules

Frank Ruhl Libre for headlines, ledes and numerals; IBM Plex Sans Hebrew for everything interactive and for data.
Scale steps only from the frontmatter table. Body never below 16px; no weight below 400; no bold above 700 except
`display` and `numeral` (900). Tabular numerals for dates, times and counts. `text-wrap: balance` on headings.

## 4. Component stylings

- **Nav**: brand at the start, 2-5 page links; active link = ink colour + 3px `rejected` underline (two cues).
- **Masthead**: date line between a 3px double rule and a 1px rule; `display` greeting; one `lede` sentence that
  carries ink marks.
- **Primary card** (one per screen): `sheet` on paper, 1.5px `ink` border, shadow `6px 6px 0 ink`, radius 0.
- **Ruled columns**: 1.5px `ink` top rule, 1px `rule` dividers, rows with dotted leaders; column head = 12px solid
  course/role square + `h3`.
- **Course card**: `sheet`, 1px `rule` border, 4px course-colour spine on the inline-start edge (the one allowed
  thick edge: it marks identity), radius 4px; title `h3`; links as text buttons with a 16px icon and a word.
- **Buttons**: primary = `ink` fill, `sheet` text, radius 2px; secondary = 1.5px ink outline; tertiary = indigo
  text link. One primary per view.
- **Status**: never a coloured dot alone: glyph + word (`✓ מוכן`, `✗ חסר`, `◐ ממתין`, `⟳ Claude הלילה`).
- **Step bar** (writing runs): equal segments with 1px ink border; done = filled violet, current = hatched, todo = empty.

## 5. Layout principles

Spacing from the scale only; space above a heading exceeds space below. Page gutter 44px desktop, 16px phone.
Max content width 1180px. Grid: 12 columns, 24px gaps. Use `gap`, never child margins.

## 6. Depth & elevation

Level 0 paper; level 1 `sheet` with a 1px rule; level 2 the single primary card with the hard offset shadow. No
blurred shadows, no glass, no glow.

## 7. Do's and don'ts

Do: paper grain; engravings blended with `multiply` (light) or inverted + `screen` (dark); real Hebrew copy; one
marker stroke per screen; course colour consistent everywhere.

Don't: gradients, colour blobs, pastel pill badges, emoji, icon-in-circle grids, nested cards, all-caps, pure
`#000`/`#fff` text, a coloured dot as the only signal, more than one hard shadow per screen, values not in this file.

## 8. Responsive behaviour

Breakpoints 640 / 1024 / 1280. Below 1024: columns stack, masthead art moves under the greeting. Below 640: nav
becomes a bottom bar with 4 icon+word items; tables stay tables (scroll horizontally), never stacked cards.
Touch targets >= 44px. `prefers-reduced-motion`: no motion. Motion otherwise 150-250ms, no load choreography.

## 9. Right to left and Hebrew

`<html lang="he" dir="rtl">`; logical properties only (`inline-start`, `inline-end`); course-card spine on the
inline-start edge (right in Hebrew). Latin names and numbers in `<bdi>`. Hebrew line-height 1.6 for body.
Dates `יום ראשון, 18 באוקטובר`; short `א׳ 25.10`.

## 10. Accessibility

Text contrast >= 4.5:1, large text and UI >= 3:1 (every token above is checked). Focus ring 2px `indigo`, 3px
offset. One `h1` per page, no skipped levels. Skip link first. Usable at 200% zoom.

## 11. Agent prompt guide

Quick reference: paper `#f5efe2`, ink `#151e37`, indigo `#253776`, red ink `#c4422c`, green ink `#288463`, marker
`#f7e59f`; course colours teal, coral, violet, blue, ochre, rose, olive, slate in that order.

Prompt stem for any screen: "Hebrew RTL page in The Margin style: a printed academic almanac on cream paper with
grain, Frank Ruhl Libre headlines, IBM Plex Sans Hebrew UI, newspaper rules and ruled columns, two-ink engravings,
state shown as pen marks plus a word, one primary card with a hard 6px offset ink shadow; no gradients, no pastel
pills, no emoji." Never invent colours, sizes or spacing outside this file; validate generated output against it.
