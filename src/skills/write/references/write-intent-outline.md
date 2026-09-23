# W0–W2 artifact reference

## Author intent

`author-intent.json` is the author's source of truth. Validate it against `author-intent.schema.json` in this directory. Preserve `thesis` verbatim and use a source ID from the selected project sources as `coreTextSourceId`. `moves` records the author's argumentative moves. `mustUse` contains evidence passage IDs, and may be empty until evidence has been built and the author selects passages.

## Evidence build

`aw evidence build` reads the intent path, extracts passages, and writes `.academic-helper/evidence.json`. Its `passages[].id` values are the only evidence IDs that may appear in outline paragraph `evidenceIds`. The evidence file also contains `sources[]`; do not substitute source IDs where passage IDs are required.

## Outline contract

The architect writes this shape directly to `.academic-helper/outline.json`, following `outline.schema.json` in this directory:

```json
{
  "thesis": "The author's exact thesis",
  "thesisSha256": "sha256 of the UTF-8 thesis string",
  "sections": [
    {
      "id": "S1",
      "title": "Section title",
      "claim": "A claim for the author to approve",
      "approved": false,
      "units": [
        {
          "id": "U1",
          "dependsOn": [],
          "paragraphs": [
            { "move": "Interpret the passage", "evidenceIds": ["p1"], "bridgeTo": "The next claim" }
          ]
        }
      ]
    }
  ]
}
```

Use one or more paragraphs in each unit. A paragraph's `move` describes its argument function; `bridgeTo` explains its transition. `dependsOn` names prerequisite unit or section IDs. A dependency cycle blocks the gate. The thesis hash is the lowercase hexadecimal SHA-256 of the exact UTF-8 bytes of `author-intent.json`'s `thesis` string.

## Support signal and author label

Store the claim, its evidence passages, and the architect's concise rationale in a project-local context file. Run `aw decide outline.support` for each claim. `--fallback` must be `supported` or `unsupported`, chosen from the architect's support note. After the author responds, set `--label` to `approved` or `rejected`. `decide()` logs the Jev/model result and label in the run ledger; the support answer never overrides the author or changes the gate verdict.

## Gate failures

- `thesis-drift`: restore the author's exact wording or update the intent only after the author changes it, then regenerate the hash.
- `unresolved-evidence`: replace each unknown ID with an actual `passages[].id` from evidence.
- `must-use-unplaced`: include every required passage in a paragraph's `evidenceIds`.
- `unapproved-section`: ask the author to approve or revise the claim; never infer approval.
- `dependency-cycle`: remove a circular `dependsOn` edge while preserving the intended reading order.

Rerun `outline-v2` after every change. Only an exit code of zero permits drafting.
