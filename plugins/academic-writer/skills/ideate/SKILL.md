---
name: ideate
description: "Guided brainstorming that turns a vague topic into a sharp research question, using who/what/when/where/why/how, a gap check against the author's sources and a choice of approach; saves a research brief that /academic-writer:write reads. Use when the author has a topic but no clear question or thesis yet. Not for drafting (use /academic-writer:write)."
user-invocable: true
allowed-tools: [Bash, Read, Write, Glob, Grep, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.2.23"}
---

# Academic Writer — Research Ideation

Help the researcher turn a topic into a clear, answerable research question before any writing starts. Work as a thinking partner: propose, ask, and let the researcher choose. The brief you save becomes the starting point of `/academic-writer:write`, so the thesis direction must be in the researcher's own words.

## Load Profile

```bash
cat .academic-helper/profile.md
```

If no profile, tell the researcher to run `/academic-writer:init` first.

Extract `fieldOfStudy`, `targetLanguage`, and `tools` configuration.

## Step 1: Topic Exploration

Ask the researcher in plain conversation (this is an open question, so do not use `AskUserQuestion`, which needs fixed options):

> "What topic or area are you thinking about exploring? This can be vague — we'll sharpen it together."

Show examples relevant to their `fieldOfStudy`:
> "Examples:
> - A specific text or passage you've been thinking about
> - A debate in your field you want to contribute to
> - A concept that seems under-explored
> - Something you noticed in your sources that doesn't fit existing explanations"

---

## Step 2: 5W1H Brainstorming

Apply the 5W1H framework to the topic. Generate questions in `targetLanguage`:

| Dimension | Question | Purpose |
|-----------|----------|---------|
| **What** (מה) | What is the phenomenon, text, or concept? | Define the object of study |
| **Who** (מי) | Who are the key figures, authors, or communities? | Identify actors |
| **When** (מתי) | What is the historical period or textual dating? | Temporal context |
| **Where** (איפה) | What is the geographic, cultural, or textual context? | Spatial/contextual frame |
| **Why** (למה) | Why does this matter? Why now? | Significance and urgency |
| **How** (כיצד) | How does this work? How was it received/transmitted? | Mechanism or process |

Present the brainstorm:
> "Here's a 5W1H exploration of your topic:
>
> **What:** [...]
> **Who:** [...]
> **When:** [...]
> **Where:** [...]
> **Why:** [...]
> **How:** [...]
>
> Which angles interest you most?"


---

## Step 3: Gap Analysis

If Candlekeep is enabled, scan the researcher's library:

```bash
ck items list --json
```

For each source, check its metadata against the topic:
- What has been written about this topic in the researcher's sources?
- What perspectives or arguments are represented?
- What's missing — which angles are NOT covered?

Present the gap analysis:
> "Based on your source library:
>
> **Covered ground:**
> - [Source A] addresses [aspect X]
> - [Source B] discusses [aspect Y]
>
> **Gaps I identified:**
> - No source addresses [aspect Z]
> - The relationship between [X] and [Y] is unexplored
> - [Historical period / figure / concept] is mentioned but never analyzed
>
> These gaps could be fertile ground for a research question."

If CandleKeep is not enabled, ask the researcher which sources they know on the topic and do the gap analysis from their answer. Never invent sources.

---

## Step 4: Approach Framing

Ask which kind of study fits. `AskUserQuestion` allows at most four options and always adds an "Other" choice for free text, so offer these four:

```python
AskUserQuestion(questions=[{
  "question": "What kind of study fits your topic best?",
  "header": "Approach",
  "options": [
    {"label": "Textual analysis", "description": "Close reading of a specific text or corpus to offer a new interpretation"},
    {"label": "Comparative study", "description": "Comparing two or more texts, thinkers or traditions on defined points"},
    {"label": "History or reception", "description": "Tracing how an idea, practice or text developed, or how it was read over time"},
    {"label": "Conceptual analysis", "description": "Defining and analysing a philosophical, theological or cultural concept"}
  ],
  "multiSelect": false
}])
```

If the researcher picks "Other", ask them to describe their method and help frame it.

---

## Step 5: Research Question Formulation

Based on the topic, gaps, and approach, propose 3 structured research questions in `targetLanguage`:

For each question, provide:
1. **The question** — clear, specific, answerable
2. **Thesis direction** — what the likely argument would be
3. **Key sources** — which of the researcher's sources are most relevant
4. **Feasibility** — can this be answered with available sources?

Present and ask:

```python
AskUserQuestion(questions=[{
  "question": "Here are three research questions I've formulated. Which one excites you?",
  "header": "Question",
  "options": [
    {"label": "Question 1", "description": "SHORT_SUMMARY_1"},
    {"label": "Question 2", "description": "SHORT_SUMMARY_2"},
    {"label": "Question 3", "description": "SHORT_SUMMARY_3"},
    {"label": "Refine one", "description": "Tell me which to adjust"}
  ],
  "multiSelect": false
}])
```

The automatic "Other" choice lets the researcher write their own question instead; accept it verbatim.

---

## Step 6: Generate Research Brief

Write a `research-brief.md` file that feeds directly into `/academic-writer:write`:

If `.academic-helper/` does not exist yet, the plugin is not set up in this folder: tell the researcher to run `/academic-writer:setup` first (only setup and init create that folder), and show the brief in the chat meanwhile so nothing is lost.

Otherwise, use the `Write` tool to create `.academic-helper/research-brief.md`:

```markdown
# Research Brief

## Research Question
[The approved question]

## Thesis Direction
[Preliminary thesis statement in the author's words; /write W0 reads this heading as its thesis seed.]

## Approach
[Selected methodology]

## Key Sources
1. [Source with ID] — relevance
2. [Source with ID] — relevance
3. ...

## Gap This Addresses
[What's missing in existing scholarship]

## Scope
- Estimated sections: [N]
- Primary texts: [list]
- Secondary literature: [list]

## 5W1H Summary
- What: [...]
- Who: [...]
- When: [...]
- Where: [...]
- Why: [...]
- How: [...]

---
*Generated by /academic-writer:ideate on [DATE]*
*Feed this into /academic-writer:write to start writing.*
```

## Completion

> "Your research brief has been saved to `.academic-helper/research-brief.md`.
>
> **Research question:** [question]
> **Approach:** [approach]
> **Key sources:** [N] identified
>
> To start writing, run `/academic-writer:write`. The brief will be loaded automatically as a starting point."
