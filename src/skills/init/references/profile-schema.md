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
    scalar_keys = ['fieldOfStudy', 'citationStyle', 'targetLanguage', 'updatedAt', 'createdAt']
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

## Profile File Format

`.academic-helper/profile.md` uses markdown with YAML frontmatter + JSON sections:

```markdown
# Academic Writer Profile

---
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
  "candlekeep": { "enabled": true },
  "agentic-search-vectorless": { "enabled": true, "port": 8000 },
  "notebooklm": { "enabled": false }
}
```

## Output Format Preferences

```json
{}
```

## Style Fingerprint

```json
{ ... full 25-dimension fingerprint object ... }
```

## Article Structure

```json
{ ... article structure object ... }
```

## Sources

```json
[]
```
```

## 25-Dimension Style Analysis Rubric

Run via style-miner agent. Dimensions span 8 categories (A–I):

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
