# Proofread (הגהה) feature — build record

**Date:** 2026-06-07 · **Version:** proofread skill v0.1.0
**Decision:** Option A (markdown report) + mechanical-only, per user.
**Modeled on:** `hebrew-book-producer`'s proof subsystem (`/proof` → `proofreader` agent → `changes-schema` → DOCX suggestions).

## What this adds

A `/academic-writer:proofread` command that runs a **mechanical-only** proofreading pass over a finished article: it fixes typos, punctuation, spacing, Hebrew typography, and clear grammar errors, writes the corrected text to a new file, and produces a markdown report documenting **every change and why**. It never rewrites prose for style, tone, register, or voice — that stays with `/academic-writer:edit`.

## Design decisions (what transferred, what didn't)

| From hebrew-book-producer | Decision | Why |
|---|---|---|
| Suggestion mode (never edit manuscript) | **Adapted** — original file untouched; fixes go to `*.proofed.md` | Safety: user accepts/rejects from the report. The original is never mutated in place. |
| Four levels (letter/word/sentence/idea) | **Kept** | The canonical הגהה taxonomy; idea-level stays flag-only. |
| Idea-flags never auto-fixed | **Kept** | Idea-level issues need a human; auto-fixing them would change meaning. |
| Citation verification inline | **Replaced with a deterministic differential guard** (see Code-review revisions) | The proofreader is forbidden from touching citation tokens; the guard verifies that invariant directly rather than re-auditing. |
| Report at the end | **Kept (markdown, not DOCX)** | Option A. Markdown report = no new Python; upgradeable to DOCX/`/apply` later with no rework to the agent. |
| Two-pass (pre/post-typeset) | **Dropped** | academic-writer has no typesetting stage that induces layout errors — no concrete pass-2 trigger. |
| Chunk-parallel by chapter | **Dropped as default** | An article is not book-scale. One spawn over the whole article by default; per-section parallel is an optional optimization for long articles only. |
| `section-writer` for fixes | **Explicitly avoided** | section-writer rewrites prose — the opposite of proofreading. |

## Files changed and why

| File | Change | Why |
|---|---|---|
| `src/agents/proofreader.md` | **New agent.** Suggestion-only מגיה. Reads text, returns a JSON change list (`typo`/`punctuation`/`word`/`grammar`/`typography`/`idea-flag` at four levels). Read-only tools (`Read, Grep, Glob`), `model: sonnet`. | The find step. Kept read-only so it can never edit a file or rewrite prose; it only proposes. Named failure modes ("Helpful Rewriter", "Citation Surgeon", "Silent Meaning Shift") fence it to mechanical scope. |
| `src/skills/proofread/SKILL.md` | **New skill** (`user-invocable: true`). Orchestrates: load profile → resolve article to a text `PROOF_BASE` (`.md`/`.docx`) → spawn `proofreader` → deterministic citation-integrity guard → apply mechanical fixes to `*.proofed.md` (ordered, overlap-aware, no-match-safe) → write `*.proofread.md` report → summarize. | The orchestrator. Applies only guard-passing mechanical changes; idea-flags and citation-touching changes are reported, never applied. |
| `CLAUDE.md` | Added rows to the **slash-command table** and the **agents table**. | Project doc convention — both tables are the registry of commands/agents. |
| `src/skills/help/SKILL.md` | Added a `proofread` row to the slash-command list. | Enforced by `tests/test_plugin_structure.py::test_help_lists_all_slash_commands` — help must list every user-invocable command. |

No new Python, no new dependency, no `thresholds.json` change (mechanical proofreading has no numeric gate). No `.academic-helper/` writes — all outputs land in `articles/`.

## Runtime outputs (per run)

- `articles/<name>.proofed.md` — the corrected copy (mechanical fixes applied; idea-flags NOT applied).
- `articles/<name>.proofread.md` — the change report: one table row per applied change with its rationale, plus a separate idea-flags table, plus a notes section (citation-integrity guard downgrades, un-localizable snippets).

## Verification

- `npm run build` → exit 0 (17 skills, 10 agents, 12 commands).
- `python3 tests/test_plugin_structure.py` → 26 tests, all pass.

## CandleKeep validation (2026-06-07)

Reviewed the encoded conventions against the library's source-of-truth books: *The Writer's Guide: How to Write, Edit, and Proofread a Book* and *Hebrew Linguistic Reference*.

