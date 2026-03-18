---
description: Style learning — scans past-articles/ for new files, extracts style patterns, and merges them into the existing style fingerprint. Shows a diff report.
allowed-tools: [Bash, Read, Write, Glob, Grep, AskUserQuestion]
---

# Auto-generated from skills/learn/SKILL.md


# Academic Writer — Learn from New Articles

Trigger the style miner to analyze new articles in `past-articles/` and update the researcher's style fingerprint.

## Load Profile

```bash
cat .academic-helper/profile.md
```

If no profile, tell the researcher to run `/academic-writer:init` first.

Extract the current `styleFingerprint` and `analyzedArticles` list (if present).

## Cognetivy Tracking

If Cognetivy is enabled:
```bash
echo '{"phase": "style_learning"}' > /tmp/aw-learn-input.json
cognetivy run start --workflow wf_learn --input /tmp/aw-learn-input.json
```

## Step 1: Scan for New Articles

```bash
ls past-articles/
```

Compare against `profile.analyzedArticles` (array of filenames already analyzed). Identify new files not yet processed.

If no new files found:
> "No new articles found in `past-articles/`. Add new papers (PDF or DOCX) and run `/academic-writer:learn` again."

If new files found, show them:
> "Found [N] new article(s) to analyze:
> 1. [filename]
> 2. [filename]
>
> I'll extract style patterns from these and merge them into your existing fingerprint."

## Step 2: Spawn Style Miner

**Use the Agent tool to spawn the `style-miner` subagent.** Pass:
- List of new article filenames
- Current `styleFingerprint` from the profile
- `targetLanguage`
- `runId` (if Cognetivy enabled)

The style miner returns:
- Updated fingerprint dimensions
- New representative excerpts
- Statistics (sentence lengths, transition patterns, vocabulary patterns, linking word usage)
- A diff report showing what changed

## Step 3: Present Diff Report

Show the researcher what changed:

```
╔══════════════════════════════════════════════════╗
║           STYLE FINGERPRINT UPDATE               ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  Articles analyzed: [N] new + [M] previous       ║
║                                                  ║
║  Changes detected:                               ║
║                                                  ║
║  Sentence length:  18.5 → 19.2 words (avg)       ║
║  Passive voice:    moderate → moderate-high       ║
║  Vocabulary:       complex (unchanged)            ║
║  New openers:      +2 patterns detected           ║
║  New transitions:  +3 phrases added               ║
║  New excerpts:     +2 representative samples      ║
║                                                  ║
╚══════════════════════════════════════════════════╝
```

## Step 4: Confirm and Save

```python
AskUserQuestion(questions=[{
  "question": "Would you like to save these updates to your style fingerprint?",
  "header": "Fingerprint Update",
  "options": [
    {"label": "Save updates", "description": "Merge the new patterns into your profile."},
    {"label": "Review details first", "description": "Show me the full before/after comparison."},
    {"label": "Discard", "description": "Keep the current fingerprint unchanged."}
  ],
  "multiSelect": false
}])
```

If **Save**, update the profile:
1. Merge the updated `styleFingerprint` into `.academic-helper/profile.md`
2. Add the new filenames to `analyzedArticles` array
3. Update `updatedAt` timestamp

Use the `Write` tool to save the updated profile.

If **Review details**, show the full before/after for each dimension, then ask again.

## Completion

Log to Cognetivy:
```bash
echo '{"type":"step_completed","nodeId":"style_learning","newArticles":N,"dimensionsUpdated":N}' | cognetivy event append --run RUN_ID
cognetivy run complete --run RUN_ID
```

> "Style fingerprint updated! [N] new article(s) analyzed, [M] dimensions adjusted.
>
> Your writing pipeline will now use the updated fingerprint. Every paragraph will be checked against the new patterns."
