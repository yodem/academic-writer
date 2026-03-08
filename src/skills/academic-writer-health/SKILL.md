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

## 3. Agentic-Search-Vectorless

**Skip if `tools.agentic-search-vectorless.enabled` is false.** Report as "Disabled (enable with `/academic-writer-update-tools`)".

```bash
ls ../Agentic-Search-Vectorless/src 2>/dev/null && echo "REPO_FOUND" || echo "REPO_NOT_FOUND"
```

Report:
- Local repo found at `../Agentic-Search-Vectorless/`? ✓/✗
- If not found: "Clone the repo to `../Agentic-Search-Vectorless/` to enable semantic search."

---

## 4. Candlekeep

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
ls .cognetivy/ 2>/dev/null && echo "DIR_EXISTS" || echo "DIR_MISSING"
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
  - If missing: "Run `cognetivy init` in this directory to initialize the workspace."
- Workspace initialized? ✓/✗
  - If `cognetivy workflow list` errors or shows nothing: "Run `cognetivy init` to initialize."
- Workflow `wf_academic_writer` registered? ✓/✗
- Number of past runs

**Fix instruction** (if not initialized):
> "Cognetivy is not initialized in this directory. Run:
> ```
> cognetivy init
> ```
> Then re-run `/academic-writer-health`."

---

## 7. Agent Files

```bash
ls .claude/agents/*.md 2>/dev/null
```

Verify all required agent files exist:
- `.claude/agents/deep-reader.md` ✓/✗
- `.claude/agents/architect.md` ✓/✗
- `.claude/agents/section-writer.md` ✓/✗
- `.claude/agents/auditor.md` ✓/✗
- `.claude/agents/synthesizer.md` ✓/✗

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
> | Agentic-Search-Vectorless | ✓ Found / ✗ Missing / — Disabled | ../Agentic-Search-Vectorless/ |
> | Candlekeep | ✓ Connected / ✗ Error / — Disabled | [N] items |
> | MongoDB Agent Skills | ✓ Configured / ✗ Missing / — Disabled | Server: [name] |
> | Cognetivy | ✓ Ready / ✗ Not initialized / — Disabled | Run `cognetivy init` if not initialized |
> | Agent Files | ✓ All present / ✗ Missing [list] | 5/5 |
>
> **Overall: [N]/[total] checks passed**

If there are issues, provide specific fix instructions:
> **To fix:**
> 1. [Issue] → [specific command or action]
> 2. [Issue] → [specific command or action]