| Convention | Verdict | Source |
|---|---|---|
| Four levels אות→מילה→משפט→רעיון | CORRECT (exact, cited from Textratz) | Writer's Guide ch.7 §7.3, p.8 |
| idea-level = flag, not rewrite | CORRECT (book: "very limited; flag rather than rewrite"; we tighten to flag-only) | Writer's Guide §7.3 |
| Proofreader = mechanical only; rephrasing/register/restructure forbidden | CORRECT — "Proofreading is not editing… changes are limited to correcting typographical errors" | Writer's Guide ch.6–7, pp.7–8 |
| gershayim ״ / geresh ׳ / maqaf ־ | Rules CORRECT but agent was under-specified | Hebrew Linguistic Reference ch.6, p.1 |

Refinements applied to `proofreader.md` as a result:

- **Over-correction guards** (the books' explicit warnings): maqaf only for compound/construct words — ranges take an en-dash (45–67), phone/model codes keep the ASCII hyphen; geresh = single-letter abbreviations, gershayim = multi-letter acronyms + quotation; single-letter number markers take *no* mark (פרק ב, not ב׳).
- **Added mechanical categories** a מגיה owns: NBSP between number+unit; comma-not-colon in Hebrew source refs; en-dash ranges + decimal/thousands; gershayim in Talmud folio markers; 2017 כתיב מלא spelling reform (guarded: proper names exempt, no retro-fix, enforce internal consistency, ambiguous → idea-flag).
- **Explicitly excluded** register-consistency and connective-frequency caps — the reviewer flagged these as valuable, but they are עריכה לשונית (language editor), not הגהה. Excluding them keeps the mechanical-only boundary the books endorse.

**Deliberately not adopted from the books:** the *two-pass (pre/post-typeset)* standard and the post-typeset layout checks (RTL/LTR drift, broken running headers). Those presuppose a typesetting (עימוד) stage that academic-writer does not have — there is no concrete pass-2 trigger here. Documented as a known divergence; revisit if a typesetting/DOCX-layout stage is ever added.

## Code-review revisions (2026-06-07) — skill v0.1.0 → v0.2.0

Two parallel ork reviewers (code-quality + system-design) ran against the working tree. Both converged on the citation gate as the central defect. Fixes applied:

| Finding (severity) | Resolution |
|---|---|
| **`.docx` corrected-copy corruption** (blocking) — Step 5 `cp`'d the binary source into a `.md`, so all `Edit`s failed and the "corrected copy" was an unreadable blob | Introduced **`PROOF_BASE`**: the `.docx` text is extracted to a real `articles/<name>.extracted.md`, which is both what the proofreader reads and what the corrected copy is seeded from. The corrected copy is never a copy of a binary. |
| **Citation gate measured the wrong thing** (P0, both reviewers) — re-auditing the edited sentence in isolation gives an *absolute* verdict (auditor REJECTs on a footnote it can't resolve out of context, or on pre-existing Check E/F/G issues), silently downgrading *valid* mechanical fixes; missing `sources.json` made it vacuous; `PARTIAL` over-blocked | Replaced the auditor spawn with a **deterministic differential citation-integrity guard**: it checks whether a change's `before`/`after` overlaps a citation/quotation/page/footnote *token* and, if so, refuses to apply it (downgrade to idea-flag). Answers the differential question directly, needs no `sources.json`, can't over-block clean prose, can't silently drop a non-citation fix. `auditor` removed from the skill's `agents:` list — resolves the false "exactly as the edit skill does" claim and the auditor's "spawned only by section-writer" contract violation. |
| **Apply strategy fragile** (P1) — no ordering, no overlap handling, verbatim exotic-Unicode round-trip brittle exactly on the typography this tool targets | Step 5 now: sorts changes and applies **bottom-to-top**; **combines overlapping same-span edits**; requires a **unique match** (expand context or skip); treats an **`Edit` no-match as a hard skip recorded in Notes**, never a hand-forced rewrite; anchors typography fixes by line + ASCII neighbour. |
| **Empty-change run** wrote a duplicate file + empty report | Zero-applicable-changes path now skips the corrected copy and reports a clean pass. |
| **"Accept or reject" overstated the UX** (P2) — corrected copy has all fixes pre-applied | Reworded: "review the report against the corrected copy and revert by hand"; one-click accept/reject noted as the Option-B upgrade. |

Re-verified after fixes: `npm run build` → exit 0; `python3 tests/test_plugin_structure.py` → 26 tests pass.

## Future upgrade path (Option B, not built)

`changes.json` schema + DOCX native tracked-changes renderer + `/apply` accept/reject round-trip. Feasible — `generate-docx.py` already manipulates raw OXML (`OxmlElement`), so Word `w:ins`/`w:del`/comments are reachable with the existing `python-docx` + `lxml` stack. Only the report-rendering layer would change; the `proofreader` agent's output is already a structured change list.

---

## v2 (0.7.0, in progress) — unified three-stage pipeline, after the קתרסיס rejection

Plan of record: `the 0.7.0 plan of record (local, not committed to this repo)` (2026-09-02).
The article proofread on 2026-07-10 was submitted to קתרסיס and rejected; **all 9 mechanical
errors the editor quoted survive in `the sample article (~6,600 Hebrew tokens)`** (grep-verified 2026-09-02).
Several belong to error classes the same pass fixed elsewhere — a **recall** failure of a single
unverified pass, not a rule gap. Root cause is recorded in the section above: the source books'
two-pass standard was deliberately dropped, chunk-parallel was dropped as the default, and no
convergence gate or adversarial verification replaced them.

### Phase 0 — hspell spike, 2026-09-02: NO-GO on the stated gate, adopted in a narrowed role

hspell 1.4 via Homebrew, measured over the 6,584 Hebrew tokens (2,587 unique) of
`the sample article (~6,600 Hebrew tokens)`:

| Measure | Gate | Measured | Verdict |
|---|---|---|---|
| Known target tokens flagged | ≥ 4 of 6 | **0 of the 4 present in the file** (2 of 6 counting נישאוים / קאטנ fed directly — those are not in this file) | fail |
| Flag rate | ≤ 8% of tokens | **3.71%** — 60 unique flags, 244 occurrences | pass |

**The gate was measuring the wrong thing.** hspell accepts לארוס · התרי · למלות · לאוהב as valid
Hebrew morphology, and it is right to: they are real words in wrong contexts, not misspellings.
No spell-checker of any kind reaches that error class. **Recall on the editor's 9 quotes therefore
depends entirely on the LLM finder plus chunking and the convergence loop, never on hspell** — and
the regression fixture asserts the spell-check stage contributes 0 of the 9, so a future recall
regression cannot be masked by the checker.

hspell is still adopted as an *additive* candidate generator, on its own merits: of the 60 unique
flags, ~15 are real orthographic errors that the 2026-07-10 pass also missed — בהגתו · ישיעיהו ·
האריסטותליות · האוקראניים · בליברליזים / לפלורליזים / שבליברליזים · כעיסקת / עיסקה ·
נסיונותיהם · בשניה · דחיה. The rest are ~20 legitimate ktiv-male forms the Academy dictionary
rejects (אמיתי, איתו/איתה/איתם, אזי, אידיאולוגיה, האשה, הדוגמא, הינה, האוכלוסיה, מודרנים,
קורבנות, רדיקאלית, פרסונאלי), ~9 proper nouns (בובר, בודפסט, הרטמן, ליבוביץ, פינס, קאנט,
בלייקווד) and 10 artifacts of stripped ׳/״ in abbreviations (הרמב, התנ, פרופ, סולוביצ). Precision
≈30%, which is acceptable because an LLM adjudicates each candidate — a false positive costs one
line of prompt. The 2026-05-19 pg_hspell rejection (CandleKeep "Personal · Projects" p.26) does
reproduce here after all, via ktiv male rather than Mishnaic orthography; a project-extensible
allowlist at `src/skills/proofread/references/hspell-allowlist.txt` suppresses that class.

**Encoding is a correctness requirement, not a detail.** hspell 1.4 reads **ISO-8859-8 only**, and
a plain `iconv -f UTF-8 -t ISO-8859-8` **aborts at the first niqqud or geresh**, after which hspell
silently scores a truncated document. This spike measured 2, then 4, then 10 flags off the same
vocabulary before `iconv -c` was used; the true figure is 60. `spellcheck-candidates.py` must
transcode lossily in both directions, assert its output token count against its input, and preserve
׳/״ (or map them to ASCII) so abbreviations are not shredded into phantom flags. A pytest case
feeds niqqud and geresh and asserts no truncation.

> **Correction, 2026-09-02 (same day):** `דוצדדית` was listed above as a real error. It is not.
> The source reads `דו־צדדית` with a **maqaf (U+05BE)**; the hand measurement's token regex
> `[\u0590-\u05FF]{2,}` swallowed the maqaf, and `iconv -c` then dropped it — fabricating a
> non-word that never appears in the article. `spellcheck-candidates.py` treats maqaf as a
> separator and correctly yields two valid words. The real-error count is ~14, not ~15.
> Guarded by `tests/test_spellcheck_tokenizer.py::test_maqaf_separates_words`.

