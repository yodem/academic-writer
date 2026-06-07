---
description: Mechanical proofreading (הגהה) pass over a finished article — fixes typos, punctuation, spacing, Hebrew typography, and clear grammar errors, then writes a markdown report documenting every change and why. Suggestion-grade safety: never rewrites prose for style, tone, or voice. Use when an article is drafted and you want a clean copy-edit / proofread (הגהה) before submission, without touching wording or argument.
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, Agent, AskUserQuestion]
---

# Auto-generated from skills/proofread/SKILL.md


# Academic Writer — Proofread (הגהה)

A focused, **mechanical-only** proofreading pass over a finished article. It catches the errors every writing pass misses — typos, punctuation, spacing, broken Hebrew typography, doubled words, clear grammar slips — applies the safe ones to a corrected copy, and writes a report documenting **every change and why**.

It does **not** rewrite prose for style, tone, register, or voice, and it does not restructure. For those, use `/academic-writer:edit`. Think of this as the מגיה's pass, not the editor's.

> **Suggestion-grade safety.** The original file is never modified in place. Mechanical fixes are written to a new `*.proofed.md`; the report records every one with its rationale so you can review it against the corrected copy and revert anything by hand. (One-click accept/reject is the future Option B — DOCX tracked-changes + `/apply`.) Idea-level issues are flagged, never auto-fixed.


## Step 1 — Load profile (optional)

```bash
cat .academic-helper/profile.md 2>/dev/null || echo "MISSING"
```

The profile gives the researcher's primary `targetLanguage` (drives typography rules). If missing, don't block — default language detection to the article's script (Hebrew → RTL/Hebrew typography; Latin → standard orthography) and note in the report that no profile was loaded.

## Step 2 — Resolve the article

If the user passed a path as an argument, use it. Otherwise ask:

> "Which article should I proofread? Give me a path to a `.md` or `.docx` file, or I can use the most recent article in `articles/`."

List candidates:

```bash
ls -t articles/*.md 2>/dev/null | head
```

Establish a single **`PROOF_BASE`** — a plain-text/markdown file that is both what the proofreader reads and what the corrected copy is built from. This is the key safety step: the corrected copy is **never** a copy of a binary source.

