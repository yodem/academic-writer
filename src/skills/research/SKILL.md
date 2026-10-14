---
name: research
description: "Investigate a topic or check a claim against the author's indexed sources, returning only passages whose quotations were verified word for word. Use when the author asks what their sources say about something, or wants evidence for or against a thesis. Not for framing a question from scratch (use /academic-writer:ideate)."
user-invocable: true
allowed-tools: [Bash, Read, AskUserQuestion]
context: fork
model: sonnet
effort: medium
metadata: {author: "Yotam Fromm", version: "0.2.24"}
---

# Research

Run `aw evidence build` and summarise the verified passages it returns. Do not answer from memory or from an unverified summary instead: the author may quote what you report, so every quotation must come from the verified evidence file.

## 1. Prepare

1. Read `.academic-helper/profile.md` and, if it exists, `.academic-helper/author-intent.json`.
2. If there is no intent file and no question, ask the author what they want to find out.
3. When needed, write `.academic-helper/author-intent.json` with the thesis (in the author's words) and any passages the author says must be used.
4. Take the indexed Trove source ids from the project profile. For a Sefaria text, pass its reference with `--sefaria`. If a source the author wants is not yet in Trove, point them at the ingest skills before continuing: a single article or chapter → `/academic-writer:ingest`, a whole book (multi-volume, scanned, EPUB, 100+ pages) → `/academic-writer:ingest-book`; they upload it with its printed page numbers preserved.

## 2. Extract evidence

```bash
aw evidence build --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" --sources "<ck-id,...>" --intent ".academic-helper/author-intent.json" --run "<run-id>"
```

Add `--sefaria "<ref,...>"` when relevant. If the command exits with `ERROR` or `CAP_REACHED` (the run's cost cap was reached), report that and do not claim the extraction worked.

## 3. Report

Read `.academic-helper/evidence.json`. It holds the source details and only those passages whose quotations matched the source exactly.

- Say which passages support, complicate or contradict the thesis, citing each by source title and locator (page or section).
- Present the model's glosses as your summary, never as quotations.
- Keep the summary short and name the gaps: what the available sources do not cover.
