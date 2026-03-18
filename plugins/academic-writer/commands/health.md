---
description: Check the health of all Academic Writer integrations — profile, Candlekeep, RAG, Cognetivy, past articles, and source index.
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Auto-generated from skills/health/SKILL.md


# Academic Writer — Health Check

Run a comprehensive health check on every component of the Academic Writer system. Report status clearly so the researcher knows what's working and what needs attention.

## 1. Profile Check

```bash
if [ -f .academic-helper/profile.md ]; then
  cat .academic-helper/profile.md
else
  echo "MISSING"
fi
```

If missing: report `FAIL` and suggest `/academic-writer:init`.

If found, validate:
- Has `fieldOfStudy`? ✓/✗
- Has `citationStyle`? ✓/✗
- Has `styleFingerprint`? ✓/✗
- Fingerprint format: is it the expanded (nested) format or the old flat format?
  - If flat format: suggest re-running `/academic-writer:init` to get the expanded 25-dimension fingerprint
- Has `tools` object? ✓/✗
- Has `sources` array? ✓/✗ (and count)
- `createdAt` / `updatedAt` timestamps


## 2. Past Articles

```bash
ls past-articles/ 2>/dev/null | head -20
```

Report:
- Folder exists? ✓/✗
- Number of files found
- File types (PDF, DOCX, other)
- If empty: "Add 5–10 published articles for style analysis, then re-run `/academic-writer:init`."


## 3. Agentic-Search-Vectorless

**Skip if `tools.agentic-search-vectorless.enabled` is false.** Report as "Disabled (enable with `/academic-writer:update-tools`)".

Check port 8000 first (default):
```bash
curl -s --max-time 3 http://localhost:8000/health 2>/dev/null && echo "RUNNING" || echo "NOT_RUNNING"
```

- If `RUNNING`: service is available. ✓
- If `NOT_RUNNING`: check if a custom port is saved in `profile.tools.agentic-search-vectorless.port`. If a custom port is stored, retry with that port:
  ```bash
  curl -s --max-time 3 http://localhost:<CUSTOM_PORT>/health 2>/dev/null && echo "RUNNING" || echo "NOT_RUNNING"
  ```
- If still not running: ask the researcher: "Agentic-Search-Vectorless is not responding on port 8000. What port is it running on? (Or press Enter to skip this check.)"
  - If they provide a port: retry the curl with that port, then save it to `profile.tools.agentic-search-vectorless.port`
  - If they skip: report as ✗ Not running

Report:
- Service responding? ✓/✗
- Port used


## 4. Candlekeep

**Skip if `tools.candlekeep.enabled` is false.** Report as "Disabled (enable with `/academic-writer:update-tools`)".

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


## 5. Cognetivy

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
- Workspace initialized? ✓/✗
- Workflow `wf_academic_writer` registered? ✓/✗
- Number of past runs

**If CLI not installed**, show this setup guide:

> **How to set up Cognetivy:**
>
> 1. Install the CLI:
>    ```
>    npm install -g cognetivy
>    ```
>    Or if you use bun:
>    ```
>    bun install -g cognetivy
>    ```
>
> 2. Initialize the workspace in this project folder:
>    ```
>    timeout 5 cognetivy init --workspace-only
>    ```
>    (The `timeout` is needed because `cognetivy init` starts a studio server that blocks.)
>
> 3. Register Academic Writer workflows:
>    ```
>    cognetivy workflow set --file plugins/academic-writer/workflows/wf_write_article.json
>    cognetivy workflow set --file plugins/academic-writer/workflows/wf_edit_article.json
>    cognetivy workflow set --file plugins/academic-writer/workflows/wf_setup.json
>    ```
>
> 4. Re-run `/academic-writer:health` to verify.

**If CLI is installed but workspace not initialized:**
> "Cognetivy is installed but not initialized in this project. Run:
> ```
> timeout 5 cognetivy init --workspace-only
> ```
> Then re-run `/academic-writer:health`."


## 6. NotebookLM

**Skip if `tools.notebooklm.enabled` is false.** Report as "Disabled (enable with `/academic-writer:update-tools`)".

```bash
command -v nlm >/dev/null 2>&1 && echo "CLI: INSTALLED" || echo "CLI: NOT_FOUND"
```

If installed:
```bash
nlm login --check 2>&1
```

```bash
nlm notebook list 2>&1 | head -5
```

Report:
- CLI installed? ✓/✗
- Authenticated? ✓/✗
- Can list notebooks? ✓/✗ (and count)
- If error: show the error message

**If CLI not installed**, show this setup guide:

> **How to set up NotebookLM:**
>
> 1. Install the CLI:
>    ```
>    npm install -g notebooklm-mcp-cli
>    ```
>
> 2. Authenticate:
>    ```
>    nlm login
>    ```
>
> 3. Re-run `/academic-writer:health` to verify.


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


## Present Results

Show a clean summary table:

> **Academic Writer — Health Report**
>
> | Component | Status | Details |
> |-----------|--------|---------|
> | Profile | ✓ OK / ✗ MISSING | Field: [field], Citation: [style], Sources: [N] |
> | Style Fingerprint | ✓ Expanded / ⚠ Legacy / ✗ Missing | [N] dimensions |
> | Past Articles | ✓ [N] files / ✗ Empty | PDF: [n], DOCX: [n] |
> | Agentic-Search-Vectorless | ✓ Running / ✗ Not running / — Disabled | Port: [port] |
> | Candlekeep | ✓ Connected / ✗ Error / — Disabled | [N] items |
> > | Cognetivy | ✓ Ready / ✗ Not initialized / — Disabled | Run `timeout 5 cognetivy init --workspace-only` if not initialized |
> | NotebookLM | ✓ Connected / ✗ Not found / — Disabled | [N] notebooks |
> | Agent Files | ✓ All present / ✗ Missing [list] | 5/5 |
>
> **Overall: [N]/[total] checks passed**

If there are issues, provide specific fix instructions:
> **To fix:**
> 1. [Issue] → [specific command or action]
> 2. [Issue] → [specific command or action]
