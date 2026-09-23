# Academic Helper — Claude Code Conventions

This is a Claude Code plugin for Humanities researchers. The user is a single
researcher on a local machine; the plugin should never assume team workflows.

## Commands

- `npm run build` — build the plugin (esbuild hooks → bundle, copy src/ → plugins/)
- `npm run build:hooks` — rebuild only the TypeScript hooks
- `npm run typecheck` — strict TS check on src/hooks/
- `python3 tests/test_plugin_structure.py` — structural integrity tests
- `npm run clean` — wipe plugins/ and src/hooks/dist/

## Source layout

| Path | What |
|---|---|
| `src/skills/<name>/SKILL.md` | Skill definition (markdown + YAML frontmatter) |
| `src/agents/<name>.md` | Agent definition (markdown + YAML frontmatter) |
| `src/hooks/src/lifecycle/*.ts` | TypeScript hook handlers, bundled by esbuild |
| `src/hooks/hooks.json` | Hook registry — what events fire which handlers |
| `src/thresholds.json` | Single source of truth for all numeric quality gates |
| `src/cli/src/<command>.ts` | `aw` CLI command implementation |
| `manifests/academic-writer.json` | Plugin manifest (name, version, description) |
| `scripts/build-plugins.sh` | Build script — assembles `plugins/academic-writer/` from `src/` |

## Conventions

- **Profile-scoped**: every hook must silently skip in projects without `.academic-helper/profile.md`. The `run-hook.mjs:54` outer guard checks for the `.academic-helper/` directory; individual hooks then verify `profile.md` exists. New hooks should include the `profile.md` check.
- **Thresholds**: edit `src/thresholds.json`, never inline numbers in skills or agents.
- **Strict TypeScript**: hooks must compile under `tsc --noEmit`; never use `any` (use `unknown` and narrow).
- **Markdown frontmatter**: skills use documented keys including `name`, `description`, `user-invocable`, `allowed-tools`, and `metadata`. Agents use documented keys including `name`, `description`, `tools`, `model`, and `omitClaudeMd: true`. Add `metadata: {author, version}` to skills.
- **No global pollution**: write only inside `CLAUDE_PROJECT_DIR` and `${CLAUDE_PLUGIN_DATA}`; never write elsewhere under `$HOME`. The plugin must be safe to run in any project.

## Plugin invocation

Slash commands are auto-generated from skills with `user-invocable: true`. To add a command, add a skill. To remove a command, set `user-invocable: false` (skill becomes internal).

### User-facing slash commands

| Command | Skill | Purpose |
|---|---|---|
| `/academic-writer:write` | write | Start a new article from scratch |
| `/academic-writer:edit` | edit | Revise a drafted article |
| `/academic-writer:edit-section` | edit-section | Revise one section only |
| `/academic-writer:proofread` | proofread | Run the `aw proofread` find, verify, memo, and apply pipeline |
| `/academic-writer:ocr` | ocr | OCR a scanned PDF/image (or directory) into clean text via Gemini vision |
| `/academic-writer:init` | init | Full onboarding (first install); pass `--quick` for fast onboarding |
| `/academic-writer:setup` | setup | Guided first-run wizard (Gemini key, Python tools, sample paragraph) — slash-command only (`disable-model-invocation: true`, so Claude will not auto-invoke it) |
| `/academic-writer:research` | research | Investigate a topic |
| `/academic-writer:ideate` | ideate | Frame a research question |
| `/academic-writer:review` | review | Score an article before submission |
| `/academic-writer:health` | health | Check integration health |
| `/academic-writer:help` | help | List available commands |
| `/academic-writer:voice` | voice | Stage 2 deep voice profile (7-session adversarial interview) |
| `/academic-writer:revise` | revise | Read Word comments and tracked changes; update the draft and feedback stores |

## Agents

| Agent file | Role |
|---|---|
| `src/agents/deep-reader.md` | Explores Candlekeep source documents; maps evidence before thesis |
| `src/agents/architect.md` | Generates thesis options or structured article outline |
| `src/agents/auditor.md` | Citation hard gate — verifies claims against sources.json |
| `src/agents/voice-miner.md` | Stage 1 voice subsystem — reads corpus and emits markdown style fingerprint |

## Pipeline pattern

The `write` skill uses a CLI-backed, gated pipeline:
1. Conversational planning and approval (architect agent, human in the loop), then outline validation.
2. `aw draft` writes body units in dependency order and intro/conclusion last, applying code gates.
3. The auditor receives one batch per unit; it remains the citation hard gate, and failed units are redrafted with feedback.
4. `aw synthesize` applies paragraph-level transition edits, then the skill creates the DOCX and hands it back for Word comments and `/academic-writer:revise`.

Auditor is the only mandatory hard gate — it must reject paragraphs whose citations don't match `sources.json` or fail external verification.

## Anti-patterns

- Don't inline thresholds — read `thresholds.json`.
- Don't run cognetivy — it was removed (`docs/reviews/2026-05-01-plugin-review.md`).
- Don't create `.academic-helper/` outside the setup or init skills.
- Don't author skill descriptions that omit "Use when…" trigger phrases.
