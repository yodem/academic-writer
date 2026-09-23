---
name: learn
description: "Style learning — scans past-articles/ for new files, extracts style patterns, and merges them into the existing style fingerprint. Shows a diff report. Use after adding new past articles to past-articles/ — rebuilds the style fingerprint. Use when this skill's command or workflow is needed."
user-invocable: false
allowed-tools: [Bash, Read, Write, Glob, Grep, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.2.23"}
---

# Academic Writer — Learn from New Articles

Trigger the style miner to analyze new articles in `past-articles/` and update the researcher's style fingerprint.

## Load Profile

```bash
cat .academic-helper/profile.md
```

If no profile, tell the researcher to run `/academic-writer:init` first.

Extract the current `styleFingerprint` and `analyzedArticles` list (if present).

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

**Use the Agent tool to spawn the `voice-miner` subagent.** Pass:
- List of new article filenames
- Current `styleFingerprint` from the profile
- `targetLanguage`

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

## Step 5: Refresh Voice Exemplars

Gemini matches the researcher's voice from real paragraphs in `.academic-helper/voice-exemplars.md`, not from the fingerprint's description. The selection script cannot tell a finished paper from a course reflection (on a real corpus the whole-folder run picked a colloquial reflection), so the researcher chooses the sources:

```python
AskUserQuestion(questions=[{
  "question": "Which of your past articles best represent your finished academic writing? Gemini will imitate paragraphs taken from them.",
  "header": "Voice examples",
  "options": [<one option per file in past-articles/, label = filename>],
  "multiSelect": true
}])
```

Then run (with the chosen files):

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract-voice-exemplars.py past-articles/<chosen-1> [past-articles/<chosen-2> ...] \
  --output .academic-helper/voice-exemplars.md --language <targetLanguage lowercased>
```

Show the researcher the written paragraphs and tell them they can edit or replace any of them (paragraphs are separated by a line containing only `---`). Exit code 1 means no paragraph met the criteria (body paragraph with a citation, within `thresholds.json > voice.exemplars` word bounds): say so and suggest a different article.

## Completion


> "Style fingerprint updated! [N] new article(s) analyzed, [M] dimensions adjusted.
>
> Your writing pipeline will now use the updated fingerprint. Every paragraph will be checked against the new patterns."
