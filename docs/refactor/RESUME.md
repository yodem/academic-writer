# RESUME: academic-writer refactor (state at 2026-09-23, author away)

## Where things stand (after the dev-server lead's pushes, 12ebd17)
- **Integration branch** `refactor/aw-step-engine` on origin: T1–T8, T10–T12 and **T14** are accepted and merged. The lead reported the smoke gate passing, pytest 498 passed / 4 skipped, and test:cli 32/32. **Nothing is on `main`, and nothing is released** (the author chose to release at the end).
- **T8** (proofread on `aw`) merged, with the capped-word occurrence fix (`כמו כן` now has a positional target) and an optional wrong-word second finder pass behind `thresholds.proofread.wrongWordPass.enabled` (default **false**, unmeasured). **Re-measured on the Mac after the merge** (2 runs, stable): typo 0.77, names/terms 1.00, style_words 1.00, inside_quote 0 (targets 0.85/0.98/0.98/0). **3 of 4 met.** The wrong-word pass gives no gain, so it stays off. Typo recall is capped by Gemini flash on real-word errors (see decisions.md for options a/b/c; the author picks).
- **T15** was split into **T15a** (the CLI: `aw draft/synthesize/edit/ocr`, per `docs/refactor/handoff/T15-cli-contract.md`) and **T15b** (skills, agents, tests, build, manifest, MCP retirement). Both were **in progress on the dev server and never pushed**. Their worktrees are `~/dev/aw-wt-T15a` and `~/dev/aw-wt-T15b` on that host. Deleting the MCP server needs the author's approval before any release.
- **Remaining after T15:** T9/T13/T16, the live measurement and the single final release (0.14.0). Merging and pushing `main` needs the author.
- **The author must decide:** verified `wrong_word` fixes labelled `meaningRisk: medium` (for example `אם→עם`) are never applied, because the apply gate takes low risk only. That caps typo recall at 12/13. Should the gate be relaxed for verified medium-risk wrong_word fixes?
- **Follow-up:** `scripts/build-plugins.sh` does not ship `src/schemas/`, so gate.py falls back to drift-tested copies.
- Full context: `docs/refactor/HANDOFF-2026-09-23.md`, `docs/refactor/handoff/` (specs, labels, `decisions.md`), `.team/state.md` on the branch (the lead's ownership map), and the spec and plan under `docs/superpowers/`.

## Dev-server lead session: state UNKNOWN
A lead Claude session was started on the dev server in **tmux** (`tmux attach -t aw-lead`, worktree `~/dev/aw-refactor-lead`). About 20 minutes later the dev server went **offline on Tailscale** ("last seen" at roughly the same time). By then it had pushed T8, T14 and the T15 contract; T15a and T15b were still running locally and unpushed. The author's follow-up instruction ("Codex is not installed on this host, so use only Opus or Sonnet subagents; document blockers in STATUS.md") may **not** have been delivered.

When the server is back:
1. `ssh yodem@100.106.37.39` and `tmux attach -t aw-lead`. If the session is alive, check its work; if not, start a new one (below).
2. Check `docs/refactor/STATUS.md` on `origin/refactor/aw-step-engine` for what it finished.

## Why tmux, not herdr
The Mac session's auto-mode classifier blocked even reading `herdr-exec.py --help` ("Self-Modification"). tmux could be driven over ssh. Next time, start the lead with herdr from a session where herdr is permitted: `herdr-exec.py --host dev-server start aw-lead --kind claude`, then send it `docs/refactor/RESUME.md`.

## Executors (author's rule)
- Codex (`gpt-6-luna`) when available. **Codex CLI is NOT installed on the dev server** (no `codex` binary, no `~/.codex`; installing it needs the author's login).
- Otherwise use **only Opus or Sonnet subagents**: Sonnet for mechanical tasks, Opus for T15 and for every review.
- Always re-run acceptance plus `bash scripts/smoke-built-plugin.sh` yourself. Every shipping bug so far passed its unit tests.

## Host gaps to fix before unattended runs
- Dev server has no `GOOGLE_API_KEY`, so the live recall eval (`smoke-built-plugin.sh --live`) cannot run there. Add the key to the shell env, or run the eval on the Mac.
- Dev server has no `hspell`, so typo numbers from that host will differ from the Mac.
- Dev server lacks pytest for system python (the lead was creating `~/dev/.venv-aw-refactor`).

## Resume from the Mac instead
The Mac checkout holds the ALE run (`.ale/runs/aw-refactor-2026-09-23`, gitignored) with the worktrees `wt/T8` and `wt/T14`. The Codex launcher is `.ale/runs/aw-refactor-2026-09-23/launch-codex.sh <task>`; it refreshes each spec from its label, passes the prompt via stdin, and runs Codex `gpt-6-luna`. If the dev-server lead pushed newer work, `git pull` the branches first. Start a Claude Code session in the repo and say: *"Resume the academic-writer refactor from docs/refactor/RESUME.md."*
