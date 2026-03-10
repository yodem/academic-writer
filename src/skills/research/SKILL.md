---
name: academic-writer-research
description: "Research a subject or answer questions using your indexed sources — Candlekeep, RAG, and MongoDB. Spawns parallel subagents for speed."
user-invocable: true
allowedTools: [Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion]
agents: [research-rag, research-candlekeep]
---

# Academic Writer — Research

You are a research assistant. The researcher wants to explore their indexed sources, retrieve information, or answer questions — **without writing an article**.

This skill uses whichever data tools are enabled in the profile. It spawns **parallel subagents** to query multiple tools simultaneously for fast results.

## Load Profile & Tools

```bash
cat .academic-writer/profile.json
```

If no profile exists: "Run `/academic-writer:init` first to set up your profile and index your sources."

Read the `tools` object to know which integrations are available.

---

## Understand the Question

If the researcher hasn't stated their question yet, ask:
> "What would you like to research? You can ask a direct question, explore a topic, compare authors, search for quotes, or browse your sources."

Accept any of these forms:

- A direct question: *"What does Foucault say about power in Discipline and Punish?"*
- A topic exploration: *"Show me everything I have on settler colonialism"*
- A comparison: *"Compare how Author A and Author B treat the concept of sovereignty"*
- A source lookup: *"What sources do I have about Ottoman Palestine?"*
- A quote search: *"Find the exact quote where Ben-Gurion talks about..."*

---

## Parallel Research via Subagents

**Speed is critical.** Spawn subagents in parallel to query all enabled tools simultaneously. Do NOT query tools sequentially.

### Determine which subagents to launch

Based on the question and enabled tools, spawn ALL applicable agents **at the same time**:

**Use the Agent tool to spawn subagents in parallel — call the Agent tool multiple times in a single response:**

1. **RAG subagent**: Pass as prompt the question, questionType, sourceIds. This subagent runs multi-mode RAG queries (mix + local + bypass as needed).

2. **Candlekeep subagent** (if `tools.candlekeep.enabled`): Pass as prompt the question, questionType, sourceIds. This subagent searches and reads Candlekeep documents directly.

3. **MongoDB** (if `tools.mongodb-agent-skills.enabled`): Query MongoDB directly inline — lightweight, no subagent needed.

Each subagent runs independently and returns its findings.

### RAG Subagent Instructions

The RAG subagent should:

1. **Classify the question type** and select RAG modes:

| Question type | Queries to run |
|--------------|----------------|
| Direct question | `mix` (broad) + `local` (key entities) |
| Topic exploration | `global` (themes) + `mix` (detail) + `local` (per entity) |
| Comparison | `local` (Author A) + `local` (Author B) + `mix` (topic) |
| Quote search | `bypass` (exact) + `mix` (context) |
| Source lookup | `mix` (topic) |

2. **Run all queries** with `include_context: true`, `top_k: 30`, `rerank_top_k: 10`, `enable_rerank: true`
3. **Return organized passages** with source attribution from the `context` field
4. **Never cite the `answer` field** — only `context`

### Candlekeep Subagent Instructions

The Candlekeep subagent should:

1. **Search** across all sources: `ck items search "QUERY"`
2. **Read relevant documents** for full passages: `ck items read DOC_ID`
3. **Verify page numbers** when exact citations are needed: `ck items read "DOC_ID:PAGE-PAGE"`
4. **Return full text passages** with document ID, title, and page numbers

### MongoDB Queries (inline, no subagent)

If MongoDB is enabled, run directly:
- Search research collections for annotations/notes
- Look up metadata about sources
- Retrieve any stored research data

---

## Merge & Present Findings

Once all subagents return, **merge results** by deduplicating and cross-referencing:

1. If both RAG and Candlekeep found the same passage, use Candlekeep's version (more precise page numbers)
2. If RAG found something Candlekeep didn't, include it with a note that page numbers come from RAG
3. If Candlekeep found full text that RAG summarized, prefer the full text

### For factual questions:

> **Answer:** [Direct answer grounded in sources]
>
> **Sources:**
> - [Author], *[Work]*, p. [page] — "[relevant quote]" *(via Candlekeep/RAG)*
> - [Author], *[Work]*, p. [page] — "[relevant quote]" *(via RAG)*
>
> **Context:** [Brief explanation of how these sources relate]

### For topic explorations:

> **What your sources say about [topic]:**
>
> **1. [Theme/aspect]**
> [Summary with citations]
>
> **2. [Theme/aspect]**
> [Summary with citations]
>
> **Available sources on this topic:**
> - [list of relevant documents from Candlekeep/profile]
>
> **Gaps:** [What your sources don't cover]

### For comparisons:

> **[Author A] vs. [Author B] on [concept]:**
>
> | Aspect | Author A | Author B |
> |--------|----------|----------|
> | ... | ... (with citations) | ... (with citations) |
>
> **Key differences:** ...
> **Points of agreement:** ...

### For quote searches:

> **Found in [Author], *[Work]*, p. [page]:**
> > "[exact quote]"
>
> **Context:** [surrounding text / chapter / argument]
> **Verified:** ✓ Candlekeep page confirmed / ⚠ RAG only (page may need verification)

---

## Cognetivy Logging (if enabled)

Log the research session:
```bash
echo '{"subject": "RESEARCH_TOPIC", "type": "research"}' > /tmp/aw-research-input.json
cognetivy run start --workflow wf_academic_writer --input /tmp/aw-research-input.json
```

Log query results:
```bash
echo '{"type":"step_completed","nodeId":"research","ragQueries":N,"candlekeepReads":N,"totalPassages":N,"toolsUsed":["rag","candlekeep","mongodb"]}' | cognetivy event append --run RUN_ID
```

---

## Follow-up

After presenting findings, ask:
> "Would you like me to:
> - Dig deeper into any of these sources?
> - Search for related topics?
> - Find exact page numbers for any of the citations?
> - Save these findings for use in an article?"

---

## Critical Rules

- **NEVER fabricate citations.** Only cite what RAG or Candlekeep returns.
- **NEVER invent page numbers.** Use `bypass` mode + `ck items read` to verify.
- If a question can't be answered from available sources, say so clearly: "Your indexed sources don't contain information about this. You may need to add more sources via Candlekeep."
- Always show which tool provided each piece of information.
- If a tool is disabled, skip it and note: "I searched [available tools]. Enable [disabled tool] with `/academic-writer:update-tools` for broader coverage."
