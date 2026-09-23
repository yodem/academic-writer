---
name: research
description: "Use when investigating a topic or checking claims against indexed sources."
user-invocable: true
allowed-tools: [Bash, Read, AskUserQuestion]
context: fork
model: sonnet
effort: medium
metadata: {author: "Yotam Fromm", version: "0.2.24"}
---

# Research

Running `aw evidence build` and synthesizing its verified passages is the purpose of this skill. Do not replace the evidence extraction command with model memory or an unverified summary.

Read `.academic-helper/profile.md` and the author's intent file. Ask the researcher for a question if no intent or question is available. Prepare an `author-intent.json` with the thesis and must-use passages when needed.

Fetch indexed Candlekeep source IDs from the project profile. For a Sefaria text, pass its reference with `--sefaria`. Run:

```bash
aw evidence build --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" --sources "<ck-id,...>" --intent ".academic-helper/author-intent.json" --run "<run-id>"
```

Include `--sefaria "<ref,...>"` when relevant. Read `.academic-helper/evidence.json` after the command completes. The file contains source metadata and only passages whose quotations passed verbatim verification. Explain which passages support, complicate, or contradict the thesis, and cite their source title and locator. Do not present generated glosses as quotations.

If the command exits with `ERROR` or `CAP_REACHED`, report that result and do not claim the extraction succeeded. Keep the final research summary concise and identify gaps in the available evidence.
