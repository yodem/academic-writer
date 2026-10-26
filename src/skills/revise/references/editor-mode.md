# Editor mode: prompts, schemas and categories

Used by `/academic-writer:revise <file.docx> --editor`. `SKILL.md` has the steps; this file has the
text each agent receives. Replace the `{PLACEHOLDERS}` before sending: `{WORK}` is the working
folder (`.academic-helper/editor-review`), `{PAPER}` is one line about the paper (language, field,
venue), `{PLUGIN}` is `${CLAUDE_PLUGIN_ROOT}`, `{TOTAL}` is the op count from `extract`.

Model for every agent: `sonnet` for chunk analysis and skeptics, `opus` for synthesis. Never any
other model.

## Folder contract

```
{WORK}/edited.docx, original.docx      the two inputs (copy or note their paths)
{WORK}/extract/units.json, ops.json, global.json
{WORK}/full-before.md, full-after.md   the paper with all changes rejected / accepted
{WORK}/chunks/text-NN.md, text-NN.ids.json, layout.md, layout.ids.json, auto-classified.json
{WORK}/analysis/<chunk>.json           one file per chunk, written by the analysis agents
{WORK}/synthesis/rules.json            the Opus synthesis, written by the script from its answer
{WORK}/synthesis/verdicts.json         all skeptic verdicts, concatenated
{WORK}/verified-catalogue.json, .md    output of `docx-editor-diff.py merge`
{WORK}/decisions.json                  the author's answers
```

## Categories

Every op gets exactly one. Language-specific entries apply to Hebrew papers; drop them for others.

`dash-hyphen`, `quotation-marks`, `geresh-gershayim` (Hebrew), `maqaf` (Hebrew),
`punctuation-other`, `spacing-whitespace`, `spelling-orthography`, `typo-fix`,
`grammar-agreement`, `syntax-word-order`, `word-choice-register`, `concision-redundancy`,
`sentence-restructure`, `connective-linking`, `terminology-consistency`, `name-transliteration`,
`abbreviation`, `number-date-format`, `footnote-citation-format`, `bibliography-format`,
`primary-source-citation`, `quotation-handling`, `heading-numbering-title`, `toc`, `title-page`,
`italic-bold-emphasis`, `layout-spacing-alignment`, `paragraph-split-merge`, `factual-correction`,
`content-argument`, `bidi-debris`, `editor-inconsistency-or-error`, `other`.

Tiers: `universal-hebrew-academic` (any paper in the language), `venue-or-citation-style` (one
institution, journal or citation style), `article-specific` (this paper's content; at most a voice
pair), `noise`. Mechanizable: `regex-or-script`, `docx-generator`, `llm-judgment`, `not-applicable`.

Per-op row (a JSON array in `analysis/<chunk>.json`):

```json
{"id": "op-0042", "category": "quotation-marks", "pattern_key": "ascii-quotes-hebrew",
 "explanation": "one sentence: what changed and why an editor would do it",
 "tier": "universal-hebrew-academic", "mechanizable": "regex-or-script", "confidence": 0.8}
```

## Chunk analysis prompt (one Sonnet agent per text chunk)

