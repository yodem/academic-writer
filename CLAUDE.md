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
| `manifests/academic-writer.json` | Plugin manifest (name, version, description) |
| `scripts/build-plugins.sh` | Build script — assembles `plugins/academic-writer/` from `src/` |

## Conventions

- **Profile-scoped**: every hook must silently skip in projects without `.academic-helper/profile.md`. The `run-hook.mjs:54` directory guard handles this; new hooks should respect it.
- **Thresholds**: edit `src/thresholds.json`, never inline numbers in skills or agents.
- **Strict TypeScript**: hooks must compile under `tsc --noEmit`; never use `any` (use `unknown` and narrow).
- **Markdown frontmatter**: skills require `name`, `description`, `user-invocable`, `allowedTools`. Agents require `name`, `description`, `tools`, `model`. Add `metadata: {author, version}` to skills.
- **No global pollution**: never write to `$HOME` or paths outside `CLAUDE_PROJECT_DIR`. The plugin must be safe to run in any project.

## Plugin invocation

Slash commands are auto-generated from skills with `user-invocable: true`. To add a command, add a skill. To remove a command, set `user-invocable: false` (skill becomes internal).

### User-facing slash commands

| Command | Skill | Purpose |
|---|---|---|
| `/academic-writer:write` | write | Start a new article from scratch |
| `/academic-writer:edit` | edit | Revise a drafted article |
| `/academic-writer:edit-section` | edit-section | Revise one section only |
| `/academic-writer:init` | init | Full onboarding (first install) |
| `/academic-writer:setup` | setup | Quick onboarding |
| `/academic-writer:research` | research | Investigate a topic |
| `/academic-writer:ideate` | ideate | Frame a research question |
| `/academic-writer:review` | review | Score an article before submission |
| `/academic-writer:health` | health | Check integration health |
| `/academic-writer:help` | help | List available commands |
| `/academic-writer:voice` | voice | Stage 2 deep voice profile (7-session adversarial interview) |

## Agents

| Agent file | Role |
|---|---|
| `src/agents/deep-reader.md` | Explores Candlekeep source documents; maps evidence before thesis |
| `src/agents/architect.md` | Generates thesis options or structured article outline |
| `src/agents/section-writer.md` | Writes one complete section through the 8-skill quality pipeline |
| `src/agents/auditor.md` | Citation hard gate — verifies claims against sources.json |
| `src/agents/synthesizer.md` | Post-section review for coherence and cross-section flow |
| `src/agents/voice-miner.md` | Stage 1 voice subsystem — reads corpus and emits markdown style fingerprint |

## Pipeline pattern

The `write` and `edit` skills use a chained-with-gates pattern:
1. Conversational planning phase (architect agent, human in the loop).
2. Parallel section writing (one section-writer subagent per section).
3. Per-paragraph 8-skill pipeline (draft → 6 checks → citation audit hard gate).
4. Synthesis pass + self-review scorecard.

Auditor is the only mandatory hard gate — it must reject paragraphs whose citations don't match `sources.json` or fail external verification.

## Anti-patterns

- Don't inline thresholds — read `thresholds.json`.
- Don't run cognetivy — it was removed (`docs/reviews/2026-05-01-plugin-review.md`).
- Don't create `.academic-helper/` outside the setup or init skills.
- Don't author skill descriptions that omit "Use when…" trigger phrases.
