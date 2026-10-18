---
name: health
description: "Check that Academic Writer is ready to use — your profile, the tools it needs (Python and its add-ons, Hebrew spelling, Trove, NotebookLM), the Gemini key and past articles — with a plain-language fix for anything missing. Use when something stops working, after install or an update, or before a long writing session."
user-invocable: true
allowed-tools: [Bash, Read]
metadata: {author: "Yotam Fromm", version: "0.4.0"}
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
(refreshing the plugin list alone does not update an installed plugin).

## 1. Profile Check

Run the checks once; sections 1, 3, 4 and 5 read their rows from this output (the same checks the
dashboard's Setup page shows). The script only reads: it installs and writes nothing, and never prints the Gemini key.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_checks.py" --data-dir "${CLAUDE_PLUGIN_DATA}" --json
```

Each row is `{id, label_he, ok, optional, found, required, reason_he, fix}`; `ok: null` means "not applicable here".
Use the `home` and `profile` rows for this section: if `profile` is not ok, report `FAIL` and suggest
`/academic-writer:init`; if `home` is not ok, suggest `/academic-writer:setup`. Then read the profile itself:

```bash
[ -f .academic-helper/profile.md ] && cat .academic-helper/profile.md
```

If found, validate:
- Has `fieldOfStudy`? ✓/✗
- Has `citationStyle`? ✓/✗
- Has `styleFingerprint`? ✓/✗
- Style fingerprint: is it the full, detailed version or the old short version?
  - If it is the old short version: suggest re-running `/academic-writer:init` to get the full, detailed one
- Has a `tools` section? ✓/✗
- Has a `sources` list? ✓/✗ (and how many)
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

Use the rows `python` (found version against the required 3.9), `python-addons`, `hspell`, `gemini-key` and
`nightly-job` from the section 1 output. Show each row's `reason_he` and `fix` as the plain "To fix" line. Then run
the plugin's own command check (it changes nothing):

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" models check >/dev/null 2>&1 && echo "AW_OK" || echo "AW_FAILED"
```

If the profile's `## Gemini` block has `enabled: true` and the `gemini-key` row is ok, run the live key check
from `${CLAUDE_PLUGIN_ROOT}/skills/setup/references/gemini-key.md § Checking the key`.

| Result | Report as | To fix (say exactly this, in the researcher's language) |
|---|---|---|
| `python` row not ok | ✗ Python | "Python isn't installed. It's free; run `/academic-writer:setup` and I'll walk you through it." |
| `python-addons` row not ok | ✗ Python add-ons | "Some Python add-ons are missing. Run `/academic-writer:setup` — it will ask before installing them." |
| `hspell` row not ok (Hebrew profile only) | ⚠ Hebrew spelling | "The Hebrew spelling checker isn't installed; proofreading still works. Run `/academic-writer:setup` to add it (not available on Windows)." |
| `gemini-key` row not ok with Gemini enabled | ✗ Gemini key | "Gemini is on but no key reached this session. Store it in `/plugin` → Installed → academic-writer → Configure → `google_api_key`, then restart Claude Code." |
| live check not `HTTP 200` | ✗ Gemini key | the matching line from the table in `gemini-key.md` |
| `AW_FAILED` | ✗ Plugin | "The plugin itself didn't start. Update or reinstall the plugin (see version check above)." |

## 4. Library (Trove, PageIndex)

The project's library route (Trove, PageIndex or both) decides what is checked. Ask the plugin which library it uses:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --project-dir "$PWD" library status
```

**Skip if its output says `"enabled": false`** (set by `tools.trove.enabled`, or the older `tools.candlekeep.enabled`, being false). Report as "Disabled (enable with `/academic-writer:update-tools`)". If the output has an `ERROR library` line (for example the route file is not valid), show that line and one plain fix line: "The library setting file is damaged — run `/academic-writer:update-tools` to choose the library again."

If enabled, check each route that the route setting uses:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --project-dir "$PWD" library status --check
```

The `check` part of the output has one entry per library (`trove`, `pageindex`) with `ok`, `latency_ms`, `count` and `error`. When Trove is one of the routes, also use the `trove` row from the section 1 output (Trove installed or not).

Report:
- Which library the project uses (Trove, PageIndex or both, and which one answers)
- Per library: can connect? ✓/✗, the number of items (`count`) and how fast it answered
- If a library has an `error`: show the message, then one plain fix line (for example: "Not signed in — type
  `! trove login`, which opens your browser.")
- When both routes are on, a failing second library is only a warning: the answering route still works, and the second one runs quietly in the background.
- **The PageIndex helper**, from the same status output: where the helper comes from (`pageindex_source`: `setting` or `library.json` = the author's own command, `installed` = the built-in helper, `default` = `pilib` found on this computer), for the built-in helper its level (`installed.tier`, say "level": `core` = the basic helper, books with a table of contents; `structure` = the full helper), the Python version it uses (`installed.python`) and whether it matches the version this plugin pins (`installed.matches_pinned`), and `pilib.index_trove` (can it prepare new books). Print each `warnings` entry in plain words. A version mismatch or `index_trove: false` is a warning, not a failure: offer to update it (`/academic-writer:update-tools`, which asks first); never install from here. When PageIndex is not set up at all and the route is Trove only, say nothing.
- With a server you set up yourself, say that its own Gemini key is used there; the plugin never sends yours.

**If Trove is not installed** and Trove is one of the libraries: "Trove isn't installed. Run `/academic-writer:setup` — it can
install it after asking." **If PageIndex is one of the libraries and is not found**: "PageIndex isn't set up. Run `/academic-writer:setup` to install the built-in helper or connect your own, or switch to Trove with `/academic-writer:update-tools`."

---

## 5. NotebookLM

**Skip if `tools.notebooklm.enabled` is false.** Report as "Disabled (enable with `/academic-writer:update-tools`)".

Use the `notebooklm` row from the section 1 output to see whether the NotebookLM connector is installed. If installed:
```bash
nlm login --check 2>&1
nlm notebook list 2>&1 | head -5
```

Report:
- Connector installed? ✓/✗
- Authenticated? ✓/✗
- Can list notebooks? ✓/✗ (and count)
- If error: show the error message

**If the connector is not installed**: "NotebookLM's connector isn't installed. Run `/academic-writer:setup` —
it can install it after asking; you then sign in once with `! nlm login`."

**If not authenticated**: "Not signed in to NotebookLM — type `! nlm login`, which opens your
browser, then run this check again."

---

## 6. Plugin agents

The plugin comes with its own helpers; nothing needs to be copied into your project.

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
> | Style Fingerprint | ✓ Full / ⚠ Old short version / ✗ Missing | [N] dimensions |
> | Past Articles | ✓ [N] files / ✗ Empty | PDF: [n], DOCX: [n] |
> | Python + add-ons | ✓ Ready / ✗ [what's missing] | Python [version] |
> | Hebrew spelling | ✓ / ⚠ Missing / — Not needed | |
> | Gemini key | ✓ Works / ✗ [problem] / — Not set up (needed to write, proofread, read scans) | |
> | Library | ✓ Connected / ✗ Error / — Disabled | [Trove or PageIndex]: [N] items |
> | NotebookLM | ✓ Connected / ✗ Not found / — Disabled | [N] notebooks |
> | Plugin agents | ✓ Both present / ✗ Missing [list] | 2/2 |
>
> **Overall: [N]/[total] checks passed**

If there are issues, list one plain fix line per issue, in the same words as the tables above:
> **To fix:**
> 1. [Issue] → [what to do, in one sentence]
> 2. [Issue] → [what to do, in one sentence]

After updating the plugin, restart Claude Code: a running session keeps the old skills until then.

If everything passed, say so and suggest `/academic-writer:write` (or `/academic-writer:intro` for
the guide).
