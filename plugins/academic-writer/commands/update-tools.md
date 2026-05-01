---
description: Add, remove, or reconfigure integrations (Candlekeep, Vectorless, NotebookLM)
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion]
---

# Auto-generated from skills/update-tools/SKILL.md


# Academic Writer — Update Tools

Modify which integrations are enabled without re-running the full initialization.

## Load Current Profile

```bash
if [ -f .academic-helper/profile.md ]; then
  cat .academic-helper/profile.md
else
  echo "No profile found. Run /academic-writer:init first."
  exit 1
fi
```

Parse the current `tools` object from the profile. If the profile has no `tools` key (legacy profile), treat all tools as not configured.

## Tool Registry

Run detection for every tool in the registry, regardless of current status:

**1. Candlekeep** (`candlekeep`)
```bash
command -v ck >/dev/null 2>&1 && echo "DETECTED" || echo "NOT_DETECTED"
```

**2. Agentic-Search-Vectorless** (`agentic-search-vectorless`)
```bash
curl -s --max-time 3 http://localhost:8000/health 2>/dev/null && echo "DETECTED" || echo "NOT_DETECTED"
```

**4. NotebookLM** (`notebooklm`)
```bash
command -v nlm >/dev/null 2>&1 && nlm login --check 2>/dev/null && echo "DETECTED" || echo "NOT_DETECTED"
```

## Present Current State

Show a table with current status and detection:

> "Here are your current tool integrations:
>
> | # | Tool | Currently | Detected | Setup |
> |---|------|-----------|----------|-------|
> | 1 | Candlekeep | ✓ Enabled / ✗ Disabled | ✓ / ✗ | https://github.com/romiluz13/candlekeep |
> | 2 | Agentic-Search-Vectorless | ✓ Running / ✗ Not running | ✓ / ✗ | localhost:8000 |
> | 4 | NotebookLM | ✓ Enabled / ✗ Disabled | ✓ / ✗ | https://github.com/jacob-bd/notebooklm-mcp-cli |
>
> What would you like to change? You can:
> - **Enable** a tool by number or name (I'll help install if not detected)
> - **Disable** a tool by number or name
> - Say **'done'** when finished"

## Process Changes

For each tool the user wants to **enable**:
1. If not detected, show the setup URL and walk them through installation
2. Re-run the detection command to confirm
3. Only mark as enabled once detected

For each tool the user wants to **disable**:
1. Mark it as disabled immediately
2. Warn if it affects existing sources: "Note: disabling Candlekeep won't delete your indexed sources, but new source management will need to be done manually."

## Save Updated Profile

Update ONLY the `tools` key and `updatedAt` in the profile. Preserve all other fields:

```bash
python3 << 'PYTHON'
import re, json
from datetime import datetime

PROFILE_PATH = '.academic-helper/profile.md'

with open(PROFILE_PATH) as f:
    content = f.read()

# Parse frontmatter scalars and lists
profile = {}
fm_match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
if fm_match:
    fm_text = fm_match.group(1)
    i, fm_lines = 0, fm_text.split('\n')
    while i < len(fm_lines):
        line = fm_lines[i]
        kv = re.match(r'^([\w-]+): (.+)$', line)
        ko = re.match(r'^([\w-]+):\s*$', line)
        if kv:
            k, v = kv.group(1), kv.group(2).strip()
            profile[k] = None if v == 'null' else ([] if v == '[]' else v)
            i += 1
        elif ko and i + 1 < len(fm_lines) and fm_lines[i + 1].startswith('  - '):
            k = ko.group(1)
            items = []
            i += 1
            while i < len(fm_lines) and fm_lines[i].startswith('  - '):
                items.append(fm_lines[i][4:])
                i += 1
            profile[k] = items
        else:
            i += 1

# Parse JSON sections
for m in re.finditer(r'^## (.+?)\n+```json\n(.*?)\n```', content, re.MULTILINE | re.DOTALL):
    heading = m.group(1).strip().lower().replace(' ', '')
    try:
        parsed = json.loads(m.group(2))
        mapping = {'tools': 'tools', 'stylefingerprint': 'styleFingerprint',
                   'sources': 'sources', 'articlestructure': 'articleStructure',
                   'outputformatpreferences': 'outputFormatPreferences'}
        if heading in mapping:
            profile[mapping[heading]] = parsed
    except Exception:
        pass

# Update tools — replace TOOL_CONFIG with actual selections
profile['tools'] = TOOL_CONFIG
profile['updatedAt'] = datetime.now().isoformat()

# Write profile.md
scalar_keys = ['fieldOfStudy', 'citationStyle', 'targetLanguage', 'updatedAt', 'createdAt']
list_keys = ['abstractLanguages', 'analyzedArticles']
json_sections = [
    ('tools', 'Tools'), ('outputFormatPreferences', 'Output Format Preferences'),
    ('styleFingerprint', 'Style Fingerprint'), ('articleStructure', 'Article Structure'),
    ('sources', 'Sources'),
]
lines = ['# Academic Writer Profile', '', '---']
for k in scalar_keys:
    if k in profile and profile[k] is not None:
        lines.append(f'{k}: {profile[k]}')
for k in list_keys:
    v = profile.get(k) or []
    if not v:
        lines.append(f'{k}: []')
    else:
        lines.append(f'{k}:')
        for item in v:
            lines.append(f'  - {item}')
lines.extend(['---', ''])
for k, heading in json_sections:
    if k in profile and profile[k] is not None:
        lines.extend([f'## {heading}', '', '```json',
                      json.dumps(profile[k], indent=2, ensure_ascii=False), '```', ''])

with open(PROFILE_PATH, 'w') as f:
    f.write('\n'.join(lines))

print("Tools updated successfully.")
PYTHON
```

Replace `TOOL_CONFIG` with the actual tools dict, e.g.:
```json
{
  "candlekeep": { "enabled": true, "version": "detected" },
  "agentic-search-vectorless": { "enabled": true, "port": 8000 },
  "notebooklm": { "enabled": true, "version": "detected" }
}
```

## Confirm

> "Done! Your tools are now:
>
> [list each tool with ✓/✗ status]
>
> These changes take effect immediately for `/academic-writer:write`.
> If you enabled Candlekeep and haven't indexed sources yet, run `/academic-writer:init` to add them."
