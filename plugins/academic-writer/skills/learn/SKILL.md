---
name: learn
description: "Update the shared author voice store from new papers and author rewrites. Use when new past articles or writing corrections should inform future drafts."
user-invocable: false
allowed-tools: [Bash, Read, Write, Glob, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "1.0.0"}
---

# Learn from new articles

Scan `past-articles/` against `.academic-helper/profile.md`'s `analyzedArticles`. Extract style metrics with `extract-style-metrics.py` and show the diff before updating the project fingerprint.

Refresh voice candidates with `aw --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" voice exemplars --corpus "$PWD/past-articles"`. Show candidate text and source paper. Ask the author to select the configured representative paragraph range from `thresholds.json > voice.selection` from finished papers, then update `${CLAUDE_PLUGIN_DATA}/voice/exemplars.jsonl` with stable ids, source names, and text. Do not silently replace selected exemplars.

Record author rewrites as `{before, after}` rows in `pairs.jsonl`; summarize repeated preferences into `style-words.json` after showing the proposed changes. Push changed store content with `aw --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" voice push`.
