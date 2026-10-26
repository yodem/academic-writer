---
name: revise
description: "Read the Word comments and tracked changes the author left on a generated draft, group them, confirm each group, then update the article and the voice and feedback stores. Use when the author has commented on or tracked-changed a .docx from this plugin. Not for new instructions without a Word file (use /academic-writer:edit)."
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit, Glob, Agent, Workflow, AskUserQuestion]
argument-hint: "<file.docx> [--editor [original.docx]]"
metadata: {author: "Yotam Fromm", version: "0.12.0"}
---

# Revise a reviewed draft

With `--editor` the file is a paper a professional editor returned, and the goal is to learn the editor's conventions: go to [Editor mode](#editor-mode) after step 0.

Fold the author's Word review back into the article. Confirm every group with the author before anything is applied: their comments are instructions, but your grouping of them is a guess.

## 0. Record the run

Use one run ID for the whole review, e.g. `revise-ashkenazi-creation-20261015-1430` (Latin letters, digits and hyphens only). Record the run and register the workspace before anything else:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --project-dir "$CLAUDE_PROJECT_DIR" --data-dir "${CLAUDE_PLUGIN_DATA}" activity start --flow revise --run-id <id>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/home.py" --data-dir "${CLAUDE_PLUGIN_DATA}" register --path "$CLAUDE_PROJECT_DIR" --type project
```

`activity start` writes its opening line once per run. If `home.py register` says no home folder is set, skip it and tell the researcher once. The `aw revise` commands below record their own `read`, `update-draft` and `update-stores` steps.

## 1. Read the review

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/docx-read-review.py" <file.docx> --json > .academic-helper/review-items.json
```

The reader covers the body, the footnotes and the endnotes. Every item keeps `id`, `kind`, `anchorText`, `text`, `author` and `date`, and adds `part`, `location` (`body:12`, `footnote:3`), `section`, `paragraphBefore` and `paragraphAfter` (the whole paragraph with the change rejected and accepted), and `citedIn` for a note. Besides comments, inserts, deletes, replaces and moves it reports `format` (bold, italic, size or font), `paragraph-format` and `paragraph-mark` (a split or a merge); font-switch churn and blank-line marks are counted in `summary` instead.

Save the JSON inside the current project, then classify it (use the same `--run <id>`):

```bash
aw revise classify --items .academic-helper/review-items.json --run <id> --data-dir "$CLAUDE_PLUGIN_DATA" --project-dir "$CLAUDE_PROJECT_DIR"
```

## 2. Confirm with the author

Show the grouped items and the proposed action for each, in plain language. Ask for confirmation one group at a time with `AskUserQuestion`. Write a plan JSON that contains only the confirmed items.

## 3. Apply

```bash
aw revise apply --plan <plan.json> --data-dir "$CLAUDE_PLUGIN_DATA" --project-dir "$CLAUDE_PROJECT_DIR"
```

What happens to each kind of item:

- **Text edit**: applied to the article markdown using its exact `file`, `before` and `after`.
- **Argument question**: added to `.academic-helper/revise-todo.md`, for the `/academic-writer:write` or `/academic-writer:edit` loop to resolve.
- **Voice signal**: appended to the shared `voice/pairs.jsonl`; style-word and terminology proposals are written to their store files only after confirmation.
- **Plugin defect**: appended to `${CLAUDE_PLUGIN_DATA}/feedback/ledger.jsonl` so the plugin can be improved.

The command prints which items were applied and which were deferred.

## 4. Rebuild the Word file and report

Regenerate the Word document the way `/academic-writer:write` built it: run `aw docx` with the same outline and output arguments (it rebuilds `.academic-helper/runs/<id>/article.json` and calls `generate-docx.py` for you). If there is no outline, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/generate-docx.py" --input <article.json> --output <file.docx>` on the last run's article JSON. Then tell the author, in four short lists: what was edited, what went to the voice store, what went to the plugin feedback ledger, and what is still open in `revise-todo.md`.

