---
description: Capture researcher feedback on a completed article and turn it into concrete improvements — article edits, profile updates, new anti-AI pattern entries, pattern-cap adjustments, and session memory. Use after the researcher reviews an article produced by /academic-writer.
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion, Agent]
---

# Auto-generated from skills/feedback/SKILL.md


# Academic Writer — Feedback

You capture what the researcher thinks of a finished article and convert each piece of feedback into a **targeted change**: to the article, to her profile, to the plugin's pattern references, or to the feedback log that future sessions read.

**This is not a free-form chat.** Your job is:
1. Identify the article she's giving feedback on.
2. Collect feedback through a structured interview (one topic at a time).
3. Classify every item into one of the five action categories below.
4. Apply the change, or stage it, with her confirmation.
5. Log the session.

Never summarize feedback without acting on it.

## Action Categories

| Category | What it touches | Example |
|----------|-----------------|---------|
| **A. Article edit** | The finished article file in `articles/` | "Section III repeats Text 360 — consolidate" |
| **B. Profile update** | `.academic-helper/profile.md` — fingerprint, preferences, article structure, targetLanguage, abstractLanguages, outputFormatPreferences | "My paragraphs should be shorter by default" |
| **C. Pattern reference update** | `plugins/academic-writer/skills/write/references/anti-ai-patterns-${language}.md` — add/adjust pattern caps | "'I suggest that' appeared too often — lower the cap to 2" |
| **D. Source registry fix** | `.academic-helper/sources.json` — correct a bibliographic metadata field | "Cohen 2019 should be 2018 — fix the registry so future runs use the right year" |
| **E. Memory / known-issue note** | Writes to `.academic-writer/feedback/YYYY-MM-DD-<article-slug>.md` AND the session memory system. Use for observations that don't fit A–D but should carry forward. | "I don't like em-dashes in my writing, ever" |

Every feedback item must land in exactly one category — if it's ambiguous, pick the most specific applicable one.

## Load Profile

```bash
cat .academic-helper/profile.md
```

If the profile doesn't exist, tell the researcher: "Please run `/academic-writer:init` first — there's no profile yet to update."

Capture `targetLanguage` — you'll need it when editing the pattern reference.

## Phase 1 — Identify the Article

Ask:
> "Which article would you like to give feedback on?"

Use `AskUserQuestion` with options listed from the `articles/` directory:

```bash
ls articles/*.md 2>/dev/null | head -20
```

If multiple `.md` files exist, present the most recent ones as options plus an "Other path / paste a file path" option. If only one exists, confirm it's the one.

Once chosen, load the artifacts:

```bash
# The article text
cat articles/<slug>.md
```

```bash
# The bibliographic registry for this run
cat .academic-helper/sources.json 2>/dev/null || echo "[]"
```

```bash
# The evidence ownership map for this run
cat .academic-helper/evidence-ownership.json 2>/dev/null || echo "{}"
```

```bash
# The most recent Cognetivy run for this article, if available
cognetivy run list --limit 5 2>/dev/null
```

If Cognetivy is enabled and a matching run is found, pull its events — they show what each pipeline gate flagged and fixed, which is useful context when the researcher says "why did it keep using X?"

## Phase 2 — Structured Interview

Walk the researcher through four topic blocks, one at a time. For each block, use `AskUserQuestion` to prompt — then use free-text follow-up to capture the specifics. **Do not** ask all four blocks at once.

### Block 1: Structure

> "How did the article's structure feel? (outline, section distribution, intro/conclusion conventions)"

Options:
- "Structure was good" — skip to next block
- "Section distribution was off" — ask which sections felt wrong and how she'd redistribute
- "Intro/conclusion conventions missed the mark" — ask what she expected
- "Something else about structure" — free text

### Block 2: Prose Quality

> "How did the written prose feel? (voice match, verbosity, repetition, rhythm)"

