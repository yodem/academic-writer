---
name: academic-writer-update-field
description: "Update your field of study in the Academic Writer profile."
user-invocable: true
---

# Academic Writer — Update Field of Study

Quick update to your research field without re-running the full initialization.

## Load Current Profile

First, check if a profile exists and load it:

```bash
if [ -f .academic-writer/profile.json ]; then
  PROFILE=$(cat .academic-writer/profile.json)
  CURRENT_FIELD=$(echo "$PROFILE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('fieldOfStudy', 'Not set'))")
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

Update the profile JSON with the new field while keeping all other settings intact:

```bash
python3 << 'PYTHON'
import json
from datetime import datetime

# Load existing profile
with open('.academic-writer/profile.json', 'r') as f:
    profile = json.load(f)

# Update field
profile['fieldOfStudy'] = 'NEW_FIELD_HERE'
profile['updatedAt'] = datetime.now().isoformat()

# Save
with open('.academic-writer/profile.json', 'w') as f:
    json.dump(profile, f, indent=2)

print(f"✓ Field updated to: {profile['fieldOfStudy']}")
PYTHON
```

## Confirm

Show the updated profile:
> "Done! Your field is now: **[new field]**
>
> Your citation style and writing style remain unchanged.
> Run `/academic-writer:write` anytime to start writing."
