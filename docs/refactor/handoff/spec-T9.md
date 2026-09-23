# Executor spec — T9 (academic-writer refactor)

Work in this git worktree of the academic-writer plugin. Read `CLAUDE.md` first, then the design
`docs/superpowers/specs/2026-09-23-academic-writer-refactor-design.md` only as needed.

## Rules
- Modify ONLY these paths:
- .claude-plugin/marketplace.json
- CHANGELOG.md
- docs/refactor/measure-0.12.0.md
- manifests/academic-writer.json
- Do NOT commit, push, or change git history; the lead integrates.
- Stay inside this worktree except for running the repo's own scripts and tests.
- TDD: failing test first, then implementation.
- No `any` in TypeScript; no inline numeric thresholds (src/thresholds.json).
- Done only when EVERY acceptance command exits 0; paste each command's final lines in your last message.
- If blocked, stop and state the blocker.

## Acceptance (all must exit 0)
- `test "$(jq -r .version manifests/academic-writer.json)" = 0.12.0`
- `python3 scripts/version-sync.py --check`
- `test -f docs/refactor/measure-0.12.0.md`

## Global Constraints

- Numbers are never inlined. Every cap, budget, model id and concurrency lives in `src/thresholds.json` (new keys `models`, `budget`).
- Gemini runs on flash only, the latest id. Model ids appear only in `src/thresholds.json > models`.
- **Where the plugin writes.** Plugin runtime writes only inside the project (`CLAUDE_PROJECT_DIR`) and `${CLAUDE_PLUGIN_DATA}`. Nothing else under `$HOME`.
- **API keys.** Keys come only from userConfig `sensitive` values or the environment. The plaintext `.academic-helper/secrets.json` path is removed.
- **Hook guard.** Every hook silently skips a project without `.academic-helper/profile.md`.
- **Strict TypeScript.** No `any`. `npm run typecheck` passes for hooks and the CLI.
- **Failures are named.** A step that exceeds its budget exits `CAP_REACHED` or `ERROR`. A missing verdict is `ERROR`, never `PASS`. Model errors never fall back silently to another model.
- **Frontmatter.** Skills use documented frontmatter keys only: `name`, `description` (with "Use when…"), `allowed-tools`, `user-invocable`, `disable-model-invocation`, `model`, `effort`, `context`, `metadata`. Agents use `name`, `description`, `tools`, `disallowedTools`, `model`, `omitClaudeMd`.
- **Size.** Every SKILL.md is ≤ 500 lines.
- **Tests.** The existing suite stays green: `python3 -m pytest -q tests` (519 passing at the 2026-09-23 baseline, after rebasing onto `3d46c9b`).
- **Release.** Every slice ends with a release: version bump through `scripts/version-sync.py`, `npm run build`, marketplace refresh, and `claude plugin update`.
- **ALE and Codex stay out of the plugin.** The shipped plugin never calls the `ale` CLI or Codex.
- **Pi is isolated.** Pi is called only through `judge()` (Task 6), always with the isolation flags. The plugin stores no OpenRouter key; Pi's own auth owns it.
- **Jev runs only through `decide()`.** Every Jev use goes through `decide()` (Task 6) with a per-point mode in `thresholds.json > jev.points`. Hebrew points start in `shadow`, and moving a point to `cascade` is a release decision (at least 100 labels and the roster bar). Jev never skips the Claude citation auditor.


## Task 9: Release 0.12.0 (slice 1) and measure a real /proofread

Depends on Task 4. Depends on Task 8.

**Files:**
- Modify: `manifests/academic-writer.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `CHANGELOG.md`
- Create: `docs/refactor/measure-0.12.0.md`

**Interfaces:**
- Produces: `docs/refactor/measure-0.12.0.md`, a table comparing against `baseline-0.11.0.md` and the spec §5 targets: Claude tokens ≤ 5M, Gemini + OpenRouter ≤ $0.50, all stages complete, eval recall per class.

- [ ] **Step 1: Release.** Bump to 0.12.0 (`python3 scripts/version-sync.py --fix`), then run `npm run build`, `python3 -m pytest -q tests` and `npm run test:cli`. Refresh the marketplace and update the plugin.
- [ ] **Step 2: Author's run.** The author runs `/academic-writer:proofread` on the same kabalah article in a fresh session (a human step).
- [ ] **Step 3: Measure.** Run: `python3 scripts/measure-run.py --session <jsonl> --json`, and read `aw ledger show <runId>`. Write `measure-0.12.0.md`. If a target is missed, the doc names the stage with the largest share and the task reopens.
- [ ] **Step 4: Verify.** Run: `python3 scripts/version-sync.py --check`
- [ ] **Step 5: Commit** with the message `release: 0.12.0 — proofread on aw`.

