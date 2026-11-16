# What counts as a stub `AUTHOR_VOICE.md`

> Loaded on demand by `voice` SKILL.md. This is the shared, checkable definition that any other
> gate consuming `AUTHOR_VOICE.md` (e.g. a write-time gate in `write`/`SKILL.md`) should use instead
> of inventing its own heuristic — the deterministic implementation lives in
> `scripts/check-voice-populated.py` (see below) so the definition is enforceable, not just
> documented prose.

## Definition

`AUTHOR_VOICE.md` is a **stub** — i.e. not yet usable to imitate a voice — if it fails to have
**both** of the following:

1. **Template placeholders replaced.** The title line is not the literal
   `# Voice Profile — <writer name>` and the `> Updated` line is not the literal
   `> Updated <YYYY-MM-DD> by <plugin>`. (A file that has never been through `voice-distiller` at
   all still has these literal placeholder tokens.)
2. **Real content in at least one section, past the minimum-content floor.** At least one of the
   four required sections (`## Core voice (cross-project)`, `## Terminology`,
   `## Academic-specific`, `## Non-fiction-book-specific`) contains something other than the
   `_Empty._` placeholder, blank lines, or comment trailers — **and** the total word count of all
   section bodies combined is at least 20 words. (The 20-word floor exists so a single throwaway
   sentence doesn't count as "populated" — it guards the same failure mode as the empty-template
   case, just one step later.)

A file is a **real (non-stub) voice profile** the moment both conditions hold — this does NOT
require all four sections to be populated, and does NOT require any particular session count to
have run. A profile distilled from just session 1 (13 questions) is a real, partial, honestly-labeled
profile, not a stub — see "Marking partial sections" in `SKILL.md`. The bar for "not a stub" is
intentionally low: it means "has been through the pipeline at least once with a real answer in it",
not "is complete."

A **missing** `AUTHOR_VOICE.md` file is treated as a stub (there is nothing to distinguish it from
the empty case for any consumer's purposes).

## Deterministic check script

`scripts/check-voice-populated.py` implements exactly the rule above.

```bash
sh "${CLAUDE_PLUGIN_ROOT}/bin/aw-python" "${CLAUDE_PLUGIN_ROOT}/scripts/check-voice-populated.py" AUTHOR_VOICE.md
```

- Exit code `0` → populated (real, usable voice profile).
- Exit code `1` → stub (missing, untouched template, or below the content floor).
- Exit code `2` → usage error (bad path argument, unreadable/non-UTF-8 file) — distinct from "stub"
  so a caller doesn't silently treat a read error as "no voice profile" and proceed writing
  unvoiced prose.

Add `--json` for a machine-readable reason payload (used by callers that want to explain *why* a
file was flagged, not just whether):

```bash
sh "${CLAUDE_PLUGIN_ROOT}/bin/aw-python" "${CLAUDE_PLUGIN_ROOT}/scripts/check-voice-populated.py" AUTHOR_VOICE.md --json
```

```json
{
  "populated": false,
  "path": "AUTHOR_VOICE.md",
  "reasons": ["placeholder_untouched"],
  "populatedSections": 0,
  "totalWords": 0
}
```

Possible `reasons` values: `"missing"`, `"placeholder_untouched"`, `"all_sections_empty"`,
`"below_minimum_content"`. More than one may be present.

## Who consumes this

- `:voice status` runs the check and shows populated/stub in its summary.
- `:voice recompress` / end-of-session distillation logs the result so the user can see the file
  crossed from stub to real the moment it happens.
- Any write-time gate elsewhere in the plugin that needs to decide whether `AUTHOR_VOICE.md` is
  usable should shell out to this script rather than re-deriving the rule, so the definition never
  drifts between the two skills.
