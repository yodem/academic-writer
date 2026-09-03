# Changelog

All notable changes to the academic-writer plugin are documented here.

## [Unreleased]

## [0.7.2] — 2026-09-03
### Fixed

- **The Gemini routing added in 0.7.x never ran — every reference used a tool name
  that does not resolve.** Claude Code registers a plugin-provided MCP server as
  `mcp__plugin_<plugin>_<server>__<tool>`, so the bundled server's real tool names
  are `mcp__plugin_academic-writer_gemini-api__*`. All 35 references across 11 source
  files used the bare `mcp__gemini-api__*` form instead. The failure was silent by
  construction: `section-writer`, `synthesizer` and `voice-calibrator` each name the
  tool in their frontmatter `tools:` allowlist, so the allowlist named a tool that
  does not exist and each agent was spawned without it; their prompts then hit the
  documented guard — "if the tool is NOT present in your available tools at all,
  treat that identically to a `no_credentials` error and use the fallback path
  immediately" — and quietly degraded to in-context Claude. Nothing errored, and the
  MCP server itself tested healthy end-to-end the entire time, which is why three
  releases shipped with the feature inert.

  Confirmed that an explicit frontmatter allowlist *does* deliver an MCP tool when the
  name is correct, rather than assuming it: `deep-reader` declares
  `mcp__claude_ai_Sefaria__get_text` and receives it, while its siblings naming the
  bare form receive nothing. The agents differed only in the tool name.

  The rename also covers `src/workflows/proofread.js:373`, a plain string assignment
  (`opts.mcpTool = '...'`) that a frontmatter-only sweep would miss, and the Path A
  prereq in `tests/e2e/fixture-project/RUN.md`, which told an operator to check for a
  tool name that never existed. Bare-form references in `CHANGELOG.md`,
  `features.json` and `docs/{audits,reviews}/` are deliberately left as-is — they are
  dated records of what was true when written. `docs/reviews/2026-05-28-ork-candlekeep-audit.md`
  is one of them: it reported this exact bug ("reference `mcp__gemini-api__*` tools
  that have no registration path") three months before it was fixed.


## [0.7.1] — 2026-09-02
### Changed

- **`release.yml` no longer bumps the version — it publishes what is committed.**
  The workflow used to derive a bump level from the commits since the last release
  tag and write the new version itself, which made the tree's own version
  meaningless between releases: a maintainer who hand-bumped to prepare a release
  got bumped a *second* time by the job, cutting a tag that disagreed with the
  CHANGELOG section written for it. The version is now decided in exactly one
  place — the commit that makes the change (`version-sync.py --bump ...` plus a
  hand-written CHANGELOG section) — and this workflow verifies and tags it. Two
  new guards replace what the bump used to guarantee implicitly: the job fails if
  `v<version>` is already tagged, and fails if `CHANGELOG.md` has no
  `## [<version>]` section. It no longer rebuilds or commits, so its gates now
  check the exact bytes that ship rather than a tree it just regenerated, and its
  only writes are the tag and the GitHub Release — it can't race a maintainer's
  push or leave `main` in a state nobody authored. All eight shared gate `run:`
  lines remain textually identical to `ci.yml`'s.

- **`release.yml` no longer triggers on push — releases are now a deliberate
  `workflow_dispatch` action.** `push: branches: [main]` meant every push auto-cut a
  release, which is exactly what let the `gemini-api` dist/ regression below ship
  silently for three releases with no one deciding "release now". The quality gates
  `release.yml` carried (test suite, `check-mcp-dist.sh`, `check-no-private-refs.sh`,
  version consistency, hooks typecheck) still need to block every push, so they moved
  to a new **`.github/workflows/ci.yml`**, which runs on `push: [main]` and
  `pull_request` and runs every one of those gates against the tree AS PUSHED —
  no bump, rebuild, tag, commit, or publish. The two files intentionally share
  identical `run:` commands for every gate so they can't drift apart in what they
  check.
- **New gate: `scripts/check-mcp-dist-fresh.sh`** (+ `tests/test_mcp_dist_fresh.py`).
  With auto-release gone, CI no longer rebuilds and commits `dist/index.js` on every
  release — the committed bundle is now the only copy that ever ships, and
  `check-mcp-dist.sh` only proves it *starts*, not that it still matches `src/`. This
  rebuilds the server from `src/` in an isolated temp copy (`npm ci` against the
  pinned `gemini-server/package-lock.json`, then the same `esbuild.config.mjs`) and
  fails if the result differs byte-for-byte from what's committed. esbuild's output
  was verified byte-identical across three consecutive rebuilds before relying on a
  direct comparison — the bundle carries no embedded absolute paths, timestamps, or
  version string, and the lockfile pins the exact esbuild version, so a rebuild in CI
  uses the same dependency graph as a rebuild on a maintainer's machine. Wired into
  both `ci.yml` and `release.yml` — in `release.yml` specifically *before* the bump
  and rebuild steps, so it validates what was actually committed rather than a
  rebuild compared against itself.
- **New `.gitattributes`** marks the committed bundle
  (`plugins/academic-writer/mcp/gemini-server/dist/index.js`) `-diff
  linguist-generated=true` so it stops showing full diffs in PR review and doesn't
  count toward GitHub's language statistics, now that it's a permanent, sizeable
  (2.3MB) tracked file rather than a build artifact.

### Fixed

- **Every user-invocable skill appeared three times in the command palette.**
  `build-plugins.sh` generated a `commands/<name>.md` wrapper for each of the 13
  skills marked `user-invocable: true`, whose body was nothing but
  `# Auto-generated from skills/<name>/SKILL.md` followed by a copy of the skill.
  Claude Code registers user-invocable skills in the palette on its own, so every one
  of those names rendered three identical rows (`/academic-writer:ocr`,
  `:init`, `:edit`, `:write`, `:help`, … each ×3). The control that isolated it:
  skills with `user-invocable: false` and therefore no wrapper (`learn`, `present`,
  `feedback`, `update-field`, `update-tools`) rendered exactly one row each — which
  also ruled out the plugin being loaded more than once and ruled out stale cache
  version directories, since a directory scan would have multiplied those too.
  The generator block and all 13 generated files are gone; each skill keeps its
  single `/academic-writer:<name>` palette entry. Verified against Claude Code
  2.1.258 by removing `commands/` from an installed 0.7.0 cache and restarting —
  the triples collapsed to one row per skill.

- **`gemini-api` MCP server `CONNECTION_CLOSED` on every fresh install.** `dist/` for
  `plugins/academic-writer/mcp/gemini-server/` was gitignored, so the published plugin
  shipped `plugin.json`'s `mcpServers.gemini-api` command (`node .../dist/index.js`)
  with no `dist/index.js` on disk — a regression since v0.6.2 (confirmed broken
  through v0.7.0 across every installed copy). `dist/` is now committed (sourcemap
  generation turned off — it shipped no runtime value and is one more file for the
  privacy scan to clear).
  `dist/index.js` is now a **fully self-contained bundle**: `esbuild.config.mjs`
  inlines `@modelcontextprotocol/sdk` and `@google/genai` (`external: []`) instead of
  externalizing them, so no `node_modules` needs to ship alongside `dist/index.js` at
  all. The blocker on the first attempt at this was `google-auth-library` (pulled in
  via `@google/genai`) calling `require('child_process')` etc. internally — esbuild's
  ESM output throws `Dynamic require ... is not supported` for that, and switching to
  CJS output instead broke the `import.meta.url` resolution used elsewhere in the
  server. The fix is the standard one for exactly this case: a
  `createRequire(import.meta.url)` banner shim, so those internal dynamic `require()`
  calls resolve against the bundle's own inlined modules at runtime. Verified directly
  by running the shipped `dist/index.js` alone — no `node_modules` anywhere in its
  ancestry — through the full MCP `initialize`/`tools/list` handshake, a live
  `gemini_raw` API call, and a real `gemini_ocr` call against a two-page PDF slice
  (Python OCR helper scripts under `mcp/gemini-server/scripts/` are not bundled and
  are resolved as a sibling of `dist/` at runtime — unaffected by this change, already
  tracked in git). New gate `scripts/check-mcp-dist.sh`, wired into `release.yml` and
  `tests/test_mcp_dist.py`, copies only `dist/index.js` (plus that sibling `scripts/`
  dir) into an isolated temp dir with no `node_modules` anywhere in its ancestry and
  fails the build if it doesn't start clean — this exact regression class can no
  longer ship silently, and the check now proves self-containment rather than merely
  checking vendored deps were present.
  (A fully self-contained bundle was the first approach tried; it was set aside after
  two failures without testing the `createRequire` shim, and `node_modules` was
  vendored production-only instead — that worked but put ~4,100 files / ~55MB into git
  permanently, churning on every dependency bump. The shim was tested afterward, found
  to work end-to-end, and is what's shipped here instead.)

## [0.6.4] — 2026-09-02
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