```
You are analysing the edits a professional editor made, as Word tracked changes, to {PAPER}. The
author wants every edit understood so the conventions can be learned and built into an
academic-writing plugin.

Your chunk: {WORK}/chunks/{CHUNK}.md (read ALL of it). Its op ids are in {WORK}/chunks/{CHUNK}.ids.json.
Whole-paper context if you need it: {WORK}/full-before.md (author) and {WORK}/full-after.md (editor).

Rules:
- Classify EVERY op id in your chunk. No skipping, no "and similar". Write the per-op results to
  {WORK}/analysis/{CHUNK}.json as a JSON array of {"id","category","pattern_key","explanation",
  "tier","mechanizable","confidence"}. category must be one of: {CATEGORIES}. After writing, run a
  quick python3 check that every id in the .ids.json appears exactly once, and fix the file if not.
- Think like the editor. For word-choice, syntax and register edits name the principle (calque,
  over-nominalization, wrong preposition, redundant hedge, register, ambiguous antecedent). Quote
  exactly.
- Look-alike characters matter: the `chars:` line names them (gershayim vs ", geresh vs ', maqaf vs
  hyphen, em dash, curly vs straight quotes). Treat them as deliberate unless clearly accidental.
- Traps. (1) Mirrored or reversed parentheses and stray punctuation at the edge of right-to-left
  text are typing debris from bidirectional text, not a convention: category bidi-debris.
  (2) The editor is not consistent. A pattern needs two or more consistent instances or a clearly
  principled correction; record the places the editor did NOT apply it as counter_examples and
  file one-off or contradictory edits under editor-inconsistency-or-error. (3) Paragraph pairs
  ("paragraph-rewrite-or-move") come from fuzzy matching and can be wrong: judge the real relation
  from the two texts. (4) A split or merge of a paragraph, or an edit inside a footnote, is judged
  with its whole paragraph or note in view, not as a fragment. (5) Bibliography entries converted
  to a new citation style: identify the style and list each field-level convention (author form,
  year position, italics on which element, publisher, page ranges, URLs, retrieval dates) as its
  own pattern.
- Return patterns that group op ids (every op id in some pattern; singletons allowed) plus notable
  observations that fit no pattern (content corrections, argument changes, editor errors).
```

Structured answer: `{chunk, ops_classified, patterns: [{key, category, rule, tier, mechanizable,
op_ids, examples (up to 4, "BEFORE -> AFTER", exact), counter_examples}], notable: []}`.

## Layout analysis prompt (one Sonnet agent)

```
You are analysing the layout and formatting edits a professional editor made, as Word tracked
formatting changes, to {PAPER}. Read {WORK}/chunks/layout.md (all of it); its op ids are in
{WORK}/chunks/layout.ids.json. Context: {WORK}/full-after.md, and the page-setup and "parts that
differ without tracking" lines at the top of layout.md. If you need the XML, unzip the two .docx
files into a temp folder; never modify the inputs. The plugin's Word generator is
{PLUGIN}/scripts/generate-docx.py: read it so your rules say what the generator should do differently.
Delta strings read OLD to NEW: +x added, -x removed, ~x(a)->(b) changed. Font-switch churn was
collapsed into the "Global" count: treat it as one finding. Compare styles.xml, settings.xml and the
footer between the files for changes that carry no revision mark.
Classify EVERY op id: write {WORK}/analysis/layout.json (same row format and category list), verify
every id appears exactly once, and return patterns plus notable observations (include the untracked
style and settings differences there).
```

`auto-classified.json` already holds the blank-paragraph marks; do not classify them again.

## Synthesis prompt (one Opus agent)

```
You are the lead analyst. Sub-analyses classified every tracked edit ({TOTAL} ops; the blank-line
marks are in {WORK}/chunks/auto-classified.json) a professional editor made to {PAPER}. Per-op
classifications: {WORK}/analysis/*.json. Chunk-level pattern summaries:
{PATTERN_SUMMARIES}

Consolidate them into ONE deduplicated rule catalogue with frequency counts across chunks. Merge
same-pattern keys from different chunks; settle contradictions by looking at the evidence; mark
editor inconsistencies honestly. Tier every rule: universal (plugin-wide), venue-or-citation-style
(a profile, not a default), article-specific (a voice pair, not a rule), noise.
Then map each rule onto the plugin: read the files it would change before naming them, give a
Python regex for the BEFORE form when it is mechanizable, and quote any existing plugin rule it
contradicts or duplicates (in particular: any rule about dashes, quote marks, fonts or connectives).
Write the full catalogue as readable Markdown to {WORK}/rule-catalogue.md (coverage table first).
This file is a DRAFT for the skeptics: it must never be shown to the author as rule text.
Return the rules as structured output.
```

