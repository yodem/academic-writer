---
name: learn
description: "Refresh the author's voice store from newly added past articles and from the author's own rewrites of drafts. Use when the author adds finished papers to past-articles/ or says future drafts should learn from their corrections. Not for first-time voice setup (use /academic-writer:voice)."
user-invocable: false
allowed-tools: [Bash, Read, Write, Glob, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "1.0.0"}
---

# Learn from new articles

Keep the author's voice store current. Show every proposed change before saving it: the voice store shapes every future draft, so the author must recognise what goes into it.

## 1. Find new papers

Compare the files in `past-articles/` with the `analyzedArticles` list in `.academic-helper/profile.md`. For each new paper, run `${CLAUDE_PLUGIN_ROOT}/scripts/extract-style-metrics.py` and show the author how the style metrics differ from the current fingerprint before you update it.

## 2. Refresh exemplar paragraphs

Run:

```bash
aw --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" voice exemplars --corpus "$PWD/past-articles"
```

Show each candidate paragraph with the paper it came from. Ask the author to choose the number of paragraphs set in `thresholds.json > voice.selection`, taken from finished papers only. Save the chosen ones to `${CLAUDE_PLUGIN_DATA}/voice/exemplars.jsonl` with a stable id, the source paper name and the text. Never replace an exemplar the author selected earlier without asking.

## 3. Record the author's rewrites

Save each author rewrite as a `{before, after}` row in `pairs.jsonl`. When the same preference shows up repeatedly, propose a summary for `style-words.json`, show it, and save it only after the author agrees.

## 4. Sync

Publish the changed store:

```bash
aw --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" voice push
```

Report any sync error as an error; do not say the store was saved if the push failed.
