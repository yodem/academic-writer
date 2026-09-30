---
name: voice
description: "Build or update the author's voice profile: import older voice files, choose exemplar paragraphs from past papers, derive writing rules and sync them to CandleKeep. Use when the author sets up their voice for the first time, /write reports the voice profile is missing, or the author wants drafts to sound more like them. Not for routine learning from new papers (the learn step handles that)."
user-invocable: true
disable-model-invocation: true
allowed-tools: [Bash, Read, Write, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "1.0.0"}
---

# Voice store

Run the `aw voice` commands that manage the author's shared voice store in `${CLAUDE_PLUGIN_DATA}/voice`. Every draft is written to sound like this store, so the author approves what goes into it. Always pass both `--data-dir` and `--project-dir`: Bash does not receive Claude's plugin variables as environment variables, so the command cannot find them on its own.

Explain each step to the author in one plain sentence before you run it.

## Migrate

Run `aw --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" voice migrate --from "$PWD"`. It reads any existing `AUTHOR_VOICE.md`, `.voice/fingerprint.md` and `.academic-helper/voice-exemplars.md` and creates the versioned store. Review the result with the author before continuing.

## Choose exemplars

Run `aw --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" voice exemplars --corpus "$PWD/past-articles"`. If `past-articles/` is missing or empty, stop and ask the author to copy 3 or more of their published articles (.docx, .pdf, .md or .txt) into a `past-articles` folder inside this project, then run this command again. Show each candidate paragraph with its source paper. Ask the author to pick the number of finished-paper paragraphs set in `thresholds.json > voice.selection` (12 to 20 by default). Save only the chosen ones as JSONL records in `voice/exemplars.jsonl`, each with a stable id, the source paper name and the text. Ask before replacing earlier selections.

## Derive moves

Run `aw --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" voice moves --run-id "voice-moves"`. This makes one Gemini call and writes `rules.md`, a short list of the author's characteristic writing moves. Go through the rules with the author and adjust any they do not recognise. The maximum number of lines is set in `thresholds.json > voice.bundle.maxRuleLines`.

## Sync (only with CandleKeep)

Skip this section unless the profile has CandleKeep enabled (`candlekeep.enabled: true`); without it, the store in the plugin data folder is the only copy, and uninstalling the plugin without `--keep-data` deletes it — say so once.

Run `${CLAUDE_PLUGIN_ROOT}/skills/voice/voice-sync.sh push "${CLAUDE_PLUGIN_DATA}" "$PWD"` to save local changes to CandleKeep. Run `voice-sync.sh pull "${CLAUDE_PLUGIN_DATA}" "$PWD"` only when the author explicitly asks for a pull, because a pull replaces local changes. The wrapper runs `aw --data-dir … --project-dir … voice push` / `voice pull` with both required paths.

- Resolve conflicts by comparing `voiceVersion`, and keep both change histories by merging `CHANGELOG.jsonl`.
- Report sync errors as errors.
- Never copy the store into `$HOME` or into another project; the store belongs to this author's plugin data only.
