---
name: update-field
description: "Change the research field recorded in the author's Academic Writer profile, keeping every other setting. Use when the author says their field or specialisation has changed and does not want to redo the full setup (/academic-writer:init)."
user-invocable: false
allowed-tools: [Bash, Read, Write, Edit, AskUserQuestion]
model: haiku
effort: low
metadata: {author: "Yotam Fromm", version: "0.2.23"}
---

# Academic Writer — Update Field of Study

Change the `fieldOfStudy` in `.academic-helper/profile.md` without re-running the full setup. The field steers terminology and examples in later drafts, so record it in the author's own words.

## Load Current Profile

First, check if a profile exists and load it:

```bash
if [ -f .academic-helper/profile.md ]; then
  CURRENT_FIELD=$(python3 -c "
import re
content = open('.academic-helper/profile.md').read()
m = re.search(r'^fieldOfStudy: (.+)$', content, re.MULTILINE)
print(m.group(1).strip() if m else 'Not set')
")
  echo "Current field: $CURRENT_FIELD"
else
  echo "No profile found. Run /academic-writer:init first."
  exit 1
fi
```

## Get New Field

Ask the researcher:
> "What's your new field of study and area of specialization?"
>
> (Current: `$CURRENT_FIELD`)

Record their answer.

## Update Profile

Update the profile's frontmatter (the header block between the `---` lines) with the new field, keeping every other setting intact. Replace `NEW_FIELD_HERE` with the author's answer:

```bash
python3 << 'PYTHON'
import re, json
from datetime import datetime

PROFILE_PATH = '.academic-helper/profile.md'

with open(PROFILE_PATH) as f:
    content = f.read()

# Update fieldOfStudy and updatedAt in frontmatter
new_field = 'NEW_FIELD_HERE'
now = datetime.now().isoformat()

# Replace fieldOfStudy in frontmatter
if re.search(r'^fieldOfStudy: .+$', content, re.MULTILINE):
    content = re.sub(r'^fieldOfStudy: .+$', f'fieldOfStudy: {new_field}', content, flags=re.MULTILINE)
else:
    # Insert after first ---
    content = content.replace('---\n', f'---\nfieldOfStudy: {new_field}\n', 1)

if re.search(r'^updatedAt: .+$', content, re.MULTILINE):
    content = re.sub(r'^updatedAt: .+$', f'updatedAt: {now}', content, flags=re.MULTILINE)
else:
    content = content.replace('---\n', f'---\nupdatedAt: {now}\n', 1)

with open(PROFILE_PATH, 'w') as f:
    f.write(content)

print(f"✓ Field updated to: {new_field}")
PYTHON
```

## Confirm

Tell the author:
> "Done! Your field is now: **[new field]**
>
> Your citation style and writing style remain unchanged.
> Run `/academic-writer:write` anytime to start writing."