Structured answer: `{rules: [{id: "R-01", group, title, rule, tier, evidence_count, op_ids,
examples, consistency, plugin_target, regex_hint, conflicts}], summary}`. Groups:
`punctuation-typography`, `orthography-grammar`, `style-register-concision`, `citations-footnotes`,
`bibliography`, `structure-headings-toc-cover`, `docx-layout`, `content-argument`,
`article-specific`. The orchestrator writes `rules` to `{WORK}/synthesis/rules.json`.

## Skeptic prompt (one Sonnet agent per rule group)

```
You are a skeptical reviewer. A synthesis agent derived the following conventions from a
professional editor's tracked changes on an academic paper. Your job is to REFUTE or NARROW each
one with evidence, defaulting to "narrow" when unsure.

Evidence: {WORK}/full-before.md (author text) and {WORK}/full-after.md (editor text, accepted);
per-op classifications in {WORK}/analysis/*.json; chunk sources {WORK}/chunks/*.md; the author's
past articles as plain text if available. Use python3 or grep to COUNT: for each rule, how many
times the editor applied it, and how many times the BEFORE form still survives in full-after.md
(the editor left it, which weakens the rule). For mechanizable rules run the regex_hint over the
paper and the past articles to estimate false positives. Check each plugin-conflict claim against
the real file. Do not edit any file.

Rules (group {GROUP}):
{RULES_JSON}
```

Structured answer: `{verdicts: [{id, verdict: confirmed|narrow|reclassify|refuted, reason,
applied_count, left_unchanged_count, corrected_rule, false_positive_risk}]}`. `corrected_rule` is
required for `narrow` and `reclassify`. The orchestrator concatenates every group's verdicts into
`{WORK}/synthesis/verdicts.json`.

## Merge, then the author

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/docx-editor-diff.py" merge --work .academic-helper/editor-review [--decisions decisions.json] --strict
```

`merge` offers only the skeptic's wording: `confirmed` keeps the synthesis rule, `narrow` and
`reclassify` use `corrected_rule`, `refuted` is dropped to the noise ledger, and a rule with no
verdict or no restatement is marked `unverified` or `needs-restatement` and never shown. Show the
author `verified-catalogue.md`, never `rule-catalogue.md`.

Decision per rule group, asked with `AskUserQuestion` (one group at a time, rules listed in plain
words with one before/after example each): **Adopt as a general convention**, **Adopt for this
venue only**, **This paper only (voice example)**, **Not a rule (noise)**, **Skip for now**.
Record the answers as `decisions.json`: `{"R-01": {"decision": "adopt", "destination": "conventions"}}`
with destination one of `conventions`, `venue`, `terms`, `voice`, `noise`, `feedback`.

## Destinations

All paths are inside the author's project; nothing is written into the plugin folder.

| Destination | File | Receives |
|---|---|---|
| conventions | `.academic-helper/editor-conventions.md` | rules adopted as general: rule text (the verified wording), counts, one before/after, the `(R-NN)` tag |
| venue | `.academic-helper/venues/<slug>.md` | citation, bibliography, cover and layout choices of one venue; ask for the slug; run with `aw proofread --venue <slug>` |
| terms | `.academic-helper/terms.json` | terminology and name choices; show the merged result and write only after confirmation |
| voice | shared `voice/pairs.jsonl` through `aw revise apply` | whole-sentence before/after pairs of this paper only |
| noise | `.academic-helper/editor-noise.md` | refuted rules, bidi debris, font churn, blank-line marks, editor inconsistencies, so the next run does not offer them again |
| feedback | `${CLAUDE_PLUGIN_DATA}/feedback/ledger.jsonl` through `aw revise apply` (`plugin_defect` items) | where the plugin's own output was what the editor fixed (its generator, drafter or validators) |

Append, never overwrite: read the file first, add under a dated heading, keep earlier entries.
