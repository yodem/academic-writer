---
name: voice
description: "Manage the shared author voice store: migrate, choose exemplars, derive writing moves, and sync it. Use when setting up or updating an author's voice profile."
user-invocable: true
disable-model-invocation: true
allowed-tools: [Bash, Read, Write, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "1.0.0"}
---

# Voice store

This skill's purpose is to run `aw` commands that manage the shared voice store in `${CLAUDE_PLUGIN_DATA}/voice`. Always pass both plugin data and project directories because Bash does not receive Claude's plugin variables as environment variables.

## Migrate

Run `aw --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" voice migrate --from "$PWD"`. It reads `AUTHOR_VOICE.md`, `.voice/fingerprint.md`, and `.academic-helper/voice-exemplars.md` and creates the schema-versioned store. Review the result before continuing.

## Choose exemplars

Run `aw --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" voice exemplars --corpus "$PWD/past-articles"`. Show candidates, including their source papers, and ask the author to select the configured 12–20 finished-paper paragraph range from `thresholds.json > voice.selection`. Save only the selected candidates as JSONL records in `voice/exemplars.jsonl`, with stable ids, source paper names, and text. Ask before replacing existing selections.

## Derive moves

Run `aw --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" voice moves --run-id "voice-moves"`. This makes one Gemini Flash call and writes `rules.md`; inspect the returned rules with the author. The file line cap is configured in `thresholds.json > voice.bundle.maxRuleLines`.

## Sync

Run `${CLAUDE_PLUGIN_ROOT}/skills/voice/voice-sync.sh push "${CLAUDE_PLUGIN_DATA}" "$PWD"` to publish local changes to CandleKeep, or `voice-sync.sh pull "${CLAUDE_PLUGIN_DATA}" "$PWD"` only when the author explicitly asks for a pull. The wrapper runs `aw --data-dir … --project-dir … voice push` / `voice pull` with both required paths. Resolve conflicts by comparing `voiceVersion`; retain both change histories by merging `CHANGELOG.jsonl`. Report sync errors as errors. Never copy the store into `$HOME` or another project.