- **Markdown / text source** → `PROOF_BASE` is the source itself. Read it with the `Read` tool.
- **.docx source** → extract the text to a real markdown file first (do **not** rely on stdout):
  ```bash
  python3 -c "import docx,sys; d=docx.Document('SOURCE_PATH'); open('articles/FILEBASE.extracted.md','w').write('\n\n'.join(p.text for p in d.paragraphs))"
  ```
  `PROOF_BASE` is `articles/FILEBASE.extracted.md`. A `.docx` source produces a markdown report and a corrected `.md`; it does not round-trip back into Word (that's the future full-port / `/apply` path). The original `.docx` is never touched.

Record `SOURCE_PATH`, `FILEBASE` (the source filename without extension), and `PROOF_BASE`. Determine `LANGUAGE` from the profile's `targetLanguage` if present, else from the article's dominant script.

## Step 3 — Proofread (spawn the מגיה)

**Use the Agent tool to spawn the `proofreader` subagent.** Pass it the full article text with line numbers, `LANGUAGE`, and a `SECTION_LABEL` if you proofread section-by-section.

- Default: one `proofreader` spawn over the whole article — an article is not book-scale.
- Optional optimization for long articles (many `##` sections): split on top-level headings and spawn one `proofreader` per section **in a single message** (concurrency cap 6), each with its own `SECTION_LABEL`. Merge the returned change lists. Do this only if the article is long enough that a single pass would lose fidelity; otherwise keep it to one spawn.

Each spawn returns one JSON object: `{agent, language, changes[], summary}` (schema in `agents/proofreader.md`). Collect all `changes`.

Each change is one of:

| `type` | applied? |
|---|---|
| `typo`, `punctuation`, `word`, `grammar`, `typography` | **mechanical — applied** (subject to the citation-integrity guard below) |
| `idea-flag` | **never applied** — reported only |

## Step 4 — Citation-integrity guard (differential, deterministic)

The proofreader is forbidden from editing inside a citation, quotation, page number, or footnote marker. This step **verifies that invariant was obeyed** — it does not re-audit the article's citations. The question here is *differential* ("did this mechanical fix disturb a citation token?"), not absolute ("are the article's citations sound?"). Re-auditing edited text in isolation would answer the wrong question and would silently drop valid fixes when a paragraph had a pre-existing footnote/anchor issue — so this guard is deterministic and needs no `sources.json`.

**Define citation/quotation tokens** (match against `before` and `after` of each change; extend per the article's `LANGUAGE`):

- Footnote markers and definitions: `[^id]`, `[^id]:`, superscript reference numbers.
- Parenthetical citations: `(Author, 2019, p. 45)` and Hebrew forms (`(כהן, 2019, עמ׳ 45)`); traditional source refs (`בבלי ברכות י, ע״ב`, `בראשית א, א`).
- Quotations: `"…"`, `״…״`, `'…'`, `׳…׳`, block quotes.
- Page numbers / locators: `p. 45`, `pp. 45–47`, `עמ׳ 45`, `ע״א`/`ע״ב`.

**For each mechanical change:** does its `before` snippet (with surrounding context) overlap, or does applying it alter any character *inside*, one of these tokens?

- **No overlap** (the overwhelmingly common case — a typo/punctuation/spacing fix in plain prose) → **apply it.**
- **Overlap** → **do not apply.** Downgrade the change to an `idea-flag` with reason `"touches a citation/quotation token — needs human review"`, and record it in the report's Notes. A fix to a citation token is exactly the kind of change a מגיה must hand to a human, not auto-apply.

(Typography fixes that only normalize a quotation *mark itself* — straight `"` → `״` opening/closing a quotation — are the one expected overlap; treat them as applicable typography, but record them in Notes so the human can confirm the right mark was chosen. Anything that changes text *inside* the quotation is never applied.)

## Step 5 — Apply mechanical fixes to a corrected copy

**If there are zero applicable mechanical changes** (proofreader returned `"changes": []`, or all changes were idea-flags / guard-downgraded): do **not** write a `*.proofed.md`. Skip to Step 6 and report a clean pass. No duplicate file for an already-clean article.

Otherwise seed the corrected copy from **`PROOF_BASE`** (the text the proofreader actually read — never the binary source):

```bash
cp "PROOF_BASE" "articles/${FILEBASE}.proofed.md"
```

Apply each applicable **mechanical** change to `articles/${FILEBASE}.proofed.md` with the `Edit` tool, observing these guards (the apply step is where this feature is most error-prone — typography fixes manipulate exotic/invisible code points: ״ ׳ ־ – U+00A0 U+200F):

1. **Order matters.** Sort changes by `line` (then by offset within the line) and apply **bottom-to-top**, so an earlier edit never shifts the anchor of a later one.
2. **Detect overlap.** If two changes touch the same span (e.g. a quote-mark fix and an NBSP fix in one clause), apply them as a single combined `Edit` (one `before` → one `after` covering both), not two racing edits.
3. **Verify uniqueness before applying.** The `Edit` tool fails on a non-unique match — when that happens, expand the `before` with surrounding context until it matches exactly once. If it still can't be made unique, **skip it** and record "could not localize (ambiguous) — left for manual review" in Notes.
4. **Treat a no-match as a hard skip, never a force.** If `before` does not match (e.g. the proofreader mis-transcribed an exotic glyph), do **not** rewrite by hand — skip the change and record "could not localize (no match) — left for manual review" in Notes. For typography fixes, anchor by `line` + a plain-ASCII neighbour where possible to reduce transcription fragility.

Skip `idea-flag` and guard-downgraded changes — they are never applied. After applying, delete any `*.extracted.md` working file from Step 2.

## Step 6 — Write the change report

Write `articles/${FILEBASE}.proofread.md` documenting **every change and why**. Use the article's language for prose where natural; keep the table readable. Shape:

```markdown
# Proofread report — <FILEBASE>

- Source: `<SOURCE_PATH>`
- Corrected copy: `articles/<FILEBASE>.proofed.md`
- Language: <LANGUAGE> · Profile: <loaded | none>
- Applied: <N> mechanical · Flagged (not applied): <M> idea-level
- Date: <YYYY-MM-DD>

## Applied changes

| # | Line | Level | Type | Before → After | Why |
|---|------|-------|------|----------------|-----|
| 1 | 42 | letter | typo | `המחשבות` → `המחשבות` | doubled ו |
| … | | | | | |

## Idea-level flags (not changed — for your review)

| # | Line | Note |
|---|------|------|
| 1 | 88 | This sentence appears to contradict §2's claim that … |

## Notes

- <citation-integrity guard downgrades, un-localizable snippets (no-match / ambiguous), quotation-mark normalizations to confirm, anything skipped, and why>
```

Every applied row must carry its rationale — that is the deliverable. Idea-flags go only in the second table; they are never in the corrected copy.

## Step 7 — Report to the researcher

If changes were applied:

> "Proofread complete (mechanical only).
> - **Corrected copy:** `articles/<FILEBASE>.proofed.md`
> - **Change report:** `articles/<FILEBASE>.proofread.md`
> - Applied **<N>** mechanical fixes; flagged **<M>** idea-level issues (not changed).
> Your original is untouched. Review the report against the corrected copy and revert any change by hand if you disagree — every change is listed with its rationale."

If it was a clean pass (no applicable changes):

> "Proofread complete — clean pass. No mechanical errors to apply. <M> idea-level note(s) are in `articles/<FILEBASE>.proofread.md` for your review. No corrected copy was written."

## Hard rules

- **Mechanical only.** Typos, punctuation, spacing, typography, clear grammar/agreement. No rephrasing, no register/tone changes, no restructuring — those are `/academic-writer:edit`.
- **Never modify the source file in place.** Corrections go to `*.proofed.md`, seeded from `PROOF_BASE` — never from a binary `.docx`.
- **Idea-flags are never auto-applied** — they live in the report for human decision.
- **Citation-integrity guard is mandatory and deterministic:** any mechanical change that touches a citation/quotation/page/footnote token is **not applied** — it is downgraded to an idea-flag for human review. This guard verifies the proofreader's no-touch invariant; it does not re-audit citations and does not depend on `sources.json`.
- **Every applied change is documented with a rationale** in the report. No silent edits — and a change that can't be localized is skipped and recorded, never forced.
- **Don't create `.academic-helper/`** — all outputs land in `articles/`.
