---
name: academic-writer-setup
description: "First-time setup for Academic Writer — creates researcher profile, detects integrations, analyzes writing style from past articles"
user-invocable: true
allowedTools: [Bash, Read, Write, Glob, Grep, AskUserQuestion]
---

# Academic Writer Setup

Interactive first-time setup that replaces the old npx installer. Creates the researcher profile, detects available integrations, and optionally analyzes past articles for style fingerprinting.

## Cognetivy Workflow

If cognetivy is available, start a run for the `wf_setup` workflow:
```bash
echo '{"phase": "setup"}' > /tmp/aw-setup-input.json
cognetivy run start --input /tmp/aw-setup-input.json --name "Academic Writer Setup"
```
Capture the `run_id` and log events at each step below.

## Setup Steps

### Step 1: Check for Existing Profile

1. Check if `.academic-writer/profile.json` exists
2. If it exists:
   - Load and display current settings (field, language, citation style, enabled tools)
   - Use AskUserQuestion: "A profile already exists. What would you like to do?"
     - "Update existing profile" — keep existing data, modify selected fields
     - "Start fresh" — delete and recreate from scratch
3. If it doesn't exist, proceed to Step 2

### Step 2: Detect Available Integrations

Auto-detect which tools are available on this machine:

```bash
# Candlekeep CLI
which ck 2>/dev/null && echo "ck: available" || echo "ck: not found"

# Agentic-Search-Vectorless
curl -s --max-time 3 http://localhost:8000/health 2>/dev/null && echo "vectorless: running" || echo "vectorless: not running"

# Cognetivy CLI
which cognetivy 2>/dev/null && echo "cognetivy: available" || echo "cognetivy: not found"
```

Display results to the researcher.

### Step 3: Collect Profile Information

Use AskUserQuestion for each field:

1. **Field of Study** — Free text. Example: "Jewish Philosophy", "Biblical Studies", "Hebrew Literature"
2. **Target Language** — Options: "Hebrew (Recommended)", "English", "Other (specify)"
3. **Citation Style** — Options:
   - "Inline-parenthetical (Recommended for Hebrew)" — `(Author, Title, עמ' N)` in running text
   - "Chicago" — footnotes with full bibliography
   - "MLA" — parenthetical with Works Cited
   - "APA" — (Author, Year) style

### Step 4: Tool Selection

Present detected tools and let researcher enable/disable:

Use AskUserQuestion (multiSelect):
- "Candlekeep — Cloud document library for source PDFs" (pre-checked if detected)
- "Agentic-Search-Vectorless — Semantic search for citations" (pre-checked if detected)
- "Cognetivy — Workflow tracking and audit trail" (pre-checked if detected)
- "MongoDB Agent Skills — Database-backed research" (unchecked by default)

### Step 5: Create Profile

1. Create `.academic-writer/` directory if needed
2. Write `.academic-writer/profile.json`:

```json
{
  "fieldOfStudy": "<from Step 3>",
  "targetLanguage": "<from Step 3>",
  "citationStyle": "<from Step 3>",
  "outputFormatPreferences": {
    "font": "David",
    "bodySize": 11,
    "titleSize": 14,
    "lineSpacing": 1.5,
    "margins": "1in",
    "rtl": true
  },
  "styleFingerprint": null,
  "tools": {
    "candlekeep": { "enabled": "<from Step 4>" },
    "agentic-search-vectorless": { "enabled": "<from Step 4>", "path": "../Agentic-Search-Vectorless" },
    "mongodb-agent-skills": { "enabled": "<from Step 4>" },
    "cognetivy": { "enabled": "<from Step 4>" }
  },
  "sources": [],
  "createdAt": "<ISO timestamp>",
  "updatedAt": "<ISO timestamp>"
}
```

3. Create `past-articles/` directory if it doesn't exist
4. Create `.cognetivy/` directories if cognetivy is enabled:
   ```bash
   mkdir -p .cognetivy/runs .cognetivy/events
   ```

### Step 6: Style Fingerprint (Optional)

1. Check if `past-articles/` has any files (PDF, DOCX, TXT)
2. If files exist:
   - Use AskUserQuestion: "Found N past articles. Analyze them for style fingerprinting? This helps match your writing voice."
     - "Yes, analyze (Recommended)" — proceed to analysis
     - "Skip for now" — leave styleFingerprint as null
3. If "Yes":
   - Read each file in `past-articles/`
   - Analyze across 25 dimensions (sentence length, structure variety, vocabulary complexity, register, paragraph structure, argument progression, evidence handling, tone, transitions, citation integration, rhetorical patterns, etc.)
   - Extract representative excerpts
   - Present summary to researcher and ask for adjustments
   - Save to `profile.styleFingerprint`

### Step 7: Source Indexing (Optional)

If Candlekeep is enabled:
1. Run `ck items list` to get available sources
2. Present the list and let researcher select which to include
3. Save selected sources to `profile.sources`

### Completion

Display summary:
- Profile saved to `.academic-writer/profile.json`
- Field: [field]
- Language: [language]
- Citation style: [style]
- Tools enabled: [list]
- Style fingerprint: [yes/no]
- Sources indexed: [count]

Remind: "Run `/academic-writer` to write your first article, or `/academic-writer-init` for more detailed style analysis."

If cognetivy run was started, complete it:
```bash
echo '{"type":"run_completed","data":{}}' | cognetivy event append --run <run_id>
cognetivy run complete --run <run_id>
```
