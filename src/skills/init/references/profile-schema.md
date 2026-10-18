# Profile Schema (`.academic-helper/profile.md`)

> Loaded on demand by the `init` and `setup` skills. Do not duplicate this content in SKILL.md.

## Legacy Migration Script

Migrates any legacy profile from `.academic-writer/profile.json` → `.academic-helper/profile.md`.
Run this in Phase 0 before checking for an existing profile:

```bash
python3 << 'PYTHON'
import os, json
from datetime import datetime

old_path = '.academic-writer/profile.json'
new_path = '.academic-helper/profile.md'
if os.path.exists(old_path) and not os.path.exists(new_path):
    with open(old_path) as f:
        p = json.load(f)
    scalar_keys = ['name', 'author_key', 'fieldOfStudy', 'citationStyle', 'targetLanguage', 'updatedAt', 'createdAt']
    list_keys = ['abstractLanguages', 'analyzedArticles']
    json_sections = [
        ('tools', 'Tools'), ('outputFormatPreferences', 'Output Format Preferences'),
        ('styleFingerprint', 'Style Fingerprint'), ('articleStructure', 'Article Structure'),
        ('sources', 'Sources'),
    ]
    lines = ['# Academic Writer Profile', '', '---']
    for k in scalar_keys:
        if k in p and p[k] is not None:
            lines.append(f'{k}: {p[k]}')
    for k in list_keys:
        v = p.get(k) or []
        if not v:
            lines.append(f'{k}: []')
        else:
            lines.append(f'{k}:')
            for item in v:
                lines.append(f'  - {item}')
    lines.append('---')
    lines.append('')
    for k, heading in json_sections:
        if k in p and p[k] is not None:
            lines.extend([f'## {heading}', '', '```json',
                          json.dumps(p[k], indent=2, ensure_ascii=False), '```', ''])
    os.makedirs('.academic-helper', exist_ok=True)
    with open(new_path, 'w') as f:
        f.write('\n'.join(lines))
    print(f"Migrated profile to {new_path}")
PYTHON
```

## `author_key`

`author_key`: kebab-case slug derived from the researcher's full name, stable across projects for
the same author, used to key cross-project Trove voice-profile lookups (see
`${CLAUDE_PLUGIN_ROOT}/skills/voice/voice-sync.sh`). Derived once during `init` Phase 2 Step 1 and confirmed with the
user; should not be changed casually afterward since it identifies the author's Trove
`Voice Profile — <author_key>` book across every project.

## Profile File Format

`.academic-helper/profile.md` uses markdown with YAML frontmatter + JSON sections:

```markdown
# Academic Writer Profile

---
name: FULL_NAME_HERE
author_key: kebab-case-slug
fieldOfStudy: FIELD_HERE
citationStyle: inline-parenthetical
targetLanguage: Hebrew
abstractLanguages:
  - Hebrew
analyzedArticles: []
createdAt: ISO_TIMESTAMP
updatedAt: ISO_TIMESTAMP
---

## Tools

```json
{
  "trove": { "enabled": true },
  "notebooklm": { "enabled": false }
}
```

## Output Format Preferences

```json
{}
```

## Style Fingerprint

```json
{ ... full 25-dimension fingerprint object, including computationalMetrics.frequentTerms (see category B below) ... }
```

## Article Structure

```json
{ ... article structure object ... }
```

## Sources

```json
[]
```

## Gemini

```json
{
  "enabled": true,
  "approvedLanguages": ["Hebrew"],
  "models": {}
}
```
```

`## Gemini` reflects the outcome of `init` Phase 3.5. When the researcher enables Gemini,
`approvedLanguages` is seeded with `targetLanguage` (shown as `["Hebrew"]` above, matching the
`targetLanguage: Hebrew` example earlier in this doc) — Gemini defaults on for the language the
profile is being created for, so projects that never run `/write`'s model-comparison check (e.g.
`proofread`-only or `edit`-only projects) still route to Gemini. `enabled: false` (no
`approvedLanguages`/`models` keys) if the researcher chose "Not now" for Gemini.

### Choosing the model

Every Gemini tool defaults to **`gemini-3.8-flash`**. Three ways to change it, most specific
winning:

| Where | Scope | Example |
|---|---|---|
| `gemini.models.<tool>.model` | one tool | `{"models": {"write_section": {"model": "gemini-3.1-pro-preview"}}}` |
| `gemini.defaultModel` | every tool | `{"defaultModel": "gemini-3.6-flash"}` |
| `GEMINI_DEFAULT_MODEL` env var | every tool, machine-wide | `export GEMINI_DEFAULT_MODEL=gemini-3.6-flash` |

The profile outranks the environment: it is durable, reviewed configuration, while the env var
exists so a machine can set a default before any profile exists. A per-tool entry may set only
`thinking_budget` and inherit the model.

Tool names are `write_section`, `synthesize`, `edit`, `calibrate_sample`, `raw`. **`gemini_ocr` is
not configurable** — it is hard-pinned to `gemini-2.5-flash` because it needs `thinkingBudget: 0`,
which the Pro models reject.

`thinking_budget` keeps working across model generations: for `gemini-3.x` the client maps a budget
onto the API's `thinkingLevel` (`<512` low, `<4096` medium, else high; `-1` is high), and passes it
through as an integer for the 2.5 family.

Check what is published before pinning a version — `gemini-3.8-flash` is currently the newest
stable text model and the only 3.8 build; the newest pro-tier model of any generation is
`gemini-3.1-pro-preview`, which is a preview.

