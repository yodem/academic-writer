# Changelog

All notable changes to the academic-writer plugin are documented here.

## [Unreleased]

### Added

- **Unified three-stage `/academic-writer:proofread`.** One user-facing skill now runs
  editorial (עורך — venue/genre fit, loaded terms used without definition, insider
  references, anecdote drift, journalistic vs research treatment), language
  (עריכה לשונית — collocations, cross-clause agreement, academic register, tense), and
  mechanical (הגהה — typos, punctuation, typography) as three different lenses in
  book-production order. `--venue <slug>` and `--only editorial|language|mechanical`.
  New agents `editor.md` and `copyeditor.md`; `proofreader.md` reframed as a
  chunk-scoped exhaustive finder.
- **A shared changes contract**, `src/skills/proofread/references/changes-schema.json`,
  emitted by all three agents and consumed by every script. Carries `stage`,
  `meaningRisk`, `applied`, `skipReason` and `refutedBy`, so a guarded, refuted or
  meaning-risky change stays visible in the report instead of disappearing.
- **Six deterministic scripts, each with pytest coverage**: `chunk-article.py`,
  `spellcheck-candidates.py`, `apply-changes.py`, `citation-guard.py`,
  `build-tracked-docx.py`, `write-proof-report.py`.
- **Real Word tracked changes and comments** on the original `.docx`
  (`build-tracked-docx.py`), replacing what was previously documented as a future
  option. Direct lxml on the unzipped XML, per-stage author names, and a real
  `comments.xml` part.
- **`src/workflows/proofread.js`**, a Workflow-tool orchestrator: caps come from
  `thresholds.json > proofread` via `args`, every loop exit is named
  (`converged` / `cap-reached`), and a refute majority DOWNGRADES a candidate rather
  than dropping it — dropping a true positive was the original recall failure.
- **A regression fixture** at `tests/fixtures/proofread/hebrew-recall/` plus a manual eval
  harness at `tests/e2e/proofread-recall.mjs`.
- **Version-drift tooling**: `scripts/version-locations.json` registers every place the
  plugin version lives and `scripts/version-sync.py` reads, checks, fixes, sets and
  bumps them as one operation. Release bump level now comes from conventional commits
  across every commit in the push, with a `workflow_dispatch` override.
- **A privacy/shareability gate**, `scripts/check-no-private-refs.sh`, wired into CI and
  pytest.

### Changed

- **Gemini is default-on for the profile's target language.** `approvedLanguages` is now
  seeded with `targetLanguage` when Gemini is enabled, so a project that only proofreads
  or edits routes to Gemini instead of silently never qualifying.
  `voice-calibrator --compare-models` becomes an optional opt-OUT rather than the only
  thing that could grant approval, and `write` no longer blocks on it.
- **The release now gates on the test suite.** `pytest` and `npm run typecheck` run
  against the bumped tree before it is tagged and published; previously the whole suite
  gated nothing.

### Fixed

- Hebrew inline-parenthetical citations no longer carry a publication year
  (`(מחבר, עמ' N)`), conditioned on the target language.
- `features.json` `pluginVersion` had drifted for two releases; every version location is
  now written by one script and checked by a CI gate.
- Every `status: "partial"` feature entry now states what is missing.
- `present` declared none of the NotebookLM MCP tools its body calls, so both of its
  optional branches could never have run.
- `proofreader.md` no longer cites a source absent from the library, and its remaining
  provenance is stated by title.

### Added

- **Gemini File API upload for OCR inputs over 20MB.** `uploadViaFilesApi()` was a
  named stub with a `TODO`; documents above the inline limit could only be handled
  by splitting them and OCR'ing page by page — more API calls, more wall-clock, and
  no cross-page context. Large files now upload once and are referenced by URI via
  a `fileData` part.

  Uses `@google/genai` 1.52.0's own `files.upload` / `files.get` / `files.delete`
  primitives — no hand-rolled HTTP was needed. Polls `PROCESSING → ACTIVE` at 2s
  intervals with a 2-minute ceiling, and raises on `FAILED` rather than hanging.
  The uploaded file is deleted in a `finally` block so cleanup runs on every error
  branch as well as on success, and a failed delete never masks the real OCR error.

  The per-page split is retained as the error-path fallback rather than removed.
  Sequential-only OCR, `thinking_budget=0` / `temperature=0` / `top_k=1`, and
  image-part-before-text are all preserved.

  Gemini server suite 54 → 64 passing.

## [0.6.1] — 2026-08-09

### Fixed

- **Voice migration silently did nothing for anyone upgrading from the old
  profile layout.** `voice-migrate.sh` checked `.academic-helper/profile.json`
  for the legacy profile it is supposed to migrate *from*, when the pre-rename
  directory is `.academic-writer/profile.json`. A blanket rename in `806c962`
  swept these two path checks along with the rest of the plugin rename. The
  migration then exited 0 — reporting success — while leaving voice fields stuck
  in the old dict shape and never seeding `AUTHOR_VOICE.md`. Broken since
  2026-06-03.

  This was surfaced by `test_voice_e2e_stage1.py::test_stage1_seeds_author_voice`,
  which had been carried as an accepted "pre-existing failure" across several
  sessions and shipped in that state with 0.6.0. It was reporting a real defect
  the whole time.

  Added `test_migrate_recognizes_academic_writer_legacy_path` to isolate
  legacy-path detection so this cannot silently regress again.

