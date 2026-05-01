---
name: ideate
description: "Guided research ideation — brainstorm research questions using 5W1H, gap analysis, and structured framing. Outputs a research brief that feeds into /academic-writer:write. Use when you have a vague topic and need help framing a research question."
user-invocable: true
allowedTools: [Bash, Read, Write, Glob, Grep, AskUserQuestion]
---

# Academic Writer — Research Ideation

Guided ideation flow that helps researchers formulate strong research questions before writing.

## Load Profile

```bash
cat .academic-helper/profile.md
```

If no profile, tell the researcher to run `/academic-writer:init` first.

Extract `fieldOfStudy`, `targetLanguage`, and `tools` configuration.

## Step 1: Topic Exploration

Ask the researcher:

```python
AskUserQuestion(questions=[{
  "question": "What topic or area are you thinking about exploring? This can be vague — we'll sharpen it together.",
  "header": "Step 1 — Topic Exploration",
  "options": []
}])
```

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

If Agentic-Search-Vectorless is enabled, query for the topic:

```bash
bash plugins/academic-writer/scripts/vectorless-query.sh --query "TOPIC_DESCRIPTION" --mode global --top-k 30
```

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

Log:

---

## Step 4: Approach Framing

Present Humanities-appropriate research approaches:

```python
AskUserQuestion(questions=[{
  "question": "What kind of study fits your topic best?",
  "header": "Step 4 — Research Approach",
  "options": [
    {
      "label": "Textual Analysis",
      "description": "Close reading of a specific text or corpus",
      "markdown": "```\nTextual Analysis\n────────────────\nFocus: One or more primary texts\nMethod: Close reading, literary/philological analysis\nOutput: New interpretation or reading\nBest for: Discovering meaning in texts\n```"
    },
    {
      "label": "Comparative Study",
      "description": "Comparing two or more texts, figures, or traditions",
      "markdown": "```\nComparative Study\n─────────────────\nFocus: Two+ texts, thinkers, or traditions\nMethod: Systematic comparison on defined axes\nOutput: Reveals connections or tensions\nBest for: Cross-cultural or cross-period analysis\n```"
    },
    {
      "label": "Historical Survey",
      "description": "Tracing the development of an idea, practice, or text over time",
      "markdown": "```\nHistorical Survey\n─────────────────\nFocus: An idea or practice across time\nMethod: Chronological analysis with sources\nOutput: Developmental narrative\nBest for: Showing change over time\n```"
    },
    {
      "label": "Conceptual Analysis",
      "description": "Analyzing a philosophical, theological, or cultural concept",
      "markdown": "```\nConceptual Analysis\n───────────────────\nFocus: A concept or term\nMethod: Definition, usage mapping, critical analysis\nOutput: Clarified or redefined concept\nBest for: Philosophical and theological work\n```"
    },
    {
      "label": "Reception History",
      "description": "How a text or idea was received, interpreted, and transformed",
      "markdown": "```\nReception History\n─────────────────\nFocus: How a text was read across generations\nMethod: Track interpretive traditions\nOutput: Map of readings and their contexts\nBest for: Exegetical and hermeneutical studies\n```"
    },
    {
      "label": "Other",
      "description": "Describe your own approach",
      "markdown": "```\nCustom Approach\n───────────────\n→ Describe your methodology\n→ I'll help frame it\n```"
    }
  ],
  "multiSelect": false
}])
```

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
  "header": "Research Questions",
  "options": [
    {"label": "Question 1", "description": "SHORT_SUMMARY_1"},
    {"label": "Question 2", "description": "SHORT_SUMMARY_2"},
    {"label": "Question 3", "description": "SHORT_SUMMARY_3"},
    {"label": "I want to refine one", "description": "Tell me which to adjust"},
    {"label": "None — let me describe my own", "description": "Free-text input"}
  ],
  "multiSelect": false
}])
```

---

## Step 6: Generate Research Brief

Write a `research-brief.md` file that feeds directly into `/academic-writer:write`:

```bash
mkdir -p .academic-helper
```

Use the `Write` tool to create `.academic-helper/research-brief.md`:

```markdown
# Research Brief

## Research Question
[The approved question]

## Thesis Direction
[Preliminary thesis statement]

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

Log completion:

## Completion

> "Your research brief has been saved to `.academic-helper/research-brief.md`.
>
> **Research question:** [question]
> **Approach:** [approach]
> **Key sources:** [N] identified
>
> To start writing, run `/academic-writer:write`. The brief will be loaded automatically as a starting point."
