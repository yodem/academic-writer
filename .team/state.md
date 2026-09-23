# Team state — academic-writer refactor (dev-server lead, 2026-09-23)

## Mission
Finish T8, review+merge T14, build T15 (no release), prepare T9/T13/T16 release docs (0.14.0) without touching `main`.
Authoritative decisions: `docs/refactor/handoff/decisions.md`. Handoff: `docs/refactor/HANDOFF-2026-09-23.md`.

## Host limits
No `GOOGLE_API_KEY`, no hspell, no Codex CLI. Executors = Claude subagents (Sonnet) in sibling git worktrees
(`../aw-wt-<task>`). Tests run from a local venv with `requirements-dev.txt` (not tracked).

## Roster / file ownership (declared before launch; disjoint)
| Worker | Worktree / branch | Owns |
|---|---|---|
| T8-recall | `../aw-wt-T8` / `ale/aw-refactor-2026-09-23/T8` | `src/cli/src/proofread.ts`, `src/cli/src/prompts/proofread-*.md`, `src/cli/tests/proofread.test.ts`, `src/scripts/must-catch.py`, `src/scripts/apply-changes.py`, `tests/test_must_catch.py`, `tests/test_apply_changes*.py`, `tests/test_proofread_*.py`, `evals/proofread-recall/*` (never `expected.json`), new `proofread*` keys in `src/thresholds.json` |
| T14-review | `../aw-wt-T14` / `ale/aw-refactor-2026-09-23/T14` | `src/cli/src/main.ts`, `src/cli/src/decide.ts`, `src/scripts/gate.py`, `src/schemas/author-intent.schema.json`, `src/schemas/outline.schema.json`, `src/skills/write/*`, `src/skills/ideate/*`, `src/agents/architect.md`, `tests/test_gate_*.py`, `tests/test_architect_prompt.py`, `tests/test_plugin_structure.py`, `write*` keys in `src/thresholds.json` |
| T15 | `../aw-wt-T15` / `ale/aw-refactor-2026-09-23/T15` (after T14 merges) | T15 labels + widening (see decisions) |
| lead | `refactor/aw-step-engine` | merges, `docs/refactor/*`, `.team/state.md`, release prep (T9/T13/T16) |

Nobody hand-edits `plugins/`; it is regenerated with `npm run build` and committed.

## Active work
- [x] T8 base merged into integration (smoke gate fixes + hermetic CLI tests). Integration: smoke PASS, pytest 488 passed / 4 skipped, test:cli 27/27.
- [ ] T8-recall: `כמו כן` positional disambiguation; wrong-word second finder pass (flag, default off, unmeasured).
- [ ] T14: review vs spec-T14, merge integration in, fix gaps, acceptance.
- [ ] T15: after T14 merges.
- [ ] T9/T13/T16: release prep 0.14.0, no `main`.

## Questions for the author
- (none yet)