- `test_migrate_strips_voice_fields_and_archives` was additionally stale: it never
  created the `.academic-helper/profile.md` guard file that `voice-migrate.sh` has
  required since `bca2417`. Fixture added; no assertion was weakened.

Suite is now 82 passing, 0 failing.

## [0.6.0] — 2026-08-09

Audit-gap closure release. Everything below came out of the 2026-08-05→06 plugin
audit and the follow-up gap sweep.

### Added

- **`/academic-writer:ocr`** — the bundled `gemini_ocr` MCP tool finally has a
  user-facing entry point. Takes a PDF/image or a directory of them, calls the
  tool sequentially (never batched), follows the tool's own 40-page truncation
  loop, and writes to `ocr-output/<basename>.ocr.md`. Degrades honestly on files
  over 20MB, since the Files-API upload path is still a genuine `TODO` in the
  server.
- **Secure credential configuration** — the Gemini key can now be supplied via
  the plugin's `userConfig` (`sensitive: true`), so Claude Code stores it in the
  OS keychain instead of leaving it plaintext in the built `plugin.json`.
  Resolution order is `USER_CONFIG_GOOGLE_API_KEY` → `GOOGLE_API_KEY` env →
  `.academic-helper/secrets.json`. Strictly additive: every pre-existing path
  still resolves, including the lowercase `google_api_key` secrets-file field.
- **Resumable voice interview** — `.academic-helper/voice-checkpoint.json` is
  written after *every answered question*. `/voice` with no arguments resumes by
  default and reports position ("session 3 of 7, 12 of ~40 answered");
  `--restart` archives rather than deletes; `--session N` jumps.
- **`check-voice-populated.py`** — deterministic stub/populated check for
  `AUTHOR_VOICE.md` (exit 0 populated, 1 stub, 2 unreadable), with the rule
  documented in `skills/voice/references/stub-definition.md`.
- **`/write` voice precondition gate** — `/write` now refuses to draft against a
  stub voice file and directs the user to `/voice`. Fails closed on exit 2: an
  unreadable voice file is not treated as populated.
- **`disable-model-invocation: true`** on `init`, `setup`, and `voice` — the
  three skills that write persistent state, spend money, or hijack a session for
  ~70 minutes. They remain runnable by explicit `/name` invocation.

### Fixed

- **Voice distillation ran only after sessions 1 and 7.** This is the root cause
  of the long-standing "AUTHOR_VOICE.md is a stub" complaint: stopping partway
  through froze the session-1 output in place. The distiller now runs after every
  completed session, and partial profiles are stamped with an explicit coverage
  line instead of passing as complete.
- **8 npm vulnerabilities** (1 low, 4 moderate, 3 high) in the Gemini MCP
  server's dependencies → **0**. Six resolved by `npm audit fix`; the last two
  required `@google/genai` `^0.3.0` → `^1.26.0`, the smallest release that drops
  the vulnerable transitive `uuid`. No `--force` was used.
- **`build-plugins.sh` silently dropped manifest fields.** Its jq filter forwarded
  only `mcpServers`, so the new `userConfig` block would have vanished at build
  time; its awk extraction carried only `description`/`allowed-tools`, so
  `disable-model-invocation` would have been bypassable through the generated
  command copy. Both extended.
- **Literal plugin path** in `skills/write/SKILL.md` — the Hebrew punctuation
  validator was invoked as `plugins/academic-writer/scripts/...` instead of
  `${CLAUDE_PLUGIN_ROOT}/scripts/...`.

### Changed

- **Skills brought under the 500-line cap** via progressive disclosure:
  `init` 707 → 405, `write` 619 → 485, `voice` → 198. Detail moved verbatim into
  `references/*.md`; no step was dropped, only delegated.
- **Voice question bank trimmed** — two verbatim cross-session duplicates and one
  near-duplicate removed, two Hazal-transliteration questions merged. Session 3 is
  now declared the minimum-viable-voice milestone, so stopping there is a
  legitimate finish rather than an abandonment.
- The voice interviewer now **confirms** what the voice-miner inferred from
  `past-articles/` instead of asking cold.

### Notes

- `required-mcp-servers` was investigated and **does not exist** in current Claude
  Code. No such field was added anywhere. Every skill touching `mcp__gemini-api__*`
  has a documented Claude-only fallback, so it would not have applied regardless.
- The MCP `channels` pattern was likewise investigated and found to be for servers
  *pushing* messages into a session, not for supplying credentials. `userConfig` is
  the correct mechanism and is what shipped.
- Two pre-existing test failures remain in `test_voice_e2e_stage1.py` and
  `test_voice_migrate.py`, unrelated to this release and untouched by it.

## [0.5.1] and earlier

See git history.
