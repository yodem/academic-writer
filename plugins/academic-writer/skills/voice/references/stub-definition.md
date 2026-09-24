# What counts as a populated voice profile

> Loaded on demand by `voice` SKILL.md. This is the shared, checkable definition that any other
> gate consuming the shared voice store or legacy `AUTHOR_VOICE.md` should use instead of inventing
> its own heuristic — the deterministic implementation lives in `scripts/check-voice-populated.py`.

## Definition

The preferred voice store is `${CLAUDE_PLUGIN_DATA}/voice/`. It is considered **populated** when
one of these is true:

1. `profile.json` contains an `authorVoice` string that passes the legacy `AUTHOR_VOICE.md` stub
   check below.
2. `rules.md` and `exemplars.jsonl` are both present and non-empty.

Legacy projects may still pass via `AUTHOR_VOICE.md`. That file is a **stub** if it fails to have
**both** of the following:

1. **Template placeholders replaced.** The title line is not the literal
   `# Voice Profile — <writer name>` and the `> Updated` line is not the literal
   `> Updated <YYYY-MM-DD> by <plugin>`.
2. **Real content in at least one section, past the minimum-content floor.** At least one of the
   four required sections (`## Core voice (cross-project)`, `## Terminology`,
   `## Academic-specific`, `## Non-fiction-book-specific`) contains something other than the
   `_Empty._` placeholder, blank lines, or comment trailers — **and** the total word count of all
   section bodies combined is at least 20 words.

A missing shared store and missing legacy file is treated as a stub. An unreadable/corrupt store or
file is exit 2, so callers fail closed instead of drafting with unverifiable voice state.

## Deterministic check script

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-voice-populated.py" AUTHOR_VOICE.md --data-dir "${CLAUDE_PLUGIN_DATA}"
```

- Exit code `0` → populated (shared store or legacy file is usable).
- Exit code `1` → stub/missing.
- Exit code `2` → usage/encoding/corrupt-store error.

Add `--json` for a machine-readable reason payload:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-voice-populated.py" AUTHOR_VOICE.md --data-dir "${CLAUDE_PLUGIN_DATA}" --json
```

Possible legacy-file `reasons` values include: `"missing"`, `"placeholder_untouched"`,
`"all_sections_empty"`, and `"below_minimum_content"`. Store checks may also report
`"store_incomplete"`.

## Who consumes this

- The `/write` precondition gate.
- `:voice status` and voice maintenance flows when they need a deterministic populated/stub answer.
- Any future write-time gate that needs voice readiness should shell out to this script rather than
  re-deriving the rule.
