# Writing Style Analysis Detail (Phase 2, Step 5 of 5 + Stage 1 Voice Fingerprint)

> Read this when you reach "Step 5 of 5 — Writing Style" in SKILL.md. It has the full
> computational-extraction procedure, the qualitative-analysis steps, and the Stage 1 voice
> fingerprint chain (voice-miner → voice-distiller → voice-sync).

## Step 5 of 5 — Writing Style

(In `--quick` mode this step still runs, but only the narrative confirm/skip choice — the
computational extraction and Stage 1 voice fingerprint chain below are skipped in --quick mode.)

```python
AskUserQuestion(questions=[{
  "question": "To write articles that sound like you, I need to analyze your past work. Have you added papers to the past-articles/ folder?",
  "header": "Style (5/5)",
  "options": [
    {
      "label": "Yes, my papers are ready",
      "description": "Analyze them now to extract your writing fingerprint.",
      "markdown": "```\nStyle Analysis\n──────────────\n→ Reads PDF and DOCX files in past-articles/\n→ Analyzes 25 style dimensions:\n   sentence length, structure, vocabulary,\n   paragraph patterns, transitions, citations,\n   rhetorical moves, tone, intro/conclusion style\n→ Shows you the fingerprint before saving\n→ You can correct anything before it's stored\n```"
    },
    {
      "label": "Skip for now",
      "description": "Profile will be saved without a style fingerprint. Articles will use generic academic style.",
      "markdown": "```\nSkip Style Analysis\n───────────────────\n⚠ Articles won't match your voice yet\n→ Add papers to past-articles/ anytime\n→ Re-run: /academic-writer:init\n   (choose 'Update' → 'Style Analysis')\n```"
    }
  ],
  "multiSelect": false
}])
```

**If "Yes, my papers are ready"**, run:

```bash
ls past-articles/
```

**(skipped in --quick mode)** The Computational extraction step and the Stage 1 voice fingerprint
chain below do not run in `--quick` mode. In quick mode, do only a lightweight narrative pass:
read a couple of files and describe style qualitatively (categories D, F, G below), then save that
narrative under `## Style Fingerprint` in Phase 4 as free text instead of the full JSON object.

**Step 1: Computational extraction** — Run the metrics extraction script to get hard numbers.

