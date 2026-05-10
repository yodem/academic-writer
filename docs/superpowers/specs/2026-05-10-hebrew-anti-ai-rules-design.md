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

### Rule 2 — Use the Hebrew word, not the Hebraized form of a foreign word

Add new **Section I — Hebrew Conventions: Real Translation, Not Transliteration**:

> When writing in Hebrew, every name, place, and term must be the **actual Hebrew
> equivalent** as used in Hebrew academic literature — not a phonetic
> Hebraization of the English/foreign form. If you cannot tell which is which,
> ask: "is this word a real Hebrew word that someone reading only Hebrew
> academic prose would recognize, or is it a Hebrew-letter spelling of a foreign
> word?" If the latter, replace it.

This is a **context-aware judgment**, not a regex match. The writer must
understand what the word refers to in context and choose the Hebrew form that
fits that context.

| AI Pattern | Per-article cap | Better |
|---|---|---|
| Phonetic Hebraization of a place/person name that has an established Hebrew form (e.g. `אלפנטינה` for the island known in Hebrew/Aramaic literature as `יב`; `ירמיה` is correct, `ג׳רמייה` would be wrong) | 0 | Use the Hebrew form. If disambiguation for the reader matters, append parens: `יב (Elephantine)`. |
| `יהו` used in context to refer to the God of Israel — even when the surrounding text shows the referent is the deity (e.g. `מקדש יהו`, `הקריבו ליהו`) | 0 | `ה׳` in standard Hebrew academic prose: `מקדש ה׳`, `הקריבו לה׳`. The check is **contextual**: what does the word refer to here? If it refers to God, rewrite. |

**Exceptions (do NOT rewrite):**
1. The substring `יהו` inside a different word whose referent is not God:
   יהו**חנן** (a person), יהו**ד** (a province), יהו**דה** (the kingdom),
   יהו**די** (an adjective). These refer to people/places, not the deity, so
   they stay.
2. Inside a literal quotation from a primary source — preserve verbatim.
3. In an explicit philological/onomastic discussion of the divine name itself.

**Method (for both rules):** the writer reads each candidate token, identifies
the referent from context, and asks "is this the Hebrew word the referent is
actually called in Hebrew academic literature, or did I just respell a foreign
word in Hebrew letters?" If respelled, fix.

### Rule 3 — Citation format in Hebrew prose

Add new **Section J — Hebrew Citation Format (פורמט ציטוט בעברית):**

> When the article language is Hebrew, the entire in-text citation follows
> Hebrew conventions: page marker, range punctuation, and author name.

| AI Pattern | Per-article cap | Better |
|---|---|---|
| `p. N` / `pp. N-M` for page numbers in a Hebrew article | 0 | `עמ' N` / `עמ' N–M` (en-dash for ranges). |
| Year inside in-text citation when the bibliography has only one work by that author (e.g. `Rosenberg 2004, p. 4`) | 0 | Drop the year: `(רוזנברג, עמ' 4)`. Year stays in the bibliography entry. |
| Latin-script author surname inside a Hebrew in-text citation (e.g. `(Rosenberg, עמ' 4)`) | 0 | Hebraize the surname: `(רוזנברג, עמ' 4)`. The bibliography entry retains the original Latin spelling for retrieval. |

**Bibliography vs in-text:** the bibliography entry keeps the original
publication form (`Rosenberg, Stephen G. 2004. "The Jewish Temple at
Elephantine." …`). The in-text citation is fully Hebraized so it reads naturally
inside Hebrew prose.

## Where the Rules Are Enforced

Sections F, I, J are read by section-writer at pipeline step 6 (Anti-AI Check).
That check already iterates the table rows and applies the per-paragraph /
per-article caps. No code change is needed for enforcement — adding the rows to
the reference file is sufficient because step 6 is a generative scan against the
reference, not a fixed list of regexes.

The auditor (citation hard gate) does not need changes. For Rule 3 (citation
format) the auditor should accept either `עמ'` or `p.` as a valid page marker
and either Latin or Hebraized author surname — its job is to verify the page
number matches the source, not the typography. The anti-AI check, not the
auditor, owns Rule 3.

## What This Spec Does NOT Cover

- Pipeline behavior changes (Category B) — section-writer thesis-anchoring,
  write skill confirming word-vs-letter intent, default citation style
  (footnotes vs inline). Out of scope; tracked separately if requested.
- Refactor of memory→reference for other accumulated preferences. Out of scope.
- Equivalent additions to `anti-ai-patterns-english.md`. Out of scope.

## Acceptance

The change is one file edit: appending Sections I and J and adding one row to
Section F in `src/skills/write/references/anti-ai-patterns-hebrew.md`.

A new article in Hebrew that violates any of the three rules should be caught
by the section-writer's step-6 anti-AI check and rewritten before it reaches
the auditor or the .docx render.

No build, hook, or agent code is touched.
