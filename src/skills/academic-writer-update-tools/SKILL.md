---
name: academic-writer-update-tools
description: "Add, remove, or reconfigure integrations (Candlekeep, Vectorless, MongoDB, Cognetivy)"
user-invocable: true
allowedTools: [Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion]
---

# Academic Writer — Update Tools

Modify which integrations are enabled without re-running the full initialization.

## Load Current Profile

```bash
if [ -f .academic-writer/profile.json ]; then
  cat .academic-writer/profile.json
else
  echo "No profile found. Run /academic-writer-init first."
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

```bash
```

**3. MongoDB Agent Skills** (`mongodb-agent-skills`)
```bash
(cat ~/.claude/settings.json 2>/dev/null; cat .mcp.json 2>/dev/null) | python3 -c "
import sys, json
found = False
for line in sys.stdin.read().split('}{'):
    try:
        d = json.loads('{' + line.strip('{}') + '}')
        servers = d.get('mcpServers', {})
        if any('mongo' in k.lower() for k in servers):
            found = True
    except: pass
print('DETECTED' if found else 'NOT_DETECTED')
"
```

**4. Cognetivy** (`cognetivy`)
```bash
command -v cognetivy >/dev/null 2>&1 && echo "DETECTED" || echo "NOT_DETECTED"
```

## Present Current State

Show a table with current status and detection:

> "Here are your current tool integrations:
>
> | # | Tool | Currently | Detected | Setup |
> |---|------|-----------|----------|-------|
> | 1 | Candlekeep | ✓ Enabled / ✗ Disabled | ✓ / ✗ | https://github.com/romiluz13/candlekeep |
> | 3 | MongoDB Agent Skills | ✓ Enabled / ✗ Disabled | ✓ / ✗ | https://github.com/romiluz13/mongodb-agent-skills |
> | 4 | Cognetivy | ✓ Enabled / ✗ Disabled | ✓ / ✗ | Built-in (.cognetivy/) |
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
import json
from datetime import datetime

with open('.academic-writer/profile.json', 'r') as f:
    profile = json.load(f)

# Update tools — replace TOOL_CONFIG with actual selections
profile['tools'] = TOOL_CONFIG
profile['updatedAt'] = datetime.now().isoformat()

with open('.academic-writer/profile.json', 'w') as f:
    json.dump(profile, f, indent=2)

print("Tools updated successfully.")
PYTHON
```

Replace `TOOL_CONFIG` with the actual tools dict, e.g.:
```json
{
  "candlekeep": { "enabled": true, "version": "detected" },
  "mongodb-agent-skills": { "enabled": true, "version": "detected" },
  "cognetivy": { "enabled": true, "version": "detected" }
}
```

## Confirm

> "Done! Your tools are now:
>
> [list each tool with ✓/✗ status]
>
> These changes take effect immediately for `/academic-writer`.
> If you enabled Candlekeep and haven't indexed sources yet, run `/academic-writer-init` to add them."
