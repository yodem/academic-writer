# Findings Disposition — 2026-09-02

Source of findings: `the maintainer's private improvements page (not committed)`
(10 numbered findings, P0/P1/P2, dated 2026-09-01).

Branch audited: `feat/proofread-pipeline-0.7.0`, 4 commits ahead of `main`:
`82594aa`, `cae0f6c`, `eaec73c`, `98f5bf7`.

Method: for each finding, `git show --stat <hash>` and `git log -p main..HEAD -- <file>`
against the four commits, then read the current file content and, where a claim concerned
something that predated the branch, `git blame`/`git log --follow` to establish whether the
cited fact existed before or after the finding was written (2026-09-01).

## Disposition table

| # | Title | Disposition | Evidence |
|---|---|---|---|
| 1 | Hebrew inline-parenthetical citation carries a year | CLOSED | `eaec73c`; `plugins/academic-writer/mcp/gemini-server/src/tools/write_section.ts:74-91`; `tests/test_hebrew_citation_example.py` (8/8 pass) |
| 2 | CLAUDE.md stale on setup skill | CLOSED | `eaec73c`; `CLAUDE.md:48` |
| 3 | Gemini retry constants outside thresholds.json "violates convention" | INVALID | `src/thresholds.json:3` (description added 2026-08-06, commit `b6613d4`, predates the finding by 26 days) |
| 4 | Test suite doesn't verify referenced scripts exist | INVALID (as stated); narrower gap noted | `tests/test_plugin_structure.py:286` (`TestScriptReferences`), `:309` (`test_referenced_scripts_exist`), introduced by commit `16bf8b8` (`git log -S`); `src/agents/proofreader.md:89` |
| 5 | features.json pluginVersion stale (0.5.0 vs 0.6.3) | CLOSED | `98f5bf7`; `features.json:5`; `scripts/version-locations.json`, `scripts/version-sync.py`, `.github/workflows/release.yml` "Gate — version agrees across ALL registered locations" |
| 6 | gemini_synthesize / gemini_edit marked "partial", no issue notes | STILL-OPEN | `features.json:397-399,401-403` |
| 7 | Fallback pipeline in section-writer.md duplicates Skills 1-7 | STILL-OPEN | `src/agents/section-writer.md:330` ("## Fallback: in-context Skills 1-7"); no `references/fallback-pipeline.md` exists; file untouched by any of the 4 commits |
| 8 | voice.ruleCoverage warn == block (both 6.0) | STILL-OPEN | `src/thresholds.json:36-40` |
| 9 | "No CI configuration exists" | CLOSED (claim was partly false — see detail) | `.github/workflows/release.yml` added by `ed16818`, predates this branch; `cae0f6c` added the missing pytest/typecheck gate |
| 10 | CHANGELOG [Unreleased] contains shipped features | STILL-OPEN | `CHANGELOG.md:5,27`; file untouched by any of the 4 commits |

---

## Detail

### 1. Hebrew inline-parenthetical citation — CLOSED

Finding claimed the Gemini prompt's inline-parenthetical example used `(Author Year, page)`
for Hebrew, contradicting the no-year Hebrew convention.