Options:
- "Prose was good" — skip
- "Didn't match my voice" — ask which sections/paragraphs felt off and what her voice sounds like there
- "Too verbose / too repetitive" — ask for specific examples; if she names phrases ("I suggest that…", "I do not address here…"), these are candidates for Category C pattern-cap adjustments
- "Paragraphs too long / too short" — candidate for Category B profile update
- "Something else about prose" — free text

### Block 3: Citations

> "Were the citations correct? (author, title, year, journal, page accuracy)"

Options:
- "All citations were correct" — skip
- "Some citations had wrong metadata" — ask which citation(s), which field is wrong, and what the correct value is. Each one is a Category D source registry fix.
- "Some claims weren't cited" — Category A article edit
- "Inconsistent citation format" — Category A article edit + possibly Category B profile preference
- "Something else about citations" — free text

### Block 4: Anything else

> "Anything else you want to flag about this article or about the plugin's behavior?"

Free text. Classify each mentioned item.

## Phase 3 — Classify and Confirm

For every feedback item gathered, draft a table showing:

| # | Feedback item | Category | Proposed change |
|---|---------------|----------|-----------------|
| 1 | "'I suggest that' appears 12 times" | C — Pattern cap | Lower cap in anti-ai-patterns-english.md from 3 to 2 |
| 2 | "Cohen 2019 should be 2018" | D — Source registry | Update sources.json entry for Cohen to year=2018, confidence=high |
| 3 | "Paragraph 4 of Section II is way too long" | A — Article edit | Split the paragraph at the second sentence break |
| 4 | "I never want em-dashes" | E — Memory / profile | Add to profile preferences + feedback log |

Show this table to the researcher and ask (AskUserQuestion, multiSelect=true):

> "Which of these would you like me to apply now?"

Options are the numbered items from the table. She may deselect items or add notes. Items she doesn't select are still logged to the feedback file (Phase 4) but not applied.

## Phase 4 — Apply Changes

Execute each confirmed item.

### A. Article edit

Use `Edit` on `articles/<slug>.md`. Prefer the narrowest surgical edit. For larger restructuring (multiple paragraph rewrites, section splits), suggest running `/academic-writer:edit-section` afterward rather than doing it all in this skill.

### B. Profile update

Use `Edit` on `.academic-helper/profile.md`. Common fields:
- `paragraphStructure.length.mean` / `.stdev` — paragraph length preferences
- `toneAndVoice.descriptors` — voice adjustments
- `preferences.typography` — e.g., "never use em-dashes"
- `abstractLanguages` — which languages to emit abstracts in
- `outputFormatPreferences.font` / `.bodySize` / etc.

If the change touches the style fingerprint broadly, consider spawning the `style-miner` subagent instead of editing by hand:

> The style-miner can re-scan `past-articles/` and recompute the fingerprint. Use it when the feedback is "the voice was generically off" rather than a specific dimension.

Spawn via the Agent tool with `subagent_type: style-miner` if applicable.

### C. Pattern reference update

Compute the language suffix:
```bash
LANG_LOWER=$(python3 -c "import json, re; p=open('.academic-helper/profile.md').read(); m=re.search(r'targetLanguage[\"\\s:]+([A-Za-z]+)', p); print((m.group(1) if m else 'hebrew').lower())")
REF_FILE="plugins/academic-writer/skills/write/references/anti-ai-patterns-${LANG_LOWER}.md"
```

Use `Edit` on `$REF_FILE` to:
- Lower a pattern's per-article cap (e.g., "I suggest that…" from 3 to 2)
- Add a new pattern row to the appropriate table (Formulaic Hedging / Author-Voice / Meta-Scholarship / Inflated Transitions / Inflated Language / Structural Tells)
- Add a new before/after example if the researcher gave concrete examples

New pattern entries should follow the existing table format: **AI Pattern | Per-article cap | Better**.

If the reference file doesn't exist for this language, create it by mirroring the structure of `anti-ai-patterns-hebrew.md` or `anti-ai-patterns-english.md`.

