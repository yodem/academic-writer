# Write completion steps

W5 (`aw synthesize`, in SKILL.md) has already applied its paragraph-level transition edits to
`drafts/*.md` by the time you reach this reference — there is no separate synthesis step here.

### Step 8.5: Abstract Generation


Generate a structured abstract (תקציר) from the completed article. The abstract has 3 parts:

1. **Topic & research question** — What is this article about? What question does it address?
2. **Methodology & sources** — What approach was used? Which sources were analyzed?
3. **Main findings & contribution** — What did the research find? How does it advance the field?

**Length:** 150–300 words in `targetLanguage`.

**Dual-language abstracts:** Check the profile for `abstractLanguages`. If it includes languages beyond `targetLanguage` (e.g., both Hebrew and English), generate an abstract in each language.

If `abstractLanguages` is not set in the profile, default to `[targetLanguage]` only.

Store the abstract(s) for inclusion in the DOCX output.

---

### Step 8.7: Self-Review (Quality Gate)


Run the self-review checklist from `/academic-writer:review`. Score the article on 6 dimensions (each 1–10):

1. **Structure** — Intro/conclusion conventions, logical section order
2. **Argument Logic** — Each section advances thesis, no gaps
3. **Citation Completeness** — Every claim cited, consistent format
4. **Source Coverage** — All sources used, balanced distribution
5. **Writing Quality** — Matches style fingerprint, no grammar issues
6. **Academic Conventions** — Linking word variety, paragraph length, transitions

Present the scorecard to the researcher.

**If score is below the self-review threshold defined in `thresholds.json` (default 40/60)**, ask whether to proceed or address issues first (using `AskUserQuestion`).
**If score meets or exceeds the threshold (default 40/60)**, show the scorecard and continue to DOCX output.

---

### Step 9: DOCX Output


Assemble the final article and write to both Markdown and DOCX:

```bash
# Output to project's articles/ directory (created if needed)
mkdir -p articles
FILEBASE="$(echo 'SUBJECT' | tr ' ' '-' | tr '[:upper:]' '[:lower:]' | head -c 50)"
MD_PATH="articles/${FILEBASE}.md"
DOCX_PATH="articles/${FILEBASE}.docx"
```

#### Step 9a: Markdown Output

Assemble the article from `.academic-helper/drafts/<unitId>.md` (intro first, then body units in
outline order, then conclusion — these are the same files W4's audit and W5's synthesis already
finalized; do not re-draft or paraphrase them here). Use the `Write` tool to write the assembled
result as markdown to `$MD_PATH` — title as H1, thesis as an italic line below it, section headings
as H2 (only when `totalWords > 1500`), inline citations kept exactly as they appear. Exact structure
template and full rules: see `references/docx-generation.md#step-9a-markdown-output`.

#### Step 9a.5: Hebrew Punctuation Validation (mandatory quality gate)

Before generating the DOCX, run the deterministic punctuation validator over the markdown file just written:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate-hebrew-punctuation.py "$MD_PATH"
```

This checks logical bracket/paren/quote balance and flags mixed gershayim/straight-quote characters and likely-missing bidi marks around embedded Latin/digit runs — the exact class of defect that causes mismatched parentheses and quotation marks in the rendered DOCX.

- **If the script exits non-zero**, review each reported violation and fix the source markdown (do not proceed to DOCX generation with known punctuation defects still present).
- **If the script exits 0**, continue to Step 9b.

This gate is mandatory for any article containing Hebrew text — it is not optional and must not be skipped even under time pressure.

#### Step 9a.6: Citation Floor (mandatory quality gate)

The per-paragraph auditor is a **presence** check — it verifies that claims which *are* cited are cited correctly. It is structurally blind to a paragraph that cites nothing, and the self-review scorecard's 1–10 "Citation Completeness" dimension cannot separate 15 footnotes from 30. Absence needs its own counting gate (`VER-18`), and the count is arithmetic, not judgement.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gate.py citation-floor "$MD_PATH" \
  --sources .academic-helper/sources.json --json
```

Only **secondary** citations count toward the floor: primary sources are quoted inline in this field, so a raw citation count reads healthy on an article carrying almost no scholarly engagement. Floors live in `thresholds.json > citationFloor` — never hardcode them here.

- **Exit 1** — the article is under a floor. Do not ship it. Either the argument genuinely lacks scholarly engagement (send the thin units back through W4 with the gate's per-section counts, as a redraft feedback file), or citations were dropped in synthesis — check W5's `edits` output.
- **Exit 2** — the gate could not run (missing `sources.json`, unreadable markdown). Fix the cause; an unrun gate is not a passed gate.
- **Exit 0** — continue to Step 9b.

#### Step 9b: DOCX Output

Call `aw docx` to read synthesized draft units in outline order, structure `[^KEY]` markers as Word
footnotes, and generate the article JSON in the run directory. Keep the abstract and self-review
steps above. Pass optional JSON files for cover page, abstract, or format when populated.

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" docx \
  --outline "$PWD/.academic-helper/outline.json" --run <run-id> --out "$DOCX_PATH" \
  --title "ARTICLE_TITLE" --cover-file "$COVER_JSON" --abstract-file "$ABSTRACT_JSON" --format-file "$FORMAT_JSON"
```

The script handles all RTL formatting, directional marks, citation parentheses splitting, and conditional section titles deterministically.

Log output completion:

**Close the run in the gate ledger.** Until this runs, the `gate-enforce` Stop hook treats the run
as still in flight and will keep blocking the end of the turn:

```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path('.academic-helper/session-state.json')
if p.exists():
    d = json.loads(p.read_text())
    if isinstance(d.get('run'), dict):
        d['run']['completed'] = True
        p.write_text(json.dumps(d, indent=2, ensure_ascii=False))
PY
```

Report completion to the researcher — word count, citation count, section count, language, and a
per-check summary of quality-gate outcomes. Exact template: see
`references/docx-generation.md#closing-report-template`.
