---
name: academic-writer-health
description: "Check the health of all Academic Writer integrations — profile, Candlekeep, RAG, MongoDB, Cognetivy, past articles, and source index."
user-invocable: true
---

# Academic Writer — Health Check

Run a comprehensive health check on every component of the Academic Writer system. Report status clearly so the researcher knows what's working and what needs attention.

## 1. Profile Check

```bash
if [ -f .academic-writer/profile.json ]; then
  cat .academic-writer/profile.json
else
  echo "MISSING"
fi
```

If missing: report `FAIL` and suggest `/academic-writer-init`.

If found, validate:
- Has `fieldOfStudy`? ✓/✗
- Has `citationStyle`? ✓/✗
- Has `styleFingerprint`? ✓/✗
- Fingerprint format: is it the expanded (nested) format or the old flat format?
  - If flat format: suggest re-running `/academic-writer-init` to get the expanded 25-dimension fingerprint
- Has `tools` object? ✓/✗
- Has `sources` array? ✓/✗ (and count)
- `createdAt` / `updatedAt` timestamps

---

## 2. Past Articles

```bash
ls past-articles/ 2>/dev/null | head -20
```

Report:
- Folder exists? ✓/✗
- Number of files found
- File types (PDF, DOCX, other)
- If empty: "Add 5–10 published articles for style analysis, then re-run `/academic-writer-init`."

---

## 3. Candlekeep

**Skip if `tools.candlekeep.enabled` is false.** Report as "Disabled (enable with `/academic-writer-update-tools`)".

```bash
command -v ck >/dev/null 2>&1 && echo "CLI: INSTALLED" || echo "CLI: NOT_FOUND"
```

If installed:
```bash
ck items list 2>&1 | head -20
```

Report:
- CLI installed? ✓/✗
- Can connect? ✓/✗
- Number of items in library
- If error: show the error message

---



```bash
```

If healthy, also check:
```bash
```

Report:
- Server running? ✓/✗
- Health status: healthy/degraded/error
- Component status (if available from health response)
- Number of indexed documents (if available from status)
- If not running: show start command:
  ```
  ```

**Test a query** (only if server is healthy):
```bash
  -H "Content-Type: application/json" \
  -d '{"query": "test", "mode": "mix", "top_k": 1, "rerank_top_k": 1, "enable_rerank": false, "include_context": false}'
```

Report: Query endpoint responsive? ✓/✗

---

## 5. MongoDB Agent Skills

**Skip if `tools.mongodb-agent-skills.enabled` is false.** Report as "Disabled".

```bash
(cat ~/.claude/settings.json 2>/dev/null; cat .mcp.json 2>/dev/null) | python3 -c "
import sys, json
found = False
for line in sys.stdin.read().split('}{'):
    try:
        d = json.loads('{' + line.strip('{}') + '}')
        servers = d.get('mcpServers', {})
        for k, v in servers.items():
            if 'mongo' in k.lower():
                found = True
                print(f'Server: {k}')
                print(f'Command: {v.get(\"command\", \"N/A\")}')
    except: pass
if not found:
    print('NOT_CONFIGURED')
"
```

Report:
- MCP server configured? ✓/✗
- Server name and command

---

## 6. Cognetivy

**Skip if `tools.cognetivy.enabled` is false.** Report as "Disabled".

```bash
command -v cognetivy >/dev/null 2>&1 && echo "CLI: INSTALLED" || echo "CLI: NOT_FOUND"
```

If installed:
```bash
ls .cognetivy/ 2>/dev/null
```

```bash
cognetivy workflow list 2>&1 | head -10
```

```bash
cognetivy run list --workflow wf_academic_writer 2>&1 | head -10
```

Report:
- CLI installed? ✓/✗
- `.cognetivy/` directory exists? ✓/✗
- Workflow `wf_academic_writer` registered? ✓/✗
- Number of past runs

---

## 7. Agent Files

```bash
ls agents/*.md 2>/dev/null
```

Verify all required agent files exist:
- `agents/deep-reader.md` ✓/✗
- `agents/architect.md` ✓/✗
- `agents/section-writer.md` ✓/✗
- `agents/auditor.md` ✓/✗
- `agents/synthesizer.md` ✓/✗

---

## Present Results

Show a clean summary table:

> **Academic Writer — Health Report**
>
> | Component | Status | Details |
> |-----------|--------|---------|
> | Profile | ✓ OK / ✗ MISSING | Field: [field], Citation: [style], Sources: [N] |
> | Style Fingerprint | ✓ Expanded / ⚠ Legacy / ✗ Missing | [N] dimensions |
> | Past Articles | ✓ [N] files / ✗ Empty | PDF: [n], DOCX: [n] |
> | Candlekeep | ✓ Connected / ✗ Error / — Disabled | [N] items |
> | MongoDB Agent Skills | ✓ Configured / ✗ Missing / — Disabled | Server: [name] |
> | Cognetivy | ✓ Ready / ✗ Error / — Disabled | [N] past runs |
> | Agent Files | ✓ All present / ✗ Missing [list] | 5/5 |
>
> **Overall: [N]/[total] checks passed**

If there are issues, provide specific fix instructions:
> **To fix:**
> 1. [Issue] → [specific command or action]
> 2. [Issue] → [specific command or action]
