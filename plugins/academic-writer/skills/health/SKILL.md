---
name: health
description: "Check that Academic Writer is ready to use — your profile, the tools it needs (Python and its add-ons, Hebrew spelling, CandleKeep, NotebookLM), the Gemini key and past articles — with a plain-language fix for anything missing. Use when something stops working, after install or an update, or before a long writing session."
user-invocable: true
allowed-tools: [Bash, Read]
metadata: {author: "Yotam Fromm", version: "0.3.0"}
---

# Academic Writer — Health Check

Check every part of Academic Writer and report clearly what works and what needs attention. The
reader is a researcher, often without a technical background: every problem gets one plain fix
line ("To fix: …"). This skill only checks — it never installs anything. When a fix needs an
install, point to `/academic-writer:setup`, which asks before installing.

## 0. Plugin version

Report the installed version first, so a stale install is visible:

```bash
grep -m1 '"version"' "${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json"
```

If it is older than the version the author expects, tell them to run
`claude plugin marketplace update yodem` and then `claude plugin update academic-writer@yodem`
(a marketplace refresh alone does not update an installed plugin).

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

---

## 2. Past Articles

```bash
ls past-articles/ 2>/dev/null | head -20
```

Report:
- Folder exists? ✓/✗
- Number of files found
- File types (PDF, DOCX, other)
- If empty: "Add 5–10 published articles for style analysis, then re-run `/academic-writer:init`."

---

## 3. Tools and Gemini key

Run these together (they change nothing, and never print the key):

```bash
command -v python3 >/dev/null 2>&1 && python3 --version || echo "PYTHON_MISSING"
command -v hspell >/dev/null 2>&1 && echo "HSPELL_OK" || echo "HSPELL_MISSING"
[ -n "${GOOGLE_API_KEY:-}" ] && echo "KEY_PRESENT" || echo "NO_KEY"
"${CLAUDE_PLUGIN_ROOT}/bin/aw" models check >/dev/null 2>&1 && echo "AW_OK" || echo "AW_FAILED"
```

Then run the Python add-ons check from `${CLAUDE_PLUGIN_ROOT}/skills/setup/references/python-deps.md`.
If the profile's `## Gemini` block has `enabled: true` and `KEY_PRESENT`, run the live key check
from `${CLAUDE_PLUGIN_ROOT}/skills/setup/references/gemini-key.md § Checking the key`.

| Result | Report as | To fix (say exactly this, in the researcher's language) |
|---|---|---|
| `PYTHON_MISSING` | ✗ Python | "Python isn't installed. It's free; run `/academic-writer:setup` and I'll walk you through it." |
| `MISSING:...` | ✗ Python add-ons | "Some Python add-ons are missing. Run `/academic-writer:setup` — it will ask before installing them." |
| `HSPELL_MISSING` (Hebrew profile only) | ⚠ Hebrew spelling | "The Hebrew spelling checker isn't installed; proofreading still works. Run `/academic-writer:setup` to add it (not available on Windows)." |
| `NO_KEY` with Gemini enabled | ✗ Gemini key | "Gemini is on but no key reached this session. Store it in `/plugin` → Installed → academic-writer → Configure → `google_api_key`, then restart Claude Code." |
| live check not `HTTP 200` | ✗ Gemini key | the matching line from the table in `gemini-key.md` |
| `AW_FAILED` | ✗ Plugin command | "The plugin's own command didn't start. Update or reinstall the plugin (see version check above)." |

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
- If error: show the error message, then one plain fix line (for example: "Not signed in — type
  `! ck auth login`, which opens your browser.")

**If CLI not installed**: "CandleKeep isn't installed. Run `/academic-writer:setup` — it can
install it after asking."

---

## 5. NotebookLM

**Skip if `tools.notebooklm.enabled` is false.** Report as "Disabled (enable with `/academic-writer:update-tools`)".

```bash
command -v nlm >/dev/null 2>&1 && echo "CLI: INSTALLED" || echo "CLI: NOT_FOUND"
```

If installed:
```bash
nlm login --check 2>&1
nlm notebook list 2>&1 | head -5
```

Report:
- CLI installed? ✓/✗
- Authenticated? ✓/✗
- Can list notebooks? ✓/✗ (and count)
- If error: show the error message

**If CLI not installed**: "NotebookLM's connector isn't installed. Run `/academic-writer:setup` —
it can install it after asking; you then sign in once with `! nlm login`."

**If not authenticated**: "Not signed in to NotebookLM — type `! nlm login`, which opens your
browser, then run this check again."

---

## 6. Plugin agents

The plugin ships its helper agents itself; nothing needs to be copied into your project.

```bash
ls "${CLAUDE_PLUGIN_ROOT}/agents/"*.md 2>/dev/null
```

Verify both exist: `architect.md` (plans the argument and outline) and `auditor.md` (checks every
citation). If one is missing, the install is damaged: "Reinstall the plugin
(`claude plugin update academic-writer@yodem`)."

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
> | Python + add-ons | ✓ Ready / ✗ [what's missing] | Python [version] |
> | Hebrew spelling | ✓ / ⚠ Missing / — Not needed | |
> | Gemini key | ✓ Works / ✗ [problem] / — Claude only | |
> | Candlekeep | ✓ Connected / ✗ Error / — Disabled | [N] items |
> | NotebookLM | ✓ Connected / ✗ Not found / — Disabled | [N] notebooks |
> | Plugin agents | ✓ Both present / ✗ Missing [list] | 2/2 |
>
> **Overall: [N]/[total] checks passed**

If there are issues, list one plain fix line per issue, in the same words as the tables above:
> **To fix:**
> 1. [Issue] → [what to do, in one sentence]
> 2. [Issue] → [what to do, in one sentence]

If everything passed, say so and suggest `/academic-writer:write` (or `/academic-writer:intro` for
the guide).
