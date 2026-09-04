---
name: proofread
description: "Unified pre-submission proofreading pass over a finished article — editorial (עורך) venue-fit review, language (עריכה לשונית) sentence-level editing, and mechanical (הגהה) typo/punctuation fixes, each refute-verified before it lands. Produces a tracked-changes .docx (real w:ins/w:del + Word comments) and a markdown report documenting every change, downgrade, and why. Use when an article is drafted and you want a full pre-submission pass — venue fit, register, and mechanics — before sending it out, with every automatic edit visible and reversible in Word."
user-invocable: true
allowedTools: [Bash, Read, Write, Edit, Glob, Grep, Agent, AskUserQuestion]
agents: [editor, copyeditor, proofreader]
metadata: {author: "Yotam Fromm", version: "0.3.0"}
---

# Academic Writer — Proofread (עריכה קדם־הגשה)

A unified, three-stage pre-submission pass over a finished article: **editorial** (venue/genre fit, argument-level issues — comment-only), **language** (sentence-level register, collocation, syntax — refute-verified before it may apply), and **mechanical** (typos, punctuation, typography — the מגיה's pass). Every automatic edit is refute-verified by an independent lens before it is marked applicable, and a refute majority **downgrades** a change to a comment rather than dropping it — nothing a stage found is ever silently discarded.

Output is a real tracked-changes `.docx` (`w:ins`/`w:del` + Word comments, openable and reviewable in Word) plus a markdown report with a Gates table showing exactly which stage ran, which was skipped, and why.

`/academic-writer:proofread [path] [--venue <slug>] [--only editorial|language|mechanical]`

> **Suggestion-grade safety.** The original file is never modified in place. Corrections land in a tracked-changes `.docx` and a corrected `*.proofed.md`; every change is documented with its rationale in the report so you can accept/reject in Word or revert by hand. Idea-level and editorial findings are never auto-fixed — they are comments for you to act on.

---

## Step 1 — Load profile and venue (optional)

```bash
cat .academic-helper/profile.md 2>/dev/null || echo "MISSING"
```

The profile gives the researcher's primary `targetLanguage` (drives typography/register rules) and `approvedLanguages` (drives whether the Gemini refute lens is available). If missing, don't block — default language detection to the article's script and note in the report that no profile was loaded.

If `--venue <slug>` was passed, or a `defaultVenue:` is set in the profile frontmatter, load `.academic-helper/venues/<slug>.md` (name, genre convention, audience, "what they reject", etc). If it doesn't exist yet, ask the researcher whether they want to create one (paste a CFP / author guidelines / rejection letter and the `editor` agent will distill it), or proceed without a venue profile — the editorial stage still runs against general academic-publishing norms and says so in its memo. Never create `.academic-helper/` yourself outside this on-request path.

## Step 2 — Resolve the article

If the user passed a path as an argument, use it. Otherwise ask:

> "Which article should I proofread? Give me a path to a `.md` or `.docx` file, or I can use the most recent article in `articles/`."

List candidates:

```bash
ls -t articles/*.md articles/*.docx 2>/dev/null | head
```

Establish a single **`PROOF_BASE`** — a plain-text/markdown file that is both what every stage reads and what the corrected copy is built from. This is the key safety step: the corrected copy is **never** a copy of a binary source.

- **Markdown / text source** → `PROOF_BASE` is the source itself. Read it with the `Read` tool.
- **.docx source** → extract the text to a real markdown file first (do **not** rely on stdout):
  ```bash
  python3 -c "import docx,sys; d=docx.Document('SOURCE_PATH'); open('articles/FILEBASE.extracted.md','w').write('\n\n'.join(p.text for p in d.paragraphs))"
  ```
  `PROOF_BASE` is `articles/FILEBASE.extracted.md`. The **original `.docx`** is what the tracked-changes docx is built from in Step 8 (never touched in place); a plain markdown source has no docx to build against, so Step 8 is skipped for it and the deliverable stays the `.proofed.md` + report, as before.

Record `SOURCE_PATH`, `FILEBASE`, and `PROOF_BASE`. Determine `LANGUAGE` from the profile's `targetLanguage` if present, else from the article's dominant script. Determine `GEMINI_APPROVED` from whether `LANGUAGE` is in the profile's `approvedLanguages` list.

## Step 3 — Chunk, spell-check, and load thresholds (deterministic scripts)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/chunk-article.py" --input "PROOF_BASE" > /tmp/proofread-chunks.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/spellcheck-candidates.py" --input "PROOF_BASE" > /tmp/proofread-spellcandidates.json
```

`chunk-article.py` splits `PROOF_BASE` on `##` then paragraph boundaries into windows bounded by `proofread.chunkWords` from `src/thresholds.json`; each chunk carries absolute `startLine`/`endLine`. `spellcheck-candidates.py` wraps hspell when present and prints `{"skipped": "no checker"}` (exit 0) when absent — either way, feed its output straight through; never treat a skip as an error.

Load the `proofread` threshold block (`chunkWords`, `maxPasses`, `dryRounds`, `concurrencyCap`, `refuteVotes`, `refuteMajority`) from `src/thresholds.json` — this is the **only** place these numbers are ever set; never inline a cap anywhere else in this skill or hand a literal to the workflow.

## Step 4 — Run the pipeline (Workflow, with a sequential fallback)

**Preferred path — the `Workflow` tool.** Call it with the workflow script shipped by this plugin:

```
Workflow({
  scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflows/proofread.js",
  args: {
    language: LANGUAGE,
    geminiApproved: GEMINI_APPROVED,
    venue: VENUE_PROFILE_OR_NULL,
    thresholds: PROOFREAD_THRESHOLDS,
    chunks: CHUNKS_FROM_STEP_3,
    spellCandidates: SPELLCANDIDATES_FROM_STEP_3,
    stages: ONLY_FLAG_OR_ALL_THREE,
    authorVoice: AUTHOR_VOICE_MD_CONTENTS_OR_NULL
  }
})
```

The script has no filesystem access — it only reads `args` and returns `{memo, languageChanges, mechanicalChanges, outcome, rounds, gates}`. Everything it returns is unapplied; **this skill** applies changes and writes files, per the steps below. `stages` defaults to `['editorial', 'language', 'mechanical']`; when `--only <stage>` was passed, set `stages` to that single-element array so the script's gates record the others as skipped with reason "not requested".

**Fallback — Workflow tool absent.** Run the identical control flow by hand, spawning the **same agents** and calling the **same scripts**, in the same order (this duplicates control flow only, never the agent prompts or script logic):

1. **Editorial** (if requested): spawn `editor` once over the whole article + venue profile. Collect its memo (`changes-schema.json` shape, `stage: "editorial"`).
2. **Language** (if requested and chunks exist): for each chunk, spawn `copyeditor`; for each returned change, spawn three refute-lens checks (`meaning-preserved` / `standard-language` / `voice-preserved` — one prompt per lens, each independently judging only that concern) capped at `concurrencyCap` chunks in flight at once. A change refuted by `refuteMajority` or more lenses is **downgraded** (`applied: false, skipReason: "refuted", refutedBy: [...]`) — **never dropped**; it stays in the list you hand to Step 5.
3. **Mechanical** (if requested and chunks exist): loop rounds until `dryRounds` consecutive rounds find nothing new or `maxPasses` is hit (name the exit: `converged` or `cap-reached`). Each round: spawn `proofreader` per chunk with that chunk's `spellCandidates` slice; dedupe fresh-vs-seen by **NFC-normalized `before` plus the chunk it was found in** — never by line number, since a residual round runs on already-corrected text where lines below an applied edit have shifted. Verify each fresh change with `refuteVotes` independent lenses (Gemini `gemini_raw` if `GEMINI_APPROVED`, else an `opus` refute agent, same prompt either way); `refuteMajority`+ refutes downgrades, never drops.
4. Log every downgrade as you go (no silent caps in either path) so the report's Notes section has something to show.
5. **Validate every collected change list against the schema before Step 5.** On the Workflow path the runtime enforces the contract via each `agent()` call's `schema:` option; on this fallback path there is no such enforcement, so a malformed change object would otherwise reach `citation-guard.py` and the DOCX writer unchecked. Write each stage's list to a file and run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gate.py" changes-schema /tmp/proofread-language-changes.json --json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gate.py" changes-schema /tmp/proofread-mechanical-changes.json --json
```

Exit `0` = valid, continue to Step 5. Exit `1` = the agent returned a malformed list; the violation's `path` names the offending change — re-spawn that stage's agent rather than hand-patching the JSON, since a hand-patch hides a prompt that is producing bad output. Exit `2` = the gate could not run (missing `jsonschema`, unreadable file); fix the cause, because an unrun gate is not a passed gate.

This step is fallback-only — skip it on the Workflow path, where the same contract is already enforced at the boundary.

Either path produces the same three lists: `memo` (editorial), `languageChanges`, `mechanicalChanges`, plus a `gates` ledger recording what ran/was skipped and why.

## Step 5 — Citation-integrity guard (differential, deterministic)

No stage may touch a citation, quotation, page number, or footnote marker. This step **verifies that invariant was obeyed** — it does not re-audit the article's citations.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/citation-guard.py" --changes /tmp/proofread-language-changes.json --proof-base "PROOF_BASE" --json > /tmp/proofread-language-guarded.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/citation-guard.py" --changes /tmp/proofread-mechanical-changes.json --proof-base "PROOF_BASE" --json > /tmp/proofread-mechanical-guarded.json
```

Run it over `languageChanges` and `mechanicalChanges` (editorial findings never touch text, so they skip this guard). Any change overlapping a citation/quotation/page/footnote token comes back `applied: false, skipReason: "citation-guard"` — downgraded, never dropped, same as a refute.

## Step 6 — Apply eligible changes to a corrected copy

```bash
cp "PROOF_BASE" "articles/${FILEBASE}.proofed.md"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/apply-changes.py" --changes /tmp/proofread-language-guarded.json --proof-base "articles/${FILEBASE}.proofed.md" --json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/apply-changes.py" --changes /tmp/proofread-mechanical-guarded.json --proof-base "articles/${FILEBASE}.proofed.md" --json
```

`apply-changes.py` only ever applies a change with `meaningRisk: "low"` and a non-null `after`; everything else comes back `applied: false` with a `skipReason` (`comment-only`, `meaning-risk`, `no-match`, `ambiguous-match`, `overlap`, or a pass-through `citation-guard`/`refuted`). Apply the language batch before the mechanical batch (language runs first in the pipeline order). **If both batches return zero applied changes**, skip the `cp` above — no duplicate file for an already-clean article — and note the clean pass in Step 9.

## Step 7 — Build the tracked-changes .docx (only when the source was a .docx)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build-tracked-docx.py" \
  --original "SOURCE_PATH" \
  --final-text /tmp/proofread-final-lines.txt \
  --changes /tmp/proofread-all-changes.json \
  --output "articles/${FILEBASE}.proofed.docx"
```

`--changes` is the full merged, annotated list (editorial memo changes + guarded/applied language changes + guarded/applied mechanical changes). The script builds real `w:ins`/`w:del` per word-level diff hunk against the original `.docx`, attributes each stage to its own author name ("Editor (Claude)" / "Language editor (Claude)" / "Proofreader (Claude)"), and emits editorial findings plus medium/high-risk language changes as real Word comments. Nothing is written when the changes list is empty (a clean pass). If the source was plain markdown (no original `.docx` to build against), skip this step — the deliverable stays the `.proofed.md` + report.

## Step 8 — Write the report

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/write-proof-report.py" --input /tmp/proofread-report-input.json --out "articles/${FILEBASE}.proofread.md" --json
```

Assemble the report-input JSON from: `filebase`, `source`, `correctedCopy`, `language`, `profile`, `date`, the workflow's/fallback's `gates` array (one row per stage — editorial, language, mechanical, verify — `ran`/`why`/`model`/`rounds`/`outcome`, **including skipped stages**, per VER-10/SPC-14), the editorial `memo`, and every change from every stage (applied and not). `write-proof-report.py` renders the Gates table, the memo, one applied-changes table per stage that has applied changes, and a flags/notes section covering every `applied: false` change with its `skipReason` — idea-flags, citation-guard downgrades, refutes, no-match/ambiguous, comment-only. Nothing dropped along the way becomes invisible here.

## Step 9 — Report to the researcher

If changes were applied:

> "Proofread complete — editorial, language, and mechanical passes run.
> - **Corrected copy:** `articles/<FILEBASE>.proofed.md`
> - **Tracked-changes docx** (if the source was `.docx`): `articles/<FILEBASE>.proofed.docx` — open in Word to accept/reject per change, plus editorial and register comments
> - **Change report:** `articles/<FILEBASE>.proofread.md`
> - Applied **<N>** changes; **<M>** downgraded by refute/citation-guard (comment-only, not dropped); **<K>** editorial findings for your review.
> Your original is untouched — every applied change, every downgrade, and every skip is documented with its rationale."

If it was a clean pass (no applicable changes at any stage): report that explicitly — no corrected copy or docx was written, and the report documents the clean pass plus any editorial/comment-only findings.

## Hard rules

- **Never modify the source file in place.** Corrections go to `*.proofed.md`/`*.proofed.docx`, built from `PROOF_BASE`/the original `.docx` — never a mutation of either.
- **A refute majority downgrades, it never drops.** Every change any stage found is present in the final report, either applied, downgraded (with `skipReason` and `refutedBy`), or flagged. Silently discarding a true positive is the exact hebrew-recall-rejection failure this pipeline exists to fix.
- **Editorial findings are never auto-applied** — comment-only, always `after: null`.
- **Citation-integrity guard is mandatory and deterministic** for language and mechanical changes: anything touching a citation/quotation/page/footnote token is downgraded, not applied.
- **Every applied change carries a rationale**; every skipped/downgraded change carries a `skipReason`. No silent edits, no silent caps — every loop the workflow runs exits `converged` or `cap-reached`, named.
- **Caps come from `src/thresholds.json`'s `proofread` block, never a literal** anywhere in this skill or in `workflows/proofread.js`.
- **Don't create `.academic-helper/`** except the on-request venue-profile path in Step 1 — all other outputs land in `articles/`.