## `sources.json` page maps (`pageMap`)

A footnote names the page printed in the book. The library keeps its own page numbers (Trove's, one per page of the stored text), and a source can say how to get from one to the other with a `pageMap` field on its record in `.academic-helper/sources.json`. `aw library read --printed A-B` uses it; without a usable map, `--printed` stops with an error that asks for `--pages` (the library's own numbers) instead of guessing. Nothing here changes how `--pages` works.

`sources.json` is either an array of records or `{"sources": [...]}`. A record is found by its `sourceId` (or `id`), with or without a `#fragment`. `pageMap` is an object with a `kind`:

| `kind` | Extra fields | Meaning |
|---|---|---|
| `identity` | none | Printed page N is library page N (the book was stored with its printed numbering). |
| `offset` | `trove_minus_printed` (whole number) | Library page = printed page + `trove_minus_printed`. A page that lands below 1 is an error. |
| `crosswalk` | `file` (path under `.academic-helper/`), optional `volume` (default 1), optional `stored_minus_printed` (default 0) | Look the page up in a crosswalk file: `{"volumes": [{"volume": 1, "stored_to_ck": {"<stored page>": <library page>}}]}`. The stored page is the printed page plus `stored_minus_printed`. A page with no entry is an error. The file must stay inside the project folder. |

Examples:

```json
{ "sourceId": "SOURCE_ID", "workTitle": "…", "pageMap": { "kind": "offset", "trove_minus_printed": 12 } }
{ "sourceId": "SOURCE_ID", "workTitle": "…", "pageMap": { "kind": "crosswalk", "file": "crosswalks/SOURCE_ID.json", "volume": 2, "stored_minus_printed": 0 } }
```

Older records may hold `pageMap` as free text (for example a sentence about the offset). That text is kept for people to read, but the library ignores it and warns that it is free text; replace it with one of the shapes above to make `--printed` work for that source.

## 25-Dimension Style Analysis Rubric

Run via voice-miner agent. Dimensions span 8 categories (A–I):

### A. Sentence-Level
1. Average sentence length (mean + range in words)
2. Sentence structure variety (% complex/compound/simple)
3. Common sentence openers (patterns)
4. Passive voice frequency + examples

### B. Vocabulary & Register
5. Vocabulary complexity (simple/moderate/complex/highly-complex)
6. Academic register level + first vs. impersonal person
7. Field-specific jargon (list + how introduced)
8. Hebrew academic conventions (if applicable)
8a. `frequentTerms` — computational (not LLM-scored): the researcher's own top-N high-frequency
    content vocabulary, produced by `extract-style-metrics.py` in Step 1 (count/length from
    `thresholds.json > typography.styleMetrics.topFrequentTermsCount` / `minTermLength`). Carry
    this array through into `computationalMetrics.frequentTerms` in the saved fingerprint
    unchanged — do not re-derive it qualitatively. Used by section-writer to prefer the
    researcher's own established terms over generic phrasing (see
    `write/references/style-fingerprint-rubric.md § Preferred Terminology`).

### C. Paragraph & Argument Structure
9. Paragraph structure pattern (detailed step-by-step)
10. Average paragraph length (words + range)
11. Argument progression (inductive/deductive/other)
12. How evidence is introduced
13. How evidence is analyzed after quoting

### D. Tone & Voice
14. Tone descriptors (5–7 adjectives)
15. Authorial stance + common hedging/asserting phrases
16. Engagement with other scholars

### E. Transitions & Flow
17. Preferred transition phrases (grouped by function: addition, contrast, causation, exemplification, conclusion)
18. Section-level transition patterns

### F. Citation Style & Density
19. Citation density (sparse/moderate/dense + footnotes/paragraph average)
20. Citation integration style
21. Quote length preference

### G. Rhetorical Patterns
22. Rhetorical patterns (3–5 most common)
23. Opening moves (how they start articles)
24. Closing moves (how they end articles)

### H. Representative Excerpts
25. 5 verbatim excerpts (2–3 sentences each) showing: analytical move, argumentative voice, evidence handling, transition style, most distinctive trait

### I. Article Structure Analysis
26. Typical section inventory (in order)
27. Introduction conventions (opening pattern, elements, element order, roadmap?, typical length)
28. Conclusion conventions (opening pattern, elements, restatement?, implications?, closing pattern, typical length)
29. Paragraph formula (topic sentence style, evidence presentation, analysis type, closing move, full sequence)
30. Section transition patterns (bridging style, transitional paragraphs?, explicit signposting?)

## Home folder and workspace fields

The researcher's home folder holds `<home>/.academic-helper/home.md`: the same frontmatter keys as a
profile (`name`, `author_key`, `fieldOfStudy`, `citationStyle`, `targetLanguage`, ...) as the defaults
for every workspace. A workspace's own `.academic-helper/profile.md` overrides them key by key
(and JSON section by JSON section). The resolver is `scripts/home.py`; the pointer to the home is
set with `home.py set`.

A profile written in a workspace may carry these extra frontmatter keys, added by `home.py register`
or by `init`:

| Key | Values | Meaning |
|---|---|---|
| `workspace` | `course`, `project`, `teaching` | What kind of folder this is. Absent means a plain project. |
| `course` | course slug | Which course of the term (only when `workspace` is `course` or `teaching`). |
| `term` | term key | The academic term the course belongs to. |

The workspace list itself lives in `<home>/.academic-helper/workspaces.json`; a workspace whose
folder is moved or deleted stays in the list and is shown as not found.