**Optional, best-effort, Hebrew only:** if `targetLanguage` is Hebrew, first try to fetch the
**shared Hebrew baseline** from Trove for a contrastive score (item titled *Hebrew Linguistic
Reference*, mirrored on GitHub at
[yodem/hebrew-linguistics-data](https://github.com/yodem/hebrew-linguistics-data); the same item is
read by the `hebrew-book-producer` plugin so both share one source of truth). **Skip this whole
step if `targetLanguage` is not Hebrew, OR if `tools.trove.enabled` (or the older `tools.candlekeep.enabled`) is false, OR if no
Trove CLI/tool is present** — the baseline is a nice-to-have contrastive signal, not a
requirement, and the extractor runs fine without it (see below). Look it up by exact title rather
than a hardcoded id — ids can drift if the item is ever recreated, and there is no fallback id to
fall back to:

```bash
mkdir -p .ctx
BASELINE_TITLE="Hebrew Linguistic Reference"
BASELINE_ID=$(trove items list --json 2>/dev/null | jq -r --arg t "$BASELINE_TITLE" '[.[] | select(.title == $t)] | if length == 1 then .[0].id elif length > 1 then (sort_by(.id) | .[0].id) else empty end')
if [ -n "$BASELINE_ID" ]; then
  trove items get "$BASELINE_ID" > .ctx/hebrew-linguistic-reference.md
else
  echo "Could not find Trove item titled '$BASELINE_TITLE' by exact title match — continuing without a contrastive baseline (non-fatal)."
  echo "If you want contrastive scoring, search Trove manually (trove items list --json | jq) and rename the item to match exactly, or re-run init after adding it."
fi
```

Then run the extractor. Pass `--baseline`/`--contrastive` only when the baseline file above was
successfully fetched — the extractor degrades gracefully and simply omits the contrastive section
when no baseline is present, so this is safe to skip entirely for non-Hebrew articles or when
Trove isn't configured:

```bash
if [ -f .ctx/hebrew-linguistic-reference.md ]; then
  BASELINE_ARGS="--baseline .ctx/hebrew-linguistic-reference.md --contrastive"
else
  BASELINE_ARGS=""
fi
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract-style-metrics.py \
  --input past-articles/ \
  --aggregate \
  $BASELINE_ARGS \
  --json \
  --output /tmp/style-metrics.json
```

The extractor reads the baseline JSON code block embedded in the `08-style-fingerprint-baseline` chapter of the cached markdown, so there is no separate JSON file in the plugin's `references/` folder.

Read the results:
```bash
cat /tmp/style-metrics.json
```

This gives you 30+ numerical metrics (sentence length, passive voice, transitions, etc.) and contrastive scores showing what's distinctive about this researcher vs. baseline academic Hebrew. It also includes a `frequentTerms` field — the researcher's own top-N high-frequency content vocabulary (count/length controlled by `thresholds.json > typography.styleMetrics.topFrequentTermsCount` / `minTermLength`). Keep `frequentTerms` in the fingerprint object as-is when you assemble the `## Style Fingerprint` JSON block in Phase 4 below — it steers the section-writer toward the researcher's own established terminology instead of generic phrasing (see `style-fingerprint-rubric.md § Preferred Terminology`).

**Step 2: Text extraction for qualitative analysis** — For each file, extract text mechanically:
- PDF: `python3 -c "import sys; import pdfplumber; [print(p.extract_text()) for p in pdfplumber.open(sys.argv[1]).pages]" past-articles/FILENAME`. **If this fails** (pdfplumber not installed, or extraction errors), do NOT fall back to a crude `strings`-style byte extraction — it produces garbled, unreliable text. Instead skip that file for the qualitative pass, note it as skipped, and continue with the rest of the corpus.
- DOCX: `python3 -c "import docx; d=docx.Document('past-articles/FILENAME'); [print(p.text) for p in d.paragraphs]" 2>/dev/null`

**Step 3: Qualitative analysis** — Read the text and computational metrics. Analyze across the qualitative dimensions (C–I below) that the script cannot compute: paragraph formula, tone, rhetorical patterns, templates, representative excerpts.

Show the combined fingerprint summary (computational + qualitative) and confirm before saving:

```python
AskUserQuestion(questions=[{
  "question": "Here's the writing fingerprint I extracted. Is this accurate?",
  "header": "Style check",
  "options": [
    {"label": "Looks good — save it", "description": "Profile will be saved with this fingerprint."},
    {"label": "I'd like to adjust some things", "description": "Tell me what to change and I'll update before saving."}
  ],
  "multiSelect": false
}])
```

### 25-Dimension Style Analysis

Full rubric (all 30 dimensions across 8 categories A–I): see `references/profile-schema.md`.

## Stage 1 voice fingerprint

**(skipped in --quick mode)**

After past-articles are scanned, invoke the `voice-miner` agent:

1. Run `voice-miner` agent on `past-articles/`. Output is `.voice/fingerprint.md`.
2. **Check for `NEEDS CORPUS`** before proceeding:
   ```bash
   grep -q "NEEDS CORPUS" .voice/fingerprint.md && echo "STUB" || echo "VALID"
   ```
   If `STUB`: skip steps 3–5 below entirely and tell the user: "Not enough past articles yet for a
   voice fingerprint (need at least `thresholds.json: voice.corpus.minArticles` articles /
   `voice.corpus.minTotalWords` words — see `${CLAUDE_PLUGIN_ROOT}/thresholds.json`). Add more to `past-articles/` and
   re-run `/academic-writer:init`, or skip voice for now." Then continue to Phase 3.5/Phase 3
   without a voice fingerprint.
3. If `VALID`: run `voice-distiller --from-fingerprint` to seed the four-section
   `AUTHOR_VOICE.md` at root.
4. **Check that `AUTHOR_VOICE.md` was actually produced** before syncing:
   ```bash
   [ -s AUTHOR_VOICE.md ] && echo "PRESENT" || echo "MISSING"
   ```
   If `MISSING`: print "voice-distiller did not produce AUTHOR_VOICE.md — skipping voice-sync push.
   Re-run voice-miner/voice-distiller manually once past-articles/ has enough content." and skip
   step 5.
5. If `PRESENT`: run `voice-sync push` (this requires `author_key` to already be saved in
   `.academic-helper/profile.md` — see Phase 4 below; run Phase 4 first if needed, or rely on
   voice-sync's own loud failure if `author_key` is missing).
6. Print: "✓ Voice fingerprint created from N past articles. You can write articles now, or run
   `/academic-writer:voice` for a deeper profile (recommended)."

The user is not required to run Stage 2. They can start writing immediately with the fingerprint.
