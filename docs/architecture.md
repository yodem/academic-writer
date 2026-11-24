---
last-reviewed: 2026-11-24
covers:
  - src/skills
  - src/agents
  - src/cli/src
  - src/hooks/src/lifecycle
  - src/hooks/hooks.json
  - src/scripts/courses
  - src/scripts/pageindex
  - src/thresholds.json
  - src/brand/DESIGN.md
  - scripts/build-plugins.sh
  - manifests/academic-writer.json
---
# Architecture

Draft by Claude, 2026-11-24, from the tree, CLAUDE.md and CHANGELOG. Plugin version 0.24.0.

## Parts
- Skills (`src/skills/`): four user-facing routers, `write`, `setup`, `library`, `courses`, each with phase files
  under `phases/`. A phase is a command: `/academic-writer:write edit`. See adr/0002.
- Agents (`src/agents/`): `architect` (thesis options, outline) and `auditor` (citation hard gate against
  `sources.json`).
- `aw` CLI (`src/cli/src/`, TypeScript, bundled by esbuild): `draft`, `synthesize`, `evidence`, `proofread`, `revise`,
  `ocr`, `docx`, `voice`, `library/` (Trove default, optional PageIndex, retrieval ledger, blind eval).
- Hooks (`src/hooks/src/lifecycle/`, registry `src/hooks/hooks.json`): session env, subagent start/stop (activity
  events), gate enforcement, voice pull, stop notice. Every hook skips silently without `.academic-helper/profile.md`.
- Python scripts (`src/scripts/`): DOCX generation and diff, citation guard, voice scoring, `gate.py`, `home.py`,
  `setup_checks.py`, `courses/` (term registry, Lemida sync, nightly job, local dashboard), `ocr/`, `kotar/`,
  `pageindex/` (pinned local helper `pilib`).
- Dashboard (`src/scripts/courses/dashboard/`): Python stdlib server on 127.0.0.1, SSE, brand tokens from
  `src/brand/DESIGN.md`. See adr/0004.
- Mod (`src/mod/`): TSX pane showing live activity in Claude Code only; every feature has a dashboard equivalent.
- Config: `src/thresholds.json` (all numeric gates and per-step model routes), `features.json` (feature checklist,
  generates About data), `manifests/academic-writer.json` (plugin manifest).
- Build: `scripts/build-plugins.sh` assembles the committed `plugins/academic-writer/` from `src/`.
- Site and guide: `site/` (GitHub Pages, bilingual), `src/guide/index.html` (generated command lists), `video/`.

## Data flow (write pipeline)
1. Conversational planning with the architect agent, researcher approval, outline validation.
2. `aw draft` writes body units in dependency order, intro and conclusion last, under code gates (word bounds,
   quote gate, citation floor, argument graph).
3. The auditor gets one batch per unit and checks citations against `sources.json` and external sources; a failed
   unit is redrafted with feedback (max `rewriteCycles`), else marked `[NEEDS REVIEW]`.
4. `aw synthesize` applies transition edits; the skill builds the DOCX; the researcher comments in Word and
   `write revise` reads the comments and tracked changes back.
Sources come from Trove (default) or a PageIndex library per project (`.academic-helper/library.json`).

## State and storage
- Per project: `.academic-helper/` (profile.md overrides, runs, activity.jsonl, library.json).
- Home folder chosen at setup: `home.md`, `workspaces.json`, term registry. Plugin data: `${CLAUDE_PLUGIN_DATA}`
  (keys, caches, voice store, PageIndex venv).

## Constraints
- No global pollution outside the exceptions above; safe in any project.
- Python 3.9+ scripts; Node 20+; Windows supported (`aw-python` resolver); nightly job is macOS launchd only.
- Model calls only through the researcher's own Claude Code/Codex, plus Gemini where already allowed. See adr/0003.
- Public repo: no private identifiers or internal process notes (`check-no-private-refs.sh`); `docs/plans`,
  `docs/superpowers` are gitignored.
- Generated blocks (guide, help, About, brand CSS) are never hand-edited; `--check` modes gate them in CI.

## Quality bar
CI (`.github/workflows/ci.yml`) runs the same gates as `release.yml`: version agreement, privacy, brand, pytest,
CLI tests, typechecks, smoke of the built plugin, dashboard e2e (Playwright, baselines from CI rendering). Skill
routing has a 10-prompt eval and a listing-size budget (docs/skill-budget.md).

## Known debt
- inferred: `src/pi-skills/` and `src/cli/src/pi.ts` (an optional cross-family judge, `piModel` routes in
  thresholds.json) look like a side path; confirm it is still wanted.
- The mod's live pane is checked by hand (needs Claude Code); the rest has automated tests.
- docs/proofread-feature.md is a historical record, not current code.