Finally, end the run: `"${CLAUDE_PLUGIN_ROOT}/bin/aw" --project-dir "$CLAUDE_PROJECT_DIR" --data-dir "${CLAUDE_PLUGIN_DATA}" activity end --run-id <id> --exit OK` (use `--exit ERROR` if a step failed and you stop). Ending a run that `aw revise apply` already ended is a no-op.

## Editor mode

Use this when the author runs `/academic-writer:revise <file.docx> --editor`, or says the Word file came back from a professional editor with many tracked changes. The result is a short list of conventions the author has confirmed, not a pile of edits. Skip steps 1 to 4 above: in editor mode the author's own text is not changed. Do step 0 first. The prompts, schemas and category list are in [references/editor-mode.md](references/editor-mode.md); read it before starting.

Work in `.academic-helper/editor-review/` (`WORK` below). Ask for the author's original file (the version before the editor); without it the baseline check cannot run, so say so and go on. Copy both files there as `edited.docx` and `original.docx`.

1. **Extract.** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/docx-editor-diff.py" extract WORK/edited.docx --original WORK/original.docx --work WORK`. It must report `baseline diffs vs original, body: 0, notes: 0`; if not, show the author the differences and ask which file is the true original before going on. Tell the author the op count and the font-switch count in one plain sentence.
2. **Chunk.** `... chunk --work WORK` gives about 110 ops per text chunk (a paragraph stays with its footnotes), one layout chunk and `auto-classified.json` for blank-line marks.
3. **Analyse.** One agent per chunk and one for the layout chunk, all in parallel, each `model: sonnet`, each with the chunk-analysis (or layout) prompt from the reference. Each writes `WORK/analysis/<chunk>.json` with one row per op id. If the author has opted in to workflows, load the `workflow-authoring` skill and run steps 3 to 5 as one Workflow script (phases Analyze, Synthesize, Verify); otherwise launch the same agents with the Agent tool in one message. Only Sonnet and Opus are used; never any other model.
4. **Coverage gate.** `... coverage --work WORK` must print `coverage OK`. On `MISSING` or `DUPLICATED`, send the named chunk back to its agent with the ids, re-run, and do not go on until it passes.
5. **Synthesize.** One agent, `model: opus`, with the synthesis prompt. Save its rules to `WORK/synthesis/rules.json`. This catalogue is a draft: it is never shown to the author and never copied as rule text.
6. **Verify.** One agent per rule group, `model: sonnet`, with the skeptic prompt. Concatenate the verdicts into `WORK/synthesis/verdicts.json`.
7. **Merge.** `... merge --work WORK --strict` writes `verified-catalogue.md`. Only a skeptic-verified wording can be offered: `refuted`, unverified and unrestated rules are not.
8. **Confirm with the author.** For each rule group, show the verified rules in plain words with one before/after example and the counts (applied, left alone), then ask with `AskUserQuestion`: general convention, this venue only, this paper only, not a rule, or skip. Write the answers to `WORK/decisions.json`, run `merge --decisions` again, and keep what was decided.
9. **Route.** Write each confirmed rule to its destination (conventions file, venue profile, project terms, noise ledger, plugin feedback ledger) as in the table in the reference. Append, never overwrite, and show the author each addition. Finish with the activity `end` command from step 4 above.

Traps that cost real time, so state them to every agent:

- Mirrored or reversed parentheses at the edge of right-to-left text are typing debris, not a convention.
- Editors are inconsistent. A rule needs two or more consistent instances, and the places the editor left alone count against it.
- Fuzzy paragraph pairing ("rewrite or move") can pair the wrong paragraphs; read both texts.
- The pre-skeptic catalogue (`rule-catalogue.md`, `rules.json`) must never be used as rule text. Only the verified wording goes to the author or to a file.
- Do not append fragment-level edits to voice pairs: a pair is a whole sentence before and after, taken from `full-before.md` and `full-after.md`, never a word-diff fragment.