`eaec73c` ("two P0 corrections") added a `citationFormatBullets()` helper in
`plugins/academic-writer/mcp/gemini-server/src/tools/write_section.ts` (this path is the
committed MCP source, not a build artifact — `scripts/build-plugins.sh:45-54` explicitly
preserves `plugins/academic-writer/mcp/` across a clean because it "holds bundled MCP server
sources"). Lines 79-82:

```
const inlineParenthetical =
  targetLanguage.toLowerCase() === 'hebrew'
    ? "`inline-parenthetical`: `(מחבר, עמ' N)` — Hebrew citations omit the publication year; use author + page only."
    : '`inline-parenthetical`: `(Author Year, page)`';
```

`(Author Year, page)` still appears at line 82, but only as the non-Hebrew branch — the finding
was specifically about the Hebrew example, which is now year-free. The function is wired in at
line 122 (`citation_format_bullets: citationFormatBullets(input.target_language)`).

`src/agents/section-writer.md:363` (fallback path) was already correct pre-branch — no year
field, `(Author, Title, Page)` form.

A dedicated regression test, `tests/test_hebrew_citation_example.py`, exists and asserts no
4-digit year appears in the Hebrew example in either the Gemini prompt file or the fallback
markdown. Ran `python3 -m pytest tests/test_hebrew_citation_example.py -q` → 8 passed.

### 2. CLAUDE.md stale on setup skill — CLOSED

`eaec73c`'s commit message states the correction explicitly: `CLAUDE.md:48` now reads:

```
| `/academic-writer:setup` | setup | Guided first-run wizard (Gemini key, Python tools, sample paragraph) — slash-command only (`disable-model-invocation: true`, so Claude will not auto-invoke it) |
```

confirmed present in the current file.

### 3. Gemini retry constants outside thresholds.json — INVALID

The finding's premise is that project convention requires all numeric config in
`thresholds.json`, and that keeping Gemini retry constants in `gemini-client.ts` violates it.
But `src/thresholds.json:3` (the `description` field, i.e. the file's own statement of its
scope) already says:

> "Gemini model/thinking-budget defaults and retry policy are NOT read from here — they live
> in SPEC_DEFAULTS in plugins/academic-writer/mcp/gemini-server/src/gemini-client.ts
> (overridable per-project via profile.md), and the retry constants are hardcoded in that same
> file."

`git blame -L 3,3 main -- src/thresholds.json` attributes this line to commit `b6613d4`,
dated 2026-08-06 — 26 days before the finding was written (2026-09-01). `git log -p
main..HEAD -- src/thresholds.json` shows the only change on this branch (`82594aa`) added an
unrelated `proofread` block; the description line was not touched. The documented exclusion
is a pre-existing, intentional carve-out, not an inline-constant convention violation — the
finding is invalid as written; no code change occurred or was needed on this branch.

### 4. Test suite doesn't verify referenced scripts exist — INVALID as stated, narrower gap noted

`tests/test_plugin_structure.py:286` (`class TestScriptReferences`) and `:309`
(`def test_referenced_scripts_exist`, method body runs to line 322) already parse every
skill/agent markdown file for `scripts/<name>.py`-style references and assert each resolves
under `src/scripts/`. A direct `git blame -L 286,286 main -- tests/test_plugin_structure.py`
lands on a different line than the current working-tree line 286 (the file was reshuffled by
`82594aa`), so the introducing commit was instead pinned with
`git log -S "test_referenced_scripts_exist" --oneline -- tests/test_plugin_structure.py`,
which returns exactly one commit: `16bf8b8`, dated 2026-07-03 — almost two months before the
finding was written. The finding's factual premise ("No test asserts referenced scripts
exist") is false; disposition is INVALID.

Narrower point, not the finding as written but worth recording: `src/agents/proofreader.md:89`
references a script named `spellcheck-candidates.py` in prose, but without a `scripts/` prefix
(`` `spellcheck-candidates.py` `` rather than `` `scripts/spellcheck-candidates.py` ``), which
means the existing regex (`SCRIPT_REF_RE`) does not match it, and the test does not fail even
though the script does not exist (`find . -name spellcheck-candidates.py` returns nothing).
This is deliberate, self-acknowledged tech debt from `82594aa`'s own commit message: "Known
follow-up: proofreader.md refers to spellcheck-candidates.py without its literal path, to work
around test_referenced_scripts_exist while that script is unwritten. Restore the literal path
when it lands." This is a real but narrow gap in test coverage (one known, tracked exception),
not the broad absence the finding claimed.

### 5. features.json pluginVersion stale — CLOSED

`98f5bf7` fixed both the immediate drift and the systemic cause.
`git show 98f5bf7 -- features.json | grep -B2 -A2 pluginVersion` shows the actual hunk:
`-  "pluginVersion": "0.5.0",` / `+  "pluginVersion": "0.6.3",`. `features.json:5` in the
current tree confirms `"pluginVersion": "0.6.3"`, matching `package.json:3`. The commit also
added
`scripts/version-locations.json` (all six version-bearing locations registered as data) and
`scripts/version-sync.py` (single implementation for show/check/fix/set/bump), plus a new
`.github/workflows/release.yml` step, "Gate — version agrees across ALL registered locations,"
which runs `python3 scripts/version-sync.py --check`. This directly implements fix (b) from
the finding (a build-time drift check), going further than the finding's ask by making the
check a release gate rather than a warning.

### 6. gemini_synthesize / gemini_edit marked "partial" — STILL-OPEN

`features.json:397-399` (`synthesize-tool` / `gemini_synthesize`, `"status": "partial"`) and
`:401-403` (`edit-tool` / `gemini_edit`, `"status": "partial"`). Neither entry carries an
`"issue"` key (contrast with the `write-section-tool` entry immediately above at
`features.json:390-394`, which does have one: `"issue": "Contract fixed to match
section-writer.md — see section-writing.gemini-write for detail"`), so fix (a) from the
finding (add issue notes) has not been done. `git show 98f5bf7 -- features.json | grep -B2
-A2 pluginVersion` confirms the only line this branch changed in `features.json` is
`pluginVersion` ("0.5.0" → "0.6.3"); the `synthesize-tool`/`edit-tool` entries are untouched.
Both the "add issue notes" and "prioritize completing gemini_synthesize" asks remain open.

### 7. Fallback pipeline duplication in section-writer.md — STILL-OPEN

`src/agents/section-writer.md:330` still has an inline `## Fallback: in-context Skills 1-7`
section (file is 491 lines total; the fallback runs from line 330 to line 442, "## Style
Rules (both paths)"). `find src -iname "fallback*"` returns no results — no
`references/fallback-pipeline.md` or similarly named extracted file exists anywhere under
`src/`. `git log --oneline main..HEAD -- src/agents/section-writer.md` returns no commits —
this file was not touched on the branch. The proposed refactor has not happened.

### 8. voice.ruleCoverage warn == block — STILL-OPEN

`src/thresholds.json:36-40`:

```json
"voice": {
  "ruleCoverage": {
    "pass": 8.0,
    "warn": 6.0,
    "block": 6.0
  },
```

Both `warn` and `block` are still `6.0`. `git log -p main..HEAD -- src/thresholds.json` shows
the only change on this branch (`82594aa`) added the unrelated `proofread` block; lines 30-39
(`styleFingerprint`/`voice`) were not touched. Not addressed.

### 9. No CI configuration in repository — CLOSED (claim was partly false)

The finding's literal claim, "No `.github/workflows/` directory is present," is false and was
already false when written: `.github/workflows/release.yml` was added by commit `ed16818`
("ci: auto-bump patch version on every push to main"), which predates this branch and predates
the finding. `git show main:.github/workflows/release.yml` confirms it exists on `main`.

The true part of the concern — that the existing workflow ran `check-version-consistency.sh`
and `check-built-manifest.sh` but never ran `pytest` or `npm run typecheck`, so a broken build
or failing test suite could still be released — was real. `cae0f6c`'s commit message confirms
this was verified against the actual pre-branch file ("Verified against the repo: it is not
[CI-wired]... No pytest, no typecheck..."), and the diff in that commit adds exactly those two
gate steps ("Gate — deterministic test suite", "Gate — strict TypeScript on hooks") plus
`requirements-dev.txt` for the suite's own undeclared dependencies (`python-docx`,
`jsonschema`, `lxml`, `PyYAML`). Disposition: CLOSED for the substantive gap (no test gate);
the finding's own framing ("no CI configuration exists") was inaccurate and should be corrected
rather than closed literally.

### 10. CHANGELOG [Unreleased] contains shipped features — STILL-OPEN

`CHANGELOG.md:5` is still `## [Unreleased]`, and its content (the Gemini File API OCR upload
work) corresponds to `features.json`'s `ocr-tool` entry, which is `"status": "ok"` — i.e.
already shipped/production, matching the finding's description. `CHANGELOG.md:27` shows the
last dated header is `## [0.6.1] — 2026-08-09`, while `package.json:3` is at `0.6.3`.
`git log --oneline main..HEAD -- CHANGELOG.md` returns no commits — this file was not touched
by any of the four commits on this branch. Not addressed.

---

## `git log --oneline main..HEAD`

```
98f5bf7 build(release): bump levels, and make version drift impossible deterministically
eaec73c feat(gemini,docs): Gemini default-on for the target language; two P0 corrections
cae0f6c ci(release): gate the release on pytest and typecheck
82594aa feat(proofread): shared changes contract, three-stage agents, first deterministic scripts
```
