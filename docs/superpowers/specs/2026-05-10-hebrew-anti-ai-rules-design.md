# Hebrew Anti-AI Rules — Category A Additions

**Date:** 2026-05-10
**Scope:** `src/skills/write/references/anti-ai-patterns-hebrew.md` only.
**Source of feedback:** Live session in `~/dev/bar-ilan/mikdashim` writing on Elephantine/Yev temple.

## Problem

Four Hebrew-language conventions were violated by the writer pipeline and surfaced
only in researcher feedback. The rules currently live in conversation memory, which
makes them consultative — section-writer's anti-AI check (pipeline step 6) does not
gate on them. Per `feedback_enforcement_not_memory.md`, gate-able rules must live in
`anti-ai-patterns-hebrew.md`, not in memory.

## Rules to Add

### Rule 1 — Meta-summary opener for conclusions

Add one row to **Section F** (Editorial Meta-Summary & Unprompted Synthesis):

| `כפי שראינו לאורך המאמר` / `כפי שתואר לעיל` / `כפי שצוין` as a conclusion opener | 0 | Open the conclusion directly with the synthesis: `לסיכום, X…`. No back-reference to the article itself. |

### Rule 2 — Hebrew transliteration of place/person names

Add new **Section I — Hebrew Conventions for Names & Places (תעתיק וכינויים)**:

> When writing in Hebrew, prefer the form used in Hebrew academic literature over a
> phonetic transliteration of a foreign-language form. If a Latin-alphabet form is
> needed for reader identification, place it in parentheses after the Hebrew form.

| AI Pattern | Per-article cap | Better |
|---|---|---|
| Phonetic transliteration of a place/person name that has an established Hebrew form (e.g. `אלפנטינה` for the island known in Hebrew/Aramaic literature as `יב`) | 0 | Use the Hebrew form: `יב`. If disambiguation matters, append parens: `יב (Elephantine)`. |

**Detection guidance for the section-writer / anti-AI check:**
- Build a small lookup of known cases derived from the deep-reader's source map.
  When the deep-reader encounters a name with both forms in sources, it should
  flag the canonical Hebrew form for the writers to use.
- The auditor should treat use of the foreign form when a Hebrew form exists in
  the same source as a citation/style violation.

### Rule 3 — Name of God

Add to **Section I**:

| AI Pattern | Per-article cap | Better |
|---|---|---|
| `יהו` as a standalone reference to God | 0 | `ה׳` in standard Hebrew academic prose. |

**Exceptions (do NOT rewrite):**
1. Inside personal names: יהו**חנן**, יהו**שפט**, יהו**ד** (the kingdom/province), יהו**דה**, יהו**די**, etc. The pattern is "standalone token", not "any occurrence of the substring".
2. Inside a literal quotation from a primary source — preserve source verbatim.
3. In an explicit philological/onomastic discussion of the divine name itself.

**Detection rule for the writer / anti-AI check:** match `יהו` only when it is a
complete word (preceded and followed by whitespace, punctuation, or string
boundary). Substring matches inside larger words are exempt.

### Rule 4 — Citation format in Hebrew prose

Add new **Section J — Hebrew Citation Format (פורמט ציטוט בעברית):**

> When the article language is Hebrew, in-text citations follow Hebrew
> typographic conventions.

| AI Pattern | Per-article cap | Better |
|---|---|---|
| `p. N` / `pp. N-M` for page numbers in a Hebrew article | 0 | `עמ' N` / `עמ' N–M` (en-dash for ranges). |
| Year inside in-text citation when the bibliography has only one work by that author (e.g. `Rosenberg 2004, p. 4`) | 0 | Drop the year: `(Rosenberg, עמ' 4)`. Year stays in the bibliography entry. |

**Note on author name script:** the rule does NOT mandate Hebraizing the author's
surname. `(Rosenberg, עמ' 4)` is correct — the author appears as printed in their
original publication; only the page reference is Hebraized.

## Where the Rules Are Enforced

Sections F, I, J are read by section-writer at pipeline step 6 (Anti-AI Check).
That check already iterates the table rows and applies the per-paragraph /
per-article caps. No code change is needed for enforcement — adding the rows to
the reference file is sufficient because step 6 is a generative scan against the
reference, not a fixed list of regexes.

The auditor (citation hard gate) does not need changes for Rules 1–3. For Rule 4
(citation format) the auditor should accept either `עמ'` or `p.` as a valid page
marker — its job is to verify the page number matches the source, not the
typography. The anti-AI check, not the auditor, owns Rule 4.

## What This Spec Does NOT Cover

- Pipeline behavior changes (Category B) — section-writer thesis-anchoring,
  write skill confirming word-vs-letter intent, default citation style
  (footnotes vs inline). Out of scope; tracked separately if requested.
- Refactor of memory→reference for other accumulated preferences. Out of scope.
- Equivalent additions to `anti-ai-patterns-english.md`. Out of scope.

## Acceptance

The change is one file edit: appending Sections I and J and adding one row to
Section F in `src/skills/write/references/anti-ai-patterns-hebrew.md`.

A new article in Hebrew that violates any of the four rules should be caught by
the section-writer's step-6 anti-AI check and rewritten before it reaches the
auditor or the .docx render.

No build, hook, or agent code is touched.