### D. Source registry fix

Read `.academic-helper/sources.json`, find the entry matching the author + work title the researcher named, update the incorrect field, and set that field's `extractionConfidence` to `"high"` (the researcher has verified it manually). Write back with the Write tool.

Example:
```json
{
  "sourceId": "cohen_2018_title",
  "author": "Cohen",
  "workTitle": "...",
  "year": "2018",
  "extractionConfidence": { "year": "high", ... },
  "extractionNotes": "year corrected from 2019 by researcher feedback on 2026-04-16"
}
```

Also: if the article text itself contains the wrong year inline, fix it with `Edit` on `articles/<slug>.md`. Don't leave the article out of sync with the corrected registry.

### E. Memory / known-issue note

For items that don't fit A–D (general preferences, process observations, things to watch for next time), write to the feedback log AND to session memory.

Feedback log path:
```
.academic-writer/feedback/YYYY-MM-DD-<article-slug>.md
```

Create the directory if needed. Append an entry with the date, the item, and the category. If a feedback file for this article already exists, append to it rather than overwriting.

For session memory (the auto-memory system at `~/.claude/projects/-Users-yotamfromm-dev-Academic-Helper/memory/`), write a `feedback_*.md` file only for items that represent **persistent preferences** worth carrying across sessions — not one-off fixes. Examples worth a memory entry:
- "Never use em-dashes anywhere"
- "Abstracts should always be both Hebrew and English"
- "For Bible articles, always cite the Hebrew chapter/verse first, then the English translation"

Never create a memory file for a one-off article edit or a specific citation fix — those belong only in the feedback log.

## Phase 5 — Log & Summary

Always write the per-article feedback log (Phase 4.E path), even if every item was Category A–D and applied cleanly. The log captures the full session for future reference. Schema:

```markdown
# Feedback — <article-slug> — YYYY-MM-DD

## Items

1. **[Category X] Feedback item text**
   - Decision: applied / deferred / noted
   - Change: one-line description of the change made
   - File: path/to/file (if applicable)

2. ...

## Researcher notes

[Free-text notes the researcher added during the interview, verbatim]
```

Then show a summary to the researcher:

> "Feedback processed.
> - Applied: N items (A: N, B: N, C: N, D: N, E: N)
> - Deferred: N items (logged to `.academic-writer/feedback/<file>.md`)
> - Memory entries added: N
>
> Next runs of `/academic-writer` will pick up all profile and pattern changes automatically. For the article itself, the edits have been written to `articles/<slug>.md` — you may want to regenerate the .docx by running the last step of `/academic-writer` or edit and re-export manually."

If Cognetivy is enabled, log the feedback session:
```bash
echo '{"type":"feedback_session","data":{"article":"<slug>","itemsTotal":N,"itemsApplied":N,"byCategory":{"A":N,"B":N,"C":N,"D":N,"E":N}}}' | cognetivy event append
```

(No dedicated workflow is required — this is a freestyle event.)

## Rules

- **Never silently batch changes.** Every applied change must be confirmed by the researcher in Phase 3, and every applied change must be reflected either in the summary or the feedback log.
- **Never edit the article to hide a symptom** if the root cause belongs in the profile or pattern reference. If both an article fix and a profile update are warranted, do both — the article fix addresses the current draft, the profile update prevents recurrence.
- **Never guess at a Category D fix.** If the researcher doesn't give you the correct value for a metadata field, do NOT update the registry — just log it as a Category E "verify this later" note.
- **Never mark a `[NEEDS REVIEW: <field>]` tag as resolved without an explicit correction.** The researcher must give you the correct value or tell you the current value is confirmed.
- **Respect the plugin-router.** If the researcher's feedback crosses into territory handled by another slash command (e.g., wholesale style re-learning → `/academic-writer:learn`), say so and offer to hand off rather than duplicating that skill's work.
